import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
import cases

root = HERE
pkg = root.parents[2] / "artifacts/raw/genmem_informative30_v1/genmem_informative30_v1"
tasks = {(r["case"], r["id"]): r for r in [json.loads(l) for l in (pkg / "tasks.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]}
gts = {(t["case"], t["id"]): t for t in json.loads((pkg / "ground_truth.json").read_text(encoding="utf-8"))["targets"]}
cand = {}
for line in (pkg / "candidates.jsonl").read_text(encoding="utf-8").splitlines():
    if line.strip():
        row = json.loads(line)
        cand[(row["case"], row["id"])] = row

recipes = [
    {"case": "case_03", "target": "T02", "A": "C0012", "B": "C0016", "extras": ["C0015"],
     "intermediate": "Ruby is named after a gemstone."},
    {"case": "case_05", "target": "T07", "A": "C0020", "B": "C0024",
     "intermediate": "Gómez González perished on 26 October 1111 during the Battle of Candespina."},
    {"case": "case_06", "target": "T02", "A": "C0002", "B": "C0007",
     "intermediate": "The old man in Waiting on a Woman is Andy Griffith."},
]

def cid(case, candidate):
    return f"{case}:{candidate}"


def canon(case, candidate, text):
    return f"{cid(case, candidate)}#0-{len(text)}"

def window(case, candidate, text, start=0, end=None):
    return {"artifact_id": cid(case, candidate), "start": start, "end": len(text) if end is None else end,
            "text": text}

cases_dir = root / "cases"
cases_dir.mkdir(exist_ok=True)
manifest = []
for recipe in recipes:
    case = recipe["case"]
    task = tasks[(case, recipe["target"])]
    gt = gts[(case, recipe["target"])]
    group = max(gt["answer_groups"], key=lambda g: len(g["all_of"]))
    pool = {candidate: cand[(case, candidate)] for candidate in task["candidate_ids"]
            if (case, candidate) in cand and (cand[(case, candidate)].get("text") or "").strip()}
    evidence = [item["candidate_id"] for item in group["all_of"]]
    for candidate in evidence + [recipe["A"], recipe["B"]] + recipe.get("extras", []):
        if (case, candidate) not in pool:
            row = cand[(case, candidate)]
            pool[candidate] = row

    def materials(primary, extras):
        chosen = [primary] + extras
        used = {primary} | set(extras)
        for candidate in sorted(pool):
            if candidate in used or candidate in evidence:
                continue
            if pool[candidate]["event"] >= task["target_event"]:
                continue
            chosen.append(candidate)
            if len(chosen) >= 9:
                break
        out = []
        for index, candidate in enumerate(chosen, start=1):
            out.append({"unit_id": canon(case, candidate, pool[candidate]["text"]), "artifact_id": cid(case, candidate), "start": 0, "end": len(pool[candidate]["text"]),
                        "text": pool[candidate]["text"], "role": "evidence_a" if index == 1 and primary == recipe["A"] else
                        "evidence_b" if index == 1 and primary == recipe["B"] else "distractor",
                        "position": {"slot": "material", "index": index}})
        return out

    r1 = materials(recipe["A"], [])
    r2 = materials(recipe["B"], recipe.get("extras", []))
    target_text = task["target"]
    rounds = [
        {"round": 1, "question": task["question"], "inputs": r1,
         "output": {"text": recipe["intermediate"], "sha256": cases.sha256_text(recipe["intermediate"]),
                    "origin": "controlled_output"}, "transmission": []},
        {"round": 2, "question": task["question"], "inputs": r2,
         "output": {"text": target_text, "sha256": cases.sha256_text(target_text), "origin": "recorded_target"},
         "transmission": [{"from_round": 1, "unit_id": "round1_output", "text": recipe["intermediate"],
                           "sha256": cases.sha256_text(recipe["intermediate"]),
                           "position": {"slot": "earlier_finding", "index": 0}}]},
    ]
    candidates = []
    for candidate, row in sorted(pool.items()):
        candidates.append({"canonical_id": canon(case, candidate, row["text"]), "artifact_id": cid(case, candidate),
                           "start": 0, "end": len(row["text"]), "text": row["text"], "occurrences": [],
                           "pool_only": True})
    used = {}
    for round_record in rounds:
        for index, material in enumerate(round_record["inputs"], start=1):
            used.setdefault(material["unit_id"], []).append(
                {"round": round_record["round"], "unit_id": material["unit_id"], "role": material["role"],
                 "position": {"slot": "material", "index": index}})
    for candidate in candidates:
        candidate["occurrences"] = used.get(candidate["canonical_id"], [])
        candidate["pool_only"] = not candidate["occurrences"]
    groups = []
    for g in gt["answer_groups"]:
        items = []
        for item in g["all_of"]:
            candidate = item["candidate_id"]
            text = item.get("text") or pool[candidate]["text"][item.get("start", 0):item.get("end", len(pool[candidate]["text"]))]
            items.append({"primary": window(case, candidate, text, item.get("start", 0), item.get("end")),
                          "alternatives": [window(case, candidate, text, item.get("start", 0), item.get("end"))]})
        groups.append({"group_id": f"{case}:{recipe['target']}:support_g{len(groups)+1:02d}",
                       "coverage": "full", "items": items})
    built = {
        "schema": cases.SCHEMA, "case_id": f"{case}:{recipe['target']}", "trajectory_id": case,
        "trajectory_case": case, "split": "dev", "record_type": "controlled", "control": None,
        "analysis_pool": "union",
        "target": {"text": target_text, "sha256": cases.sha256_text(target_text), "origin": "recorded_target",
                   "artifact_id": f"{case}:{recipe['target']}", "start": 0, "end": len(target_text),
                   "original_target": {"text": target_text, "artifact_id": f"{case}:{recipe['target']}"}},
        "rounds": rounds, "candidates": candidates, "evidence_groups": groups,
        "labels": {"A": [canon(case, recipe["A"], pool[recipe["A"]]["text"])], "B": [canon(case, recipe["B"], pool[recipe["B"]]["text"])]},
        "provenance": {"package": "genmem_informative30_v1", "target": task, "group": group,
                       "intermediate": "controlled", "note": "controlled two-round; real intermediate message not yet verified"},
    }
    issues = cases.validate_case(built)
    if issues:
        raise SystemExit(f"{case}:{recipe['target']} {issues}")
    slug = f"{case}_{recipe['target']}"
    (cases_dir / f"{slug}.json").write_text(json.dumps(built, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    manifest.append({"short": slug, "case_id": built["case_id"], "trajectory_id": case, "trajectory_case": case,
                     "split": "dev", "record_type": "controlled", "control": None, "rounds": 2,
                     "candidates": len(candidates), "evidence_groups": len(groups),
                     "case_path": f"cases/{slug}.json", "matrix_path": f"matrices/{slug}.json",
                     "case_sha256": cases.case_hash(built), "registry": cases.missing_registry(built)})
(root / "manifest.json").write_text(json.dumps({
    "schema": "memoryflow.multiturn_batch.manifest.v1", "created": "2026-11-07",
    "final_budget": cases.FINAL_BUDGET, "hop_budget": cases.HOP_BUDGET, "cases": manifest,
    "totals": {"cases": len(manifest), "controlled": len(manifest), "real_request": 0, "dev": len(manifest),
               "eval": 0, "controls": 0, "trajectories": len({m['trajectory_id'] for m in manifest})},
}, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
print(json.dumps({"cases": len(manifest), "ids": [m["short"] for m in manifest]}, ensure_ascii=False))




