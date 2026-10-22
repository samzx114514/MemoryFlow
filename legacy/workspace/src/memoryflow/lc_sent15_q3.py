"""Pure functions for frozen LC-Sent-15 Q3 OOF late fusion."""
from __future__ import annotations

import hashlib
import numpy as np

from memoryflow.lc_sent15_q1_rsym import rank_ids, ranking_metrics_from_ranks

ALPHAS = tuple(round(i * .05, 2) for i in range(21))
FOLD_PREFIX = "LC-Sent15-Q3-OOF:"


def fold_for_document(document_id: str) -> int:
    digest = hashlib.sha256((FOLD_PREFIX + document_id).encode("utf-8")).hexdigest()
    return int(digest[:16], 16) % 5


def group_z(values: np.ndarray) -> np.ndarray:
    values = np.asarray(values, dtype=np.float64)
    scale = np.sqrt(np.mean((values - values.mean()) ** 2))
    return np.zeros_like(values) if scale <= 1e-12 else (values - values.mean()) / scale


def ranks(candidate_ids: list[str], values: np.ndarray, gold_source_id: str) -> tuple[list[str], int]:
    ordered = rank_ids(candidate_ids, np.asarray(values, dtype=float).tolist())
    return ordered, ordered.index(gold_source_id) + 1


def metric_from_ranks(gold_ranks: list[int]) -> dict:
    return ranking_metrics_from_ranks(gold_ranks)


def choose_alpha(rows: dict[float, list[dict]]) -> float:
    def key(alpha: float) -> tuple:
        values = rows[alpha]
        return (-np.mean([x["hit_at_1"] for x in values]), -np.mean([x["mrr"] for x in values]), -np.mean([x["ndcg_at_5"] for x in values]), alpha)
    return min(rows, key=key)
