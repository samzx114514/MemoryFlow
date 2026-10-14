from __future__ import annotations

import unittest

from memoryflow.lc_sent15_fmean import assert_allowed_path, rank_scores, single_positive_metrics


class LCSent15FmeanTest(unittest.TestCase):
    def test_tie_is_source_id_ascending(self) -> None:
        self.assertEqual(rank_scores({"source_z": 0.0, "source_a": 0.0}), ["source_a", "source_z"])

    def test_metrics_single_positive(self) -> None:
        result = single_positive_metrics([1, 2])
        self.assertEqual(result["hit_at_1"], 0.5)
        self.assertEqual(result["mrr"], 0.75)

    def test_forbidden_paths_are_blocked(self) -> None:
        for value in ("/x/blind/a", "/x/Reserve/a", "/x/multi_positive/a", "/x/mixed_catalog/a"):
            with self.assertRaises(ValueError):
                assert_allowed_path(value)


if __name__ == "__main__":
    unittest.main()
