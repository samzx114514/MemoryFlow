import unittest

from .intake import fragment, review_record, unique_targets


class IntakeTest(unittest.TestCase):
    def setUp(self):
        self.log = [{"action": "tool", "content": "The value is 5."},
                    {"action": "agent", "content": "Earlier value: 5."},
                    {"action": "tool", "content": "New value: 6."},
                    {"action": "agent", "content": "It increased."}]
        self.raw = {"sample_id": "sample", "dataset": "test", "memory_stack_log": self.log}
        self.target = {"event": 3, "start": 0, "end": 13, "text": "It increased."}

    def test_bad_label_and_future_evidence_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "does not match"):
            fragment(self.log, "/memory_stack_log/0/content", {"start": 0, "end": 3, "text": "bad"})
        f = fragment(self.log, "/memory_stack_log/3/content", self.target)
        with self.assertRaisesRegex(ValueError, "future evidence"):
            review_record("x", "old47", self.raw, self.target, [{"items": [{"alternatives": [f]}]}])

    def test_generated_source_needs_review_and_duplicate_target_counts_once(self):
        f = fragment(self.log, "/memory_stack_log/1/content", {"start": 0, "end": 17, "text": "Earlier value: 5."})
        r = review_record("x", "old47", self.raw, self.target, [{"items": [{"alternatives": [f]}]}])
        self.assertEqual(r["generated_evidence_events"], [1])
        self.assertFalse(r["complete_from_latest_tool_batch"])
        self.assertEqual(r["chain_review"], "pending_semantic_review")
        rows, duplicate = unique_targets([r, {**r, "legacy_id": "y"}])
        self.assertEqual(len(rows), 1)
        self.assertEqual(duplicate, [{"legacy_id": "y", "same_as": "x"}])

    def test_decoded_source_keeps_exact_offsets(self):
        log = [{"action": "tool", "content": '{"results":[{"content":"Alpha: 5."}]}'}]
        f = fragment(log, "/memory_stack_log/0/content#decoded/results/0/content",
                     {"start": 7, "end": 8, "text": "5"})
        self.assertEqual(f["location"], "/memory_stack_log/0/content#/results/0/content")

    def test_tool_query_is_recorded_generated_content(self):
        log = [{"action": "agent", "tool_calls": [{"args": {"query": "Alpha"}}]}]
        f = fragment(log, "/memory_stack_log/0/tool_calls/0/args/query",
                     {"start": 0, "end": 5, "text": "Alpha"})
        self.assertEqual(f["recorded_action"], "agent")


if __name__ == "__main__":
    unittest.main()
