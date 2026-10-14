"""Minimal source-prior and relational scorers for preregistered M6D."""
from __future__ import annotations
import math
from typing import Any
import torch
from torch import nn


class SourcePrior(nn.Module):
    def __init__(self, dim: int = 3584) -> None:
        super().__init__()
        self.net = nn.Sequential(nn.Linear(dim, 128), nn.GELU(), nn.Dropout(0.1), nn.Linear(128, 1))

    def forward(self, source: torch.Tensor) -> torch.Tensor:
        return self.net(source).squeeze(-1)


def symmetric_features(target: torch.Tensor, source: torch.Tensor) -> torch.Tensor:
    cosine = (target * source).sum(dim=-1, keepdim=True)
    return torch.cat((target * source, (target - source).abs(), cosine), dim=-1)


class SymmetricRelation(nn.Module):
    def __init__(self, dim: int = 3584) -> None:
        super().__init__()
        self.net = nn.Sequential(nn.Linear(2 * dim + 1, 128), nn.GELU(), nn.Dropout(0.1), nn.Linear(128, 1))

    def forward(self, target: torch.Tensor, source: torch.Tensor) -> torch.Tensor:
        return self.net(symmetric_features(target, source)).squeeze(-1)


class DirectionalRelation(nn.Module):
    def __init__(self, dim: int = 3584, rank: int = 128) -> None:
        super().__init__()
        self.rank = rank
        self.target_projection = nn.Linear(dim, rank)
        self.source_projection = nn.Linear(dim, rank)
        self.bias = nn.Parameter(torch.zeros(()))

    def forward(self, target: torch.Tensor, source: torch.Tensor) -> torch.Tensor:
        u = self.target_projection(target)
        v = self.source_projection(source)
        return (u * v).sum(dim=-1) / math.sqrt(self.rank) + self.bias


def parameter_count(model: nn.Module) -> int:
    return sum(p.numel() for p in model.parameters())


def freeze_module(module: nn.Module) -> None:
    module.eval()
    for param in module.parameters():
        param.requires_grad_(False)


def finite_json(value: Any) -> Any:
    """Convert non-finite numeric values to JSON null recursively."""
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, dict):
        return {str(k): finite_json(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [finite_json(v) for v in value]
    return value


def prior_challenging_ids(rows_by_example: dict[str, list[dict[str, Any]]]) -> tuple[set[str], dict[str, int]]:
    """Return eligible source-prior hard groups without assuming both classes exist."""
    selected: set[str] = set()
    counts = {"eligible": 0, "excluded_no_positive": 0, "excluded_no_negative": 0}
    for example_id, rows in rows_by_example.items():
        positives = [float(row["logit"]) for row in rows if int(row["label"]) == 1]
        negatives = [float(row["logit"]) for row in rows if int(row["label"]) == 0]
        if not positives:
            counts["excluded_no_positive"] += 1
            continue
        if not negatives:
            counts["excluded_no_negative"] += 1
            continue
        counts["eligible"] += 1
        if max(negatives) >= max(positives):
            selected.add(example_id)
    return selected, counts
