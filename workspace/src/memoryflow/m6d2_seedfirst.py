"""Seed-first primary-metric helpers for the immutable M6D.2 closure."""
from __future__ import annotations

import math
from typing import Iterable

import numpy as np

from memoryflow.m6d1_vectorized import edge_bootstrap_chunked, ranking_group_metrics


def finite(value: float | None) -> float | None:
    return float(value) if value is not None and math.isfinite(float(value)) else None


def require_single_seed(scores: np.ndarray) -> np.ndarray:
    """Guard against the rejected mean-seed-logits protocol."""
    values = np.asarray(scores)
    if values.ndim != 2 or values.shape[1] != 8:
        raise ValueError("single-seed [target, candidate] scores required")
    return values


def average_precision(labels: np.ndarray, scores: np.ndarray, weights: np.ndarray | None = None) -> float | None:
    """Stable AP, equivalent to explicit integer repetition when weighted."""
    labels = np.asarray(labels, dtype=np.int8).reshape(-1)
    scores = np.asarray(scores, dtype=np.float64).reshape(-1)
    if weights is None:
        weights = np.ones(len(labels), dtype=np.int64)
    else:
        weights = np.asarray(weights, dtype=np.int64).reshape(-1)
    if len(labels) != len(scores) or len(labels) != len(weights):
        raise ValueError("label/score/weight shape mismatch")
    positive = int((weights * labels).sum())
    negative = int((weights * (1 - labels)).sum())
    if positive == 0 or negative == 0:
        return None
    order = np.argsort(-scores, kind="stable")
    y, w = labels[order], weights[order]
    prior = np.cumsum(w) - w
    prior_pos = np.cumsum(w * y) - w * y
    # Sum precision at each explicitly repeated positive without expanding it.
    maximum = int(w.sum())
    harmonic = np.zeros(maximum + 1, dtype=np.float64)
    harmonic[1:] = np.cumsum(1.0 / np.arange(1, maximum + 1, dtype=np.float64))
    contribution = w.astype(np.float64) - (prior - prior_pos) * (harmonic[prior + w] - harmonic[prior])
    return float((contribution * y).sum() / positive)


def summary(values: np.ndarray) -> dict[str, object]:
    data = np.asarray(values, dtype=np.float64)
    if data.size == 0 or not np.all(np.isfinite(data)):
        return {"delta": None, "ci95": None, "p_two_sided": None, "status": "INSUFFICIENT"}
    return {
        "delta": float(data.mean()),
        "ci95": [float(np.quantile(data, 0.025)), float(np.quantile(data, 0.975))],
        "p_two_sided": float(min(1.0, 2 * min(float((data <= 0).mean()), float((data >= 0).mean())))),
        "status": "OK",
    }


def projected_counts(full_indices: np.ndarray, selected_global_ids: Iterable[int], groups: int) -> np.ndarray:
    """Project immutable full-Dev bootstrap draws onto a preregistered subset.

    No bootstrap index is generated here.  Each returned row retains the exact
    multiplicity assigned by the fixed full-Dev draw stream to subset groups.
    """
    full_indices = np.asarray(full_indices)
    ids = np.asarray(tuple(selected_global_ids), dtype=np.int64)
    if ids.ndim != 1 or not len(ids) or np.any(ids < 0) or np.any(ids >= groups):
        raise ValueError("invalid selected global target ids")
    count_full = np.zeros((len(full_indices), groups), dtype=np.int16)
    np.add.at(count_full, (np.arange(len(full_indices))[:, None], full_indices), 1)
    result = count_full[:, ids]
    if not np.all(result.sum(axis=1) > 0):
        raise ValueError("projected bootstrap produced an empty subset replicate")
    return result


def rank_seed_delta(labels: np.ndarray, left: np.ndarray, right: np.ndarray, counts: np.ndarray) -> dict[str, np.ndarray]:
    """Per-seed paired macro deltas; callers may average only these scalars."""
    left, right = require_single_seed(left), require_single_seed(right)
    labels = np.asarray(labels, dtype=np.int8)
    if labels.shape != left.shape or right.shape != left.shape or counts.shape[1] != len(labels):
        raise ValueError("ranking shapes do not align")
    out = {}
    left_metrics, right_metrics = ranking_group_metrics(labels, left), ranking_group_metrics(labels, right)
    denom = counts.sum(axis=1)
    for metric in ("mrr", "hit_at_1", "ndcg_at_5"):
        per_target = left_metrics[metric] - right_metrics[metric]
        out[metric] = (counts * per_target[None, :]).sum(axis=1) / denom
    return out


def ap_seed_delta(labels: np.ndarray, left: np.ndarray, right: np.ndarray, counts: np.ndarray) -> np.ndarray:
    """Per-seed paired AUPRC deltas using integer target multiplicities."""
    left, right = require_single_seed(left), require_single_seed(right)
    labels = np.asarray(labels, dtype=np.int8)
    if labels.shape != left.shape or right.shape != left.shape or counts.shape[1] != len(labels):
        raise ValueError("edge shapes do not align")
    # M6D.1-P already validated this chunked AP implementation.  Scores remain
    # single-seed throughout; callers only reduce the returned scalar deltas.
    return edge_bootstrap_chunked(labels.reshape(-1), left.reshape(-1), right.reshape(-1), counts, "auprc", chunk_size=128)


def seed_first_delta(values: list[np.ndarray]) -> np.ndarray:
    """The sole allowed cross-seed operation: mean of seed-level scalar deltas."""
    if len(values) != 3:
        raise ValueError("exactly three seed-level metric arrays required")
    if any(np.asarray(v).ndim != 1 for v in values):
        raise ValueError("seed-level scalar arrays required; logits are forbidden")
    lengths = {len(v) for v in values}
    if len(lengths) != 1:
        raise ValueError("seed bootstrap coverage mismatch")
    return np.mean(np.stack(values, axis=0), axis=0)
