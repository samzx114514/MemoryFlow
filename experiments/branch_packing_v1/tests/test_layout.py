"""CPU correctness checks for G7 branch packing layout (no GPU)."""

from __future__ import annotations

import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from layout import Branch, assert_isolated, build_layout, causal_single_branch_mask  # noqa: E402


class PackingLayoutTest(unittest.TestCase):
    def test_single_branch_matches_causal_reference(self) -> None:
        layout = build_layout([1, 2], [Branch("a", (3, 4))])
        self.assertEqual(layout.attention_mask, causal_single_branch_mask(2, 2))
        self.assertEqual(layout.target_positions, {"a": [2, 3]})

    def test_sibling_suffix_is_masked(self) -> None:
        branches = [Branch("a", (3, 4)), Branch("b", (5, 6))]
        layout = build_layout([1, 2], branches)
        assert_isolated(layout, branches)
        self.assertEqual(layout.target_positions, {"a": [2, 3], "b": [4, 5]})
        self.assertFalse(layout.attention_mask[4][2])  # b cannot see a
        self.assertFalse(layout.attention_mask[5][3])  # b cannot see a
        self.assertTrue(layout.attention_mask[4][1])   # b sees shared prefix
        self.assertTrue(layout.attention_mask[2][1])   # a sees shared prefix

    def test_different_branch_lengths_keep_own_target_rows(self) -> None:
        branches = [Branch("short", (7,)), Branch("long", (8, 9, 10))]
        layout = build_layout([1, 2, 3], branches)
        assert_isolated(layout, branches)
        self.assertEqual(layout.position_ids[3], 3)  # first target position
        self.assertEqual(layout.position_ids[4], 3)  # other branch restarts at 3
        self.assertEqual(layout.target_positions["short"], [3])
        self.assertEqual(layout.target_positions["long"], [4, 5, 6])

    def test_changing_other_branch_does_not_change_this_branch(self) -> None:
        base = build_layout([1, 2], [Branch("a", (3, 4)), Branch("b", (5, 6))])
        changed = build_layout([1, 2], [Branch("a", (3, 4)), Branch("b", (50, 60, 70))])
        self.assertEqual(base.target_positions["a"], changed.target_positions["a"])
        width = len(base.prefix) + len(base.target_positions["a"])
        for query in base.target_positions["a"]:
            self.assertEqual(base.attention_mask[query][:width], changed.attention_mask[query][:width])

    def test_single_token_target(self) -> None:
        branches = [Branch("one", (9,))]
        layout = build_layout([1, 2], branches)
        assert_isolated(layout, branches)
        self.assertEqual(layout.target_positions["one"], [2])
        self.assertEqual(layout.attention_mask[2], [True, True, True])

    def test_invalid_layout_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            build_layout([], [Branch("a", (1,))])
        with self.assertRaises(ValueError):
            build_layout([1], [])
        with self.assertRaises(ValueError):
            build_layout([1], [Branch("a", ())])


if __name__ == "__main__":
    unittest.main()
