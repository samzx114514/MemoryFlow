import json
import unittest
import tempfile
from pathlib import Path

from efficiency_task import claim_span, write_failure


class DeliveredClaimSpanTest(unittest.TestCase):
    def test_analysis_failure_keeps_native_success_without_inventing_ready_time(self):
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder)
            payload = {"task_started": 10, "targets": [{"claim": "result"}], "native_completion": ["completed"]}
            result = write_failure(output, payload, [], {"type": "HTTPError"}, 25, "full", "case")
            self.assertFalse(result["completed"])
            self.assertTrue(result["native_completed"])
            self.assertIsNone(result["tail_seconds"])
            self.assertEqual(result["task_total_seconds"], 15)

    def test_plain_label_and_missing_claim(self):
        self.assertEqual(claim_span("Reversal", "Reversal"),(0,8))
        self.assertIsNone(claim_span("Reversal", "CombinationErr"))

    def test_escaped_report_explanation_keeps_original_output_coordinates(self):
        claim='The term "Net Revenue" is inconsistent.\nIt has two definitions.'
        payload={"explanation":claim}
        for raw in (json.dumps(payload),json.dumps(json.dumps(payload))):
            a,b=claim_span(raw,claim)
            decoded=raw[a:b]
            for _ in range(2):
                if decoded==claim:break
                decoded=json.loads('"'+decoded+'"')
            self.assertEqual(decoded,claim)


if __name__=="__main__":
    unittest.main()
