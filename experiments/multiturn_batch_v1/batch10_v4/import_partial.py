import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
import cases
import import_batch10 as imp

root = HERE.parents[2]
subset = root / "artifacts/raw/genmem_batch10_v3/subset/contextual64_v4"
gt100 = {}
for line in (root / "artifacts/raw/genmem_batch10_v3/gt100/ground_truth_v2/ground_truth.jsonl").read_text(encoding="utf-8").splitlines():
    if line.strip():
        row = json.loads(line)
        gt100[row["target_id"]] = row

recipes = [
    {
        "case": "case_05",
        "target_id": "genmem_58452c40de4bdcb9:selected_01",
        "A": "genmem_58452c40de4bdcb9:a0047:u0-110",
        "B": "genmem_58452c40de4bdcb9:a0064:u32-123",
        "r2_extras": ["genmem_58452c40de4bdcb9:a0064:u124-143"],
        "intermediate": "The problem asks which gas has the larger van der Waals a parameter.",
    },
    {
        "case": "case_09",
        "target_id": "genmem_e81701f69088a32d:selected_08",
        "A": "genmem_e81701f69088a32d:a0222:u23-154",
        "B": "genmem_e81701f69088a32d:a0070:u0-133",
        "r2_extras": ["genmem_e81701f69088a32d:a0061:u75-219"],
        "intermediate": "TBS is derived from the same lumbar spine DXA image, without extra radiation.",
    },
    {
        "case": "case_08",
        "target_id": "genmem_996703de4e5c4aa9:selected_02",
        "A": "genmem_996703de4e5c4aa9:a0024:u0-83",
        "B": "genmem_996703de4e5c4aa9:a0045:u0-82",
        "r2_extras": ["genmem_996703de4e5c4aa9:a0030:u108-222"],
        "intermediate": "The debate asks whether biochemical activity is the same as biological function.",
    },
]

out = HERE
(out / "cases").mkdir(exist_ok=True)
index = []
for recipe in recipes:
    case = recipe["case"]
    units = imp.load_units(subset / case)
    pool = imp.build_source_pool(units)
    target = gt100[recipe["target_id"]]["target"]
    target_entry = {
        "target_id": recipe["target_id"],
        "target": target,
        "answer_groups": [
            {
                "id": f"{recipe['target_id']}:support_g01",
                "coverage": "full",
                "all_of": [
                    {"primary": {"artifact_id": units[uid]["artifact_id"], "start": units[uid]["start"],
                                 "end": units[uid]["end"], "text": units[uid]["text"]}}
                    for uid in [recipe["A"], recipe["B"], *recipe.get("r2_extras", [])]
                ],
            }
        ],
    }
    built = imp.build_case(recipe, units, target_entry, pool, subset / case)
    built["analysis_pool"] = "union"
    issues = cases.validate_case(built)
    if issues:
        raise SystemExit(f"{recipe['target_id']}: {issues}")
    slug = f"{case}_{recipe['target_id'].split(':')[-1]}"
    path = out / "cases" / f"{slug}.json"
    path.write_text(json.dumps(built, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    index.append({
        "short": slug,
        "case_id": built["case_id"],
        "trajectory_id": built["trajectory_id"],
        "trajectory_case": built["trajectory_case"],
        "split": built["split"],
        "record_type": built["record_type"],
        "control": built["control"],
        "rounds": len(built["rounds"]),
        "candidates": len(built["candidates"]),
        "evidence_groups": len(built["evidence_groups"]),
        "case_path": f"cases/{slug}.json",
        "matrix_path": f"matrices/{slug}.json",
        "case_sha256": cases.case_hash(built),
        "registry": cases.missing_registry(built),
    })
manifest = {
    "schema": "memoryflow.multiturn_batch.manifest.v1",
    "created": "2026-11-07",
    "final_budget": cases.FINAL_BUDGET,
    "hop_budget": cases.HOP_BUDGET,
    "cases": index,
    "totals": {"cases": len(index), "controlled": len(index), "real_request": 0, "dev": len(index),
               "eval": 0, "controls": 0, "trajectories": len({r["trajectory_id"] for r in index})},
}
(out / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
print(json.dumps(manifest["totals"], ensure_ascii=False))



