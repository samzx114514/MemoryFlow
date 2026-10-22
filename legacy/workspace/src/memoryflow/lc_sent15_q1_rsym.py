"""Frozen M6D R-SYM ranking helpers for LC-Sent-15 Q1."""
from __future__ import annotations

import math
from collections.abc import Sequence

import numpy as np
import torch

from memoryflow.source_prior_relational import SymmetricRelation, parameter_count


DIM = 3584
CANDIDATE_SIZE = 15
INPUT_DIM = 2 * DIM + 1
PARAMETER_COUNT = 917_889


def normalize_rows(values: np.ndarray) -> np.ndarray:
    values = np.asarray(values, dtype=np.float32)
    norms = np.linalg.norm(values, axis=1, keepdims=True)
    if not np.isfinite(values).all() or not np.isfinite(norms).all() or np.any(norms <= 0):
        raise ValueError("features must be finite nonzero vectors")
    return values / norms


def validate_rsym_contract() -> None:
    model = SymmetricRelation(DIM)
    if parameter_count(model) != PARAMETER_COUNT:
        raise RuntimeError("R-SYM parameter count differs from frozen M6D contract")
    if model.net[0].in_features != INPUT_DIM or model.net[0].out_features != 128:
        raise RuntimeError("R-SYM input/hidden dimensions differ from frozen contract")
    if model.net[1].__class__.__name__ != "GELU" or model.net[2].p != 0.1:
        raise RuntimeError("R-SYM activation/dropout differs from frozen contract")


def ranking_metrics_from_ranks(ranks: Sequence[int]) -> dict[str, float | int]:
    values = np.asarray(ranks, dtype=np.int64)
    if values.ndim != 1 or len(values) == 0 or np.any(values < 1) or np.any(values > CANDIDATE_SIZE):
        raise ValueError("invalid single-positive ranks")
    return {
        "target_count": int(len(values)),
        "hit_at_1": float(np.mean(values == 1)),
        "mrr": float(np.mean(1.0 / values)),
        "ndcg_at_5": float(np.mean(np.where(values <= 5, 1.0 / np.log2(values + 1), 0.0))),
        "mean_gold_rank": float(np.mean(values)),
        "top1_successes": int(np.sum(values == 1)),
        "top1_failures": int(np.sum(values != 1)),
    }


def rank_ids(candidate_ids: Sequence[str], scores: Sequence[float]) -> list[str]:
    if len(candidate_ids) != CANDIDATE_SIZE or len(set(candidate_ids)) != CANDIDATE_SIZE:
        raise ValueError("candidate IDs must be a unique c15 group")
    if len(scores) != CANDIDATE_SIZE or not np.isfinite(np.asarray(scores, dtype=float)).all():
        raise ValueError("invalid candidate scores")
    return sorted(candidate_ids, key=lambda source_id: (-float(scores[candidate_ids.index(source_id)]), source_id))


def listwise_single_positive_loss(logits: torch.Tensor, labels: torch.Tensor, group_ids: torch.Tensor) -> torch.Tensor:
    """M6D all-positive distribution loss; c15 makes this ordinary CE per group."""
    losses: list[torch.Tensor] = []
    for group in torch.unique(group_ids, sorted=True):
        mask = group_ids == group
        group_labels = labels[mask]
        if int(group_labels.sum().item()) != 1:
            raise ValueError("LC-Sent-15 Q1 requires exactly one positive per group")
        losses.append(-torch.log_softmax(logits[mask], dim=0)[group_labels.bool()][0])
    if not losses:
        raise ValueError("empty ranking batch")
    return torch.stack(losses).mean()


def bootstrap_seed_first(
    ranks_by_seed: np.ndarray, bm25_ranks: np.ndarray, indices: np.ndarray
) -> dict[str, dict[str, float | list[float]]]:
    """Metric first per seed, then mean scalar across seeds (never mean logits)."""
    if ranks_by_seed.shape[0] != 3 or ranks_by_seed.shape[1] != len(bm25_ranks):
        raise ValueError("unexpected seed/target ranks")
    if indices.ndim != 2 or indices.shape[1] != len(bm25_ranks):
        raise ValueError("bootstrap index shape mismatch")
    functions = {
        "hit_at_1": lambda ranks: ranks == 1,
        "mrr": lambda ranks: 1.0 / ranks,
        "ndcg_at_5": lambda ranks: np.where(ranks <= 5, 1.0 / np.log2(ranks + 1), 0.0),
    }
    result: dict[str, dict[str, float | list[float]]] = {}
    for name, fn in functions.items():
        rsym = fn(ranks_by_seed.astype(float))
        bm25 = fn(bm25_ranks.astype(float))
        point_rsym = float(rsym.mean(axis=1).mean())
        point_bm25 = float(bm25.mean())
        sampled_rsym = rsym[:, indices].mean(axis=2).mean(axis=0)
        sampled_bm25 = bm25[indices].mean(axis=1)
        delta = sampled_rsym - sampled_bm25
        result[name] = {
            "rsym_mean": point_rsym,
            "bm25": point_bm25,
            "delta": point_rsym - point_bm25,
            "delta_ci95": [float(np.quantile(delta, 0.025)), float(np.quantile(delta, 0.975))],
        }
    return result
