#!/usr/bin/env python3
"""Import the three accepted dev cases into the unified multi-turn format.

Inputs are the frozen artifacts of ``experiments/provenance_rounds_v1``:
spec, frozen rounds, saved matrices and the contextual64_v4 ground truth.
The import never recomputes scores; it only maps saved unit ids to canonical
(artifact, start, end) identities and writes a case + matrix file per target.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import cases


def material_record(material: dict, index: int) -> dict:
    return {
        "unit_id": material["unit_id"],
        "artifact_id": material["artifact_id"],
        "start": material["start"],
        "end": material["end"],
        "text": material["text"],
        "role": material["role"],
        "position": {"slot": "material", "index": index},
    }


def build_case(sample: dict, spec: dict, frozen: dict, gt_entry: dict) -> dict:
    rounds = []
    for index, round_record in enumerate(frozen["rounds"], start=1):
        record = {
            "round": index,
            "question": round_record["question"],
            "inputs": [material_record(material, position) for position, material in enumerate(round_record["materials"], start=1)],
            "output": {
                "text": round_record["answer"],
                "sha256": cases.sha256_text(round_record["answer"]),
                "origin": "model_output",
            },
            "transmission": [],
        }
        if index > 1:
            previous = frozen["rounds"][index - 2]
            record["transmission"].append(
                {
                    "from_round": index - 1,
                    "unit_id": f"round{index - 1}_output",
                    "text": previous["answer"],
                    "sha256": cases.sha256_text(previous["answer"]),
                    "position": {"slot": "earlier_finding", "index": 0},
                }
            )
        rounds.append(record)

    target_text = frozen["rounds"][-1]["answer"]
    target_original = gt_entry["target"]
    case = {
        "schema": cases.SCHEMA,
        "case_id": spec["source"]["target_id"],
        "trajectory_id": spec["source"]["target_id"].split(":")[0],
        "trajectory_case": spec["source"]["case"],
        "split": "dev",
        "record_type": "controlled",
        "control": sample.get("control"),
        "target": {
            "text": target_text,
            "sha256": cases.sha256_text(target_text),
            "origin": "controlled_output",
            "artifact_id": None,
            "start": None,
            "end": None,
            "original_target": {
                "text": target_original["text"],
                "artifact_id": target_original["artifact_id"],
                "start": target_original["start"],
                "end": target_original["end"],
                "event_index": target_original.get("event_index"),
                "group_id": spec["source"]["group_id"],
            },
        },
        "rounds": rounds,
        "candidates": cases.build_candidate_pool(rounds),
        "evidence_groups": cases.evidence_groups_from_truth(gt_entry),
        "labels": {
            label: [cases.canonical_id(item["artifact_id"], item["start"], item["end"]) for item in spec["evidence"][label]]
            for label in ("A", "B")
        },
        "provenance": {
            "archive": spec["source"].get("archive_path"),
            "archive_sha256": spec["source"].get("archive_sha256"),
            "spec_sha256": spec.get("spec_sha256"),
            "frozen_sha256": frozen.get("frozen_sha256"),
            "label_member": spec["source"]["label_member"],
            "note": "controlled multi-round reconstruction; not an original request snapshot",
        },
    }
    return case


def build_matrices(sample: dict, spec: dict, frozen: dict, scores: dict) -> dict:
    unit_to_canonical = {}
    for round_record in frozen["rounds"]:
        for material in round_record["materials"]:
            unit_to_canonical[material["unit_id"]] = cases.canonical_id(
                material["artifact_id"], material["start"], material["end"]
            )

    def rows(matrix_name: str, include_transmission: bool) -> list[dict]:
        output = []
        for row in scores["matrices"][matrix_name]["candidates"]:
            if row["id"] == "conclusion:r1":
                if not include_transmission:
                    continue
                output.append(
                    {
                        "canonical_id": "transmission:r1",
                        "text": frozen["rounds"][0]["answer"],
                        "score": float(row["score"]),
                    }
                )
                continue
            if row["id"] not in unit_to_canonical:
                raise SystemExit(f"matrix row without canonical unit: {row['id']}")
            output.append(
                {
                    "canonical_id": unit_to_canonical[row["id"]],
                    "text": row["text"],
                    "score": float(row["score"]),
                }
            )
        return output

    return {
        "schema": cases.MATRIX_SCHEMA,
        "case_id": spec["source"]["target_id"],
        "final_round": "r2",
        "hop_budget": cases.HOP_BUDGET,
        "final_budget": cases.FINAL_BUDGET,
        "matrices": {
            "r1": {"target": frozen["rounds"][0]["answer"], "candidates": rows("m1", False)},
            "r2": {"target": frozen["rounds"][1]["answer"], "candidates": rows("m2", True)},
            "flat": {"target": frozen["rounds"][1]["answer"], "candidates": rows("mflat", False)},
        },
        "source": {
            "scores_path": sample["scores"],
            "scores_sha256": cases.sha256_file(sample["scores"]),
            "matrix_keys": {"r1": "m1", "r2": "m2", "flat": "mflat"},
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True, help="provenance_rounds_v1 report manifest")
    parser.add_argument("--subset", required=True, help="extracted contextual64_v4 root")
    parser.add_argument("--out", required=True, help="output directory for cases/ and matrices/")
    args = parser.parse_args(argv)

    manifest = cases.read_json(args.manifest)
    subset = Path(args.subset)
    out = Path(args.out)
    case_dir = out / "cases"
    matrix_dir = out / "matrices"
    case_dir.mkdir(parents=True, exist_ok=True)
    matrix_dir.mkdir(parents=True, exist_ok=True)

    index = []
    for sample in manifest["samples"]:
        spec = cases.read_json(sample["spec"])
        frozen = cases.read_json(sample["frozen"])
        scores = cases.read_json(sample["scores"])
        gt = cases.read_json(subset / f"contextual64_v4/{spec['source']['case']}/ground_truth.json")
        gt_entry = [row for row in gt if row["target_id"] == spec["source"]["target_id"]][0]

        control = "final_round_sufficient" if sample["short"] == "T06" else None
        sample = dict(sample)
        sample["control"] = control
        case = build_case(sample, spec, frozen, gt_entry)
        issues = cases.validate_case(case)
        if issues:
            raise SystemExit(f"{sample['short']}: validation failed: {issues}")
        registry = cases.missing_registry(case)

        slug = sample["short"].lower()
        case_path = case_dir / f"{slug}.json"
        matrix_path = matrix_dir / f"{slug}.json"
        cases.write_json(case_path, case)
        matrix = build_matrices(sample, spec, frozen, scores)
        cases.write_json(matrix_path, matrix)

        index.append(
            {
                "short": sample["short"],
                "case_id": case["case_id"],
                "trajectory_id": case["trajectory_id"],
                "trajectory_case": case["trajectory_case"],
                "split": case["split"],
                "record_type": case["record_type"],
                "control": case["control"],
                "rounds": len(case["rounds"]),
                "candidates": len(case["candidates"]),
                "evidence_groups": len(case["evidence_groups"]),
                "case_path": case_path.relative_to(out).as_posix(),
                "matrix_path": matrix_path.relative_to(out).as_posix(),
                "case_sha256": cases.case_hash(case),
                "matrix_sha256": cases.sha256_file(matrix_path),
                "registry": registry,
            }
        )

    manifest_out = {
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
    cases.write_json(out / "manifest.json", manifest_out)
    print(json.dumps({"out": str(out), "totals": manifest_out["totals"],
                      "cases": [row["short"] for row in index]}, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
