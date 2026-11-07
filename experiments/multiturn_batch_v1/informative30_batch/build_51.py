import json
import re
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
import cases

root = HERE
pkg = root.parents[2] / "artifacts/raw/genmem_informative30_v1/genmem_informative30_v1"
targets = json.loads((HERE.parent / "informative30/targets51.json").read_text(encoding="utf-8"))
tasks = {(r["case"], r["id"]): r for r in [json.loads(l) for l in (pkg / "tasks.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]}
gts = {(t["case"], t["id"]): t for t in json.loads((pkg / "ground_truth.json").read_text(encoding="utf-8"))["targets"]}
cand = {}
for line in (pkg / "candidates.jsonl").read_text(encoding="utf-8").splitlines():
    if line.strip():
        row = json.loads(line)
        cand[(row["case"], row["id"])] = row

raw = {}
for case in {t["case"] for t in targets}:
    raw[case] = json.loads((pkg / "raw_runs" / f"{case}.json").read_text(encoding="utf-8"))["memory_stack_log"]

def tokens(text):
    return set(re.findall(r"[a-z0-9]{3,}", text.lower()))

def overlap(a, b):
    return len(tokens(a) & tokens(b))

def canon(case, candidate):
    return f"{case}:{candidate}#0-{len(cand[(case, candidate)]['text'])}"

def strip(text):
    return text.replace("\n", " ").strip()

cases_dir = HERE / "cases"
cases_dir.mkdir(exist_ok=True)
manifest = []
dispositions = []

for target in targets:
    case, tid = target["case"], target["target"]
    task = tasks[(case, tid)]
    gt = gts.get((case, tid))
    target_event = task["target_event"]
    pool = {c: cand[(case, c)] for c in task["candidate_ids"] if (case, c) in cand and cand[(case, c)].get("text", "").strip()}
    groups = []
    for g in (gt or {}).get("answer_groups") or []:
        items = []
        ok = True
        for item in g.get("all_of") or []:
            cid = item["candidate_id"]
            if cid not in pool:
                ok = False
                break
            items.append((cid, pool[cid]["event"], item))
        if ok and items:
            groups.append((items, g))
    eligible = [pair for pair in groups if all(ev < target_event for _, ev, _ in pair[0])]
    if not eligible:
        dispositions.append({"case": case, "target": tid, "list": target["list"], "status": "insufficient",
                             "reason": "no evidence group fully before target event"})
        continue
    items, group = min(eligible, key=lambda pair: (len(pair[0]), -max(ev for _, ev, _ in pair[0])))

    # special case_01:T10: C0036 is event-29 intermediate, not upstream
    if (case, tid) == ("case_01", "T10"):
        earlier = [c for c in pool if pool[c]["event"] in (27, 28) and "born to demetrios" in pool[c]["text"].lower()]
        if earlier:
            a_id = sorted(earlier, key=lambda c: (pool[c]["event"], c))[0]
            items = [(a_id, pool[a_id]["event"], {"candidate_id": a_id, "text": pool[a_id]["text"], "start": 0, "end": len(pool[a_id]["text"])})]
            for c in ("C0037", "C0042"):
                if c in pool:
                    items.append((c, pool[c]["event"], {"candidate_id": c, "text": pool[c]["text"], "start": 0, "end": len(pool[c]["text"])}))
            group = {"id": f"{case}:{tid}:custom", "all_of": [{"candidate_id": c} for c, _, _ in items]}

    if (case, tid) == ("case_01", "T10") and "C0034" in pool:
        items = [(c, pool[c]["event"], {"candidate_id": c, "text": pool[c]["text"], "start": 0, "end": len(pool[c]["text"])})
                 for c in ("C0034", "C0037", "C0042") if c in pool]
        group = {"id": f"{case}:{tid}:custom", "all_of": [{"candidate_id": c} for c, _, _ in items]}

    a_candidates = sorted([x for x in items if x[1] < target_event], key=lambda x: (x[1], x[0]))
    if len(a_candidates) < 2:
        dispositions.append({"case": case, "target": tid, "list": target["list"], "status": "insufficient",
                             "reason": "fewer than two prior evidence items"})
        continue
    min_event = min(ev for _, ev, _ in a_candidates)
    # real agent message between earliest evidence and target that carries evidence content
    intermediate = None
    for event in range(min_event + 1, target_event):
        entry = raw[case][event]
        if entry.get("action") != "agent":
            continue
        content = str(entry.get("content") or "")
        if len(content) < 50:
            continue
        if any(overlap(content, pool[c]["text"]) >= 2 for c, _, _ in a_candidates):
            intermediate = (event, content)
    if (case, tid) == ("case_03", "T04"):
        intermediate = (8, str(raw[case][8].get("content") or ""))
    if (case, tid) == ("case_06", "T10"):
        intermediate = (8, str(raw[case][8].get("content") or ""))
    if intermediate:
        cut = intermediate[0]
        early = [x for x in a_candidates if x[1] < cut]
        late = [x for x in a_candidates if x[1] > cut]
        if not early or not late:
            dispositions.append({"case": case, "target": tid, "list": target["list"], "status": "control-or-insufficient",
                                 "reason": "real intermediate exists but no evidence on both sides"})
            continue
        A = early[0]
        B = late[-1]
        extras = [x for x in a_candidates if x not in (A, B)]
        intermediate_text = intermediate[1]
        origin = "recorded_agent_message"
        r1_cut = cut
        r2_cut = target_event
    else:
        A = a_candidates[0]
        B = a_candidates[-1]
        extras = [x for x in a_candidates if x not in (A, B)]
        intermediate_text = f"The earlier material states: {pool[A[0]]['text'][:240]}"
        origin = "controlled"
        r1_cut = target_event
        r2_cut = target_event

    evidence_ids = {c for c, _, _ in a_candidates}

    def round_candidates(primary, extra_ids, cut, exclude_ids):
        chosen = [primary] + extra_ids
        used = set(chosen) | set(exclude_ids)
        for candidate in sorted(pool, key=lambda c: (pool[c]["event"], c)):
            if candidate in used or candidate in evidence_ids:
                continue
            if pool[candidate]["event"] >= cut:
                continue
            chosen.append(candidate)
            used.add(candidate)
            if len(chosen) >= 9:
                break
        return chosen

    r1_ids = round_candidates(A[0], [], r1_cut, set())
    r2_ids = round_candidates(B[0], [x[0] for x in extras], r2_cut, set(r1_ids))

    def materials(ids, roles):
        out = []
        for index, c in enumerate(ids, start=1):
            out.append({"unit_id": canon(case, c), "artifact_id": f"{case}:{c}", "start": 0,
                        "end": len(pool[c]["text"]), "text": pool[c]["text"],
                        "role": roles.get(c, "distractor"), "position": {"slot": "material", "index": index},
                        "event": pool[c]["event"]})
        return out

    roles1 = {A[0]: "evidence_a"}
    roles2 = {B[0]: "evidence_b"}
    r1 = materials(r1_ids, roles1)
    r2 = materials(r2_ids, roles2)
    # time-order audit
    audit = []
    for material in r1:
        audit.append({"round": 1, "event": material["event"], "cut": r1_cut, "ok": material["event"] < r1_cut})
    for material in r2:
        audit.append({"round": 2, "event": material["event"], "cut": r2_cut, "ok": material["event"] < r2_cut})
    if not all(row["ok"] for row in audit):
        dispositions.append({"case": case, "target": tid, "list": target["list"], "status": "blocked",
                             "reason": "time-order audit failed"})
        continue

    target_text = task["target"]
    rounds = [
        {"round": 1, "question": task["question"], "inputs": r1,
         "output": {"text": intermediate_text, "sha256": cases.sha256_text(intermediate_text), "origin": origin},
         "transmission": []},
        {"round": 2, "question": task["question"], "inputs": r2,
         "output": {"text": target_text, "sha256": cases.sha256_text(target_text), "origin": "recorded_target"},
         "transmission": [{"from_round": 1, "unit_id": "round1_output", "text": intermediate_text,
                           "sha256": cases.sha256_text(intermediate_text),
                           "position": {"slot": "earlier_finding", "index": 0}}]},
    ]
    candidates = []
    for candidate in sorted(pool):
        candidates.append({"canonical_id": canon(case, candidate), "artifact_id": f"{case}:{candidate}",
                           "start": 0, "end": len(pool[candidate]["text"]), "text": pool[candidate]["text"],
                           "occurrences": [], "pool_only": True})
    used = {}
    for round_record in rounds:
        for index, material in enumerate(round_record["inputs"], start=1):
            used.setdefault(material["unit_id"], []).append(
                {"round": round_record["round"], "unit_id": material["unit_id"], "role": material["role"],
                 "position": {"slot": "material", "index": index}})
    for candidate in candidates:
        candidate["occurrences"] = used.get(candidate["canonical_id"], [])
        candidate["pool_only"] = not candidate["occurrences"]
    evidence_groups = []
    for g in gt["answer_groups"]:
        gitems = []
        for item in g["all_of"]:
            c = item["candidate_id"]
            if c not in pool:
                continue
            gitems.append({"primary": {"artifact_id": f"{case}:{c}", "start": 0, "end": len(pool[c]["text"]),
                                        "text": pool[c]["text"]}, "alternatives": []})
            gitems[-1]["alternatives"] = [dict(gitems[-1]["primary"])]
        evidence_groups.append({"group_id": f"{case}:{tid}:support_g{len(evidence_groups)+1:02d}",
                                "coverage": "full", "items": gitems})
    built = {
        "schema": cases.SCHEMA, "case_id": f"{case}:{tid}", "trajectory_id": case, "trajectory_case": case,
        "split": "dev", "record_type": "controlled",
        "control": None, "analysis_pool": "union",
        "target": {"text": target_text, "sha256": cases.sha256_text(target_text), "origin": "recorded_target",
                   "artifact_id": f"{case}:{tid}", "start": 0, "end": len(target_text),
                   "original_target": {"text": target_text, "artifact_id": f"{case}:{tid}"}},
        "rounds": rounds, "candidates": candidates, "evidence_groups": evidence_groups,
        "labels": {"A": [canon(case, A[0])], "B": [canon(case, B[0])]},
        "provenance": {"package": "genmem_informative30_v1", "target": task, "group": group,
                       "intermediate_origin": origin, "intermediate_event": intermediate[0] if intermediate else None,
                       "time_order_audit": audit,
                       "note": "time-order checked for evidence and distractors"},
    }
    issues = cases.validate_case(built)
    if issues:
        dispositions.append({"case": case, "target": tid, "list": target["list"], "status": "blocked",
                             "reason": "; ".join(issues[:3])})
        continue
    slug = f"{case}_{tid}"
    (cases_dir / f"{slug}.json").write_text(json.dumps(built, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    manifest.append({"short": slug, "case_id": built["case_id"], "trajectory_id": case, "trajectory_case": case,
                     "split": "dev", "record_type": built["record_type"], "control": None, "rounds": 2,
                     "candidates": len(candidates), "evidence_groups": len(evidence_groups),
                     "case_path": f"cases/{slug}.json", "matrix_path": f"matrices/{slug}.json",
                     "case_sha256": cases.case_hash(built), "registry": cases.missing_registry(built)})
    dispositions.append({"case": case, "target": tid, "list": target["list"], "status": origin,
                         "reason": f"group {len(a_candidates)} items; intermediate event {intermediate[0] if intermediate else '-'}; R1 {len(r1)} R2 {len(r2)}"})

(manifest_path := HERE / "manifest.json").write_text(json.dumps({
    "schema": "memoryflow.multiturn_batch.manifest.v1", "created": "2026-11-07",
    "final_budget": cases.FINAL_BUDGET, "hop_budget": cases.HOP_BUDGET, "cases": manifest,
    "totals": {"cases": len(manifest), "controlled": sum(1 for m in manifest if m["record_type"] == "controlled"),
               "real": sum(1 for m in manifest if m["record_type"] == "real_transmission"),
               "dev": len(manifest), "eval": 0, "controls": 0,
               "trajectories": len({m["trajectory_id"] for m in manifest})},
}, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
(HERE / "dispositions.json").write_text(json.dumps(dispositions, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
print(json.dumps({"built": len(manifest), "dispositions": dispositions[-5:], "totals": json.loads((HERE / 'manifest.json').read_text(encoding='utf-8'))["totals"]}, ensure_ascii=False, indent=1))



