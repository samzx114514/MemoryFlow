import csv
import json
from pathlib import Path

root = Path(r"F:/CodexProject/MemoryFlow-research")
gt = {}
for line in (root / "artifacts/raw/genmem_batch10_v3/gt100/ground_truth_v2/ground_truth.jsonl").read_text(encoding="utf-8").splitlines():
    if line.strip():
        row = json.loads(line)
        gt[row["target_id"]] = row

subset = root / "artifacts/raw/genmem_batch10_v3/subset/contextual64_v4"
unit_cache = {}

def units(case):
    if case not in unit_cache:
        by_artifact = {}
        with (subset / case / "source_units.jsonl").open(encoding="utf-8") as handle:
            for line in handle:
                if line.strip():
                    unit = json.loads(line)
                    by_artifact.setdefault(unit["artifact_id"], []).append(unit)
        unit_cache[case] = by_artifact
    return unit_cache[case]

def map_primary(case, primary):
    candidates = units(case).get(primary["artifact_id"], [])
    exact = [u for u in candidates if u["start"] == primary["start"] and u["end"] == primary["end"]]
    if exact:
        return exact[0]["id"]
    same_text = [u for u in candidates if u["text"].strip() == primary.get("text", "").strip()]
    if same_text:
        return same_text[0]["id"]
    inside = [u for u in candidates if u["start"] >= primary["start"] and u["end"] <= primary["end"]]
    if inside:
        return max(inside, key=lambda u: u["end"] - u["start"])["id"]
    containing = [u for u in candidates if u["start"] <= primary["start"] and u["end"] >= primary["end"]]
    if containing:
        return min(containing, key=lambda u: u["end"] - u["start"])["id"]
    overlap = [u for u in candidates if u["start"] < primary["end"] and u["end"] > primary["start"]]
    if overlap:
        return max(overlap, key=lambda u: min(u["end"], primary["end"]) - max(u["start"], primary["start"]))["id"]
    text = primary.get("text", "")
    same = [u for u in candidates if u["text"] == text]
    if same:
        return same[0]["id"]
    return None

rows = list(csv.DictReader((root / "experiments/multiturn_batch_v1/batch10_v2/reports/SCREENING_100_20261106.csv").open(encoding="utf-8")))
ids = [r["target_id"] for r in rows if r["status"] == "candidate-full"]
ids += ["genmem_874c34ceb20bf193:selected_03", "genmem_874c34ceb20bf193:selected_09"]

recipes = []
for tid in ids:
    entry = gt[tid]
    case = entry["case"]
    groups = entry.get("answer_groups") or []
    best = None
    for group in groups:
        items = group.get("all_of") or []
        events = {item["primary"].get("event_index") for item in items}
        if len(items) < 2:
            continue
        if best is None or len(items) < len(best[0]):
            best = (items, group, events)
    if best is None:
        print("SKIP no group", tid)
        continue
    items, group, events = best
    mapped = []
    for item in items:
        uid = map_primary(case, item["primary"])
        if uid and uid not in [m[0] for m in mapped]:
            mapped.append((uid, item["primary"].get("event_index")))
    if len(mapped) < 2:
        print("SKIP mapping", tid, mapped)
        continue
    # prefer two items from different events
    a_index = 0
    b_index = 1
    for i in range(len(mapped)):
        for j in range(i + 1, len(mapped)):
            if mapped[i][1] != mapped[j][1]:
                a_index, b_index = i, j
                break
        else:
            continue
        break
    A = mapped[a_index][0]
    B = mapped[b_index][0]
    extras = [uid for k, (uid, _) in enumerate(mapped) if k not in (a_index, b_index)]
    a_text = ""
    for units_list in units(case).values():
        for unit in units_list:
            if unit["id"] == A:
                a_text = unit["text"]
                break
    recipe = {
        "case": case,
        "target_id": tid,
        "group_id": group["id"],
        "A": A,
        "B": B,
        "intermediate": f"The earlier material states: {a_text[:240]}",
        "analysis_pool": "union",
        "merge_same_source": False,
    }
    if extras:
        recipe["r2_extras"] = extras
    recipes.append(recipe)

out = root / "experiments/multiturn_batch_v1/batch10_v3"
out.mkdir(parents=True, exist_ok=True)
(out / "recipes.json").write_text(json.dumps(recipes, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps({"count": len(recipes), "ids": [r["target_id"] for r in recipes]}, ensure_ascii=False, indent=1))
