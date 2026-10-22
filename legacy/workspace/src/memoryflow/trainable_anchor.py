"""Utilities for training one shared Anchor vector through a frozen model."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

import torch
from torch import nn

from memoryflow.anchor_attention import PackedLayout


def inject_shared_anchor(
    detached_token_embeddings: torch.Tensor,
    anchor_positions: Sequence[int],
    trainable_anchor: torch.Tensor,
) -> torch.Tensor:
    """Replace selected positions without mutating the frozen token embeddings."""
    if detached_token_embeddings.ndim != 3 or detached_token_embeddings.shape[0] != 1:
        raise ValueError("token embeddings must have shape [1,sequence,hidden]")
    if trainable_anchor.ndim != 1 or trainable_anchor.shape[0] != detached_token_embeddings.shape[-1]:
        raise ValueError("anchor must have shape [hidden]")
    length = detached_token_embeddings.shape[1]
    if not anchor_positions or len(set(anchor_positions)) != len(anchor_positions):
        raise ValueError("anchor positions must be nonempty and unique")
    if min(anchor_positions) < 0 or max(anchor_positions) >= length:
        raise ValueError("anchor position out of range")
    mask = torch.zeros((1, length, 1), dtype=detached_token_embeddings.dtype, device=detached_token_embeddings.device)
    mask[:, list(anchor_positions)] = 1
    anchor = trainable_anchor.to(detached_token_embeddings.dtype).view(1, 1, -1)
    return detached_token_embeddings.detach() * (1 - mask) + anchor * mask


def aggregate_last_layers_anchor_scores(
    attentions: Sequence[torch.Tensor],
    layout: PackedLayout,
    *,
    last_n_layers: int = 8,
) -> torch.Tensor:
    """Return differentiable candidate-normalized Target-to-Source Anchor scores."""
    if last_n_layers <= 0 or len(attentions) < last_n_layers:
        raise ValueError("insufficient attention layers")
    values = []
    for attention in attentions[-last_n_layers:]:
        if attention.ndim != 4 or attention.shape[0] != 1:
            raise ValueError("attention must have [1,heads,query,key] shape")
        values.append(attention[0, :, layout.target_anchor_position, layout.source_anchor_positions].mean(dim=0))
    raw = torch.stack(values).mean(dim=0)
    if not bool(torch.isfinite(raw).all().item()):
        raise ValueError("candidate attention contains NaN or Inf")
    if not bool((raw.sum() > 0).item()):
        raise ValueError("candidate attention has zero total mass")
    return raw / raw.sum()


def all_positive_distribution_loss(scores: torch.Tensor, gold_mask: torch.Tensor) -> torch.Tensor:
    """Cross entropy against a uniform distribution over every positive."""
    if scores.ndim != 1 or gold_mask.shape != scores.shape:
        raise ValueError("scores and gold_mask must have matching [candidate] shapes")
    count = gold_mask.to(scores.dtype).sum()
    if not bool((count > 0).item()):
        raise ValueError("at least one positive is required")
    distribution = gold_mask.to(scores.dtype) / count
    return -(distribution * torch.log(scores + 1e-12)).sum()


def anchor_drift_penalty(trainable_anchor: torch.Tensor, initial_anchor: torch.Tensor) -> torch.Tensor:
    if trainable_anchor.shape != initial_anchor.shape:
        raise ValueError("anchor shapes must match")
    return torch.mean((trainable_anchor - initial_anchor) ** 2)


def trainable_parameter_count(model: nn.Module, trainable_anchor: nn.Parameter) -> int:
    if any(parameter.requires_grad for parameter in model.parameters()):
        raise ValueError("all model parameters must be frozen")
    if not trainable_anchor.requires_grad:
        raise ValueError("anchor parameter must require gradients")
    return trainable_anchor.numel()


@dataclass(frozen=True)
class CheckpointScore:
    ndcg_at_5: float
    recall_at_5: float
    all_positive_loss: float
    epoch: int

    @property
    def selection_key(self) -> tuple[float, float, float, int]:
        return (self.ndcg_at_5, self.recall_at_5, -self.all_positive_loss, -self.epoch)


def choose_better_checkpoint(current: CheckpointScore | None, candidate: CheckpointScore) -> bool:
    """Selection uses dev only and keeps the earlier epoch on an exact tie."""
    return current is None or candidate.selection_key > current.selection_key
