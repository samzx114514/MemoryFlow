import json
from pathlib import Path

base = Path(r"F:/CodexProject/MemoryFlow-research/experiments/multiturn_batch_v1")
v2 = json.loads((base / "batch10_v2/reports/BATCH10_V2_20261106.json").read_text(encoding="utf-8"))
v3 = json.loads((base / "batch10_v3/reports/BATCH10_V3_20261107.json").read_text(encoding="utf-8"))

keep = {
    "genmem_177236211632d6b8:selected_02",
    "genmem_874c34ceb20bf193:selected_05",
    "genmem_940c258011aac604:selected_10",
    "genmem_9f963d36b4935b97:selected_01",
    "genmem_5c054943b1a987e0:selected_07",
}
rows = [row for row in v2["cases"] if row["case_id"] in keep] + list(v3["cases"])
seen = set()
unique = []
for row in rows:
    if row["case_id"] not in seen:
        seen.add(row["case_id"])
        unique.append(row)

methods = ("last_round", "bm25_history", "head_full_history", "memoryflow")
summary = {m: {"hit3": 0, "c5": 0, "c10": 0, "ranks": [], "hit": []} for m in methods}
for row in unique:
    for m in methods:
        data = row["methods"][m]
        summary[m]["hit3"] += int(data["hit_at_3"])
        summary[m]["c5"] += int(data["complete_at_5"])
        summary[m]["c10"] += int(data["complete_at_10"])
        summary[m]["ranks"].append(data["complete_rank"] if data["complete_rank"] is not None else 11)
        summary[m]["hit"].append(data["hit_rank"] if data["hit_rank"] is not None else 11)

n = len(unique)
print("cases", n, "trajectories", len({r["trajectory_case"] for r in unique}))
for m in methods:
    s = summary[m]
    print(m, "hit", s["hit3"], "c5", s["c5"], "c10", s["c10"],
          "mean_complete", round(sum(s["ranks"]) / n, 2), "mean_hit", round(sum(s["hit"]) / n, 2))

for baseline in ("last_round", "bm25_history", "head_full_history"):
    comp = {"win": 0, "tie": 0, "loss": 0}
    hit = {"win": 0, "tie": 0, "loss": 0}
    for row in unique:
        mf = row["methods"]["memoryflow"]
        other = row["methods"][baseline]
        for key, target in (("complete_rank", comp), ("hit_rank", hit)):
            left = mf[key] if mf[key] is not None else 11
            right = other[key] if other[key] is not None else 11
            if left < right:
                target["win"] += 1
            elif left == right:
                target["tie"] += 1
            else:
                target["loss"] += 1
    print(baseline, comp, hit)

Path(base / "batch10_v3/reports/CUMULATIVE_EXPANDED.json").write_text(
    json.dumps({"cases": [r["case_id"] for r in unique], "n": n,
                "trajectories": len({r["trajectory_case"] for r in unique}),
                "summary": summary, "rows": unique}, ensure_ascii=False, indent=1), encoding="utf-8")
