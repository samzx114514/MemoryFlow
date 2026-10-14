import pytest
import torch

from memoryflow.anchor_attention import (
    aggregate_candidate_scores,
    build_anchor_attention_mask,
    build_packed_layout,
    kendall_tau_for_rankings,
    stable_tolerance_ranking,
    validate_no_fully_masked_rows,
)


def layout():
    return build_packed_layout([[11, 12], [21, 22, 23]], [31, 32], anchor_token_id=99)


def test_packed_layout_uses_local_position_ids_and_terminal_anchors() -> None:
    packed = layout()
    assert packed.input_ids == [11, 12, 99, 21, 22, 23, 99, 31, 32, 99]
    assert packed.position_ids == [0, 1, 2, 0, 1, 2, 3, 0, 1, 2]
    assert packed.source_anchor_positions == [2, 6]
    assert packed.target_anchor_position == 9


def test_anchor_mask_topology_and_source_isolation() -> None:
    packed = layout()
    allowed = build_anchor_attention_mask(packed, mode="anchor", dtype=torch.float32)[0, 0] == 0
    assert allowed[0, 0] and not allowed[0, 1]
    assert allowed[2, 0:3].all()
    assert not allowed[0:3, 3:7].any()
    assert not allowed[3:7, 0:3].any()
    assert allowed[9, [2, 6]].all()
    assert allowed[9, [7, 8, 9]].all()
    assert not allowed[9, [0, 1, 3, 4, 5]].any()


def test_token_mask_target_visibility() -> None:
    packed = layout()
    allowed = build_anchor_attention_mask(packed, mode="token", dtype=torch.float32)[0, 0] == 0
    assert allowed[9, [0, 1, 3, 4, 5, 7, 8, 9]].all()
    assert not allowed[9, [2, 6]].any()
    assert not allowed[7, 0:7].any()


def test_no_fully_masked_rows_and_invalid_mask_detection() -> None:
    mask = build_anchor_attention_mask(layout(), mode="anchor", dtype=torch.float32)
    validate_no_fully_masked_rows(mask)
    mask[:, :, 4, :] = torch.finfo(torch.float32).min
    with pytest.raises(ValueError, match="fully masked"):
        validate_no_fully_masked_rows(mask)


def test_anchor_score_aggregation_across_heads_and_layers() -> None:
    packed = layout()
    attentions = []
    for multiplier in (1.0, 2.0, 3.0, 4.0):
        value = torch.zeros(1, 2, 10, 10)
        value[0, 0, 9, 2] = 0.1 * multiplier
        value[0, 1, 9, 2] = 0.3 * multiplier
        value[0, :, 9, 6] = 0.2 * multiplier
        attentions.append(value)
    scores, diagnostic = aggregate_candidate_scores(attentions, packed, mode="anchor")
    assert diagnostic is None
    assert torch.allclose(scores, torch.tensor([0.5, 0.5]))


def test_token_mean_scores_do_not_favor_longer_chunks() -> None:
    packed = layout()
    value = torch.zeros(1, 2, 10, 10)
    value[0, :, 9, packed.source_content_positions[0]] = 0.2
    value[0, :, 9, packed.source_content_positions[1]] = 0.2
    scores, sums = aggregate_candidate_scores([value] * 4, packed, mode="token")
    assert torch.allclose(scores, torch.tensor([0.5, 0.5]))
    assert sums is not None and sums[1] > sums[0]


def test_candidate_repacking_preserves_local_positions() -> None:
    first = build_packed_layout([[1, 2], [3, 4, 5]], [8], anchor_token_id=9)
    second = build_packed_layout([[3, 4, 5], [1, 2]], [8], anchor_token_id=9)
    assert first.position_ids[:3] == second.position_ids[4:7]
    assert first.position_ids[3:7] == second.position_ids[:4]


def test_empty_chunk_and_nonfinite_attention_rejected() -> None:
    with pytest.raises(ValueError, match="source chunks"):
        build_packed_layout([[]], [1], anchor_token_id=9)
    packed = layout()
    value = torch.zeros(1, 1, 10, 10)
    value[0, 0, 9, 2] = float("nan")
    with pytest.raises(ValueError, match="NaN"):
        aggregate_candidate_scores([value] * 4, packed, mode="anchor")


def test_stable_tolerance_ranking_and_kendall_tau() -> None:
    source_ids = ["a", "b", "c"]
    first = stable_tolerance_ranking(source_ids, [0.5, 0.5000005, 0.1])
    repeated = stable_tolerance_ranking(list(reversed(source_ids)), [0.1, 0.5000005, 0.5])
    assert first == repeated
    assert kendall_tau_for_rankings(first, first) == 1.0
    assert kendall_tau_for_rankings(["a", "b", "c"], ["c", "b", "a"]) == -1.0
