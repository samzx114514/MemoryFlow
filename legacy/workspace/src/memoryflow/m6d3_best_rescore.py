"""Frozen M6B best-checkpoint rescore primitives for M6D.3."""
from __future__ import annotations

import numpy as np

from memoryflow.m6d1_vectorized import edge_bootstrap_chunked
from memoryflow.m6d2_seedfirst import seed_first_delta, summary


def require_best_binding(expected: str, actual: str) -> None:
    if expected != actual:
        raise ValueError("checkpoint SHA mismatch")


def reject_unbound_prediction(path: str) -> None:
    if path.endswith("dev_scores.jsonl"):
        raise ValueError("UNBOUND final-epoch prediction input forbidden")


def seed_first_bootstrap(seed_deltas: list[np.ndarray]) -> np.ndarray:
    return seed_first_delta(seed_deltas)


def edge_seed_first_bootstrap(labels: np.ndarray, rsym: list[np.ndarray], m6b: list[np.ndarray], indices: np.ndarray) -> np.ndarray:
    if len(rsym) != 3 or len(m6b) != 3:
        raise ValueError("exactly three seed score matrices required")
    values = [edge_bootstrap_chunked(labels.reshape(-1), left.reshape(-1), right.reshape(-1), indices, "auprc", chunk_size=128) for left, right in zip(rsym, m6b)]
    return seed_first_delta(values)


def strict_json_summary(values: np.ndarray) -> dict[str, object]:
    return summary(values)
