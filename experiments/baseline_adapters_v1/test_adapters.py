import copy
import unittest

from adapters import clm_request, clm_score, rank_scores, validate_record, yifeng_input


def example():
    return dict(id='example', query='Which animal can fly?', language='en',
                target='Birds can fly.', gold=None, candidate_policy='all_retrieved',
                sources=[dict(id='s2', text='Birds can fly.'),
                         dict(id='s1', text='Fish can swim.')])


class AdapterTests(unittest.TestCase):
    def test_order_ids_and_text(self):
        r = example()
        state, questions = clm_request(r)
        self.assertEqual(state, r['target'])
        self.assertEqual(list(questions['source']['criteria']), ['s2', 's1'])
        self.assertEqual(list(questions['source']['criteria'].values()),
                         [s['text'] for s in r['sources']])

    def test_gold_never_sent(self):
        r = example()
        expected = clm_request(r)
        r['gold'] = {'secret_answer': 's2'}
        self.assertEqual(clm_request(r), expected)

    def test_duplicate_text_not_collapsed(self):
        r = example()
        r['sources'][1]['text'] = r['sources'][0]['text']
        self.assertEqual(len(clm_request(r)[1]['source']['criteria']), 2)

    def test_duplicate_id_rejected(self):
        r = example()
        r['sources'][1]['id'] = 's2'
        with self.assertRaises(ValueError):
            validate_record(r)

    def test_empty_text_rejected(self):
        r = example()
        r['sources'][0]['text'] = ' '
        with self.assertRaises(ValueError):
            validate_record(r)

    def test_native_generation_does_not_receive_target(self):
        r = example()
        native, mapping = yifeng_input(r)
        r['target'] = 'SECRET_TARGET_NOT_IN_SOURCES'
        self.assertEqual(yifeng_input(r), (native, mapping))
        self.assertEqual(native['query'], r['query'])

    def test_source_offsets(self):
        r = example()
        native, mapping = yifeng_input(r)
        for source, loc in zip(r['sources'], mapping):
            self.assertEqual(native['context'][loc['start']:loc['end']], source['text'])
            self.assertEqual(loc['id'], source['id'])

    def test_source_id_tiebreak(self):
        self.assertEqual(rank_scores({'s2': 0.5, 's1': 0.5}), ['s1', 's2'])

    def test_nonfinite_rejected(self):
        with self.assertRaises(ValueError):
            rank_scores({'s1': float('nan')})

    def test_no_mutation(self):
        r = example()
        saved = copy.deepcopy(r)
        clm_request(r)
        yifeng_input(r)
        self.assertEqual(r, saved)

    def test_clm_output_preserves_ids(self):
        class Engine:
            def answer(self, state, questions, **kwargs):
                return {'answers': {'source': {'probabilities': {'s2': .8, 's1': .2}}}, 'usage': {}}
        result = clm_score(example(), Engine())
        self.assertEqual(result['ranking'], ['s2', 's1'])
        self.assertEqual(result['evaluation'], 'UNSCORED_NO_SEMANTIC_GOLD')

    def test_clm_wrong_candidates_rejected(self):
        class Engine:
            def answer(self, state, questions, **kwargs):
                return {'answers': {'source': {'probabilities': {'unknown': 1.0}}}, 'usage': {}}
        with self.assertRaises(ValueError):
            clm_score(example(), Engine())


if __name__ == '__main__':
    unittest.main()
