"""Verify saved E1 route measurements and write a compact, text-free summary."""
import argparse
import hashlib
import json
from pathlib import Path
import statistics


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def summarize(root):
    models = {}
    for tag in ["27b", "7b", "1_5b"]:
        folder = root/tag/"measurement"
        if not (folder/"results.json").exists():
            continue
        result = read(folder/"results.json")
        trials = []
        for trial in result["trials"]:
            repeat = trial["repeat"]
            routes = {}
            for method in ["yf", "mf"]:
                path = folder/f"{repeat}_{method}"
                route = read(path/"summary.json")
                assert route == trial["routes"][method]
                calls = [read(p) for p in path.glob("*/stage_timing.json")]
                assert len(calls) == route["completed_calls"] == route["calls"] == 30
                wall = max(c["citation_ready"] for c in calls)-min(c["generation"][0] for c in calls)
                assert abs(wall-route["wall_seconds"]) < 1e-6
                memory = path/"memory.jsonl"
                assert hashlib.sha256(memory.read_bytes()).hexdigest() == route["memory"]["trace_sha256"]
                samples = [json.loads(line) for line in memory.read_text().splitlines()]
                assert len(samples) == route["memory"]["sample_count"]
                assert max(s["total_bytes"] for s in samples) == route["memory"]["peak_bytes"]
                for sample in samples:
                    assert sum(sample["process_bytes"].values()) == sample["total_bytes"]
                    assert not set(sample["process_bytes"]) & set(sample["excluded_process_bytes"])
                routes[method] = {
                    "wall_seconds": wall,
                    "peak_gib": route["memory"]["peak_bytes"]/2**30,
                    "completed_calls": route["completed_calls"],
                    "input_tokens": route["input_tokens"],
                    "output_tokens": route["generated_output_tokens"],
                    "located_targets": len(route["located_target_ids"]),
                    "matches_frozen_output_calls": route["matches_frozen_output_calls"],
                    "replay_batches": len(route["replay_batches"]),
                }
            common = len(set(trial["routes"]["yf"]["located_target_ids"]) & set(trial["routes"]["mf"]["located_target_ids"]))
            assert common == trial["pair"]["common_targets"] > 0
            for method in routes:
                value = routes[method]["wall_seconds"]/common
                assert abs(value-trial["pair"][f"{method}_seconds_per_common_target"]) < 1e-6
                routes[method]["seconds_per_common_target"] = value
            trials.append({"repeat": repeat, "common_targets": common,
                           "same_output_tokens_calls": trial["pair"]["same_output_tokens_calls"], "routes": routes})
        assert len(trials) == 3
        for row in result["table"]:
            method = row["method"]
            for field, source in [("seconds_per_target", "seconds_per_common_target"), ("batch_wall_seconds", "wall_seconds"), ("peak_gib", "peak_gib")]:
                assert abs(row[field]-statistics.median(t["routes"][method][source] for t in trials)) < 1e-6
        models[tag] = {"identity": read(folder/"identity.json"),
                       "results_sha256": hashlib.sha256((folder/"results.json").read_bytes()).hexdigest(),
                       "table": result["table"], "trials": trials,
                       "settings": result["trials"][0]["routes"]["yf"]["settings"]}
    return {"models": models, "verification": "Saved per-call endpoints, paired denominators, NVML traces and three-repeat medians checked.",
            "scope": "30 frozen DCC inputs per model; independent real generation on each route; no new quality scoring.",
            "denominator": "Per-repeat intersection of exactly locatable frozen target sentences in both regenerated outputs; all 30 calls timed.",
            "interpretation": "Amortized batch completion time, not isolated request latency. Output-token differences are retained. Fixed resident cache contributes to process peak."}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    result = summarize(args.root)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    print("Verified:", ", ".join(result["models"]))
