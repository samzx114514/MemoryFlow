"""Pure helpers for the LC-Sent-15 frozen Qwen F_mean baseline."""

from __future__ import annotations

import math
from typing import Mapping, Sequence


FORBIDDEN_PATH_PARTS = ("blind", "reserve", "multi_positive", "mixed_catalog")


def assert_allowed_path(path: str) -> None:
    lowered = path.lower()
    if any(part in lowered for part in FORBIDDEN_PATH_PARTS):
        raise ValueError(f"forbidden input path: {path}")


def rank_scores(scores: Mapping[str, float]) -> list[str]:
    if any(not math.isfinite(float(value)) for value in scores.values()):
        raise ValueError("non-finite score")
    return sorted(scores, key=lambda source_id: (-float(scores[source_id]), source_id))


def single_positive_metrics(ranks: Sequence[int]) -> dict[str, float | int]:
    if not ranks or any(rank < 1 for rank in ranks):
        raise ValueError("ranks must be nonempty positive integers")
    total = len(ranks)
    return {
        "target_count": total,
        "hit_at_1": sum(rank == 1 for rank in ranks) / total,
        "mrr": sum(1.0 / rank for rank in ranks) / total,
        "ndcg_at_5": sum((1.0 / math.log2(rank + 1)) if rank <= 5 else 0.0 for rank in ranks) / total,
        "mean_gold_rank": sum(ranks) / total,
        "top1_successes": sum(rank == 1 for rank in ranks),
        "top1_failures": sum(rank != 1 for rank in ranks),
    }
