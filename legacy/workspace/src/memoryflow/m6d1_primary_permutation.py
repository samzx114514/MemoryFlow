"""Single-seed primary permutation-bootstrap primitives for M6D.1-P."""
from __future__ import annotations

import numpy as np

from memoryflow.m6d1_vectorized import edge_bootstrap_chunked, ranking_group_metrics


RANK_METRICS = ("mrr", "hit_at_1", "ndcg_at_5")


def require_single_seed(scores: np.ndarray) -> np.ndarray:
    """Reject any score tensor that still carries a seed axis."""
    values = np.asarray(scores)
    if values.ndim != 3 or values.shape[1:] != (228, 8):
        raise ValueError("worker requires exactly one seed: [permutation, target, candidate]")
    return values


def average_precision_explicit(labels: np.ndarray, scores: np.ndarray, indices: np.ndarray) -> float:
    counts = np.bincount(indices, minlength=228).repeat(8)
    y = np.repeat(labels.reshape(-1), counts)
    z = np.repeat(scores.reshape(-1), counts)
    positives = int(y.sum())
    if not positives:
        raise ValueError("AUPRC undefined without positives")
    order = np.argsort(-z, kind="stable")
    ranked = y[order]
    return float((np.cumsum(ranked) / np.arange(1, len(ranked) + 1))[ranked.astype(bool)].sum() / positives)


def seed_rank_bootstrap(labels: np.ndarray, original: np.ndarray, permuted: np.ndarray, indices: np.ndarray) -> dict[str, np.ndarray]:
    """Metric(original) minus mean_permutation(metric(permutation))."""
    perms = require_single_seed(permuted)
    if original.shape != (228, 8):
        raise ValueError("single-seed original must be [target, candidate]")
    if np.array_equal(original, perms[0]) and all(np.array_equal(original, score) for score in perms[1:]):
        return {metric: np.zeros(len(indices), dtype=np.float64) for metric in RANK_METRICS}
    original_metrics = ranking_group_metrics(labels, original)
    perm_metrics = {
        metric: np.mean([ranking_group_metrics(labels, score)[metric] for score in perms], axis=0)
        for metric in RANK_METRICS
    }
    return {metric: original_metrics[metric][indices].mean(axis=1) - perm_metrics[metric][indices].mean(axis=1) for metric in RANK_METRICS}


def seed_ap_bootstrap(labels: np.ndarray, original: np.ndarray, permuted: np.ndarray, indices: np.ndarray) -> np.ndarray:
    """Vectorized AP with the same seed/permutation ordering as the protocol."""
    perms = require_single_seed(permuted)
    flat_labels = labels.reshape(-1)
    flat_original = original.reshape(-1)
    if np.array_equal(original, perms[0]) and all(np.array_equal(original, score) for score in perms[1:]):
        return np.zeros(len(indices), dtype=np.float64)
    per_permutation = [
        edge_bootstrap_chunked(flat_labels, flat_original, score.reshape(-1), indices, "auprc", chunk_size=min(500, len(indices)))
        for score in perms
    ]
    return np.mean(per_permutation, axis=0)


def seed_ap_bootstrap_slow(labels: np.ndarray, original: np.ndarray, permuted: np.ndarray, indices: np.ndarray) -> np.ndarray:
    """Reference implementation: score each permutation before averaging AP."""
    perms = require_single_seed(permuted)
    output = []
    for row in indices:
        left = average_precision_explicit(labels, original, row)
        right = np.mean([average_precision_explicit(labels, score, row) for score in perms])
        output.append(left - right)
    return np.asarray(output, dtype=np.float64)


def seed_rank_bootstrap_slow(labels: np.ndarray, original: np.ndarray, permuted: np.ndarray, indices: np.ndarray) -> dict[str, np.ndarray]:
    perms = require_single_seed(permuted)
    original_metrics = ranking_group_metrics(labels, original)
    perm_metrics = [ranking_group_metrics(labels, score) for score in perms]
    values = {metric: [] for metric in RANK_METRICS}
    for row in indices:
        for metric in RANK_METRICS:
            values[metric].append(float(original_metrics[metric][row].mean() - np.mean([entry[metric][row].mean() for entry in perm_metrics])))
    return {metric: np.asarray(value, dtype=np.float64) for metric, value in values.items()}


def percentile_summary(values: np.ndarray) -> dict[str, object]:
    values = np.asarray(values, dtype=np.float64)
    return {
        "delta": float(values.mean()),
        "ci95": [float(np.quantile(values, .025)), float(np.quantile(values, .975))],
        "p_two_sided": float(min(1.0, 2 * min((values <= 0).mean(), (values >= 0).mean()))),
    }
