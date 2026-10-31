"""CPU layout/mask checks for G7 shared-prefix branch packing.

This is the local correctness layer, not a model benchmark.  It builds a
custom 4-D attention mask so a target branch sees the shared prefix and its own
suffix only; sibling branches are masked out.  Actual D/P timing still needs
the GPU runner.
"""

from __future__ import annotations

import json
import pathlib
from dataclasses import dataclass


@dataclass(frozen=True)
class Branch:
    branch_id: str
    target_tokens: tuple[int, ...]


@dataclass
class PackedLayout:
    prefix: tuple[int, ...]
    input_ids: list[int]
    position_ids: list[int]
    segment_ids: list[int]
    attention_mask: list[list[bool]]
    target_positions: dict[str, list[int]]

    def as_dict(self) -> dict:
        return {
            "prefix_length": len(self.prefix),
            "input_ids": self.input_ids,
            "position_ids": self.position_ids,
            "segment_ids": self.segment_ids,
            "attention_mask": self.attention_mask,
            "target_positions": self.target_positions,
        }


def build_layout(prefix: list[int] | tuple[int, ...], branches: list[Branch]) -> PackedLayout:
    prefix = tuple(int(token) for token in prefix)
    if not prefix:
        raise ValueError("shared prefix must be non-empty")
    if not branches:
        raise ValueError("at least one branch is required")
    ids = [branch.branch_id for branch in branches]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate branch ids")
    for branch in branches:
        if not branch.target_tokens:
            raise ValueError(f"branch {branch.branch_id} has no target tokens")

    input_ids = list(prefix)
    position_ids = list(range(len(prefix)))
    segment_ids = [0] * len(prefix)
    target_positions: dict[str, list[int]] = {}
    branch_ranges: dict[str, tuple[int, int]] = {}
    for branch_index, branch in enumerate(branches, start=1):
        start = len(input_ids)
        input_ids.extend(int(token) for token in branch.target_tokens)
        position_ids.extend(range(len(prefix), len(prefix) + len(branch.target_tokens)))
        segment_ids.extend([branch_index] * len(branch.target_tokens))
        target_positions[branch.branch_id] = list(range(start, start + len(branch.target_tokens)))
        branch_ranges[branch.branch_id] = (start, start + len(branch.target_tokens))

    mask = [[False] * len(input_ids) for _ in input_ids]
    # Shared prefix remains causal and cannot see any branch suffix.
    for query in range(len(prefix)):
        for key in range(query + 1):
            mask[query][key] = True
    # Each branch sees the whole shared prefix plus its own suffix up to itself.
    for branch in branches:
        start, end = branch_ranges[branch.branch_id]
        for offset, query in enumerate(range(start, end)):
            for key in range(len(prefix)):
                mask[query][key] = True
            for key in range(start, start + offset + 1):
                mask[query][key] = True

    return PackedLayout(
        prefix=prefix,
        input_ids=input_ids,
        position_ids=position_ids,
        segment_ids=segment_ids,
        attention_mask=mask,
        target_positions=target_positions,
    )


def assert_isolated(layout: PackedLayout, branches: list[Branch]) -> None:
    """Raise if a target branch can see a sibling suffix token."""
    for branch in branches:
        start = layout.target_positions[branch.branch_id][0]
        own = set(layout.target_positions[branch.branch_id])
        for query in layout.target_positions[branch.branch_id]:
            visible_suffix = [key for key in range(start, len(layout.input_ids))
                              if layout.attention_mask[query][key]]
            if any(key not in own and key >= start for key in visible_suffix):
                raise AssertionError(f"branch {branch.branch_id} sees a sibling suffix")


def causal_single_branch_mask(prefix_length: int, target_length: int) -> list[list[bool]]:
    """Reference mask for the one-branch D-style sequence."""
    total = prefix_length + target_length
    return [[key <= query for key in range(total)] for query in range(total)]


def main() -> int:
    prefix = [101, 102, 103]
    branches = [Branch("b1", (201, 202)), Branch("b2", (301,))]
    layout = build_layout(prefix, branches)
    assert_isolated(layout, branches)
    out = pathlib.Path(__file__).with_name("layout_example.json")
    out.write_text(json.dumps(layout.as_dict(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"out": str(out), "tokens": len(layout.input_ids),
                      "targets": layout.target_positions}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
