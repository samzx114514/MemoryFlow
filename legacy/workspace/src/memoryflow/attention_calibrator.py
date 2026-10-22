"""Small nonnegative global readouts for frozen Anchor Attention features."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
import math
from typing import Literal, Sequence

import numpy as np
import torch
from torch import nn

from memoryflow.ranking_baselines import METRIC_NAMES, compute_ranking_metrics, rank_scored_candidates


ModelType = Literal["layer_only", "separable"]
ObjectiveType = Literal["any_positive", "all_positive"]


def normalize_candidate_attention(features: np.ndarray) -> np.ndarray:
    """Normalize candidates independently within every example/layer/head."""
    values = np.asarray(features, dtype=np.float32)
    if values.ndim != 4 or not np.isfinite(values).all() or np.any(values < 0):
        raise ValueError("features must be finite nonnegative [example,layer,head,candidate]")
    denominator = values.sum(axis=-1, keepdims=True)
    if np.any(denominator <= 0):
        raise ValueError("every example/layer/head must have positive candidate mass")
    normalized = values / denominator
    if not np.allclose(normalized.sum(axis=-1), 1.0, atol=1e-6):
        raise RuntimeError("candidate normalization failed")
    return normalized


class LayerOnlyCalibrator(nn.Module):
    def __init__(self, layer_count: int = 28):
        super().__init__()
        self.alpha = nn.Parameter(torch.zeros(layer_count))

    def weights(self) -> tuple[torch.Tensor, None]:
        return torch.softmax(self.alpha, dim=0), None

    def forward(self, features: torch.Tensor) -> torch.Tensor:
        layer_weights, _ = self.weights()
        scores = torch.einsum("l,elc->ec", layer_weights, features.mean(dim=2))
        return scores


class SeparableCalibrator(nn.Module):
    def __init__(self, layer_count: int = 28, head_count: int = 12):
        super().__init__()
        self.alpha = nn.Parameter(torch.zeros(layer_count))
        self.beta = nn.Parameter(torch.zeros(head_count))

    def weights(self) -> tuple[torch.Tensor, torch.Tensor]:
        return torch.softmax(self.alpha, dim=0), torch.softmax(self.beta, dim=0)

    def forward(self, features: torch.Tensor) -> torch.Tensor:
        layer_weights, head_weights = self.weights()
        return torch.einsum("l,h,elhc->ec", layer_weights, head_weights, features)


def make_calibrator(model_type: ModelType, layer_count: int, head_count: int) -> nn.Module:
    if model_type == "layer_only":
        return LayerOnlyCalibrator(layer_count)
    if model_type == "separable":
        return SeparableCalibrator(layer_count, head_count)
    raise ValueError(f"unknown calibrator: {model_type}")


def positive_mass_loss(
    scores: torch.Tensor,
    gold_mask: torch.Tensor,
    model: nn.Module,
    *,
    regularization: float = 0.01,
) -> tuple[torch.Tensor, dict[str, torch.Tensor]]:
    if scores.ndim != 2 or scores.shape != gold_mask.shape:
        raise ValueError("scores and gold_mask must have matching [example,candidate] shapes")
    if not bool(gold_mask.any(dim=1).all().item()):
        raise ValueError("every example must have at least one positive")
    masses = (scores * gold_mask.to(scores.dtype)).sum(dim=1)
    rank_loss = -torch.log(masses + 1e-12).mean()
    layer_weights, head_weights = model.weights()
    layer_kl = torch.sum(layer_weights * torch.log(layer_weights * layer_weights.numel()))
    head_kl = torch.zeros((), dtype=scores.dtype)
    if head_weights is not None:
        head_kl = torch.sum(head_weights * torch.log(head_weights * head_weights.numel()))
    total = rank_loss + regularization * layer_kl + regularization * head_kl
    return total, {
        "rank_loss": rank_loss,
        "layer_kl": layer_kl,
        "head_kl": head_kl,
        "positive_mass": masses.mean(),
    }


def uniform_gold_distribution(gold_mask: torch.Tensor) -> torch.Tensor:
    """Return a per-example uniform distribution over all positive candidates."""
    if gold_mask.ndim != 2:
        raise ValueError("gold_mask must have [example,candidate] shape")
    positive_counts = gold_mask.to(torch.float32).sum(dim=1, keepdim=True)
    if not bool((positive_counts > 0).all().item()):
        raise ValueError("every example must have at least one positive")
    return gold_mask.to(torch.float32) / positive_counts


def all_positive_loss(
    scores: torch.Tensor,
    gold_mask: torch.Tensor,
    model: nn.Module,
    *,
    regularization: float = 0.01,
) -> tuple[torch.Tensor, dict[str, torch.Tensor]]:
    """Cross entropy against a uniform distribution over every positive."""
    if scores.ndim != 2 or scores.shape != gold_mask.shape:
        raise ValueError("scores and gold_mask must have matching [example,candidate] shapes")
    gold_distribution = uniform_gold_distribution(gold_mask).to(scores.dtype)
    rank_loss = -(gold_distribution * torch.log(scores + 1e-12)).sum(dim=1).mean()
    layer_weights, head_weights = model.weights()
    layer_kl = torch.sum(layer_weights * torch.log(layer_weights * layer_weights.numel()))
    head_kl = torch.zeros((), dtype=scores.dtype)
    if head_weights is not None:
        head_kl = torch.sum(head_weights * torch.log(head_weights * head_weights.numel()))
    total = rank_loss + regularization * layer_kl + regularization * head_kl
    masses = (scores * gold_mask.to(scores.dtype)).sum(dim=1)
    return total, {
        "rank_loss": rank_loss,
        "layer_kl": layer_kl,
        "head_kl": head_kl,
        "positive_mass": masses.mean(),
    }


def evaluate_scores(
    scores: np.ndarray,
    gold_masks: np.ndarray,
    candidate_ids: Sequence[Sequence[str]],
    example_ids: Sequence[str],
) -> tuple[dict[str, float], list[dict[str, float]], list[list[str]]]:
    if scores.shape != gold_masks.shape or scores.shape[0] != len(candidate_ids) or len(example_ids) != len(candidate_ids):
        raise ValueError("evaluation inputs have inconsistent shapes")
    rows = []
    rankings = []
    for index, source_ids in enumerate(candidate_ids):
        score_map = dict(zip(source_ids, map(float, scores[index])))
        ranking = rank_scored_candidates(source_ids, score_map, tie_namespace=f"calibrator:{example_ids[index]}")
        gold = {source_id for position, source_id in enumerate(source_ids) if gold_masks[index, position]}
        rows.append(compute_ranking_metrics(ranking, gold))
        rankings.append(ranking)
    aggregate = {name: float(np.mean([row[name] for row in rows])) for name in METRIC_NAMES}
    return aggregate, rows, rankings


def weight_entropy(weights: Sequence[float]) -> float:
    values = np.asarray(weights, dtype=np.float64)
    return float(-(values * np.log(np.clip(values, 1e-300, None))).sum())


@dataclass
class FitResult:
    model_type: ModelType
    seed: int
    best_epoch: int
    best_state: dict[str, torch.Tensor]
    best_dev_metrics: dict[str, float]
    best_train_metrics: dict[str, float]
    best_train_positive_mass: float
    best_dev_positive_mass: float
    history: list[dict[str, float | int | str]]


def fit_calibrator(
    model_type: ModelType,
    train_features: np.ndarray,
    train_gold: np.ndarray,
    train_candidate_ids: Sequence[Sequence[str]],
    train_example_ids: Sequence[str],
    dev_features: np.ndarray,
    dev_gold: np.ndarray,
    dev_candidate_ids: Sequence[Sequence[str]],
    dev_example_ids: Sequence[str],
    *,
    seed: int,
    learning_rate: float = 0.05,
    max_epochs: int = 500,
    patience: int = 50,
    regularization: float = 0.01,
    objective: ObjectiveType = "any_positive",
    dev_metric_priority: Sequence[str] = ("mrr", "ndcg_at_5", "recall_at_5"),
) -> FitResult:
    """Fit using train and dev only; test data is deliberately absent."""
    torch.manual_seed(seed)
    train_x = torch.as_tensor(train_features, dtype=torch.float32)
    train_y = torch.as_tensor(train_gold, dtype=torch.bool)
    dev_x = torch.as_tensor(dev_features, dtype=torch.float32)
    model = make_calibrator(model_type, train_x.shape[1], train_x.shape[2])
    optimizer = torch.optim.Adam(model.parameters(), lr=learning_rate)
    if objective not in ("any_positive", "all_positive"):
        raise ValueError(f"unknown objective: {objective}")
    if not dev_metric_priority or any(name not in METRIC_NAMES for name in dev_metric_priority):
        raise ValueError("dev_metric_priority contains an unknown ranking metric")
    best_key: tuple[float, ...] | None = None
    best_epoch = 0
    best_state = deepcopy(model.state_dict())
    best_dev_metrics: dict[str, float] = {}
    best_train_metrics: dict[str, float] = {}
    best_train_mass = best_dev_mass = 0.0
    history: list[dict[str, float | int | str]] = []
    epochs_without_improvement = 0
    for epoch in range(1, max_epochs + 1):
        model.train()
        optimizer.zero_grad(set_to_none=True)
        train_scores = model(train_x)
        loss_function = positive_mass_loss if objective == "any_positive" else all_positive_loss
        loss, components = loss_function(train_scores, train_y, model, regularization=regularization)
        loss.backward()
        optimizer.step()
        model.eval()
        with torch.no_grad():
            train_values = model(train_x).numpy()
            dev_values = model(dev_x).numpy()
        train_metrics, _, _ = evaluate_scores(train_values, train_gold, train_candidate_ids, train_example_ids)
        dev_metrics, _, _ = evaluate_scores(dev_values, dev_gold, dev_candidate_ids, dev_example_ids)
        train_mass = float((train_values * train_gold).sum(axis=1).mean())
        dev_mass = float((dev_values * dev_gold).sum(axis=1).mean())
        layer_weights, head_weights = model.weights()
        history.append({
            "model_type": model_type,
            "objective": objective,
            "seed": seed,
            "epoch": epoch,
            "loss": float(loss.item()),
            "rank_loss": float(components["rank_loss"].item()),
            "layer_kl": float(components["layer_kl"].item()),
            "head_kl": float(components["head_kl"].item()),
            "train_positive_mass": train_mass,
            "dev_positive_mass": dev_mass,
            "train_mrr": train_metrics["mrr"],
            "dev_mrr": dev_metrics["mrr"],
            "dev_ndcg_at_5": dev_metrics["ndcg_at_5"],
            "dev_recall_at_5": dev_metrics["recall_at_5"],
            "layer_entropy": weight_entropy(layer_weights.detach().numpy()),
            "head_entropy": math.nan if head_weights is None else weight_entropy(head_weights.detach().numpy()),
        })
        key = tuple(dev_metrics[name] for name in dev_metric_priority)
        if best_key is None or key > best_key:
            best_key = key
            best_epoch = epoch
            best_state = deepcopy(model.state_dict())
            best_dev_metrics = dev_metrics
            best_train_metrics = train_metrics
            best_train_mass = train_mass
            best_dev_mass = dev_mass
            epochs_without_improvement = 0
        else:
            epochs_without_improvement += 1
            if epochs_without_improvement >= patience:
                break
    return FitResult(
        model_type=model_type,
        seed=seed,
        best_epoch=best_epoch,
        best_state=best_state,
        best_dev_metrics=best_dev_metrics,
        best_train_metrics=best_train_metrics,
        best_train_positive_mass=best_train_mass,
        best_dev_positive_mass=best_dev_mass,
        history=history,
    )
