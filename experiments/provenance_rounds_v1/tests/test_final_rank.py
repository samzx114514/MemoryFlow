"""Offline checks for the final-original ranking (no model, no GPU)."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
PACKAGE = HERE.parent
sys.path.insert(0, str(PACKAGE))

import final_rank  # noqa: E402


class MergePathsTest(unittest.TestCase):
    def test_direct_plus_indirect_and_text_dedup(self) -> None:
        frozen = {
            "rounds": [
                {
                    "materials": [
                        {"unit_id": "r1a", "text": "alpha evidence", "role": "evidence_a"},
                        {"unit_id": "shared", "text": "shared passage", "role": "distractor"},
                    ]
                },
                {
                    "materials": [
                        {"unit_id": "shared", "text": "shared passage", "role": "distractor"},
                        {"unit_id": "r2b", "text": "beta evidence", "role": "evidence_b"},
                    ]
                },
            ]
        }
        scores = {
            "matrices": {
                "m1": {
                    "candidates": [
                        {"id": "r1a", "text": "alpha evidence", "score": 0.5},
                        {"id": "shared", "text": "shared passage", "score": 0.2},
                    ]
                },
                "m2": {
                    "candidates": [
                        {"id": "conclusion:r1", "text": "conclusion", "score": 0.4},
                        {"id": "shared", "text": "shared passage", "score": 0.1},
                        {"id": "r2b", "text": "beta evidence", "score": 0.3},
                    ]
                },
            }
        }
        merged = final_rank.merge_paths(frozen, scores)
        rows = {row["text"]: row for row in merged["rows"]}
        self.assertAlmostEqual(merged["s_c"], 0.4)
        self.assertAlmostEqual(rows["alpha evidence"]["score"], 0.4 * 0.5)
        self.assertAlmostEqual(rows["alpha evidence"]["direct"], 0.0)
        self.assertAlmostEqual(rows["alpha evidence"]["indirect"], 0.4 * 0.5)
        self.assertAlmostEqual(rows["beta evidence"]["score"], 0.3)
        self.assertAlmostEqual(rows["beta evidence"]["direct"], 0.3)
        self.assertAlmostEqual(rows["shared passage"]["score"], 0.1 + 0.4 * 0.2)
        self.assertEqual(rows["shared passage"]["units"], ["shared"])

    def test_ranking_order_and_budget(self) -> None:
        rows = [
            {"units": ["u1"], "roles": ["x"], "text": "a", "score": 0.1, "max": 0.1},
            {"units": ["u2"], "roles": ["x"], "text": "b", "score": 0.3, "max": 0.3},
            {"units": ["u3"], "roles": ["x"], "text": "c", "score": 0.2, "max": 0.2},
        ]
        ranked = final_rank.grouped_ranking(rows, 2)
        self.assertEqual([row["units"][0] for row in ranked], ["u2", "u3"])
        self.assertEqual([row["rank"] for row in ranked], [1, 2])


if __name__ == "__main__":
    unittest.main()
