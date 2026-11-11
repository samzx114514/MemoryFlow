"""Bounded real DCC wiring probe; not an official efficiency measurement."""
import json
import hashlib
import os
import subprocess
import time
from pathlib import Path
from urllib.request import Request, urlopen

from transformers import AutoTokenizer
from pipeline import author_functions, spans, write


def run(output, config, task, tree, bundle, max_actions=2):
    model = "/data/Qwen3.8-27B-FP8"
    python = "/data2/xyf/conda_envs/xuyf/vllm_hook_env/bin/python3"
    gateway_output = output / "gateway"
    output.mkdir()
    command = [python, str(Path(__file__).with_name("live_gateway.py")), str(gateway_output),
               "--analysis-model", model, "--mode", "full"]
    with (output / "gateway.log").open("w") as gateway_log:
        gateway = subprocess.Popen(command, stdout=gateway_log, stderr=subprocess.STDOUT)
        try:
            for _ in range(200):
                if gateway.poll() is not None:
                    raise RuntimeError("Gateway failed before health check")
                try:
                    urlopen("http://127.0.0.1:8784/health", timeout=1).close()
                    break
                except OSError:
                    time.sleep(.2)
            else:
                raise TimeoutError("Gateway did not start")
            started = time.time()
            native = ["/data1/songzhengxing_intern_dccv2/sp2_env/bin/python", "-B", "scripts/infer_sp_benchmarks.py",
                      "--tasks", str(task), "--run-dir", str(output / "native"),
                      "--dataset-source", "dcc_inline", "--dataset-plugin", "dcc_harness.preprocessing.native:make_inline_plugin",
                      "--config", str(config), "--base-url", "http://127.0.0.1:8784/v1", "--model", "mf-model",
                      "--recover-qwen-tool-calls", "--max-actions", str(max_actions), "--max-tokens", "1024", "--timeout", "300",
                      "--central-timeout", "90", "--central-retry-timeout", "90", "--max-concurrent-subagents", "1",
                      "--temperature", "0", "--top-p", "1", "--seed", "0"]
            write(output / "command.json", {"argv": native, "purpose": "bounded wiring probe; no official efficiency claim",
                                             "task_sha256": hashlib.sha256(task.read_bytes()).hexdigest(),
                                             "config_sha256": hashlib.sha256(config.read_bytes()).hexdigest(),
                                             "dcc_commit": subprocess.check_output(["git", "-C", str(tree), "rev-parse", "HEAD"], text=True).strip()})
            env = {**os.environ, "PYTHONPATH": f"{tree}:{tree}/backend/packages/harness:{tree}/backend",
                   "DCC_MODEL_API_KEY": "EMPTY", "DCC_BUNDLE": str(bundle)}
            with (output / "native.log").open("w") as log:
                result = subprocess.run(native, cwd=tree, env=env, stdout=log, stderr=subprocess.STDOUT, timeout=1800)
            answer_end = time.time()
            tok = AutoTokenizer.from_pretrained(model, local_files_only=True)
            functions = author_functions(tok)
            targets = []
            for wire in sorted((gateway_output / "wire").glob("*.json"), reverse=True):
                record = json.loads(wire.read_text())
                if record["status"] != 200:
                    continue
                text = tok.decode(record["response"]["choices"][0]["token_ids"], clean_up_tokenization_spaces=False)
                candidates = spans(text, functions)
                if len(candidates) >= 2:
                    targets = [{"call": record["id"], "span": list(span)} for span in candidates[:2]]
                    break
            if not targets:
                raise ValueError("No two distinct output spans for the multi-query wiring probe")
            status = []
            for path in (output / "native").rglob("predictions.jsonl"):
                status.extend(json.loads(line).get("status") for line in path.read_text().splitlines() if line.strip())
            payload = {"targets": targets, "task_started": started, "answer_end": answer_end,
                       "native_completion": status, "native_exit_code": result.returncode}
            write(output / "finish_request.json", payload)
            request = Request("http://127.0.0.1:8784/finish", json.dumps(payload).encode(),
                              headers={"Content-Type": "application/json"})
            with urlopen(request, timeout=1800) as response:
                summary = json.load(response)
            write(output / "result.json", {**summary, "purpose": "wiring probe, automatic spans, not quality labels or official timing"})
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
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--task", type=Path, required=True)
    parser.add_argument("--tree", type=Path, required=True)
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--max-actions", type=int, default=2)
    args = parser.parse_args()
    run(args.output, args.config, args.task, args.tree, args.bundle, args.max_actions)
