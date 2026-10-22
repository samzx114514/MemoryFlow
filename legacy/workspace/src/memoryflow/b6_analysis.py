from __future__ import annotations

import itertools
import math
from collections.abc import Mapping, Sequence
from statistics import mean
from typing import Any

import numpy as np
import torch
from torch import nn
from torch.nn import functional as F

from memoryflow.b3_analysis import average_precision, ndcg_at_4


RANK_METRICS = ("hit_at_1", "mrr", "map", "ndcg_at_4")


class GlobalLayerHeadReadout(nn.Module):
    def __init__(self, num_layers: int = 28, num_heads: int = 12) -> None:
        super().__init__()
        self.layer_logits = nn.Parameter(torch.zeros(num_layers))
        self.head_logits = nn.Parameter(torch.zeros(num_heads))

    def weights(self) -> tuple[torch.Tensor, torch.Tensor]:
        return self.layer_logits.softmax(dim=0), self.head_logits.softmax(dim=0)

    def forward(self, features: torch.Tensor) -> torch.Tensor:
        layer_weights, head_weights = self.weights()
        return torch.einsum("l,h,nlhc->nc", layer_weights, head_weights, features)


def per_example_pairwise_loss(scores: torch.Tensor, gold: torch.Tensor) -> torch.Tensor:
    differences = scores.unsqueeze(2) - scores.unsqueeze(1)
    pair_mask = gold.unsqueeze(2) & ~gold.unsqueeze(1)
    losses = F.softplus(-differences) * pair_mask
    return losses.sum(dim=(1, 2)) / pair_mask.sum(dim=(1, 2)).clamp_min(1)


def balanced_pairwise_loss(scores: torch.Tensor, gold: torch.Tensor, single: torch.Tensor) -> torch.Tensor:
    per_example = per_example_pairwise_loss(scores, gold)
    pairwise_defined = gold.sum(dim=1) < gold.shape[1]
    if not single.any() or single.all():
        raise ValueError("balanced loss requires both single-positive and multi-positive examples")
    if not (pairwise_defined & single).any() or not (pairwise_defined & ~single).any():
        raise ValueError("both strata require at least one example with a gold-negative pair")
    return 0.5 * per_example[pairwise_defined & single].mean() + 0.5 * per_example[pairwise_defined & ~single].mean()


def exact_random_metrics(gold_count: int, candidate_count: int = 4) -> dict[str, float]:
    if not 0 < gold_count <= candidate_count:
        raise ValueError("gold_count must be between one and candidate_count")
    gold = set(range(gold_count))
    values = {metric: [] for metric in RANK_METRICS}
    for ranking in itertools.permutations(range(candidate_count)):
        values["hit_at_1"].append(float(ranking[0] in gold))
        values["mrr"].append(1.0 / min(index for index, candidate in enumerate(ranking, 1) if candidate in gold))
        values["map"].append(average_precision([str(item) for item in ranking], {str(item) for item in gold}))
        values["ndcg_at_4"].append(ndcg_at_4([str(item) for item in ranking], {str(item) for item in gold}))
    return {metric: mean(items) for metric, items in values.items()}


def example_metrics(scores: Sequence[float], gold_labels: Sequence[bool], candidate_ids: Sequence[str]) -> dict[str, float]:
    score_map = dict(zip(candidate_ids, map(float, scores)))
    gold = {candidate_id for candidate_id, label in zip(candidate_ids, gold_labels) if label}
    ranking = sorted(candidate_ids, key=lambda candidate_id: (-score_map[candidate_id], candidate_id))
    positives = [score_map[candidate_id] for candidate_id in candidate_ids if candidate_id in gold]
    negatives = [score_map[candidate_id] for candidate_id in candidate_ids if candidate_id not in gold]
    pairs = [1.0 if positive > negative else 0.5 if positive == negative else 0.0 for positive in positives for negative in negatives]
    ordered = sorted(score_map.values(), reverse=True)
    probabilities = torch.softmax(torch.tensor(list(score_map.values()), dtype=torch.float64), dim=0).tolist()
    return {
        "hit_at_1": float(ranking[0] in gold),
        "mrr": 1.0 / min(index for index, candidate_id in enumerate(ranking, 1) if candidate_id in gold),
        "map": average_precision(ranking, gold),
        "ndcg_at_4": ndcg_at_4(ranking, gold),
        "gold_mean_score": mean(positives),
        "negative_mean_score": mean(negatives) if negatives else None,
        "gold_negative_gap": mean(positives) - mean(negatives) if negatives else None,
        "pairwise_ranking_accuracy": mean(pairs) if pairs else None,
        "top1_top2_margin": ordered[0] - ordered[1],
        "score_softmax_entropy_nats": -sum(value * math.log(value) for value in probabilities if value > 0),
        "pairwise_logistic_loss": mean(
            max(0.0, -(positive - negative)) + math.log1p(math.exp(-abs(positive - negative)))
            for positive in positives
            for negative in negatives
        ) if negatives else None,
    }


def summarize_method(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    if not rows:
        raise ValueError("rows must not be empty")
    fields = list(rows[0]["metrics"])
    summary = {}
    for field in fields:
        defined = [float(row["metrics"][field]) for row in rows if row["metrics"][field] is not None]
        summary[field] = mean(defined) if defined else None
        summary[f"{field}_defined_example_count"] = len(defined)
    singles = [row for row in rows if row["stratum"] == "single_positive"]
    multis = [row for row in rows if row["stratum"] == "multi_positive"]
    single_losses = [row["metrics"]["pairwise_logistic_loss"] for row in singles if row["metrics"]["pairwise_logistic_loss"] is not None]
    multi_losses = [row["metrics"]["pairwise_logistic_loss"] for row in multis if row["metrics"]["pairwise_logistic_loss"] is not None]
    if single_losses and multi_losses:
        summary["balanced_pairwise_loss"] = 0.5 * mean(single_losses) + 0.5 * mean(multi_losses)
    elif single_losses:
        summary["balanced_pairwise_loss"] = mean(single_losses)
    elif multi_losses:
        summary["balanced_pairwise_loss"] = mean(multi_losses)
    else:
        summary["balanced_pairwise_loss"] = None
    summary["pairwise_undefined_example_count"] = sum(row["metrics"]["pairwise_logistic_loss"] is None for row in rows)
    summary["example_count"] = len(rows)
    return summary


def cluster_bootstrap_difference(
    rows: Sequence[Mapping[str, Any]],
    left_field: str,
    right_field: str,
    metric: str,
    iterations: int,
    seed: int,
) -> dict[str, float]:
    clusters = sorted({str(row["run_id"]) for row in rows})
    cluster_index = {cluster: index for index, cluster in enumerate(clusters)}
    sums = np.zeros(len(clusters), dtype=np.float64)
    counts = np.zeros(len(clusters), dtype=np.float64)
    differences = []
    for row in rows:
        difference = float(row[left_field][metric]) - float(row[right_field][metric])
        index = cluster_index[str(row["run_id"])]
        sums[index] += difference
        counts[index] += 1
        differences.append(difference)
    rng = np.random.default_rng(seed)
    draws = rng.integers(0, len(clusters), size=(iterations, len(clusters)))
    estimates = sums[draws].sum(axis=1) / counts[draws].sum(axis=1)
    return {
        "point_estimate": float(np.mean(differences)),
        "ci_lower_95": float(np.quantile(estimates, 0.025)),
        "ci_upper_95": float(np.quantile(estimates, 0.975)),
        "bootstrap_iterations": iterations,
        "cluster_count": len(clusters),
    }


def weight_diagnostics(weights: torch.Tensor) -> dict[str, Any]:
    values = weights.detach().double().cpu().numpy()
    entropy = float(-np.sum(values * np.log(values + 1e-300)))
    return {
        "weights": values.tolist(),
        "entropy_nats": entropy,
        "effective_number": float(np.exp(entropy)),
        "maximum_weight": float(values.max()),
        "argmax_index": int(values.argmax()),
        "single_component_above_0_95": bool(values.max() > 0.95),
    }
