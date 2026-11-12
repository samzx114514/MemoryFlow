"""Warm replay and queries with saved real calls, without another agent generation."""
import asyncio
import hashlib
import json
import time
from pathlib import Path

from live_gateway import Gateway
from pipeline import write


async def run(args):
    saved = json.loads((args.source / "result.json").read_text())
    if not saved["completed"] or not saved["final_targets"]:
        raise ValueError("Warmup needs a completed recorded task and actual targets")
    records = [json.loads(path.read_text()) for path in sorted((args.source / "gateway/wire").glob("*.json"))]
    if len(records) != saved["calls"] or any(record.get("status") != 200 for record in records):
        raise ValueError("Saved warmup calls are incomplete")
    args.output.mkdir()
    gateway = Gateway(args.output / "gateway", args.executor, "/data/Qwen3.8-27B-FP8",
                      args.analysis_model, args.mode, "clause", 8192)
    started = time.time()
    gateway.records = records
    if args.mode == "full":
        for record in records:
            gateway.queue.put_nowait(record)

    class Finish:
        async def json(self):
            return {"targets": saved["final_targets"], "task_started": started,
                    "answer_end": started, "native_completion": saved["native_completion"]}

    response = await gateway.finish(Finish())
    result = json.loads(response.body)
    write(args.output / "result.json", {**result, "warmup": True, "warmup_replay_only": True,
          "completed": True, "task_id": saved["task_id"], "final_targets": saved["final_targets"],
          "source": str(args.source),
          "source_result_sha256": hashlib.sha256((args.source / "result.json").read_bytes()).hexdigest(),
          "note": "Saved real task calls; no new execution-model generation. Excluded from all measured-repeat tables."})


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--executor", required=True)
    parser.add_argument("--analysis-model", required=True)
    parser.add_argument("--mode", choices=("full", "serial"), required=True)
    asyncio.run(run(parser.parse_args()))
