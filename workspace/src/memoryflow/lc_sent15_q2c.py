"""Frozen LC-Sent-15 Q2C D-Full-128 capacity-control primitives."""
from __future__ import annotations

import torch
from torch import nn

from memoryflow.directional_scorer import pair_features
from memoryflow.lc_sent15_q2 import DIM, GROUP_SIZE, grouped_loss

HEAD = "D_FULL_128"
LOSS = "L1_LISTWISE_CE"
EXPECTED_PARAMETERS = 1_835_393


class DirectionalFull128(nn.Module):
    """Role-preserving full pair scorer; target and source are never shared."""

    def __init__(self) -> None:
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(4 * DIM + 1, 128), nn.GELU(), nn.Dropout(0.1), nn.Linear(128, 1)
        )

    def forward(self, target: torch.Tensor, source: torch.Tensor) -> torch.Tensor:
        return self.net(pair_features(target, source)).squeeze(-1)


def parameter_count(model: nn.Module) -> int:
    return sum(p.numel() for p in model.parameters())


def validate_contract() -> None:
    model = DirectionalFull128()
    if parameter_count(model) != EXPECTED_PARAMETERS:
        raise RuntimeError("D-Full-128 parameter contract mismatch")
    if model.net[0].in_features != 4 * DIM + 1 or GROUP_SIZE != 15:
        raise RuntimeError("D-Full-128 input/group contract mismatch")


__all__ = ["HEAD", "LOSS", "EXPECTED_PARAMETERS", "DirectionalFull128", "grouped_loss", "parameter_count", "validate_contract"]
