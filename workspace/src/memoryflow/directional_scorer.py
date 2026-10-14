"""Small direction-aware pair scorers for M6B."""
from __future__ import annotations

import torch
from torch import nn


def pair_features(target: torch.Tensor, source: torch.Tensor) -> torch.Tensor:
    """Ordered target/source features; target and source are already normalized."""
    if target.shape != source.shape or target.ndim != 2:
        raise ValueError("target/source must have the same rank-2 shape")
    cosine = (target * source).sum(dim=1, keepdim=True)
    return torch.cat((target, source, target * source, (target - source).abs(), cosine), dim=1)


class LinearPair(nn.Module):
    def __init__(self, input_dim: int):
        super().__init__()
        self.linear = nn.Linear(input_dim, 1)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.linear(x).squeeze(-1)


class MLPPair(nn.Module):
    def __init__(self, input_dim: int):
        super().__init__()
        self.net = nn.Sequential(nn.Linear(input_dim, 128), nn.GELU(), nn.Dropout(0.1), nn.Linear(128, 1))

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.net(x).squeeze(-1)


def all_positive_distribution_loss(logits: torch.Tensor, labels: torch.Tensor, groups: torch.Tensor) -> torch.Tensor:
    losses = []
    for group in torch.unique(groups, sorted=True):
        mask = groups == group
        positives = labels[mask] > 0.5
        if not bool(positives.any()):
            raise ValueError("ranking group has no positive")
        logp = torch.log_softmax(logits[mask], dim=0)
        losses.append(-logp[positives].mean())
    if not losses:
        raise ValueError("empty ranking batch")
    return torch.stack(losses).mean()
