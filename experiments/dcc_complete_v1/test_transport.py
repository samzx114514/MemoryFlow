import json
import unittest

from .transport import normalize, structured_value


class StructuredTransportTest(unittest.TestCase):
    def test_nested_string_preserves_unicode_and_content(self):
        value = [{"text": "第二条 😀", "explanation": "first\nsecond"}]
        self.assertEqual(structured_value(json.dumps(json.dumps(value))), value)
        escaped = json.dumps(json.dumps(value, ensure_ascii=False), ensure_ascii=False)[1:-1]
        self.assertEqual(structured_value(escaped), value)

    def test_truncated_payload_is_not_completed(self):
        self.assertIsNone(structured_value('[{"text":"unfinished'))

    def test_recover_json_field_only_when_schema_requires_structure(self):
        value = [{"text": "A", "explanation": "B"}]
        request = {"tools": [{"function": {"name": "write_file", "parameters": {"properties": {
            "json_content": {"anyOf": [{"type": "object"}, {"type": "array"}, {"type": "null"}]}}}}}]}
        response = {"choices": [{"message": {"tool_calls": [{"id": "x", "function": {"name": "write_file",
            "arguments": json.dumps({"json_content": json.dumps(value)})}}]}}]}
        self.assertEqual(len(normalize(response, request, "clause")), 1)
        self.assertEqual(json.loads(response["choices"][0]["message"]["tool_calls"][0]["function"]["arguments"])["json_content"], value)

    def test_wrapper_repair_is_clauselike_and_keeps_array(self):
        original = {"artifact_content": [{"text": "evidence", "explanation": "finding"}]}
        response = {"choices": [{"message": {"content": json.dumps(original)}}]}
        self.assertEqual(normalize(response, {}, "finauditing"), [])
        self.assertEqual(len(normalize(response, {}, "clause")), 1)
        self.assertEqual(json.loads(response["choices"][0]["message"]["content"]), original["artifact_content"])


if __name__ == "__main__":
    unittest.main()
