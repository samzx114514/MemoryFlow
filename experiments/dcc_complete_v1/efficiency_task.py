"""Measure a complete DCC task with targets taken from its actual delivery."""
import json
import os
import subprocess
import time
from pathlib import Path
from urllib.request import Request, urlopen

from pipeline import offsets, write
from provenance_v2.span_views import View, views


def claim_span(text, claim):
    def find(view, depth):
        left=view.text.rfind(claim)
        if left>=0:
            return view.span(left,left+len(claim))
        if depth:
            for child in reversed(views(view.text,structured=True)):
                if child.text==view.text:
                    continue
                located=find(child,depth-1)
                if located is not None:
                    return view.span(*located)
        return None
    return find(View(text,0),3)


def final_targets(records, delivery, tokenizer):
    try:
        values = json.loads(delivery)
    except (TypeError, ValueError):
        values = delivery
    if isinstance(values,dict) and isinstance(values.get("artifact_content"),list):
        values=values["artifact_content"]
    if isinstance(values,list) and values and all(isinstance(x,dict) for x in values):
        values=[x.get("explanation") or x.get("text") for x in values]
    claims=list(dict.fromkeys(values))[:3] if isinstance(values,list) else [values]
    if not claims or any(not isinstance(value, str) or not value for value in claims):
        raise ValueError("The pilot expects a nonempty scalar label or list of final labels")
    targets = []
    for claim in claims:
        for record in reversed(records):
            if record.get("status") != 200:
                continue
            ids = record["response"]["choices"][0]["token_ids"]
            text, _ = offsets(tokenizer, ids)
            span=claim_span(text,claim)
            if span is not None:
                targets.append({"call": record["id"], "span": list(span), "claim": claim,
                                "raw_text":text[span[0]:span[1]]})
                break
        else:
            raise ValueError(f"Final label has no exact generated-token span: {claim}")
    return targets


def run(args):
    from transformers import AutoTokenizer
    model = "/data/Qwen3.8-27B-FP8"
    tokenizer = AutoTokenizer.from_pretrained(model, local_files_only=True)
    output = args.output
    output.mkdir()
    python = "/data2/xyf/conda_envs/xuyf/vllm_hook_env/bin/python3"
    command = [python, str(Path(__file__).with_name("live_gateway.py")), str(output / "gateway"),
               "--executor", args.executor, "--analysis-model", args.analysis_model,
               "--mode", args.mode, "--port", str(args.port), "--benchmark", args.benchmark,
               "--execution-max-tokens", str(args.execution_max_tokens)]
    url = f"http://127.0.0.1:{args.port}"
    with (output / "gateway.log").open("w") as log:
        gateway = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT)
        try:
            for _ in range(240):
                if gateway.poll() is not None:
                    raise RuntimeError("Efficiency gateway failed")
                try:
                    urlopen(url+"/health", timeout=1).close()
                    break
                except OSError:
                    time.sleep(.25)
            else:
                raise TimeoutError("Gateway did not start")
            native = ["/data1/songzhengxing_intern_dccv2/sp2_env/bin/python", "-B", "scripts/infer_sp_benchmarks.py",
                      "--tasks", str(args.task), "--run-dir", str(output / "native"), "--config", str(args.config),
                      "--base-url", url+"/v1", "--model", "mf-model", "--recover-qwen-tool-calls",
                      "--max-actions", "6", "--max-tokens", str(args.execution_max_tokens), "--timeout", "900",
                      "--central-timeout", "180", "--central-retry-timeout", "180", "--max-concurrent-subagents", "1",
                      "--temperature", "0", "--top-p", "1", "--seed", "0"]
            if args.benchmark=="clause":
                native += ["--benchmark","clause","--dataset-source","clause-files-l1-test-v1"]
            else:
                native += ["--benchmark","dcc_files","--dataset-source","finauditing-files-test-v1",
                           "--dataset-plugin","dcc_harness.preprocessing.native:make_file_plugin"]
            env = {**os.environ, "PYTHONPATH": f"{args.tree}:{args.tree}/backend/packages/harness:{args.tree}/backend",
                   "DCC_MODEL_API_KEY": "EMPTY", "DCC_BUNDLE": str(args.bundle)}
            import hashlib
            write(output / "command.json", {"argv": native, "mode": args.mode, "warmup": args.warmup,
                 "execution_max_tokens": args.execution_max_tokens,
                 "task_sha256": hashlib.sha256(args.task.read_bytes()).hexdigest(),
                 "config_sha256": hashlib.sha256(args.config.read_bytes()).hexdigest(),
                 "dcc_commit": subprocess.check_output(["git", "-C", str(args.tree), "rev-parse", "HEAD"], text=True).strip()})
            started = time.time()
            with (output / "native.log").open("w") as native_log:
                completed = subprocess.run(native, cwd=args.tree, env=env, stdout=native_log,
                                           stderr=subprocess.STDOUT, timeout=1080)
            returned = time.time()
            selection_started=time.time()
            predictions = [json.loads(line) for p in (output / "native").rglob("predictions.jsonl")
                           for line in p.read_text().splitlines() if line.strip()]
            records = [json.loads(p.read_text()) for p in sorted((output / "gateway/wire").glob("*.json"))]
            delivered = [p for p in predictions if p.get("status") == "completed"]
            targets = final_targets(records, delivered[0]["delivery"], tokenizer) if delivered else []
            end_by_call = {record["id"]: record["end"] for record in records}
            target_generation_end = max((end_by_call[target["call"]] for target in targets), default=returned)
            write(output / "finish_request.json", {"targets": targets, "task_started": started,
                  "answer_end": returned, "native_return_time": returned,"target_generation_end":target_generation_end,
                  "target_selection_seconds":time.time()-selection_started,
                  "native_completion": [p.get("status") for p in predictions]})
            if not targets and args.mode != "execution":
                write(output / "failed_task.json", {"native_exit_code": completed.returncode, "predictions": predictions})
            request = Request(url+"/finish", (output / "finish_request.json").read_bytes(), headers={"Content-Type": "application/json"})
            with urlopen(request, timeout=1800) as response:
                summary = json.load(response)
            write(output / "result.json", {**summary, "warmup": args.warmup,
                 "native_exit_code": completed.returncode, "native_return_time": returned,
                 "completed": bool(delivered), "final_targets": targets,
                 "task_id": json.loads(args.task.read_text().splitlines()[0])["id"]})
        finally:
            gateway.terminate()
            try:
                gateway.wait(timeout=20)
            except subprocess.TimeoutExpired:
                gateway.kill()
                gateway.wait()


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    for key in ("task", "config", "tree", "bundle"):
        parser.add_argument("--"+key, type=Path, required=True)
    parser.add_argument("--analysis-model", required=True)
    parser.add_argument("--mode", choices=("execution", "serial", "full"), required=True)
    parser.add_argument("--executor", default="http://127.0.0.1:8770")
    parser.add_argument("--port", type=int, default=8792)
    parser.add_argument("--warmup", action="store_true")
    parser.add_argument("--execution-max-tokens", type=int, default=8192)
    parser.add_argument("--benchmark",choices=("finauditing","clause"),default="finauditing")
    run(parser.parse_args())
