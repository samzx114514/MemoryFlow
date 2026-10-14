"""Protocol guards for Q3, including train-only alpha selection primitives."""
from __future__ import annotations
import unittest
import numpy as np
from memoryflow.lc_sent15_q3 import ALPHAS, choose_alpha, fold_for_document, group_z, ranks


class Q3Tests(unittest.TestCase):
    def test_fold_is_deterministic_and_bounded(self):
        self.assertEqual(fold_for_document("d1"), fold_for_document("d1")); self.assertIn(fold_for_document("d1"), range(5))
    def test_group_z_hand_calculation(self):
        self.assertTrue(np.allclose(group_z(np.array([1., 2., 3.])), np.array([-1.22474487, 0., 1.22474487])))
    def test_group_z_zero_variance(self): self.assertTrue(np.array_equal(group_z(np.array([2., 2., 2.])), np.zeros(3)))
    def test_candidate_permutation_preserves_id_ranking(self):
        ids = [f"c{i:02d}" for i in range(15)]; ids[1] = "a"
        scores = np.array([1., 1.] + [.5] * 13)
        ordered, _ = ranks(ids, scores, "a")
        p = np.array([1, 2, 0] + list(range(3, 15)))
        ordered2, _ = ranks([ids[i] for i in p], scores[p], "a")
        self.assertEqual(ordered, ordered2)
    def test_alpha_grid_and_lower_alpha_tie_break(self):
        self.assertEqual(ALPHAS[0],0.); self.assertEqual(ALPHAS[-1],1.)
        x=[{'hit_at_1':.5,'mrr':.6,'ndcg_at_5':.7} for _ in range(3)];self.assertEqual(choose_alpha({.2:x,.3:x}),.2)
    def test_seed_first_uses_scalar_metrics(self):
        rows={.5:[{'hit_at_1':.2,'mrr':.2,'ndcg_at_5':.2},{'hit_at_1':.9,'mrr':.9,'ndcg_at_5':.9},{'hit_at_1':.8,'mrr':.8,'ndcg_at_5':.8}]};self.assertEqual(choose_alpha(rows),.5)

if __name__ == '__main__': unittest.main()
