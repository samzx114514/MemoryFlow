from __future__ import annotations

from collections.abc import Mapping, Sequence
from statistics import mean
from typing import Any

from memoryflow.b2_5_analysis import expected_random_ranking
from memoryflow.b3_analysis import average_precision, ndcg_at_4


def summarize_scores(records: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    if not records:
        raise ValueError("records must not be empty")
    hits: list[float] = []
    reciprocal_ranks: list[float] = []
    average_precisions: list[float] = []
    ndcgs: list[float] = []
    gold_scores: list[float] = []
    negative_scores: list[float] = []
    pairwise: list[float] = []
    margins: list[float] = []
    random_hits: list[float] = []
    random_mrrs: list[float] = []
    rankings: list[dict[str, Any]] = []
    for record in records:
        scores = record["scores"]
        gold = set(record["gold_source_ids"])
        ranking = sorted(scores, key=lambda candidate_id: (-scores[candidate_id], candidate_id))
        hits.append(float(ranking[0] in gold))
        first_gold = min(index for index, candidate_id in enumerate(ranking, 1) if candidate_id in gold)
        reciprocal_ranks.append(1.0 / first_gold)
        average_precisions.append(average_precision(ranking, gold))
        ndcgs.append(ndcg_at_4(ranking, gold))
        positives = [scores[candidate_id] for candidate_id in ranking if candidate_id in gold]
        negatives = [scores[candidate_id] for candidate_id in ranking if candidate_id not in gold]
        gold_scores.extend(positives)
        negative_scores.extend(negatives)
        pairwise.extend(1.0 if positive > negative else 0.5 if positive == negative else 0.0 for positive in positives for negative in negatives)
        ordered = sorted(scores.values(), reverse=True)
        margins.append(ordered[0] - ordered[1])
        baseline = expected_random_ranking(len(gold), len(scores))
        random_hits.append(baseline["expected_hit_at_1"])
        random_mrrs.append(baseline["expected_mrr"])
        rankings.append({"example_id": record["example_id"], "ranking": ranking, "scores": scores, "gold_source_ids": sorted(gold)})
    hit = mean(hits)
    mrr = mean(reciprocal_ranks)
    random_hit = mean(random_hits)
    random_mrr = mean(random_mrrs)
    gold_mean = mean(gold_scores)
    negative_mean = mean(negative_scores)
    return {
        "example_count": len(records),
        "random_expected_hit_at_1": random_hit,
        "random_expected_mrr": random_mrr,
        "hit_at_1": hit,
        "mrr": mrr,
        "map": mean(average_precisions),
        "ndcg_at_4": mean(ndcgs),
        "gold_mean_score": gold_mean,
        "negative_mean_score": negative_mean,
        "gold_minus_negative_score": gold_mean - negative_mean,
        "gold_vs_negative_pairwise_accuracy": mean(pairwise),
        "mean_top1_top2_margin": mean(margins),
        "hit_at_1_minus_random": hit - random_hit,
        "mrr_minus_random": mrr - random_mrr,
        "rankings": rankings,
    }


def stratified_metrics(records: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    groups = {
        "all": list(records),
        "single_positive": [record for record in records if record["stratum"] == "single_positive"],
        "multi_positive": [record for record in records if record["stratum"] == "multi_positive"],
    }
    return {name: summarize_scores(group) for name, group in groups.items()}


def ranking_agreement(left: Mapping[str, float], right: Mapping[str, float]) -> dict[str, Any]:
    ids = sorted(left)
    if ids != sorted(right):
        raise ValueError("candidate ids differ")
    left_rank = sorted(ids, key=lambda candidate_id: (-left[candidate_id], candidate_id))
    right_rank = sorted(ids, key=lambda candidate_id: (-right[candidate_id], candidate_id))
    return {
        "top1_same": left_rank[0] == right_rank[0],
        "full_ranking_same": left_rank == right_rank,
        "left_ranking": left_rank,
        "right_ranking": right_rank,
    }
