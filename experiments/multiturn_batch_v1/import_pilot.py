#!/usr/bin/env python3
"""Import genmem63 pilot-v4 targets into the unified multi-turn format.

The pilot archive and the frozen run inputs provide the target window, the full
candidate pool and the reference evidence groups. The two rounds themselves are
controlled constructions from a recipe: fixed questions, fixed intermediate
conclusions, fixed final target text and a fixed material selection.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import cases

WINDOW_RE = re.compile(r"^(?P<artifact>.+):line:(?P<start>\d+):(?P<end>\d+)$")


def parse_window(window_id: str) -> dict:
    match = WINDOW_RE.match(window_id)
    if not match:
        raise SystemExit(f"cannot parse window id: {window_id}")
    return {
        "window_id": window_id,
        "artifact_id": match.group("artifact"),
        "start": int(match.group("start")),
        "end": int(match.group("end")),
        "canonical_id": cases.canonical_id(match.group("artifact"), int(match.group("start")), int(match.group("end"))),
    }


def material(record: dict, source: dict, role: str, index: int) -> dict:
    return {
        "unit_id": record["window_id"],
        "artifact_id": record["artifact_id"],
        "start": record["start"],
        "end": record["end"],
        "text": source["text"],
        "role": role,
        "position": {"slot": "material", "index": index},
    }


def build_case(recipe: dict, records: dict, reference: dict, dataset: dict) -> dict:
    case_id = recipe["case_id"]
    record = records[case_id]
    sources = {source["id"]: source for source in record["sources"]}
    truth = {target["id"]: target for target in dataset["targets"]}[case_id]
    unit = truth["unit"]
    target_text = unit["text"]

    rounds = []
    used: dict[str, list[dict]] = {}
    for round_index, round_recipe in enumerate(recipe["rounds"], start=1):
        materials = []
        for index, item in enumerate(round_recipe["materials"], start=1):
            window = parse_window(item["window"])
            if window["window_id"] not in sources:
                raise SystemExit(f"{case_id}: unknown window {window['window_id']}")
            materials.append(material(window, sources[window["window_id"]], item["role"], index))
            used.setdefault(window["canonical_id"], []).append(
                {
                    "round": round_index,
                    "unit_id": window["window_id"],
                    "role": item["role"],
                    "position": {"slot": "material", "index": index},
                }
            )
        record_round = {
            "round": round_index,
            "question": round_recipe["question"],
            "inputs": materials,
            "output": {
                "text": round_recipe["output"],
                "sha256": cases.sha256_text(round_recipe["output"]),
                "origin": round_recipe.get("origin", "controlled_output"),
            },
            "transmission": [],
        }
        if round_index > 1:
            previous = rounds[-1]["output"]
            record_round["transmission"].append(
                {
                    "from_round": round_index - 1,
                    "unit_id": f"round{round_index - 1}_output",
                    "text": previous["text"],
                    "sha256": previous["sha256"],
                    "position": {"slot": "earlier_finding", "index": 0},
                }
            )
        rounds.append(record_round)

    candidates = []
    for source in record["sources"]:
        window = parse_window(source["id"])
        candidates.append(
            {
                "canonical_id": window["canonical_id"],
                "artifact_id": window["artifact_id"],
                "start": window["start"],
                "end": window["end"],
                "text": source["text"],
                "occurrences": used.get(window["canonical_id"], []),
                "pool_only": window["canonical_id"] not in used,
            }
        )

    reference_target = reference["targets"][case_id]
    groups = []
    for group in reference_target["groups"]:
        items = []
        for window_id in group["window_ids"]:
            window = parse_window(window_id)
            items.append(
                {
                    "primary": {
                        "artifact_id": window["artifact_id"],
                        "start": window["start"],
                        "end": window["end"],
                        "text": sources[window_id]["text"],
                    },
                    "alternatives": [
                        {
                            "artifact_id": window["artifact_id"],
                            "start": window["start"],
                            "end": window["end"],
                            "text": sources[window_id]["text"],
                        }
                    ],
                }
            )
        groups.append({"group_id": group["group_id"], "coverage": group["coverage"], "items": items})

    excluded = []
    for group in truth.get("explanation_groups") or []:
        if (group.get("support") or {}).get("role") != "prior_state_not_positive_support":
            continue
        windows = []
        for window_id in group.get("candidate_window_ids") or []:
            window = parse_window(window_id)
            windows.append(
                {
                    "artifact_id": window["artifact_id"],
                    "start": window["start"],
                    "end": window["end"],
                    "text": sources[window_id]["text"],
                }
            )
        excluded.append(
            {
                "group_id": group["id"],
                "role": group["support"]["role"],
                "coverage": group["support"].get("coverage"),
                "reason_zh": group["support"].get("reason_zh"),
                "windows": windows,
            }
        )

    case = {
        "schema": cases.SCHEMA,
        "case_id": case_id,
        "trajectory_id": recipe["trajectory_id"],
        "trajectory_case": recipe["trajectory_case"],
        "split": "dev",
        "record_type": "controlled",
        "control": recipe.get("control"),
        "target": {
            "text": target_text,
            "sha256": cases.sha256_text(target_text),
            "origin": "recorded_target",
            "artifact_id": unit["artifact_id"],
            "start": unit["start"],
            "end": unit["end"],
            "original_target": {
                "text": target_text,
                "artifact_id": unit["artifact_id"],
                "start": unit["start"],
                "end": unit["end"],
                "event_index": unit.get("event_index"),
                "group_id": None,
            },
        },
        "rounds": rounds,
        "candidates": candidates,
        "evidence_groups": groups,
        "excluded_groups": excluded,
        "labels": {
            label: [parse_window(window_id)["canonical_id"] for window_id in recipe["labels"][label]]
            for label in ("A", "B")
        },
        "provenance": {
            "archive": recipe["archive"],
            "archive_sha256": recipe.get("archive_sha256"),
            "records_sha256": recipe.get("records_sha256"),
            "reference_sha256": recipe.get("reference_sha256"),
            "dataset_sha256": recipe.get("dataset_sha256"),
            "target_window": unit.get("candidate_window_ids"),
            "note": recipe["note"],
        },
    }
    return case


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--records", required=True)
    parser.add_argument("--reference", required=True)
    parser.add_argument("--dataset", required=True)
    parser.add_argument("--recipe", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args(argv)

    records = {row["id"]: row for row in cases.read_json(args.records)}
    reference = cases.read_json(args.reference)
    dataset = cases.read_json(args.dataset)
    recipe_path = Path(args.recipe)
    if recipe_path.is_dir():
        recipes = [cases.read_json(path) for path in sorted(recipe_path.glob("*.json"))]
    else:
        recipes = cases.read_json(recipe_path)
        if isinstance(recipes, dict):
            recipes = [recipes]

    out = Path(args.out)
    case_dir = out / "cases"
    case_dir.mkdir(parents=True, exist_ok=True)
    index = []
    for recipe in recipes:
        case = build_case(recipe, records, reference, dataset)
        issues = cases.validate_case(case)
        if issues:
            raise SystemExit(f"{recipe['case_id']}: validation failed: {issues}")
        registry = cases.missing_registry(case)
        slug = recipe["case_id"].lower()
        path = case_dir / f"{slug}.json"
        cases.write_json(path, case)
        index.append(
            {
                "short": recipe["case_id"],
                "case_id": case["case_id"],
                "trajectory_id": case["trajectory_id"],
                "trajectory_case": case["trajectory_case"],
                "split": case["split"],
                "record_type": case["record_type"],
                "control": case["control"],
                "rounds": len(case["rounds"]),
                "candidates": len(case["candidates"]),
                "evidence_groups": len(case["evidence_groups"]),
                "excluded_groups": len(case.get("excluded_groups") or []),
                "case_path": path.relative_to(out).as_posix(),
                "matrix_path": f"matrices/{slug}.json",
                "case_sha256": cases.case_hash(case),
                "registry": registry,
            }
        )

    manifest = {
        "schema": "memoryflow.multiturn_batch.manifest.v1",
        "created": "2026-11-06",
        "final_budget": cases.FINAL_BUDGET,
        "hop_budget": cases.HOP_BUDGET,
        "cases": index,
        "totals": {
            "cases": len(index),
            "controlled": sum(1 for row in index if row["record_type"] == "controlled"),
            "real_request": sum(1 for row in index if row["record_type"] == "real_request"),
            "dev": sum(1 for row in index if row["split"] == "dev"),
            "eval": sum(1 for row in index if row["split"] == "eval"),
            "controls": sum(1 for row in index if row["control"]),
        },
    }
    cases.write_json(out / "manifest.json", manifest)
    print(json.dumps({"out": str(out), "totals": manifest["totals"],
                      "cases": [row["short"] for row in index]}, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
