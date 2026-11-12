import unittest

from .replay import recorded_calls


class RecordedCallsTest(unittest.TestCase):
    def test_full_prefix_and_full_output_keep_tools_and_exclude_future(self):
        log = [{"action": "user", "content": "question"},
               {"action": "agent", "content": "finding", "tool_calls": [{"id": "a", "name": "search", "args": {"query": "value"}}]},
               {"action": "tool", "content": "original evidence", "tool_call_id": "a"},
               {"action": "agent", "content": "result. second sentence."},
               {"action": "tool", "content": "future evidence"}]
        calls = recorded_calls(log, 3)
        self.assertEqual(len(calls), 2)
        self.assertEqual([m["content"] for m in calls[1]["request"]["messages"]], ["question", "finding", "original evidence"])
        self.assertEqual(calls[1]["output"], "result. second sentence.")
        self.assertIn('"query": "value"', calls[0]["output"])
        self.assertNotIn("future evidence", str(calls))


if __name__ == "__main__":
    unittest.main()
