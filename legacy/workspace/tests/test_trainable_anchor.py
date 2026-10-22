import numpy as np
import pytest
import torch
from torch import nn
from safetensors.torch import load_file, save_file

from memoryflow.anchor_attention import build_anchor_attention_mask, build_packed_layout
from memoryflow.trainable_anchor import (
    CheckpointScore,
    aggregate_last_layers_anchor_scores,
    all_positive_distribution_loss,
    anchor_drift_penalty,
    choose_better_checkpoint,
    inject_shared_anchor,
    trainable_parameter_count,
)


class FrozenToy(nn.Module):
    def __init__(self):
        super().__init__()
        self.embedding = nn.Embedding(10, 4)


def test_eos_initialization_is_exactly_equivalent() -> None:
    model = FrozenToy().requires_grad_(False)
    ids = torch.tensor([[1, 9, 2, 9]])
    base = model.embedding(ids).detach()
    anchor = nn.Parameter(model.embedding.weight[9].detach().clone())
    injected = inject_shared_anchor(base, [1, 3], anchor)
    assert torch.equal(injected, base)


def test_only_anchor_is_trainable_and_counted() -> None:
    model = FrozenToy().requires_grad_(False)
    anchor = nn.Parameter(torch.ones(4))
    assert trainable_parameter_count(model, anchor) == 4
    assert [parameter for parameter in [anchor] if parameter.requires_grad] == [anchor]
    assert all(not parameter.requires_grad for parameter in model.parameters())


def test_all_positive_loss_backpropagates_to_every_positive() -> None:
    logits = torch.tensor([0.2, -0.3, 0.1, 0.0], requires_grad=True)
    scores = torch.softmax(logits, dim=0)
    loss = all_positive_distribution_loss(scores, torch.tensor([True, True, False, False]))
    loss.backward()
    assert logits.grad is not None and torch.isfinite(logits.grad).all()
    assert logits.grad[0] != 0 and logits.grad[1] != 0


def test_single_update_changes_only_anchor() -> None:
    model = FrozenToy().requires_grad_(False)
    before = model.embedding.weight.detach().clone()
    anchor = nn.Parameter(model.embedding.weight[9].detach().clone())
    optimizer = torch.optim.AdamW([anchor], lr=0.01, weight_decay=0)
    base = model.embedding(torch.tensor([[1, 9, 2, 9]])).detach()
    output = inject_shared_anchor(base, [1, 3], anchor)
    loss = output[:, [1, 3]].sum() + 1e-4 * anchor_drift_penalty(anchor, before[9])
    loss.backward(); optimizer.step()
    assert not torch.equal(anchor.detach(), before[9])
    assert torch.equal(model.embedding.weight, before)
    assert all(parameter.grad is None for parameter in model.parameters())


def test_anchor_save_load_preserves_scores(tmp_path) -> None:
    anchor = torch.arange(4, dtype=torch.float32)
    features = torch.arange(12, dtype=torch.float32).reshape(3, 4)
    before = features @ anchor
    path = tmp_path / "anchor.safetensors"
    save_file({"trainable_anchor": anchor}, path)
    loaded = load_file(path)["trainable_anchor"]
    after = features @ loaded
    assert torch.equal(anchor, loaded)
    assert torch.equal(before, after)


def test_checkpoint_selection_has_no_test_input_and_obeys_priority() -> None:
    first = CheckpointScore(0.5, 0.6, 1.2, 1)
    better_ndcg = CheckpointScore(0.6, 0.1, 9.0, 2)
    assert choose_better_checkpoint(first, better_ndcg)
    assert not choose_better_checkpoint(first, CheckpointScore(0.5, 0.6, 1.2, 2))


def test_best_checkpoint_can_be_restored_exactly() -> None:
    anchor = nn.Parameter(torch.tensor([1.0, 2.0]))
    best = anchor.detach().clone()
    with torch.no_grad():
        anchor.add_(3)
        anchor.copy_(best)
    assert torch.equal(anchor, best)


def test_mask_topology_is_unchanged() -> None:
    layout = build_packed_layout([[1, 2], [3, 4]], [5, 6], anchor_token_id=9)
    allowed = build_anchor_attention_mask(layout, mode="anchor", dtype=torch.float32)[0, 0] == 0
    assert allowed[layout.target_anchor_position, layout.source_anchor_positions].all()
    assert not allowed[layout.target_anchor_position, layout.source_content_positions[0]].any()


def test_fp32_candidate_reordering_is_stable_for_symmetric_attention() -> None:
    first = build_packed_layout([[1], [2]], [3], anchor_token_id=9)
    second = build_packed_layout([[2], [1]], [3], anchor_token_id=9)
    def scores(layout, raw):
        attention = torch.zeros(1, 2, layout.sequence_length, layout.sequence_length)
        attention[0, :, layout.target_anchor_position, layout.source_anchor_positions] = torch.tensor(raw)
        return aggregate_last_layers_anchor_scores([attention] * 8, layout)
    left = dict(zip(["a", "b"], scores(first, [0.2, 0.8]).tolist()))
    right = dict(zip(["b", "a"], scores(second, [0.8, 0.2]).tolist()))
    assert max(abs(left[key] - right[key]) for key in left) < 1e-7


def test_invalid_inputs_are_rejected() -> None:
    with pytest.raises(ValueError, match="positive"):
        all_positive_distribution_loss(torch.ones(4) / 4, torch.zeros(4, dtype=torch.bool))
