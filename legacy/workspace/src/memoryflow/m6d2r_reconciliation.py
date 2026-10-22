"""Pure helpers for the read-only M6D.2-R lineage reconciliation."""
from __future__ import annotations

import numpy as np


def seed_first(values: list[float]) -> float:
    data = np.asarray(values, dtype=np.float64)
    if data.shape != (3,):
        raise ValueError("exactly three seed-level metric scalars required")
    return float(data.mean())


def ensure_alignment(left: list[tuple], right: list[tuple]) -> None:
    if len(left) != 1824 or len(right) != 1824 or left != right:
        raise ValueError("Target/candidate/order/label alignment failure")


def checkpoint_score_binding(best_metric: float, recomputed_metric: float, tolerance: float = 1e-10) -> str:
    return "BOUND" if abs(best_metric - recomputed_metric) <= tolerance else "UNBOUND"


def no_cross_track(track: str, checkpoint_variant: str) -> None:
    expected = "M-RANK" if track == "rank" else "M-EDGE"
    if checkpoint_variant != expected:
        raise ValueError(f"cross-track checkpoint forbidden: {track}/{checkpoint_variant}")
