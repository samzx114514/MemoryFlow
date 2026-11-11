import unittest

from .evaluate import answer_metrics, metrics


class EvidenceScoringTest(unittest.TestCase):
    def setUp(self):
        self.target = {"supporting_sources": ["a", "b", "alternative"],
                       "complete_support_sets": [["a", "b"], ["alternative"]]}

    def test_multiple_evidence_partial_and_alternative(self):
        self.assertEqual(metrics(["a"], self.target)["recall"], .5)
        self.assertEqual(metrics(["a", "b"], self.target)["recall"], 1)
        self.assertEqual(metrics(["alternative"], self.target)["recall"], 1)

    def test_wrong_and_missing_citations(self):
        self.assertEqual(metrics(["wrong"], self.target)["recall"], 0)
        self.assertEqual(metrics([], self.target)["covered"], 0)
        self.assertEqual(metrics(["wrong"], self.target)["covered"], 1)

    def test_precision_counts_returned_citations_before_answer_f1(self):
        result = answer_metrics([metrics(["alternative"], self.target),
                                 metrics(["a", "wrong", "wrong2"], self.target)])
        self.assertEqual(result["precision"], .5)
        self.assertEqual(result["recall"], .75)
        self.assertAlmostEqual(result["f1"], .6)

    def test_empty_complete_set_is_not_vacuous_success(self):
        with self.assertRaises(ValueError):
            metrics([], {"supporting_sources": [], "complete_support_sets": [[]]})


if __name__ == "__main__":
    unittest.main()
