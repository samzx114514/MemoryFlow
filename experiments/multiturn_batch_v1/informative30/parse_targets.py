import json
import re
from pathlib import Path

root = Path(r"F:/CodexProject/MemoryFlow-research")
pkg = root / "artifacts/raw/genmem_informative30_v1/genmem_informative30_v1"
pre = Path(r"C:/Users/25779/Documents/Codex/2026-11-05/memoryflow-2026-11-05-memoryflow-ppt/outputs/GenMem_informative30_接入预检_20261107.md")

targets = []
in_priority = False
in_extra = False
for line in pre.read_text(encoding="utf-8").splitlines():
    if line.startswith("## 优先复核的 36 个目标"):
        in_priority, in_extra = True, False
        continue
    if line.startswith("## 其余 15 个跨事件目标"):
        in_priority, in_extra = False, True
        continue
    if line.startswith("## ") and not line.startswith("## 优先") and not line.startswith("## 其余"):
        in_priority, in_extra = False, False
    m = re.match(r"\|\s*(case_\d+)\s*\|\s*(T\d+)\s*\|", line)
    if m and (in_priority or in_extra):
        targets.append((m.group(1), m.group(2), "priority" if in_priority else "extra"))

print("targets", len(targets))
tasks = {(r["case"], r["id"]): r for r in [json.loads(l) for l in (pkg / "tasks.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]}
gts = {(t["case"], t["id"]): t for t in json.loads((pkg / "ground_truth.json").read_text(encoding="utf-8"))["targets"]}
cands = {}
for line in (pkg / "candidates.jsonl").read_text(encoding="utf-8").splitlines():
    if line.strip():
        r = json.loads(line)
        cands[(r["case"], r["id"])] = r

rows = []
for case, tid, group in targets:
    task = tasks[(case, tid)]
    gt = gts.get((case, tid))
    groups = []
    if gt:
        for g in gt.get("answer_groups") or []:
            items = g.get("all_of") or []
            evs = [cands[(case, i["candidate_id"])]["event"] for i in items if (case, i["candidate_id"]) in cands]
            groups.append({"n": len(items), "events": evs, "max": max(evs) if evs else None})
    rows.append({"case": case, "target": tid, "list": group, "target_event": task["target_event"],
                 "groups": groups, "n_groups": len(groups)})
print(json.dumps({"priority": sum(1 for r in rows if r["list"]=="priority"), "extra": sum(1 for r in rows if r["list"]=="extra")}))
Path(root / "experiments/multiturn_batch_v1/informative30/targets51.json").write_text(json.dumps(rows, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
