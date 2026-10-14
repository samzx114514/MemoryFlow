"""Frozen, seed-first late-fusion helpers for M7.

The module intentionally accepts score arrays for one seed at a time.  It
therefore makes the rejected mean-seed-logit protocol structurally awkward:
cross-seed reduction is allowed only over already computed scalar metrics.
"""
from __future__ import annotations

import math
from typing import Iterable

import numpy as np

from memoryflow.m6d1_vectorized import ranking_group_metrics, weighted_edge_metric
from memoryflow.m6d2_seedfirst import average_precision, rank_seed_delta, seed_first_delta, summary


ALPHAS = tuple(round(value / 10, 1) for value in range(11))
ZSCORE_EPSILON = 1e-12


def require_single_seed(scores: np.ndarray) -> np.ndarray:
    value = np.asarray(scores, dtype=np.float64)
    if value.ndim != 2 or value.shape[1] != 8:
        raise ValueError("single-seed [target, candidate] score matrix required")
    if not np.all(np.isfinite(value)):
        raise ValueError("scores must be finite")
    return value


def group_zscore(scores: np.ndarray, epsilon: float = ZSCORE_EPSILON) -> tuple[np.ndarray, np.ndarray]:
    value = require_single_seed(scores)
    mean = value.mean(axis=1, keepdims=True)
    std = value.std(axis=1, keepdims=True)
    zero = (std[:, 0] < epsilon)
    output = np.zeros_like(value)
    valid = ~zero
    output[valid] = (value[valid] - mean[valid]) / std[valid]
    return output, zero


def train_zscore(train_scores: np.ndarray, apply_scores: np.ndarray, epsilon: float = ZSCORE_EPSILON) -> tuple[np.ndarray, dict[str, float | bool]]:
    train = require_single_seed(train_scores)
    apply = require_single_seed(apply_scores)
    mean = float(train.mean())
    std = float(train.std())
    if std < epsilon:
        return np.zeros_like(apply), {"mean": mean, "std": std, "zeroed": True}
    return (apply - mean) / std, {"mean": mean, "std": std, "zeroed": False}


def fuse(alpha: float, semantic: np.ndarray, lexical: np.ndarray) -> np.ndarray:
    if alpha not in ALPHAS:
        raise ValueError("alpha outside preregistered grid")
    semantic = require_single_seed(semantic)
    lexical = require_single_seed(lexical)
    if semantic.shape != lexical.shape:
        raise ValueError("fusion matrices do not align")
    return alpha * semantic + (1.0 - alpha) * lexical


def ranking_metrics(labels: np.ndarray, scores: np.ndarray) -> dict[str, float]:
    labels = np.asarray(labels, dtype=np.int8)
    values = ranking_group_metrics(labels, require_single_seed(scores))
    return {name: float(array.mean()) for name, array in values.items()}


def auroc(labels: np.ndarray, scores: np.ndarray) -> float | None:
    """Tie-corrected unweighted AUROC without an optional sklearn dependency."""
    y = np.asarray(labels, dtype=np.int8).reshape(-1)
    s = np.asarray(scores, dtype=np.float64).reshape(-1)
    pos, neg = int(y.sum()), int(len(y) - y.sum())
    if pos == 0 or neg == 0:
        return None
    order = np.argsort(s, kind="stable")
    ranks = np.empty(len(s), dtype=np.float64)
    start = 0
    while start < len(s):
        stop = start + 1
        while stop < len(s) and s[order[stop]] == s[order[start]]:
            stop += 1
        ranks[order[start:stop]] = (start + 1 + stop) / 2.0
        start = stop
    rank_sum = float(ranks[y == 1].sum())
    return (rank_sum - pos * (pos + 1) / 2.0) / (pos * neg)


def edge_metrics(labels: np.ndarray, scores: np.ndarray) -> dict[str, float | None]:
    matrix = require_single_seed(scores)
    return {"auprc": average_precision(labels, matrix), "auroc": auroc(labels, matrix)}


def select_alpha(curve: Iterable[dict[str, float]], primary: str) -> float:
    rows = list(curve)
    if not rows:
        raise ValueError("empty alpha curve")
    best = max(float(row[primary]) for row in rows)
    tied = [row for row in rows if best - float(row[primary]) < 1e-6]
    # Higher alpha is closer to frozen R-SYM and is the prespecified fallback.
    return float(max(tied, key=lambda row: float(row["alpha"]))["alpha"])


def seed_first_rank_bootstrap(labels: np.ndarray, left: list[np.ndarray], right: list[np.ndarray], counts: np.ndarray) -> dict[str, np.ndarray]:
    if len(left) != 3 or len(right) != 3:
        raise ValueError("exactly three seed matrices required")
    return {
        metric: seed_first_delta([rank_seed_delta(labels, a, b, counts)[metric] for a, b in zip(left, right)])
        for metric in ("mrr", "hit_at_1", "ndcg_at_5")
    }


def seed_first_ap_bootstrap(labels: np.ndarray, left: list[np.ndarray], right: list[np.ndarray], counts: np.ndarray, chunk_size: int = 128) -> np.ndarray:
    """Seed-first AP deltas from *multiplicities*, never bootstrap indices.

    `m6d2_seedfirst.ap_seed_delta` accepts bootstrap index rows and must not be
    passed projected count matrices.  M7 needs those counts for hard subsets,
    so it evaluates the trusted weighted AP primitive directly.
    """
    if len(left) != 3 or len(right) != 3:
        raise ValueError("exactly three seed matrices required")
    labels = np.asarray(labels, dtype=np.int8)
    if counts.ndim != 2 or counts.shape[1] != len(labels):
        raise ValueError("target multiplicity matrix mismatch")
    values = []
    for a, b in zip(left, right):
        a, b = require_single_seed(a), require_single_seed(b)
        pieces = []
        for start in range(0, len(counts), chunk_size):
            current = counts[start : start + chunk_size]
            pieces.append(weighted_edge_metric(labels.reshape(-1), a.reshape(-1), current, "auprc") - weighted_edge_metric(labels.reshape(-1), b.reshape(-1), current, "auprc"))
        values.append(np.concatenate(pieces))
    return seed_first_delta(values)


def strict_summary(values: np.ndarray) -> dict[str, object]:
    return summary(np.asarray(values, dtype=np.float64))


def target_wlt(labels: np.ndarray, left: np.ndarray, right: np.ndarray, metric: str) -> dict[str, int]:
    if metric != "mrr":
        raise ValueError("target win/loss/tie diagnostic is defined for MRR")
    a = ranking_group_metrics(labels, left)["mrr"]
    b = ranking_group_metrics(labels, right)["mrr"]
    return {"wins": int((a > b).sum()), "losses": int((a < b).sum()), "ties": int((a == b).sum())}


def assert_seed_first_scalar(values: list[np.ndarray]) -> np.ndarray:
    """Explicitly named guard used by the M7 runner and tests."""
    return seed_first_delta(values)
