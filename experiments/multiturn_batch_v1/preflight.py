#!/usr/bin/env python3
"""Validate a multi-turn batch before any method score is inspected.

Writes ``preflight.json`` with blocking problems, missing-input/label registries
and matrix-consistency checks. Exit code 1 if any case is blocked.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import cases


def matrix_issues(case: dict, matrix: dict) -> list[str]:
    issues: list[str] = []
    if matrix.get("schema") != cases.MATRIX_SCHEMA:
        issues.append(f"matrix schema must be {cases.MATRIX_SCHEMA}")
    if matrix.get("case_id") != case["case_id"]:
        issues.append("matrix case_id differs from case")
    final_round = matrix.get("final_round")
    if final_round not in (matrix.get("matrices") or {}):
        issues.append(f"final_round {final_round} has no matrix")
    candidate_ids = {candidate["canonical_id"] for candidate in case["candidates"]}
    rounds = {f"r{round_record['round']}": round_record for round_record in case["rounds"]}
    for round_key, round_record in rounds.items():
        if round_key not in (matrix.get("matrices") or {}):
            issues.append(f"matrix for {round_key} is missing")
            continue
        target = matrix["matrices"][round_key].get("target")
        if target != round_record["output"]["text"]:
            issues.append(f"{round_key} matrix target differs from output")
        for row in matrix["matrices"][round_key]["candidates"]:
            cid = row["canonical_id"]
            if cid.startswith("transmission:"):
                source_round = cid.split(":", 1)[1]
                if source_round not in rounds:
                    issues.append(f"{round_key} transmission points to missing {source_round}")
                elif row["text"] != rounds[source_round]["output"]["text"]:
                    issues.append(f"{round_key} transmission text differs from {source_round} output")
            elif cid not in candidate_ids:
                issues.append(f"{round_key} matrix row not in case candidates: {cid}")
    flat = matrix.get("matrices", {}).get("flat")
    if flat is None:
        issues.append("flat matrix is missing")
    else:
        if flat.get("target") != case["target"]["text"]:
            issues.append("flat matrix target differs from final target")
        flat_ids = {row["canonical_id"] for row in flat["candidates"]}
        if case.get("analysis_pool") == "union":
            expected = {
                cases.canonical_id(material["artifact_id"], material["start"], material["end"])
                for round_record in case["rounds"]
                for material in round_record["inputs"]
            }
        else:
            expected = candidate_ids
        missing = expected - flat_ids
        if missing:
            issues.append(f"flat matrix misses {len(missing)} candidates")
    return issues


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dir", required=True, help="batch directory with manifest.json")
    parser.add_argument("--out", default=None, help="preflight JSON (default <dir>/preflight.json)")
    args = parser.parse_args(argv)

    directory = Path(args.dir).resolve()
    manifest = cases.read_json(directory / "manifest.json")
    out_path = Path(args.out) if args.out else directory / "preflight.json"

    entries = []
    blocked = 0
    for row in manifest["cases"]:
        case = cases.read_json(directory / row["case_path"])
        matrix = cases.read_json(directory / row["matrix_path"])
        issues = cases.validate_case(case) + matrix_issues(case, matrix)
        registry = cases.missing_registry(case)
        status = "blocked" if issues else ("incomplete" if registry["missing_inputs"] or registry["missing_labels"] else "ok")
        if issues:
            blocked += 1
        entries.append(
            {
                "short": row["short"],
                "case_id": case["case_id"],
                "trajectory_id": case["trajectory_id"],
                "split": case["split"],
                "status": status,
                "issues": issues,
                "registry": registry,
                "rounds": len(case["rounds"]),
                "candidates": len(case["candidates"]),
                "evidence_groups": len(case["evidence_groups"]),
            }
        )

    payload = {
        "schema": "memoryflow.multiturn_batch.preflight.v1",
        "cases": entries,
        "trajectory_split_issues": [],
        "totals": {
            "cases": len(entries),
            "ok": sum(1 for entry in entries if entry["status"] == "ok"),
            "incomplete": sum(1 for entry in entries if entry["status"] == "incomplete"),
            "blocked": blocked,
        },
    }
    by_trajectory: dict[str, set[str]] = {}
    for entry in entries:
        by_trajectory.setdefault(entry["trajectory_id"], set()).add(entry["split"])
    for trajectory, splits in sorted(by_trajectory.items()):
        if len(splits) > 1:
            payload["trajectory_split_issues"].append(
                {"trajectory_id": trajectory, "splits": sorted(splits)}
            )
    if payload["trajectory_split_issues"]:
        blocked += len(payload["trajectory_split_issues"])
        payload["totals"]["blocked"] = blocked
    cases.write_json(out_path, payload)
    print(json.dumps({"out": str(out_path), "totals": payload["totals"],
                      "statuses": {entry["short"]: entry["status"] for entry in entries},
                      "trajectory_split_issues": payload["trajectory_split_issues"]},
                     ensure_ascii=False, indent=1))
    return 1 if blocked else 0


if __name__ == "__main__":
    raise SystemExit(main())
