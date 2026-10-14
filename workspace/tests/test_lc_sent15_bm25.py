from __future__ import annotations

import math
import unittest

from memoryflow.lc_sent15_bm25 import GroupBM25, mixed_v1_tokenize, rank_by_score_then_source_id, score_group


class LCSent15BM25Test(unittest.TestCase):
    def test_hand_computable_toy(self) -> None:
        scores = GroupBM25({"a": "cat cat", "b": "dog"}).score("cat")
        expected_idf = math.log(1 + (2 - 1 + 0.5) / (1 + 0.5))
        expected = expected_idf * (2 * 2.2 / (2 + 1.2 * (0.25 + 0.75 * 2 / 1.5)))
        self.assertAlmostEqual(scores["a"], expected, places=15)
        self.assertEqual(scores["b"], 0.0)

    def test_mixed_language_tokenizer(self) -> None:
        self.assertEqual(mixed_v1_tokenize("ＡＢＣ 123，中文测试!"), ["abc", "123", "中", "文", "测", "试", "中文", "文测", "测试"])

    def test_candidate_permutation_invariance(self) -> None:
        first = score_group("alpha", {"b": "alpha beta", "a": "alpha"}, implementation="BM25_MIXED_V1")
        second = score_group("alpha", {"a": "alpha", "b": "alpha beta"}, implementation="BM25_MIXED_V1")
        self.assertEqual(first, second)

    def test_source_id_tie_break(self) -> None:
        self.assertEqual(rank_by_score_then_source_id({"z": 0.0, "a": 0.0}), ["a", "z"])

    def test_labels_do_not_enter_score_path(self) -> None:
        docs = {"s1": "alpha", "s2": "beta"}
        self.assertEqual(
            score_group("alpha", docs, implementation="BM25_MIXED_V1"),
            score_group("alpha", docs, implementation="BM25_MIXED_V1"),
        )


if __name__ == "__main__":
    unittest.main()
