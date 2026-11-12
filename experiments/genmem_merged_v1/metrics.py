"""Evaluate fixed root-material rankings using the historic span-union rule."""
import argparse
import json
import sys
from pathlib import Path
from statistics import mean

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from multiturn_batch_v1.cases import complete_at, covered_fragment, fragment_hit_at


def evaluate(case, ranking):
    if not case["evidence_groups"]:
        return {"status": "incomplete_material_support"}
    if len(ranking) != len(set(ranking)):
        raise ValueError("Ranking contains duplicate material identities")
    index = {c["canonical_id"]: c for c in case["candidates"]}
    groups = [{"coverage": "full", **g} for g in case["evidence_groups"]]
    selected = [index[cid] for cid in ranking[:10] if cid in index]
    windows = [(c["artifact_id"], c["start"], c["end"]) for c in selected]
    all_alts = [a for g in groups for item in g["items"] for a in item["alternatives"]]
    relevant = sum(any(c["artifact_id"] == a["artifact_id"] and min(c["end"], a["end"]) > max(c["start"], a["start"])
                       for a in all_alts) for c in selected)
    precision = relevant/min(10, len(ranking)) if ranking else 0.0
    recall = max(sum(any(covered_fragment(a, windows) for a in item["alternatives"]) for item in g["items"])/len(g["items"]) for g in groups)
    def first(k):
        return [(index[cid]["artifact_id"], index[cid]["start"], index[cid]["end"]) for cid in ranking[:k] if cid in index]
    return {"status": "scored", "precision_at_10": precision, "recall_at_10": recall,
            "f1_at_10": 2*precision*recall/(precision+recall) if precision+recall else 0.0,
            "coverage": float(bool(selected)), "hit_at_3": float(fragment_hit_at(groups, first(3))),
            "complete_at_5": float(complete_at(groups, first(5))), "complete_at_10": float(complete_at(groups, windows))}


def summarize(cases, rows):
    by_id = {}
    for row in rows:
        by_id.setdefault(row["id"], []).append(row)
    if set(by_id) != {c["case_id"] for c in cases}:
        raise ValueError("Method target coverage differs from fixed 96 targets")
    per_target = []
    for case in cases:
        scores = [evaluate(case, r["ranking"]) for r in by_id[case["case_id"]]]
        result = {"id": case["case_id"], "sample_id": case["sample_id"], "status": scores[0]["status"],
                  "rankings": [r["ranking"][:10] for r in by_id[case["case_id"]]]}
        if result["status"] == "scored":
            result.update({key: mean(s[key] for s in scores) for key in scores[0] if key != "status"})
        per_target.append(result)
    scored = [r for r in per_target if r["status"] == "scored"]
    if len(scored) != 92:
        raise ValueError("User-approved material-quality denominator must remain 92")
    table = {key: mean(r[key] for r in scored) for key in scored[0] if key not in {"id", "sample_id", "status", "rankings"}}
    return {"targets": len(cases), "quality_targets": len(scored), "incomplete": 4, "metrics": table, "per_target": per_target}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--common", type=Path, required=True)
    parser.add_argument("--method", nargs=2, action="append", metavar=("NAME", "RANKINGS"), required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    cases = json.loads((args.common/"cases.json").read_text())
    result = {}
    for name, path in args.method:
        p = Path(path)
        rows = [json.loads(line) for line in p.read_text().splitlines() if line.strip()] if p.suffix == ".jsonl" else json.loads(p.read_text())
        if name == "DFAMS":
            seeds = {}
            for row in rows:
                seeds.setdefault(row["id"], []).append(row.get("checkpoint_seed"))
            if len(rows) != 288 or any(sorted(values) != [0, 1, 2] for values in seeds.values()):
                raise ValueError("DFAMS must retain the three original seeds for every target")
        result[name] = summarize(cases, rows)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    if args.output.exists():
        raise FileExistsError(args.output)
    args.output.write_text(json.dumps({"return_cap": 10, "quality_denominator": 92, "methods": result,
        "metric_note": "Material-span reference metrics: Precision is returned fragments overlapping an annotated support span; Recall is covered required items in the best complete support group. Not the E1 semantic citation metric or a causal chain score."}, ensure_ascii=False, indent=2)+"\n")
