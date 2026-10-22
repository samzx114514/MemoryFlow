from __future__ import annotations

import itertools
import math
from collections import defaultdict
from collections.abc import Mapping, Sequence
from statistics import mean
from typing import Any

from memoryflow.b2_5_analysis import entropy, expected_random_ranking, normalize, pearson, slot_additive_r2, spearman


METHODS = ("last_layer_head_mean", "last_four_layers_head_mean")


def average_precision(ranking: Sequence[str], gold_ids: set[str]) -> float:
    hits = 0
    precision_sum = 0.0
    for rank, candidate_id in enumerate(ranking, 1):
        if candidate_id in gold_ids:
            hits += 1
            precision_sum += hits / rank
    return precision_sum / len(gold_ids)


def ndcg_at_4(ranking: Sequence[str], gold_ids: set[str]) -> float:
    dcg = sum((1.0 / math.log2(rank + 1)) for rank, candidate_id in enumerate(ranking, 1) if candidate_id in gold_ids)
    ideal = sum(1.0 / math.log2(rank + 1) for rank in range(1, len(gold_ids) + 1))
    return dcg / ideal


def summarize_variant(records: Sequence[Mapping[str, Any]], score_field: str = "scores") -> dict[str, Any]:
    hits = []
    reciprocal_ranks = []
    average_precisions = []
    ndcgs = []
    gold_scores = []
    negative_scores = []
    pairwise_correct = []
    margins = []
    entropies = []
    normalized_entropies = []
    rankings = []
    random_hits = []
    random_mrrs = []
    for record in records:
        scores = record[score_field]
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
        for positive in positives:
            for negative in negatives:
                pairwise_correct.append(1.0 if positive > negative else 0.5 if positive == negative else 0.0)
        ordered_scores = sorted(scores.values(), reverse=True)
        margins.append(ordered_scores[0] - ordered_scores[1])
        normalized = normalize(list(scores.values()))
        entropies.append(entropy(normalized))
        normalized_entropies.append(entropy(normalized) / math.log(len(normalized)))
        baseline = expected_random_ranking(len(gold), len(scores))
        random_hits.append(baseline["expected_hit_at_1"])
        random_mrrs.append(baseline["expected_mrr"])
        rankings.append({"example_id": record["example_id"], "ranking": ranking, "gold_source_ids": sorted(gold), "scores": scores})
    gold_mean = mean(gold_scores)
    negative_mean = mean(negative_scores)
    hit = mean(hits)
    mrr = mean(reciprocal_ranks)
    random_hit = mean(random_hits)
    random_mrr = mean(random_mrrs)
    return {
        "example_count": len(records),
        "random_expected_hit_at_1": random_hit,
        "random_expected_mrr": random_mrr,
        "hit_at_1": hit,
        "mrr": mrr,
        "map": mean(average_precisions),
        "ndcg_at_4": mean(ndcgs),
        "gold_mean_raw_attention": gold_mean,
        "negative_mean_raw_attention": negative_mean,
        "gold_minus_negative_raw_attention": gold_mean - negative_mean,
        "gold_vs_negative_pairwise_accuracy": mean(pairwise_correct),
        "mean_top1_top2_margin_raw": mean(margins),
        "mean_attention_entropy_nats": mean(entropies),
        "mean_normalized_attention_entropy": mean(normalized_entropies),
        "hit_at_1_minus_random": hit - random_hit,
        "mrr_minus_random": mrr - random_mrr,
        "rankings": rankings,
    }


def block_reset_position_ids(ordinary_lengths: Sequence[int], anchor_position_id: int = 192) -> list[int]:
    result = []
    for length in ordinary_lengths:
        if not 0 <= length <= anchor_position_id:
            raise ValueError("ordinary chunk length must be between zero and anchor_position_id")
        result.extend(range(length))
        result.append(anchor_position_id)
    return result


def cyclic_orders(candidate_ids: Sequence[str]) -> list[list[str]]:
    values = list(candidate_ids)
    return [values[shift:] + values[:shift] for shift in range(len(values))]


def cycle_stability(examples: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    pair_pearsons = []
    pair_spearmans = []
    absolute_changes = []
    top1_agreements = []
    ranking_agreements = []
    slot_scores = [[] for _ in range(4)]
    movements = []
    per_example = []
    for example in examples:
        cycles = example["cycles"]
        ids = example["candidate_ids"]
        for cycle in cycles:
            for slot, candidate_id in enumerate(cycle["candidate_order"]):
                slot_scores[slot].append(cycle["scores"][candidate_id])
        example_pairs = []
        for left_index, right_index in itertools.combinations(range(len(cycles)), 2):
            left = cycles[left_index]["scores"]
            right = cycles[right_index]["scores"]
            left_values = [left[candidate_id] for candidate_id in ids]
            right_values = [right[candidate_id] for candidate_id in ids]
            left_rank = sorted(ids, key=lambda candidate_id: (-left[candidate_id], candidate_id))
            right_rank = sorted(ids, key=lambda candidate_id: (-right[candidate_id], candidate_id))
            changes = [abs(a - b) for a, b in zip(left_values, right_values)]
            p = pearson(left_values, right_values)
            s = spearman(left_values, right_values)
            if p is not None:
                pair_pearsons.append(p)
            if s is not None:
                pair_spearmans.append(s)
            absolute_changes.extend(changes)
            top1_agreements.append(float(left_rank[0] == right_rank[0]))
            ranking_agreements.append(float(left_rank == right_rank))
            example_pairs.append({
                "cycles": [left_index, right_index],
                "pearson": p,
                "spearman": s,
                "mae": mean(changes),
                "max_absolute_change": max(changes),
                "top1_consistent": left_rank[0] == right_rank[0],
                "full_ranking_consistent": left_rank == right_rank,
            })
        base = cycles[0]
        for cycle in cycles[1:]:
            for candidate_id in ids:
                before = base["scores"][candidate_id]
                after = cycle["scores"][candidate_id]
                movements.append({
                    "example_id": example["example_id"],
                    "candidate_id": candidate_id,
                    "from_slot": base["candidate_order"].index(candidate_id),
                    "to_slot": cycle["candidate_order"].index(candidate_id),
                    "delta": after - before,
                    "absolute_change": abs(after - before),
                })
        per_example.append({"example_id": example["example_id"], "pairwise_cycle_comparisons": example_pairs})
    return {
        "example_count": len(examples),
        "cycle_pair_comparison_count": len(top1_agreements),
        "mean_aligned_pearson": mean(pair_pearsons),
        "mean_aligned_spearman": mean(pair_spearmans),
        "mean_aligned_mae": mean(absolute_changes),
        "max_aligned_score_change": max(absolute_changes),
        "pairwise_top1_consistency": mean(top1_agreements),
        "pairwise_full_ranking_consistency": mean(ranking_agreements),
        "slot_mean_raw_attention": [mean(values) for values in slot_scores],
        "movement_r2_signed_delta": slot_additive_r2(movements, "delta"),
        "movement_r2_absolute_change": slot_additive_r2(movements, "absolute_change"),
        "per_example": per_example,
    }
