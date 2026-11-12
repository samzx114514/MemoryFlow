import unittest

from .metrics import evaluate


class MaterialMetricsTest(unittest.TestCase):
    def test_combination_needs_both_items_and_alternatives_do_not_inflate_recall(self):
        def span(artifact, start, end, text):
            return {"artifact_id": artifact, "start": start, "end": end, "text": text}
        a, b = span("a", 0, 3, "one"), span("b", 0, 3, "two")
        case = {"candidates": [{"canonical_id": "a", **a}, {"canonical_id": "b", **b}],
                "evidence_groups": [{"items": [{"alternatives": [a, a]}, {"alternatives": [b]}]}]}
        half = evaluate(case, ["a"])
        self.assertEqual(half["citation_precision"], 1)
        self.assertEqual(half["evidence_recall"], .5)
        self.assertEqual(half["complete_at_10"], 0)
        self.assertEqual(evaluate(case, ["a", "b"])["complete_at_10"], 1)

    def test_unknown_return_uses_budget_and_incomplete_label_stays_unscored(self):
        case = {"candidates": [], "evidence_groups": []}
        self.assertEqual(evaluate(case, ["missing"]), {"status": "incomplete_material_support"})


if __name__ == "__main__":
    unittest.main()
