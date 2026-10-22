"""Document-cluster statistics and feature aggregation for LongCite C2B."""

from __future__ import annotations

from collections import defaultdict
import hashlib
from typing import Mapping, Sequence

import numpy as np


SPLIT_SEED = "memoryflow-longcite-hard-v1-split"
WINDOWS = {
    "last1": tuple(range(27, 28)),
    "last2": tuple(range(26, 28)),
    "last4": tuple(range(24, 28)),
    "last8": tuple(range(20, 28)),
    "all_layers": tuple(range(28)),
}
WINDOW_TIE_PRIORITY = ("last4", "last2", "last8", "last1", "all_layers")


def stable_document_split(
    document_ids: Sequence[str], *, seed: str = SPLIT_SEED
) -> dict[str, list[str]]:
    unique = sorted(set(document_ids))
    if len(unique) != 27:
        raise ValueError(f"expected 27 document groups, got {len(unique)}")
    ordered = sorted(unique, key=lambda value: hashlib.sha256((seed + value).encode()).hexdigest())
    return {"train": ordered[:17], "dev": ordered[17:22], "test": ordered[22:27]}


def aggregate_feature_window(features: np.ndarray, layers: Sequence[int]) -> np.ndarray:
    """Average selected layers and all heads into candidate scores."""
    if features.ndim != 4:
        raise ValueError("features must have shape [examples,layers,heads,candidates]")
    if not layers or min(layers) < 0 or max(layers) >= features.shape[1]:
        raise ValueError("invalid layer window")
    scores = features[:, list(layers)].mean(axis=(1, 2))
    denominator = scores.sum(axis=1, keepdims=True)
    if not np.isfinite(scores).all() or np.any(denominator <= 0):
        raise ValueError("feature scores must be finite and have positive sums")
    return scores / denominator


def select_dev_window(dev_mrr: Mapping[str, float]) -> str:
    if set(dev_mrr) != set(WINDOWS):
        raise ValueError("all preregistered windows are required")
    best = max(dev_mrr.values())
    return next(name for name in WINDOW_TIE_PRIORITY if dev_mrr[name] == best)


def cluster_bootstrap_difference(
    first: Sequence[float],
    second: Sequence[float],
    clusters: Sequence[str],
    *,
    iterations: int,
    seed: int,
) -> dict[str, float | int | bool]:
    first_array = np.asarray(first, dtype=np.float64)
    second_array = np.asarray(second, dtype=np.float64)
    if first_array.shape != second_array.shape or first_array.shape != (len(clusters),):
        raise ValueError("values and clusters must have matching one-dimensional shapes")
    grouped: dict[str, list[int]] = defaultdict(list)
    for index, cluster in enumerate(clusters):
        grouped[cluster].append(index)
    cluster_ids = sorted(grouped)
    rng = np.random.default_rng(seed)
    differences = np.empty(iterations, dtype=np.float64)
    for iteration in range(iterations):
        sampled = rng.choice(cluster_ids, size=len(cluster_ids), replace=True)
        indices = [index for cluster in sampled for index in grouped[str(cluster)]]
        differences[iteration] = np.mean(first_array[indices] - second_array[indices])
    point = float(np.mean(first_array - second_array))
    low, high = np.quantile(differences, [0.025, 0.975])
    return {
        "iterations": iterations,
        "cluster_count": len(cluster_ids),
        "mean_difference": point,
        "ci95_low": float(low),
        "ci95_high": float(high),
        "ci_crosses_zero": bool(low <= 0 <= high),
    }

