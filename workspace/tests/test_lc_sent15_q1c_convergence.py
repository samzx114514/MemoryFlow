"""Pure guards for Q1C's frozen convergence protocol."""
from __future__ import annotations

import unittest

from run_lc_sent15_q1c_rsym_convergence import MAX_EPOCH, PATIENCE, selection_key


class Q1CProtocolTests(unittest.TestCase):
    def test_comparator_is_mrr_first(self):
        better_mrr = {"overall": {"mrr": .8, "ndcg_at_5": .1}, "ranking_loss": 99}
        better_ndcg = {"overall": {"mrr": .7, "ndcg_at_5": .99}, "ranking_loss": 0}
        self.assertLess(selection_key(better_mrr, 2), selection_key(better_ndcg, 1))

    def test_earlier_epoch_breaks_exact_tie(self):
        metric = {"overall": {"mrr": .8, "ndcg_at_5": .7}, "ranking_loss": 1.0}
        self.assertLess(selection_key(metric, 1), selection_key(metric, 2))

    def test_frozen_patience_and_cap(self):
        self.assertEqual(PATIENCE, 5); self.assertEqual(MAX_EPOCH, 100)

    def test_no_hit_at_1_in_selection_key(self):
        a = {"overall": {"mrr": .8, "ndcg_at_5": .7, "hit_at_1": 0}, "ranking_loss": 1.0}
        b = {"overall": {"mrr": .8, "ndcg_at_5": .7, "hit_at_1": 1}, "ranking_loss": 1.0}
        self.assertEqual(selection_key(a, 3), selection_key(b, 3))


if __name__ == "__main__": unittest.main()
