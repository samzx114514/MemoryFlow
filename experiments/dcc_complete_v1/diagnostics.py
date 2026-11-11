"""Summarize observed scheduling, numerical isolation, timing and process memory."""
import json
from pathlib import Path

import numpy as np

from pipeline import reduce, write


def merged(intervals):
    result = []
    for start, end in sorted(intervals):
        if result and start <= result[-1][1]:
            result[-1][1] = max(end, result[-1][1])
        else:
            result.append([start, end])
    return result


def overlap(first, second):
    return sum(max(0, min(b, d)-max(a, c)) for a, b in merged(first) for c, d in merged(second))


def summarize(run):
    jobs = json.loads((run / "inputs.json").read_text())
    intervals, batches, rows = {"yf": [], "mf": []}, {}, []
    gpu_events_complete = True
    for job in jobs:
        record = {"id": job["id"], "benchmark": job["benchmark"], "prompt_tokens": len(job["prompt_ids"])}
        generated = json.loads((run / job["id"] / "yf" / "response.json").read_text())["choices"][0]["token_ids"]
        record["output_tokens"] = len(generated)
        for method in ("yf", "mf"):
            folder = run / job["id"] / method
            timing = json.loads((folder / "timing.json").read_text())
            intervals[method].append((timing["start"], timing["end"]))
            record[method+"_wall_seconds"] = timing["end"]-timing["start"]
            header = json.loads((folder / "capture" / "qk.json").read_text())
            if header["rows"] < len(job["prompt_ids"])+len(generated)-1:
                raise ValueError("Incomplete output prediction-row coverage")
            record[method+"_max_batch_size"] = max(step["batch_size"] for step in header["schedule"])
            record[method+"_prefill_batch_size"] = max(step["batch_size"] for step in header["schedule"] if step["sequence_start"] == 0)
            gpu_events_complete = gpu_events_complete and "gpu_batches" in header
            for batch in header.get("gpu_batches", []):
                batches[batch["batch_id"]] = batch
        rows.append(record)
    memory_path = run.parent / (run.name+".memory.jsonl")
    memory = [json.loads(line) for line in memory_path.read_text().splitlines()] if memory_path.exists() else []
    gpu = {"generation_only_ms": 0., "replay_only_ms": 0., "mixed_ms": 0.}
    for batch in batches.values():
        phase = set(batch["phases"])
        key = "generation_only_ms" if phase == {"generation"} else "replay_only_ms" if phase == {"replay"} else "mixed_ms"
        gpu[key] += batch["cuda_ms"]
    return {"calls": rows, "generation_replay_overlap_seconds": overlap(intervals["yf"], intervals["mf"]),
            "generation_wall_seconds": sum(b-a for a, b in merged(intervals["yf"])),
            "replay_wall_seconds": sum(b-a for a, b in merged(intervals["mf"])),
            "gpu_batch_times": gpu if gpu_events_complete else None,
            "process_peak_mib": max((sum(row["processes_mib"].values()) for row in memory), default=None),
            "memory_measurement": "NVML process samples every 0.5s; includes preallocated vLLM KV pool",
            "execution_note": "Single-call collection pipeline; these are not complete DCC task efficiency results"}


def isolation(run, test):
    result = []
    for i, job in enumerate(json.loads((run / "inputs.json").read_text())):
        generated = json.loads((run / job["id"] / "yf" / "response.json").read_text())["choices"][0]["token_ids"]
        args = len(job["prompt_ids"]), len(generated), job["sources"]
        serial, _ = reduce(test / f"serial{i}" / "capture", *args)
        packed, header = reduce(test / f"packed{i}" / "capture", *args)
        entry = {"id": job["id"], "serial_vs_packed_max": float(np.abs(serial-packed).max()),
                 "serial_vs_packed_mean": float(np.abs(serial-packed).mean()),
                 "prefill_batch_size": max(s["batch_size"] for s in header["schedule"] if s["sequence_start"] == 0)}
        if i == 0:
            altered, _ = reduce(test / "altered0" / "capture", *args)
            entry["packed_vs_altered_neighbour_max"] = float(np.abs(packed-altered).max())
            entry["packed_vs_altered_neighbour_mean"] = float(np.abs(packed-altered).mean())
        result.append(entry)
    return {"comparisons": result,
            "note": "Neighbour isolation compares two equally packed runs; serial-vs-packed is a separate numerical diagnostic"}


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--packing-test", type=Path)
    args = parser.parse_args()
    write(args.output, isolation(args.run, args.packing_test) if args.packing_test else summarize(args.run))
