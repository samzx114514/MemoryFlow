from __future__ import annotations

import itertools
import math
from collections import defaultdict
from collections.abc import Mapping, Sequence
from statistics import mean
from typing import Any, Callable

import numpy as np

from memoryflow.b3_analysis import average_precision


BOOTSTRAP_SEED = "memoryflow-b4-cluster-bootstrap-v1"
BOOTSTRAP_REPLICATES = 5000


def exact_random_expectations(gold_count: int, candidate_count: int = 4) -> dict[str, float]:
    if not 0 < gold_count <= candidate_count:
        raise ValueError("gold_count must be between one and candidate_count")
    candidate_ids = [str(index) for index in range(candidate_count)]
    gold = set(candidate_ids[:gold_count])
    hits = []
    reciprocal_ranks = []
    aps = []
    for ranking in itertools.permutations(candidate_ids):
        hits.append(float(ranking[0] in gold))
        reciprocal_ranks.append(1.0 / min(index for index, candidate_id in enumerate(ranking, 1) if candidate_id in gold))
        aps.append(average_precision(ranking, gold))
    return {
        "ranking_count": math.factorial(candidate_count),
        "expected_hit_at_1": mean(hits),
        "expected_mrr": mean(reciprocal_ranks),
        "expected_map": mean(aps),
    }


def per_example_ranking_values(record: Mapping[str, Any]) -> dict[str, float]:
    scores = record["scores"]
    gold = set(record["gold_source_ids"])
    ranking = sorted(scores, key=lambda candidate_id: (-scores[candidate_id], candidate_id))
    random = exact_random_expectations(len(gold), len(scores))
    return {
        "hit_at_1": float(ranking[0] in gold),
        "mrr": 1.0 / min(index for index, candidate_id in enumerate(ranking, 1) if candidate_id in gold),
        "map": average_precision(ranking, gold),
        "random_hit_at_1": random["expected_hit_at_1"],
        "random_mrr": random["expected_mrr"],
        "random_map": random["expected_map"],
    }


def percentile_interval(values: Sequence[float]) -> list[float]:
    return [float(np.percentile(values, 2.5)), float(np.percentile(values, 97.5))]


def cluster_bootstrap(
    rows: Sequence[Mapping[str, Any]],
    statistics: Mapping[str, Callable[[Sequence[Mapping[str, Any]]], float]],
    *,
    replicates: int = BOOTSTRAP_REPLICATES,
    seed: str = BOOTSTRAP_SEED,
) -> dict[str, Any]:
    groups: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for row in rows:
        groups[str(row["run_id"])].append(row)
    group_ids = sorted(groups)
    seed_value = int.from_bytes(seed.encode("utf-8"), "little") % (2**63 - 1)
    rng = np.random.default_rng(seed_value)
    samples = {name: [] for name in statistics}
    for _ in range(replicates):
        selected = rng.choice(group_ids, size=len(group_ids), replace=True)
        resampled = [row for group_id in selected for row in groups[str(group_id)]]
        for name, function in statistics.items():
            samples[name].append(float(function(resampled)))
    return {
        "seed": seed,
        "replicates": replicates,
        "cluster_field": "run_id",
        "cluster_count": len(group_ids),
        "intervals": {
            name: {
                "point_estimate": float(function(rows)),
                "ci_95_percentile": percentile_interval(samples[name]),
            }
            for name, function in statistics.items()
        },
    }


def decide_b4(
    *,
    v3_hit_above_random_ci_low: float,
    v3_mrr_above_random_ci_low: float,
    single_hit_above_quarter_ci_low: float,
    v3_hit_above_random_point: float,
    v3_mrr_above_random_point: float,
    single_hit_above_quarter_point: float,
    v3_top1_consistency: float,
    v3_max_score_change: float,
    v3_minus_v2_hit: float,
    v3_minus_v2_mrr: float,
    mechanics_pass: bool,
) -> tuple[str, dict[str, bool]]:
    overall = (
        v3_hit_above_random_point > 0
        and v3_mrr_above_random_point > 0
        and v3_hit_above_random_ci_low > 0
        and v3_mrr_above_random_ci_low > 0
    )
    single = single_hit_above_quarter_point > 0 and single_hit_above_quarter_ci_low > 0
    stable = v3_top1_consistency >= 0.90 and v3_max_score_change <= 0.02
    pairwise_close = v3_minus_v2_hit >= -0.05 and v3_minus_v2_mrr >= -0.05
    conditions = {
        "overall_above_random_with_positive_ci": overall,
        "single_positive_hit_with_positive_ci": single,
        "v3_top1_consistency_at_least_0_90": v3_top1_consistency >= 0.90,
        "v3_max_score_change_at_most_0_02": v3_max_score_change <= 0.02,
        "v3_not_more_than_0_05_below_pairwise": pairwise_close,
        "mechanics_pass": mechanics_pass,
    }
    if all(conditions.values()):
        return "B4_POSITION_RESET_HELDOUT_PASS", conditions
    if overall and not single:
        return "B4_POSITION_RESET_PARTIAL_MULTI_ONLY", conditions
    if stable and not overall:
        return "B4_POSITION_RESET_STABLE_BUT_NO_SEMANTIC_EVIDENCE", conditions
    return "B4_INCONCLUSIVE", conditions
