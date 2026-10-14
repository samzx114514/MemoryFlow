"""Frozen LC-Sent-15 Q2 head/loss matrix primitives."""
from __future__ import annotations

import torch
from torch import nn

from memoryflow.directional_scorer import pair_features
from memoryflow.source_prior_relational import SymmetricRelation, symmetric_features

DIM = 3584
GROUP_SIZE = 15
HEADS = ("H1_LINEAR_FULL", "H2_R_SYM_128", "H3_D_FULL_64")
LOSSES = ("L1_LISTWISE_CE", "L2_PAIRWISE_SOFTPLUS", "L3_BALANCED_POINTWISE_BCE")
EXPECTED_PARAMETERS = {"H1_LINEAR_FULL": 14_338, "H2_R_SYM_128": 917_889, "H3_D_FULL_64": 917_697}


class LinearFull(nn.Module):
    def __init__(self) -> None:
        super().__init__(); self.linear = nn.Linear(4 * DIM + 1, 1)

    def forward(self, target: torch.Tensor, source: torch.Tensor) -> torch.Tensor:
        return self.linear(pair_features(target, source)).squeeze(-1)


class DirectionalFull64(nn.Module):
    def __init__(self) -> None:
        super().__init__(); self.net = nn.Sequential(nn.Linear(4 * DIM + 1, 64), nn.GELU(), nn.Dropout(.1), nn.Linear(64, 1))

    def forward(self, target: torch.Tensor, source: torch.Tensor) -> torch.Tensor:
        return self.net(pair_features(target, source)).squeeze(-1)


def make_head(name: str) -> nn.Module:
    if name == "H1_LINEAR_FULL": return LinearFull()
    if name == "H2_R_SYM_128": return SymmetricRelation(DIM)
    if name == "H3_D_FULL_64": return DirectionalFull64()
    raise ValueError(name)


def parameter_count(model: nn.Module) -> int:
    return sum(parameter.numel() for parameter in model.parameters())


def validate_heads() -> None:
    for name in HEADS:
        if parameter_count(make_head(name)) != EXPECTED_PARAMETERS[name]: raise RuntimeError(f"parameter mismatch: {name}")


def grouped_loss(name: str, logits: torch.Tensor, labels: torch.Tensor, groups: torch.Tensor) -> torch.Tensor:
    values = []
    for group in torch.unique(groups, sorted=True):
        local_logits, local_labels = logits[groups == group], labels[groups == group]
        if len(local_logits) != GROUP_SIZE or int(local_labels.sum().item()) != 1: raise ValueError("Q2 requires c15 with one positive")
        positive = local_logits[local_labels.bool()][0]; negative = local_logits[~local_labels.bool()]
        if name == "L1_LISTWISE_CE": value = -torch.log_softmax(local_logits, 0)[local_labels.bool()][0]
        elif name == "L2_PAIRWISE_SOFTPLUS": value = torch.nn.functional.softplus(negative - positive).mean()
        elif name == "L3_BALANCED_POINTWISE_BCE": value = .5 * torch.nn.functional.softplus(-positive) + .5 * torch.nn.functional.softplus(negative).mean()
        else: raise ValueError(name)
        values.append(value)
    if not values: raise ValueError("empty batch")
    return torch.stack(values).mean()
