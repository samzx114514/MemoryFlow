"""Offline tests for the multi-turn batch format, methods and metrics."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
PACKAGE = HERE.parent
sys.path.insert(0, str(PACKAGE))

import cases  # noqa: E402
import methods  # noqa: E402
import metrics  # noqa: E402

ALPHA = "alpha evidence"
BETA = "beta evidence"
ALPHA_ID = f"art:a#0-{len(ALPHA)}"
BETA_ID = f"art:b#0-{len(BETA)}"


def material(unit, artifact, start, end, text, role, slot="material", index=1):
    return {
        "unit_id": unit, "artifact_id": artifact, "start": start, "end": end, "text": text,
        "role": role, "position": {"slot": slot, "index": index},
    }


def make_case() -> dict:
    rounds = [
        {
            "round": 1,
            "question": "q1",
            "inputs": [material("a", "art:a", 0, len(ALPHA), ALPHA, "evidence_a", index=1)],
            "output": {"text": "round one output", "sha256": cases.sha256_text("round one output"), "origin": "model_output"},
            "transmission": [],
        },
        {
            "round": 2,
            "question": "q2",
            "inputs": [material("b", "art:b", 0, len(BETA), BETA, "evidence_b", index=1)],
            "output": {"text": "round two output", "sha256": cases.sha256_text("round two output"), "origin": "model_output"},
            "transmission": [
                {"from_round": 1, "unit_id": "round1_output", "text": "round one output",
                 "sha256": cases.sha256_text("round one output"),
                 "position": {"slot": "earlier_finding", "index": 0}}
            ],
        },
    ]
    return {
        "schema": cases.SCHEMA,
        "case_id": "traj:selected_01",
        "trajectory_id": "traj",
        "trajectory_case": "case_x",
        "split": "dev",
        "record_type": "controlled",
        "control": None,
        "target": {"text": "round two output", "sha256": cases.sha256_text("round two output"),
                   "origin": "controlled_output",
                   "artifact_id": None, "start": None, "end": None,
                   "original_target": {"text": "orig", "artifact_id": "art:t", "start": 0, "end": 4}},
        "rounds": rounds,
        "candidates": cases.build_candidate_pool(rounds),
        "evidence_groups": [
            {
                "group_id": "g1",
                "coverage": "full",
                "items": [
                    {"primary": {"artifact_id": "art:a", "start": 0, "end": len(ALPHA), "text": ALPHA},
                     "alternatives": [{"artifact_id": "art:a", "start": 0, "end": len(ALPHA), "text": ALPHA}]},
                    {"primary": {"artifact_id": "art:b", "start": 0, "end": len(BETA), "text": BETA},
                     "alternatives": [{"artifact_id": "art:b", "start": 0, "end": len(BETA), "text": BETA}]},
                ],
            }
        ],
        "labels": {"A": [ALPHA_ID], "B": [BETA_ID]},
        "provenance": {"note": "test"},
    }


def make_matrices() -> dict:
    return {
        "schema": cases.MATRIX_SCHEMA,
        "case_id": "traj:selected_01",
        "final_round": "r2",
        "hop_budget": 5,
        "final_budget": 10,
        "matrices": {
            "r1": {"target": "round one output",
                   "candidates": [{"canonical_id": ALPHA_ID, "text": ALPHA, "score": 0.9}]},
            "r2": {"target": "round two output",
                   "candidates": [{"canonical_id": "transmission:r1", "text": "round one output", "score": 0.8},
                                  {"canonical_id": BETA_ID, "text": BETA, "score": 0.5}]},
            "flat": {"target": "round two output",
                     "candidates": [{"canonical_id": ALPHA_ID, "text": ALPHA, "score": 0.6},
                                    {"canonical_id": BETA_ID, "text": BETA, "score": 0.4}]},
        },
        "source": {},
    }


class CaseTest(unittest.TestCase):
    def test_valid_case(self) -> None:
        case = make_case()
        self.assertEqual(cases.validate_case(case), [])
        self.assertEqual(len(case["candidates"]), 2)
        self.assertTrue(all(candidate["occurrences"] for candidate in case["candidates"]))

    def test_missing_target_is_blocking(self) -> None:
        case = make_case()
        case["target"]["text"] = ""
        self.assertTrue(any("target.text" in issue for issue in cases.validate_case(case)))

    def test_missing_transmission_is_registered(self) -> None:
        case = make_case()
        case["rounds"][1]["transmission"] = []
        self.assertEqual(cases.validate_case(case), [])
        registry = cases.missing_registry(case)
        self.assertIn("round2:transmission", registry["missing_inputs"])

    def test_shared_evidence_merges_positions(self) -> None:
        case = make_case()
        case["rounds"][1]["inputs"].append(
            material("a2", "art:a", 0, len(ALPHA), ALPHA, "context", index=2)
        )
        pool = cases.build_candidate_pool(case["rounds"])
        alpha = [candidate for candidate in pool if candidate["canonical_id"] == ALPHA_ID][0]
        self.assertEqual([occurrence["round"] for occurrence in alpha["occurrences"]], [1, 2])


class MethodTest(unittest.TestCase):
    def test_last_round_excludes_transmission(self) -> None:
        ranked = methods.rank_last_round(make_case(), make_matrices(), 10)
        self.assertEqual(ranked, [BETA_ID])

    def test_memoryflow_merges_direct_and_indirect(self) -> None:
        ranked, hops = methods.rank_memoryflow(make_case(), make_matrices(), 10, 5)
        self.assertEqual(ranked[0], ALPHA_ID)
        self.assertEqual(ranked[1], BETA_ID)
        self.assertEqual(len(hops), 2)
        self.assertAlmostEqual(hops[1]["factor"], 0.8)

    def test_flat_head_ranking(self) -> None:
        ranked = methods.rank_head_full_history(make_case(), make_matrices(), 10)
        self.assertEqual(ranked[0], ALPHA_ID)

    def test_metrics_complete(self) -> None:
        case = make_case()
        output = methods.run(case, make_matrices(), 10, 5)
        row = metrics.evaluate_case(case, output)
        memory = row["methods"]["memoryflow"]
        self.assertTrue(memory["hit_at_3"])
        self.assertTrue(memory["complete_at_5"])
        self.assertEqual(memory["complete_rank"], 2)
        self.assertEqual(memory["label_ranks"], {"A": 1, "B": 2})
        last = row["methods"]["last_round"]
        self.assertTrue(last["hit_at_3"])
        self.assertFalse(last["complete_at_5"])

    def test_paired_counts(self) -> None:
        case = make_case()
        output = methods.run(case, make_matrices(), 10, 5)
        row = metrics.evaluate_case(case, output)
        summary = metrics.summarize([row], 10)
        self.assertEqual(summary["paired_main"]["last_round"]["complete_rank"], {"win": 1, "tie": 0, "loss": 0})


if __name__ == "__main__":
    unittest.main()
