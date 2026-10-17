import unittest
from extract import visible, flatten_text, add_visibility, validate


class ExtractionTests(unittest.TestCase):
    def test_exact_text_visibility(self):
        self.assertTrue(visible('A long clause with twenty or more letters.', 'Prefix A long clause\n with twenty or more letters. Suffix'))

    def test_url_alone_is_not_text_visibility(self):
        self.assertFalse(visible('A long clause with twenty or more letters.', 'https://example.org'))

    def test_short_fragments_not_accepted(self):
        self.assertFalse(visible('OK', 'OK'))

    def test_nested_tool_json(self):
        self.assertIn('some evidence', flatten_text({'content': '[{"content":"some evidence"}]'}))

    def test_missing_outputs_not_invented(self):
        flow = {'nodes': [{'id': 'c1', 'kind': 'model_call', 'input_text': 'x'}], 'edges': []}
        add_visibility(flow)
        self.assertEqual(flow['edges'], [])
        self.assertFalse(any(n['kind'] == 'research_summary' for n in flow['nodes']))

    def test_edge_integrity(self):
        flow = {'nodes': [{'id': 's', 'kind': 'source_chunk', 'text': 'A long clause with twenty or more letters.'},
                          {'id': 'c', 'kind': 'model_call', 'input_text': 'A long clause with twenty or more letters.', 'origin': 'fixture'}], 'edges': []}
        add_visibility(flow)
        validate(flow)
        self.assertEqual(flow['edges'][0]['kind'], 'text_visible_in_input')
        self.assertFalse(flow['edges'][0]['semantic_gold'])

    def test_duplicate_ids_rejected(self):
        with self.assertRaises(AssertionError):
            validate({'nodes': [{'id': 'x'}, {'id': 'x'}], 'edges': []})


if __name__ == '__main__':
    unittest.main()
