from __future__ import annotations

import math
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from statistics import mean
from typing import Any


def token_jaccard(left: Sequence[int], right: Sequence[int]) -> float:
    left_set, right_set = set(left), set(right)
    union = left_set | right_set
    return len(left_set & right_set) / len(union) if union else 0.0


def fit_document_frequency(documents: Iterable[Sequence[int]]) -> tuple[Counter[int], int]:
    frequency: Counter[int] = Counter()
    count = 0
    for document in documents:
        frequency.update(set(document))
        count += 1
    return frequency, count


def tfidf_cosine(
    left: Sequence[int], right: Sequence[int], document_frequency: Mapping[int, int], document_count: int
) -> float:
    left_counts, right_counts = Counter(left), Counter(right)
    common = set(left_counts) & set(right_counts)
    def idf(token: int) -> float:
        return math.log((document_count + 1) / (document_frequency.get(token, 0) + 1)) + 1.0
    dot = sum(left_counts[token] * right_counts[token] * idf(token) ** 2 for token in common)
    left_norm = math.sqrt(sum(count**2 * idf(token) ** 2 for token, count in left_counts.items()))
    right_norm = math.sqrt(sum(count**2 * idf(token) ** 2 for token, count in right_counts.items()))
    return dot / (left_norm * right_norm) if left_norm and right_norm else 0.0


def bm25_score(
    query: Sequence[int],
    document: Sequence[int],
    document_frequency: Mapping[int, int],
    document_count: int,
    average_document_length: float,
    k1: float = 1.2,
    b: float = 0.75,
) -> float:
    counts = Counter(document)
    normalization = k1 * (1 - b + b * len(document) / average_document_length)
    score = 0.0
    for token in set(query):
        frequency = counts.get(token, 0)
        if not frequency:
            continue
        df = document_frequency.get(token, 0)
        idf = math.log(1.0 + (document_count - df + 0.5) / (df + 0.5))
        score += idf * frequency * (k1 + 1) / (frequency + normalization)
    return score


def distribution(values: Sequence[float]) -> dict[str, float | int]:
    if not values:
        return {"count": 0}
    ordered = sorted(map(float, values))
    def quantile(probability: float) -> float:
        position = probability * (len(ordered) - 1)
        low = int(math.floor(position))
        high = int(math.ceil(position))
        fraction = position - low
        return ordered[low] * (1 - fraction) + ordered[high] * fraction
    return {
        "count": len(ordered),
        "mean": mean(ordered),
        "minimum": ordered[0],
        "p25": quantile(0.25),
        "median": quantile(0.5),
        "p75": quantile(0.75),
        "p95": quantile(0.95),
        "maximum": ordered[-1],
    }


def pairwise_auc(examples: Sequence[Mapping[str, Any]], score_field: str) -> float:
    comparisons = []
    for example in examples:
        gold = set(example["gold_source_ids"])
        scores = example[score_field]
        positives = [scores[candidate["id"]] for candidate in example["candidates"] if candidate["id"] in gold]
        negatives = [scores[candidate["id"]] for candidate in example["candidates"] if candidate["id"] not in gold]
        comparisons.extend(1.0 if positive > negative else 0.5 if positive == negative else 0.0 for positive in positives for negative in negatives)
    return mean(comparisons)
