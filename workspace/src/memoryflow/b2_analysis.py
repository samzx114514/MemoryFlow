from __future__ import annotations

import hashlib
from collections.abc import Mapping, Sequence
from statistics import mean
from typing import Any


SELECTION_SEED = "memoryflow-b2-selection-v1"
PERMUTATION_SEED = "memoryflow-b2-permutation-v1"


def _stable_digest(*parts: str) -> str:
    return hashlib.sha256("\x1f".join(parts).encode("utf-8")).hexdigest()


def select_b2_examples(
    rows: Sequence[Mapping[str, Any]], single_count: int = 4, multi_count: int = 4
) -> list[Mapping[str, Any]]:
    """Select examples before model execution using a fixed, model-independent hash."""
    singles = [row for row in rows if len(row["gold_source_ids"]) == 1]
    multis = [row for row in rows if len(row["gold_source_ids"]) > 1]
    singles.sort(key=lambda row: _stable_digest(SELECTION_SEED, "single", row["example_id"]))
    multis.sort(key=lambda row: _stable_digest(SELECTION_SEED, "multi", row["example_id"]))
    return singles[:single_count] + multis[:multi_count]


def deterministic_candidate_permutation(example: Mapping[str, Any]) -> list[int]:
    candidates = example["candidates"]
    order = sorted(
        range(len(candidates)),
        key=lambda index: _stable_digest(
            PERMUTATION_SEED, example["example_id"], candidates[index]["id"]
        ),
    )
    identity = list(range(len(candidates)))
    if len(order) > 1 and order == identity:
        order = order[1:] + order[:1]
    return order


def normalize_source_anchor_scores(scores: Sequence[float]) -> list[float]:
    total = sum(scores)
    if total <= 0:
        return [0.0 for _ in scores]
    return [float(score / total) for score in scores]


def rank_candidate_ids(scores_by_id: Mapping[str, float]) -> list[str]:
    return sorted(scores_by_id, key=lambda candidate_id: (-scores_by_id[candidate_id], candidate_id))


def diagnostic_metrics(records: Sequence[Mapping[str, Any]], score_field: str) -> dict[str, Any]:
    hit_at_1 = []
    reciprocal_ranks = []
    gold_scores = []
    negative_scores = []
    rankings = []
    for record in records:
        scores_by_id = record[score_field]
        gold_ids = set(record["gold_source_ids"])
        ranking = rank_candidate_ids(scores_by_id)
        hit_at_1.append(float(ranking[0] in gold_ids))
        first_gold_rank = min(index for index, candidate_id in enumerate(ranking, 1) if candidate_id in gold_ids)
        reciprocal_ranks.append(1.0 / first_gold_rank)
        gold_scores.extend(scores_by_id[candidate_id] for candidate_id in ranking if candidate_id in gold_ids)
        negative_scores.extend(scores_by_id[candidate_id] for candidate_id in ranking if candidate_id not in gold_ids)
        rankings.append(
            {
                "example_id": record["example_id"],
                "ranking": ranking,
                "gold_source_ids": sorted(gold_ids),
                "scores": {candidate_id: scores_by_id[candidate_id] for candidate_id in ranking},
            }
        )
    gold_mean = mean(gold_scores)
    negative_mean = mean(negative_scores)
    return {
        "score_field": score_field,
        "example_count": len(records),
        "hit_at_1": mean(hit_at_1),
        "mrr": mean(reciprocal_ranks),
        "gold_candidate_mean_score": gold_mean,
        "negative_candidate_mean_score": negative_mean,
        "gold_minus_negative_mean": gold_mean - negative_mean,
        "rankings": rankings,
    }


def classify_semantic_signal(
    metrics_by_method: Mapping[str, Mapping[str, Any]],
    permutation: Mapping[str, Any],
    content_sensitivity: Mapping[str, Any],
) -> tuple[str, list[str]]:
    """Apply fixed diagnostic thresholds; never search layers or heads."""
    methods = list(metrics_by_method.values())
    metric_positive = all(
        metric["hit_at_1"] >= 0.5
        and metric["mrr"] >= 0.6
        and metric["gold_minus_negative_mean"] > 0
        for metric in methods
    )
    permutation_stable = (
        permutation["mean_exact_ranking_consistency"] >= 0.5
        and permutation["max_aligned_score_change"] <= 0.15
    )
    content_sensitive = content_sensitivity["mean_absolute_changed_source_score_delta"] >= 1e-5
    reasons = [
        f"both_fixed_metrics_positive={metric_positive}",
        f"permutation_stable={permutation_stable}",
        f"content_sensitive={content_sensitive}",
    ]
    if metric_positive and permutation_stable and content_sensitive:
        return "B2_SEMANTIC_SIGNAL_POSITIVE", reasons

    metric_absent = all(
        metric["hit_at_1"] <= 0.375 and metric["gold_minus_negative_mean"] <= 0
        for metric in methods
    )
    if metric_absent and not content_sensitive:
        return "B2_SEMANTIC_SIGNAL_ABSENT", reasons
    return "B2_SEMANTIC_SIGNAL_WEAK", reasons
