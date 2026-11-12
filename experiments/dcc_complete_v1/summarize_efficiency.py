"""Summarize measured repeats, retaining failed attempts and excluding warmups."""
import json
import statistics
from collections import defaultdict
from pathlib import Path


def summarize(root):
    groups, attempts = defaultdict(list), []
    metrics = ("analysis_seconds_per_target", "task_total_seconds", "tail_seconds",
               "analysis_gpu_seconds", "process_peak_total_mib", "execution_prompt_tokens",
               "execution_output_tokens", "successful_calls", "targets")
    paths = list(root.glob("*/result.json")) + list(root.glob("*/*/result.json"))
    for path in sorted(paths):
        value = json.loads(path.read_text())
        if value.get("warmup"):
            continue
        identity = json.loads((path.parent / "gateway/identity.json").read_text())
        key = identity["analysis_model"] if value["mode"] != "execution" else "execution_only"
        attempts.append({"run": path.parent.name, "analysis_model": key, **value})
        groups[key, value["mode"]].append(value)
    table = []
    for (model, mode), values in sorted(groups.items()):
        completed = [value for value in values if value.get("completed")]
        table.append({"analysis_model": model, "mode": mode, "attempts": len(values),
                      "completed": len(completed), "planned_repeats": 3,
                      "completion_rate": len(completed)/len(values),
                      "all_three_complete": len(completed) == 3 and len(values) == 3,
                      **{metric: statistics.median([v[metric] for v in completed if v.get(metric) is not None])
                         if any(v.get(metric) is not None for v in completed) else None for metric in metrics}})
    return {"cases": sorted({row["task_id"] for row in attempts}), "aggregation": "median of completed measured repeats; failure counts retained",
            "table": table, "attempts": attempts}


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    args.output.write_text(json.dumps(summarize(args.root), ensure_ascii=False, indent=2)+"\n")
