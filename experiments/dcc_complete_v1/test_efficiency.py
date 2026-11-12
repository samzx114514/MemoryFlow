import json
import unittest

from efficiency_task import claim_span


class DeliveredClaimSpanTest(unittest.TestCase):
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
