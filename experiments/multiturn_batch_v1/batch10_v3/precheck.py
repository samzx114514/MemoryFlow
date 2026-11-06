#!/usr/bin/env python3
"""Pre-score check: union covers a full group, fits top-10, final round alone does not."""

import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

import cases


def windows_for(case, round_numbers):
    index = {candidate["canonical_id"]: candidate for candidate in case["candidates"]}
    windows = []
    for round_record in case["rounds"]:
        if round_record["round"] not in round_numbers:
            continue
        for material in round_record["inputs"]:
            cid = cases.canonical_id(material["artifact_id"], material["start"], material["end"])
            if cid in index:
                windows.append((index[cid]["artifact_id"], index[cid]["start"], index[cid]["end"]))
    return windows


def min_windows(group, windows):
    remaining = set(range(len(group["items"])))
    used = 0
    while remaining:
        best = set()
        for window in windows:
            covered = {
                i for i in remaining
                if any(cases.covered_fragment(alt, [window]) for alt in (group["items"][i].get("alternatives") or [group["items"][i]["primary"]]))
            }
            if len(covered) > len(best):
                best = covered
        if not best:
            return None
        remaining -= best
        used += 1
    return used


def check(case):
    union = windows_for(case, {1, 2})
    final = windows_for(case, {2})
    full = [group for group in case["evidence_groups"] if group.get("coverage") == "full"]
    covered = [group for group in full if cases.group_complete(group, union)]
    if not covered:
        return False, "union candidates cannot cover any full group"
    feasible = [(group, min_windows(group, union)) for group in covered]
    feasible = [(group, count) for group, count in feasible if count is not None]
    if not feasible:
        return False, "no feasible window cover"
    group, count = min(feasible, key=lambda pair: pair[1])
    if count > 10:
        return False, f"best group needs {count} windows > 10"
    if any(cases.group_complete(group, final) for group in full):
        return False, "final round alone already covers a full group"
    return True, f"group {group['group_id'].split(':')[-1]} coverable by {count} windows"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dir", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    directory = Path(args.dir)
    manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    results = []
    for entry in manifest["cases"]:
        case = json.loads((directory / entry["case_path"]).read_text(encoding="utf-8"))
        ok, reason = check(case)
        results.append({"case_id": case["case_id"], "short": entry["short"], "ok": ok, "reason": reason})
    Path(args.out).write_text(json.dumps({"ok": sum(1 for r in results if r["ok"]), "total": len(results), "cases": results}, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    for row in results:
        print(("PASS" if row["ok"] else "BLOCK"), row["short"], row["reason"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


