import json
import tempfile
import unittest
from pathlib import Path

import numpy as np
import torch
from safetensors.torch import save_file

if __package__:
    from .pipeline import check_budget, model_context_limit, reduce
else:
    from pipeline import check_budget, model_context_limit, reduce


class PredictionPositionTest(unittest.TestCase):
    def test_flat_and_nested_model_context_config(self):
        self.assertEqual(model_context_limit({"max_position_embeddings":32768}),32768)
        self.assertEqual(model_context_limit({"text_config":{"max_position_embeddings":262144}}),262144)

    def test_native_context_reserves_output_space_before_gpu_work(self):
        check_budget("native", 30720, 2048, 32768)
        with self.assertRaisesRegex(ValueError, "exceed.*32768"):
            check_budget("over", 30721, 2048, 32768)
        with self.assertRaisesRegex(ValueError, "exceed.*32768"):
            check_budget("original_failed_nba", 36024, 2048, 32768)

    def test_full_output_rows_and_causal_output_prefix(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            save_file({"q": torch.ones(6, 1), "k": torch.zeros(6, 1)}, root / "qk.safetensors")
            (root / "qk.json").write_text(json.dumps({"config": {"attention_multiplier": 1.}}))
            sources = [{"token_span": [0, 2]}, {"token_span": [4, 5]}, {"token_span": [5, 7]}]
            matrix, _ = reduce(root, 4, 3, sources)
            np.testing.assert_allclose(matrix[:, 0], [2/4, 2/5, 2/6])
            np.testing.assert_allclose(matrix[:, 1], [0, 1/5, 1/6])
            np.testing.assert_allclose(matrix[:, 2], [0, 0, 1/6])
            self.assertEqual(matrix.shape, (3, 3))
            save_file({"author_q": torch.ones(3, 1), "author_k": torch.zeros(6, 1)}, root / "qk.safetensors")
            (root / "qk.json").write_text(json.dumps({"config": {"attention_multiplier": 1.},
                "hookq_mode": "last_token", "layer_order": [{"key_q": "author_q", "key_k": "author_k"}]}))
            author, _ = reduce(root, 4, 3, sources)
            np.testing.assert_array_equal(author, matrix)


if __name__ == "__main__":
    unittest.main()
