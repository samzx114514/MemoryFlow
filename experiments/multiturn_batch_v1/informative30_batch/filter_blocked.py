import json
from collections import Counter

base = "experiments/multiturn_batch_v1/informative30_batch/"
man = json.load(open(base + "manifest.json", encoding="utf-8"))
pre = json.load(open(base + "precheck.json", encoding="utf-8"))
blocked = {r["short"] for r in pre["cases"] if not r["ok"]}
man["cases"] = [c for c in man["cases"] if c["short"] not in blocked]
man["totals"]["cases"] = len(man["cases"])
man["totals"]["dev"] = len(man["cases"])
man["totals"]["trajectories"] = len({c["trajectory_id"] for c in man["cases"]})
json.dump(man, open(base + "manifest.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
d = json.load(open(base + "dispositions.json", encoding="utf-8"))
for r in d:
    if f"{r['case']}_{r['target']}" in blocked:
        r["status"] = "control-final-round-sufficient"
        r["reason"] = "precheck: final round alone covers a full group"
json.dump(d, open(base + "dispositions.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print(Counter(r["status"] for r in d), "cases", len(man["cases"]))
