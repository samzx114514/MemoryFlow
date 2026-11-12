import unittest

from .evaluate import aggregate_answers, answer_metrics, evaluation_jobs, metrics


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

    def test_task_macro_does_not_overweight_tasks_with_more_calls(self):
        jobs = {key: {"task_id": "taskA" if key != "b" else "taskB"} for key in ("a1", "a2", "a3", "b")}
        answers = {("mf", "nba", key): [metrics(["alternative"] if key != "b" else ["wrong"], self.target)]
                   for key in jobs}
        table, tasks = aggregate_answers(answers, jobs)
        self.assertEqual(len(tasks), 2)
        self.assertEqual(table[0]["calls_with_claims"], 4)
        self.assertEqual(table[0]["precision"], .5)
        self.assertEqual(table[0]["recall"], .5)
        self.assertEqual(table[0]["f1"], .5)

    def test_benchmark_table_requires_all_frozen_calls_without_duplicates(self):
        jobs = [{"id": "a", "benchmark": "nba"}, {"id": "b", "benchmark": "nba"},
                {"id": "c", "benchmark": "clause"}]
        calls = [{"id": "a"}, {"id": "b"}]
        self.assertEqual(set(evaluation_jobs(jobs, calls, "nba")), {"a", "b"})
        for incomplete in (calls[:1], calls + calls[:1], calls + [{"id": "c"}]):
            with self.assertRaises(ValueError):
                evaluation_jobs(jobs, incomplete, "nba")


if __name__ == "__main__":
    unittest.main()
