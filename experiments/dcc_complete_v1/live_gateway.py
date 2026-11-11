"""DCC gateway: record execution and run full/serial provenance on another GPU."""
import asyncio
import csv
import copy
import hashlib
import importlib.util
import json
import os
import subprocess
import time
from pathlib import Path

from aiohttp import ClientError, ClientSession, ClientTimeout, web
from transformers import AutoTokenizer

from forest_bridge import export_episode, query
from pipeline import HEADS, author_functions, offsets, reduce, render, send, send_batch, validate_model, write
from rich_sources import full_sources
from transport import normalize as normalize_structure


class Gateway:
    def __init__(self, output, executor, execution_model, analysis_model, mode, benchmark=None):
        output.mkdir()
        self.output, self.executor, self.mode = output, executor, mode
        self.benchmark = benchmark
        self.execution_model, self.analysis_model = execution_model, analysis_model
        execution_info = validate_model(execution_model, executor+"/v1/completions")
        self.execution_served_name = execution_info["data"][0]["id"]
        if mode != "execution":
            validate_model(analysis_model)
        self.execution_tokenizer = AutoTokenizer.from_pretrained(execution_model, local_files_only=True)
        self.tokenizer = AutoTokenizer.from_pretrained(analysis_model, local_files_only=True)
        self.functions = author_functions(self.tokenizer)
        self.records, self.jobs, self.batches = [], {}, []
        self.response_events = []
        self.queue = asyncio.Queue()
        transport_path = Path("/data1/songzhengxing_intern_dccv2/mf_yf_batch12_20261109/code/capture.py")
        spec = importlib.util.spec_from_file_location("existing_dcc_transport", transport_path)
        self.transport = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.transport)
        self.transport_sha256 = hashlib.sha256(transport_path.read_bytes()).hexdigest()
        self.started = time.time()
        self.worker = asyncio.create_task(self.analyze()) if mode == "full" else None
        self.closed = False
        gpu_ids = {int(index) for index in os.environ.get("MF_RESOURCE_GPUS", "4,6").split(",")}
        inventory = subprocess.check_output(["nvidia-smi", "--query-gpu=index,uuid,name", "--format=csv,noheader"], text=True)
        self.gpus = {uuid.strip(): {"index": int(index), "name": name.strip()}
                     for index, uuid, name in csv.reader(inventory.splitlines()) if int(index) in gpu_ids}
        self.memory = []
        self.memory_worker = asyncio.create_task(self.sample_memory())
        write(output / "identity.json", {"execution_model": execution_model, "analysis_model": analysis_model,
                                          "mode": mode, "started": self.started, "transport_sha256": self.transport_sha256,
                                          "code_sha256": {name: hashlib.sha256(Path(__file__).with_name(name).read_bytes()).hexdigest()
                                                          for name in ("live_gateway.py", "pipeline.py", "rich_sources.py", "forest_bridge.py", "transport.py")}})

    async def sample_memory(self):
        with (self.output / "memory.jsonl").open("w", buffering=1) as stream:
            while True:
                process = await asyncio.create_subprocess_exec(
                    "nvidia-smi", "--query-compute-apps=gpu_uuid,pid,used_gpu_memory", "--format=csv,noheader,nounits",
                    stdout=asyncio.subprocess.PIPE)
                data, _ = await process.communicate()
                by_gpu = {str(gpu["index"]): {} for gpu in self.gpus.values()}
                for uuid, pid, mib in csv.reader(data.decode().splitlines()):
                    if uuid.strip() in self.gpus and mib.strip().isdigit():
                        by_gpu[str(self.gpus[uuid.strip()]["index"])][pid.strip()] = int(mib)
                row = {"time": time.time(), "processes_mib": by_gpu}
                self.memory.append(row)
                stream.write(json.dumps(row)+"\n")
                await asyncio.sleep(.25)

    async def forward(self, request):
        if self.closed:
            raise web.HTTPConflict(text="Task is already finalized")
        payload = await request.json()
        index = len(self.records)
        record = {"id": f"call{index:02d}", "framework_request": payload, "start": time.time()}
        self.records.append(record)
        finished = asyncio.Event()
        self.response_events.append(finished)
        forwarded = self.transport.forward_payload({**payload, "model": self.execution_served_name, "stream": False}, "efficiency_no_capture")
        forwarded.pop("vllm_xargs", None)
        record["request"] = forwarded
        try:
            async with ClientSession(timeout=ClientTimeout(total=900)) as client:
                async with client.post(self.executor + "/v1/chat/completions", json=forwarded) as response:
                    body, status = await response.read(), response.status
            record.update(end=time.time(), status=status)
            if status == 200:
                record["response"] = json.loads(body)
                client_response = copy.deepcopy(record["response"])
                record["range_normalizations"] = self.transport.normalize_read_ranges(client_response, forwarded)
                record["structure_normalizations"] = normalize_structure(client_response, forwarded, self.benchmark)
                body = json.dumps(client_response).encode()
                if self.mode == "full":
                    self.queue.put_nowait(record)
            else:
                record["error_body"] = body.decode(errors="replace")
            return web.Response(body=body, status=status, content_type="application/json")
        except (ClientError, asyncio.TimeoutError) as error:
            record.update(end=time.time(), status=502, error_type=type(error).__name__, error_body=str(error))
            return web.json_response({"error": record["error_type"]}, status=502)
        finally:
            write(self.output / "wire" / f"{record['id']}.json", record)
            finished.set()

    def prepare(self, record):
        response = record["response"]
        generated = response["choices"][0].get("token_ids")
        if not generated:
            raise ValueError(f"{record['id']} lacks raw generated token IDs")
        raw = self.execution_tokenizer.decode(generated, clean_up_tokenization_spaces=False)
        prompt_ids, sources = render(self.tokenizer, record["request"], self.functions)
        if self.execution_model == self.analysis_model and response.get("prompt_token_ids"):
            if prompt_ids != response["prompt_token_ids"]:
                raise ValueError("Execution and replay prompt tokens differ")
        output_ids = (generated if self.execution_model == self.analysis_model
                      else self.tokenizer.encode(raw, add_special_tokens=False))
        decoded, _ = offsets(self.tokenizer, output_ids)
        if decoded != raw:
            raise ValueError("Replay output text does not preserve the actual generated output")
        sources = full_sources(self.tokenizer, record["request"], prompt_ids, sources, output_ids)
        tool_calls = []
        for tool in response["choices"][0]["message"].get("tool_calls") or []:
            fn = tool["function"]
            tool_calls.append({"id": tool["id"], "name": fn["name"], "args": json.loads(fn["arguments"])})
        job = {"id": record["id"], "tool_calls": tool_calls, "benchmark": "dcc_efficiency", "request": record["request"],
               "prompt_ids": prompt_ids, "sources": sources, "output_receipt": "observed/response.json"}
        write(self.output / job["id"] / "observed" / "response.json", {"choices": [{"token_ids": output_ids}]})
        self.jobs[job["id"]] = job
        return job, output_ids

    async def batch(self, records, tag="mf"):
        started = time.time()
        prepared = [await asyncio.to_thread(self.prepare, record) for record in records]
        payloads = [{"prompt": job["prompt_ids"]+generated[:-1], "max_tokens": 1, "temperature": 0, "seed": 0}
                    for job, generated in prepared]
        destinations = [self.output / job["id"] / tag / "mf" for job, _ in prepared]
        if len(records) == 1:
            await asyncio.to_thread(send, payloads[0], destinations[0])
        else:
            await asyncio.to_thread(send_batch, payloads, destinations)
        for (job, generated), destination in zip(prepared, destinations, strict=True):
            matrix, header = await asyncio.to_thread(reduce, destination / "capture", len(job["prompt_ids"]),
                                                     len(generated), job["sources"])
            config = header["config"]
            if (config["target_layer"], config["target_query_head"]) != HEADS[Path(self.analysis_model).name]:
                raise ValueError("Analysis capture does not use the frozen head")
            import numpy as np
            np.save(self.output / job["id"] / f"{tag}.npy", matrix, allow_pickle=False)
            # Expose the standard per-method capture path for the forest adapter.
            (self.output / job["id"] / tag / "capture").symlink_to(destination / "capture", target_is_directory=True)
        self.batches.append({"calls": [record["id"] for record in records], "start": started,
                             "end": time.time(), "tag": tag})
        write(self.output / "analysis_batches.json", self.batches)

    async def analyze(self):
        while True:
            first = await self.queue.get()
            if first is None:
                return
            second = await self.queue.get()
            await self.batch([first] if second is None else [first, second])
            if second is None:
                return

    async def finish(self, request):
        if self.closed:
            raise web.HTTPConflict(text="Already finalized")
        payload = await request.json()
        targets = payload.get("targets") or []
        if self.mode != "execution" and not targets:
            raise web.HTTPBadRequest(text="Provide actual output spans for the efficiency targets")
        self.closed = True
        answer_end = payload["answer_end"]
        await asyncio.gather(*(event.wait() for event in self.response_events))
        successful = [record for record in self.records if record.get("status") == 200]
        if self.mode == "full":
            await self.queue.put(None)
            await self.worker
        elif self.mode == "serial":
            # Disable shared-target replay, cross-call packing and live analysis.
            for index in range(len(targets)):
                for record in successful:
                    await self.batch([record], tag=f"serial{index}")
        if self.mode != "execution":
            jobs = [self.jobs[record["id"]] for record in successful]
            write(self.output / "inputs.json", jobs)
            query_started = time.time()
            for index, target in enumerate(targets):
                episode = self.output / ("forest" if self.mode == "full" else f"forest{index}")
                method = "mf" if self.mode == "full" else f"serial{index}"
                if not episode.exists():
                    await asyncio.to_thread(export_episode, self.output, episode, [job["id"] for job in jobs],
                                            self.tokenizer, method)
                mapped = f"call{[job['id'] for job in jobs].index(target['call']):02d}"
                await asyncio.to_thread(query, episode, mapped, target["span"], self.tokenizer,
                                        self.output / f"target{index}.json")
            query_seconds = time.time()-query_started
        else:
            query_seconds = 0
        ready = time.time()
        summary = {"mode": self.mode, "calls": len(self.records), "successful_calls": len(successful),
                   "targets": len(targets),
                   "execution_prompt_tokens": sum(record["response"].get("usage", {}).get("prompt_tokens", 0) for record in successful),
                   "execution_output_tokens": sum(record["response"].get("usage", {}).get("completion_tokens", 0) for record in successful), "task_started": payload["task_started"], "answer_end": answer_end,
                   "provenance_ready": ready, "task_total_seconds": ready-payload["task_started"],
                   "tail_seconds": max(0, ready-answer_end),
                   "analysis_seconds": sum(batch["end"]-batch["start"] for batch in self.batches)+query_seconds,
                   "forest_query_seconds": query_seconds, "native_completion": payload["native_completion"]}
        summary["analysis_seconds_per_target"] = summary["analysis_seconds"]/len(targets) if targets else None
        gpu_batches = {}
        for header_path in self.output.glob("call*/*/mf/capture/qk.json"):
            for batch in json.loads(header_path.read_text())["gpu_batches"]:
                gpu_batches[batch["batch_id"]] = batch["cuda_ms"]
        summary["analysis_gpu_seconds"] = sum(gpu_batches.values())/1000
        summary["gpu_inventory"] = self.gpus
        summary["process_peak_total_mib"] = max((sum(sum(gpu.values()) for gpu in row["processes_mib"].values())
                                                   for row in self.memory), default=None)
        summary["process_peak_per_gpu_mib"] = {
            str(gpu["index"]): max((sum(row["processes_mib"][str(gpu["index"])].values()) for row in self.memory), default=None)
            for gpu in self.gpus.values()}
        self.memory_worker.cancel()
        write(self.output / "summary.json", summary)
        return web.json_response(summary)


async def application(args):
    gateway = Gateway(args.output, args.executor, args.execution_model, args.analysis_model, args.mode, args.benchmark)
    app = web.Application(client_max_size=32*1024**2)
    app.router.add_post("/v1/chat/completions", gateway.forward)
    app.router.add_post("/finish", gateway.finish)
    app.router.add_get("/health", lambda _: web.json_response({"ready": True}))
    return app


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument("--executor", default="http://127.0.0.1:8781")
    parser.add_argument("--execution-model", default="/data/Qwen3.8-27B-FP8")
    parser.add_argument("--analysis-model", required=True)
    parser.add_argument("--mode", choices=("execution", "serial", "full"), required=True)
    parser.add_argument("--port", type=int, default=8784)
    parser.add_argument("--benchmark", choices=("nba", "clause", "finauditing"))
    args = parser.parse_args()
    web.run_app(application(args), host="127.0.0.1", port=args.port)
