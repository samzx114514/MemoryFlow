"""Pure, cache-only guards for the Q4A layer-representation recovery."""
from __future__ import annotations

import numpy as np


def rowwise_cosine(reference: np.ndarray, candidate: np.ndarray) -> np.ndarray:
    """Return one cosine per matching FP32 feature row, refusing malformed input."""
    reference = np.asarray(reference)
    candidate = np.asarray(candidate)
    if reference.ndim != 2 or candidate.ndim != 2:
        raise ValueError("rowwise_cosine requires two rank-2 arrays")
    if reference.shape != candidate.shape:
        raise ValueError(f"rowwise_cosine shape mismatch: {reference.shape} != {candidate.shape}")
    left = np.linalg.norm(reference, axis=1)
    right = np.linalg.norm(candidate, axis=1)
    if np.any(left == 0) or np.any(right == 0):
        raise ValueError("rowwise_cosine refuses zero-norm rows")
    return np.einsum("nd,nd->n", reference, candidate) / (left * right)
