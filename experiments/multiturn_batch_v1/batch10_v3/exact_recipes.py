import json
from pathlib import Path

root = Path(r"F:/CodexProject/MemoryFlow-research")
subset = root / "artifacts/raw/genmem_batch10_v3/subset/contextual64_v4"

targets = [
    "genmem_177236211632d6b8:selected_03",
    "genmem_177236211632d6b8:selected_04",
    "genmem_177236211632d6b8:selected_09",
    "genmem_177236211632d6b8:selected_10",
    "genmem_9f963d36b4935b97:selected_04",
    "genmem_9f963d36b4935b97:selected_07",
    "genmem_40dc9b8b15c0c5b8:selected_05",
    "genmem_40dc9b8b15c0c5b8:selected_09",
    "genmem_f46a08bc62ee9b37:selected_02",
    "genmem_874c34ceb20bf193:selected_03",
    "genmem_874c34ceb20bf193:selected_09",
]

def load_units(case):
    by_span = {}
    by_id = {}
    for line in (subset / case / "source_units.jsonl").read_text(encoding="utf-8").splitlines():
        if line.strip():
            unit = json.loads(line)
            by_span[(unit["artifact_id"], unit["start"], unit["end"])] = unit
            by_id[unit["id"]] = unit
    return by_span, by_id

case_of = {}
for line in (root / "artifacts/raw/genmem_batch10_v3/gt100/ground_truth_v2/ground_truth.jsonl").read_text(encoding="utf-8").splitlines():
    if line.strip():
        row = json.loads(line)
        case_of[row["target_id"]] = row["case"]

recipes = []
for tid in targets:
    case = case_of[tid]
    gt = {row["target_id"]: row for row in json.loads((subset / case / "ground_truth.json").read_text(encoding="utf-8"))}
    entry = gt[tid]
    by_span, _ = load_units(case)

    def unit_for(primary):
        key = (primary["artifact_id"], primary["start"], primary["end"])
        if key in by_span:
            return by_span[key]
        for occurrence in []:
            pass
        return None

    groups = []
    for group in entry.get("answer_groups") or []:
        mapped = []
        ok = True
        for item in group.get("all_of") or []:
            primary = item["primary"]
            unit = unit_for(primary)
            if unit is None:
                ok = False
                break
            mapped.append(unit)
        if ok and len(mapped) >= 2:
            groups.append((mapped, group))
    if not groups:
        print("SKIP", tid)
        continue
    groups.sort(key=lambda pair: len(pair[0]))
    mapped, group = groups[0]
    # prefer two different events
    a_index, b_index = 0, 1
    for i in range(len(mapped)):
        for j in range(i + 1, len(mapped)):
            if mapped[i]["event_index"] != mapped[j]["event_index"]:
                a_index, b_index = i, j
                break
        else:
            continue
        break
    A = mapped[a_index]
    B = mapped[b_index]
    extras = [u["id"] for k, u in enumerate(mapped) if k not in (a_index, b_index)]
    recipe = {
        "case": case,
        "target_id": tid,
        "group_id": group["id"],
        "A": A["id"],
        "B": B["id"],
        "intermediate": f"The earlier material states: {A['text'][:240]}",
        "analysis_pool": "union",
        "merge_same_source": False,
    }
    if extras:
        recipe["r2_extras"] = extras
    recipes.append(recipe)

out = root / "experiments/multiturn_batch_v1/batch10_v3/exact_recipes.json"
out.write_text(json.dumps(recipes, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps({"count": len(recipes), "ids": [r["target_id"] for r in recipes]}, ensure_ascii=False, indent=1))
