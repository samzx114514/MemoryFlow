import unittest

from .candidates import material_id, source_window


class CandidateIdentityTest(unittest.TestCase):
    def test_decoded_span_deduplicates_different_json_encodings(self):
        for body in ['{"content":"A\\nB"}', '{"content":"A\\u000aB"}']:
            left = body.index('B')
            window = source_window(body, {"span": [left, left+1], "text": "B", "match_text": "B"}, True)
            self.assertEqual(window, {"artifact_id": material_id("A\nB"), "start": 2, "end": 3, "text": "B"})

    def test_mismatched_column_is_not_silently_mapped(self):
        with self.assertRaisesRegex(ValueError, "differs"):
            source_window("actual text", {"span": [0, 6], "text": "wrong"}, False)


if __name__ == "__main__":
    unittest.main()
