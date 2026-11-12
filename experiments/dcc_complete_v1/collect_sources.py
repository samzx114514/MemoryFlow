"""Collect actual DCC call inputs with one native process per source task."""
import argparse
import concurrent.futures
import hashlib
import json
import os
import subprocess
import time
from pathlib import Path
from urllib.request import Request, urlopen

from pipeline import write


def run_task(task, output, tree, config, benchmark, executor, port, timeout, bundle, max_tokens):
    output.mkdir()
    python = "/data2/xyf/conda_envs/xuyf/vllm_hook_env/bin/python3"
    model = "/data/Qwen3.8-27B-FP8"
    source = Path(task["task_file"])
    if hashlib.sha256(source.read_bytes()).hexdigest() != task["sha256"]:
        raise ValueError("Source task changed after selection")
    gateway_command = [python, str(Path(__file__).with_name("live_gateway.py")), str(output / "capture"),
                       "--executor", executor, "--analysis-model", model, "--mode", "execution", "--port", str(port), "--benchmark", benchmark]
    with (output / "gateway.log").open("w") as gateway_log:
        gateway = subprocess.Popen(gateway_command, stdout=gateway_log, stderr=subprocess.STDOUT)
        try:
            for _ in range(200):
                if gateway.poll() is not None:
                    raise RuntimeError("Source gateway failed")
                try:
                    urlopen(f"http://127.0.0.1:{port}/health", timeout=1).close()
                    break
                except OSError:
                    time.sleep(.25)
            else:
                raise TimeoutError("Source gateway did not start")
            command = ["/data1/songzhengxing_intern_dccv2/sp2_env/bin/python", "-B", "scripts/infer_sp_benchmarks.py",
                       "--tasks", str(source), "--run-dir", str(output / "native"), "--config", str(config),
                       "--base-url", f"http://127.0.0.1:{port}/v1", "--model", "mf-model",
                       "--recover-qwen-tool-calls", "--max-actions", "6", "--max-tokens", str(max_tokens),
                       "--timeout", str(timeout), "--central-timeout", "180", "--central-retry-timeout", "180",
                       "--max-concurrent-subagents", "1", "--temperature", "0", "--top-p", "1", "--seed", "0"]
            if benchmark == "nba":
                command += ["--dataset-source", "dcc_inline", "--dataset-plugin", "dcc_harness.preprocessing.native:make_inline_plugin"]
            elif benchmark == "clause":
                command += ["--benchmark", "clause", "--dataset-source", "clause-intext-yes-whole-document-v1"]
            else:
                command += ["--benchmark", "dcc_files", "--dataset-source", "finauditing-files-test-v1",
                            "--dataset-plugin", "dcc_harness.preprocessing.native:make_file_plugin"]
            env = {**os.environ, "PYTHONPATH": f"{tree}:{tree}/backend/packages/harness:{tree}/backend", "DCC_MODEL_API_KEY": "EMPTY"}
            if bundle:
                env["DCC_BUNDLE"] = str(bundle)
            write(output / "command.json", {"argv": command, "task": task,
                                             "config_sha256": hashlib.sha256(config.read_bytes()).hexdigest(),
                                             "purpose": "source-call collection, no attribution quality score"})
            started = time.time()
            with (output / "native.log").open("w") as log:
                completed = subprocess.run(command, cwd=tree, env=env, stdout=log, stderr=subprocess.STDOUT, timeout=timeout+180)
            ended = time.time()
            statuses = [json.loads(line).get("status") for path in (output / "native").rglob("predictions.jsonl")
                        for line in path.read_text().splitlines() if line.strip()]
            payload = {"task_started": started, "answer_end": ended, "targets": [], "native_completion": statuses}
            request = Request(f"http://127.0.0.1:{port}/finish", json.dumps(payload).encode(),
                              headers={"Content-Type": "application/json"})
            with urlopen(request, timeout=1000) as response:
                summary = json.load(response)
            write(output / "result.json", {"native_exit_code": completed.returncode, "task_id": task["id"], **summary})
        finally:
            gateway.terminate()
            try:
                gateway.wait(timeout=20)
            except subprocess.TimeoutExpired:
                gateway.kill()
                gateway.wait()


def main(args):
    args.output.mkdir()
    tasks = json.loads(args.tasks.read_text())
    def collect(index, task):
        output = args.output / f"{index:02d}-{task['id']}"
        try:
            run_task(task, output, args.tree, args.config, args.benchmark, args.executor, args.port+index, args.timeout, args.bundle, args.max_tokens)
            print(task["id"], "recorded", flush=True)
        except Exception as error:
            output.mkdir(exist_ok=True)
            write(output / "collector_error.json", {"type": type(error).__name__, "detail": str(error)})
            print(task["id"], "collector_error", type(error).__name__, flush=True)
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.parallel) as pool:
        futures = [pool.submit(collect, index, task) for index, task in enumerate(tasks)]
        for future in futures:
            future.result()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("tasks", "output", "tree", "config"):
        parser.add_argument(name, type=Path)
    parser.add_argument("--benchmark", choices=("nba", "clause", "finauditing"), required=True)
    parser.add_argument("--executor", required=True)
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--timeout", type=int, default=900)
    parser.add_argument("--bundle", type=Path)
    parser.add_argument("--max-tokens", type=int, default=2048)
    parser.add_argument("--parallel", type=int, default=1)
    main(parser.parse_args())
