import json
from pathlib import Path

root = Path(r"F:/CodexProject/MemoryFlow-research")
base = root / "experiments/multiturn_batch_v1/batch10_v3"
subset = root / "artifacts/raw/genmem_batch10_v3/subset/contextual64_v4"
manifest = json.loads((base / "manifest.json").read_text(encoding="utf-8"))

for entry in manifest["cases"]:
    case_path = base / entry["case_path"]
    case = json.loads(case_path.read_text(encoding="utf-8"))
    case_dir = subset / case["trajectory_case"]
    by_artifact = {}
    for line in (case_dir / "source_units.jsonl").read_text(encoding="utf-8").splitlines():
        if line.strip():
            unit = json.loads(line)
            by_artifact.setdefault(unit["artifact_id"], []).append(unit)
    changed = 0
    for group in case["evidence_groups"]:
        for item in group["items"]:
            primary = item["primary"]
            units = by_artifact.get(primary["artifact_id"], [])
            inside = [u for u in units if u["start"] >= primary["start"] and u["end"] <= primary["end"]]
            if not inside:
                continue
            best = max(inside, key=lambda u: u["end"] - u["start"])
            if (best["start"], best["end"]) == (primary["start"], primary["end"]):
                continue
            primary["start"] = best["start"]
            primary["end"] = best["end"]
            primary["text"] = best["text"]
            changed += 1
    case_path.write_text(json.dumps(case, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(entry["short"], "changed", changed)
