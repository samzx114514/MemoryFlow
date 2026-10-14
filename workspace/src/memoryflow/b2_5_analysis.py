from __future__ import annotations

import itertools
import math
from collections import defaultdict
from collections.abc import Mapping, Sequence
from statistics import mean
from typing import Any

import numpy as np


METHOD_FIELDS = {
    "last_layer_head_mean": "last_layer_scores_by_id",
    "last_four_layers_head_mean": "last_four_layers_scores_by_id",
}


def normalize(scores: Sequence[float]) -> list[float]:
    total = float(sum(scores))
    if total <= 0:
        return [0.0 for _ in scores]
    return [float(value / total) for value in scores]


def entropy(scores: Sequence[float]) -> float:
    return -sum(value * math.log(value) for value in scores if value > 0)


def average_ranks(values: Sequence[float]) -> list[float]:
    order = sorted(range(len(values)), key=lambda index: values[index])
    ranks = [0.0] * len(values)
    cursor = 0
    while cursor < len(order):
        end = cursor + 1
        while end < len(order) and values[order[end]] == values[order[cursor]]:
            end += 1
        rank = (cursor + 1 + end) / 2
        for index in order[cursor:end]:
            ranks[index] = rank
        cursor = end
    return ranks


def pearson(left: Sequence[float], right: Sequence[float]) -> float | None:
    if len(left) != len(right) or len(left) < 2:
        return None
    x = np.asarray(left, dtype=float)
    y = np.asarray(right, dtype=float)
    if np.allclose(x, x[0]) or np.allclose(y, y[0]):
        return None
    return float(np.corrcoef(x, y)[0, 1])


def spearman(left: Sequence[float], right: Sequence[float]) -> float | None:
    return pearson(average_ranks(left), average_ranks(right))


def expected_random_ranking(gold_count: int, candidate_count: int = 4) -> dict[str, float]:
    if not 0 < gold_count <= candidate_count:
        raise ValueError("gold_count must be between one and candidate_count")
    gold = set(range(gold_count))
    hit_values = []
    rr_values = []
    for ranking in itertools.permutations(range(candidate_count)):
        hit_values.append(float(ranking[0] in gold))
        first_gold = min(index for index, candidate in enumerate(ranking, 1) if candidate in gold)
        rr_values.append(1.0 / first_gold)
    return {
        "ranking_count": math.factorial(candidate_count),
        "expected_hit_at_1": mean(hit_values),
        "expected_mrr": mean(rr_values),
    }


def summarize_scores(records: Sequence[Mapping[str, Any]], score_field: str) -> dict[str, Any]:
    hits = []
    reciprocal_ranks = []
    gold_scores = []
    negative_scores = []
    margins = []
    entropies = []
    for record in records:
        scores = record[score_field]
        gold = set(record["gold_source_ids"])
        ranking = sorted(scores, key=lambda candidate: (-scores[candidate], candidate))
        hits.append(float(ranking[0] in gold))
        reciprocal_ranks.append(1.0 / min(i for i, candidate in enumerate(ranking, 1) if candidate in gold))
        gold_scores.extend(scores[candidate] for candidate in ranking if candidate in gold)
        negative_scores.extend(scores[candidate] for candidate in ranking if candidate not in gold)
        ordered = sorted(scores.values(), reverse=True)
        margins.append(ordered[0] - ordered[1])
        entropies.append(entropy(list(scores.values())))
    gold_mean = mean(gold_scores)
    negative_mean = mean(negative_scores)
    return {
        "example_count": len(records),
        "hit_at_1": mean(hits),
        "mrr": mean(reciprocal_ranks),
        "gold_mean_score": gold_mean,
        "negative_mean_score": negative_mean,
        "gold_minus_negative": gold_mean - negative_mean,
        "mean_top1_top2_margin": mean(margins),
        "mean_entropy_nats": mean(entropies),
        "mean_normalized_entropy": mean(entropies) / math.log(4),
    }


def distribution_diagnostic(candidate_ids: Sequence[str], scores: Sequence[float]) -> dict[str, Any]:
    normalized = normalize(scores)
    ordered = sorted(normalized, reverse=True)
    l1 = sum(abs(value - 0.25) for value in normalized)
    return {
        "candidate_scores": dict(zip(candidate_ids, normalized)),
        "maximum": max(normalized),
        "minimum": min(normalized),
        "range": max(normalized) - min(normalized),
        "top1_top2_margin": ordered[0] - ordered[1],
        "l1_distance_from_uniform": l1,
        "l2_distance_from_uniform": math.sqrt(sum((value - 0.25) ** 2 for value in normalized)),
        "total_variation_from_uniform": l1 / 2,
        "entropy_nats": entropy(normalized),
        "normalized_entropy": entropy(normalized) / math.log(4),
    }


def slot_additive_r2(movements: Sequence[Mapping[str, Any]], value_key: str = "delta") -> float | None:
    if not movements:
        return None
    y = np.asarray([move[value_key] for move in movements], dtype=float)
    if np.allclose(y, y[0]):
        return 0.0
    design = []
    for move in movements:
        row = [1.0]
        row.extend(float(move["from_slot"] == slot) for slot in range(1, 4))
        row.extend(float(move["to_slot"] == slot) for slot in range(1, 4))
        design.append(row)
    matrix = np.asarray(design)
    fitted = matrix @ np.linalg.lstsq(matrix, y, rcond=None)[0]
    residual = float(np.square(y - fitted).sum())
    total = float(np.square(y - y.mean()).sum())
    return 1.0 - residual / total if total else 0.0


def contiguous_true_ranges(flags: Sequence[bool]) -> list[list[int]]:
    ranges = []
    start = None
    for index, value in enumerate(list(flags) + [False]):
        if value and start is None:
            start = index
        elif not value and start is not None:
            ranges.append([start, index - 1])
            start = None
    return ranges
