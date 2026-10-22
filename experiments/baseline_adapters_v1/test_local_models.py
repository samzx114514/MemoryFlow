import unittest

import torch

from run_local_models import LocalEmbedder, last_token_vector, overlap_ids


class LocalModelTests(unittest.TestCase):
    def test_length_limit_keeps_smoke_default(self):
        self.assertEqual(LocalEmbedder(None, None).max_tokens, 2048)
        self.assertEqual(LocalEmbedder(None, None, max_tokens=8192).max_tokens, 8192)

    def test_limit_rejects_without_truncation(self):
        def tokenizer(text, **kwargs):
            self.assertNotIn('truncation', kwargs)
            return {'input_ids': torch.zeros(1, 2049, dtype=torch.long)}
        with self.assertRaisesRegex(ValueError, 'no truncation allowed'):
            LocalEmbedder(tokenizer, None).embed(['text'])

    def test_last_not_mean(self):
        v = last_token_vector(torch.tensor([[[8., 0.], [0., 2.]]]))
        self.assertEqual(v.tolist(), [0., 1.])

    def test_zero_rejected(self):
        with self.assertRaises(ValueError):
            last_token_vector(torch.zeros(1, 2, 3))

    def test_all_overlaps(self):
        m = [dict(id='a', start=0, end=5), dict(id='b', start=7, end=10)]
        self.assertEqual(overlap_ids(3, 9, m), ['a', 'b'])
        self.assertEqual(overlap_ids(5, 7, m), [])

    def test_exact_boundary(self):
        self.assertEqual(overlap_ids(0, 5, [dict(id='a', start=0, end=5)]), ['a'])


if __name__ == '__main__':
    unittest.main()
