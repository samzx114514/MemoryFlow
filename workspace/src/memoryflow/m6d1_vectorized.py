"""Numerically exact, chunked target-group bootstrap primitives for M6D.1."""
from __future__ import annotations
import numpy as np


def ranking_group_metrics(labels: np.ndarray, scores: np.ndarray) -> dict[str, np.ndarray]:
    """Target-level ranking metrics for fixed groups of eight candidates."""
    groups = labels.shape[0]
    result = {key: np.zeros(groups, dtype=np.float64) for key in ("mrr", "hit_at_1", "ndcg_at_5")}
    for i in range(groups):
        order = np.argsort(-scores[i], kind="stable")
        y = labels[i, order]
        positives = int(y.sum())
        first = int(np.flatnonzero(y)[0])
        result["mrr"][i] = 1.0 / (first + 1)
        result["hit_at_1"][i] = float(y[0])
        discounts = 1.0 / np.log2(np.arange(2, 7))
        dcg = float((y[:5] * discounts).sum())
        ideal = float((np.ones(min(positives, 5)) * discounts[:min(positives, 5)]).sum())
        result["ndcg_at_5"][i] = dcg / ideal if ideal else np.nan
    return result


def weighted_edge_metric(labels: np.ndarray, scores: np.ndarray, multiplicities: np.ndarray, metric: str) -> np.ndarray:
    """Stable-sort weighted AP/AUC, exactly equivalent to repeating each target group."""
    labels = labels.astype(np.int64)
    order = np.argsort(-scores, kind="stable")
    y = labels[order]
    group_size = len(labels) // multiplicities.shape[1]
    w = np.repeat(multiplicities, group_size, axis=1)[:, order].astype(np.int64)
    total = w.sum(axis=1); total_pos = (w * y).sum(axis=1); total_neg = total - total_pos
    good = (total_pos > 0) & (total_neg > 0)
    output = np.full(len(multiplicities), np.nan, dtype=np.float64)
    if not np.any(good): return output
    prior_total = np.cumsum(w, axis=1) - w
    prior_pos = np.cumsum(w * y, axis=1) - w * y
    if metric == "auroc":
        if np.unique(scores).size != len(scores):
            # Exact tie-block reduction of the explicit repeated-sample
            # Mann-Whitney reference: positives in a score block beat all
            # lower-score negatives and tie half its same-score negatives.
            contribution = np.zeros(len(w), dtype=np.float64)
            for value in np.unique(scores):
                members = scores == value
                pg = (w[:, members] * y[members]).sum(axis=1)
                ng = (w[:, members] * (1 - y[members])).sum(axis=1)
                negative_lower = (w[:, scores < value] * (1 - y[scores < value])).sum(axis=1)
                contribution += pg * (negative_lower + .5 * ng)
            output[good] = contribution[good] / (total_pos[good] * total_neg[good])
            return output
        ranks = w * (prior_total + 1) + w * (w - 1) / 2.0
        rank_sum = (ranks * y).sum(axis=1)
        # Ranks above are descending-score positions. Convert the conventional
        # ascending-rank Mann-Whitney form to positive-beats-negative form.
        inversions = rank_sum[good] - total_pos[good] * (total_pos[good] + 1) / 2.0
        output[good] = 1.0 - inversions / (total_pos[good] * total_neg[good])
        return output
    if metric != "auprc": raise ValueError(metric)
    # Sum (TP_before+k)/(all_before+k), k=1..w, with a precomputed harmonic table.
    maximum = int(total.max())
    harmonic = np.zeros(maximum + 1, dtype=np.float64); harmonic[1:] = np.cumsum(1.0 / np.arange(1, maximum + 1))
    fp_before = prior_total - prior_pos
    denominator_before = prior_total.astype(np.int64)
    contribution = w.astype(np.float64) - fp_before * (harmonic[denominator_before + w] - harmonic[denominator_before])
    output[good] = (contribution * y).sum(axis=1)[good] / total_pos[good]
    return output


def bootstrap_macro(left: np.ndarray, right: np.ndarray, indices: np.ndarray) -> np.ndarray:
    """Paired target-level bootstrap deltas for macro metrics."""
    delta = left - right
    return delta[indices].mean(axis=1)


def percentile_summary(values: np.ndarray) -> dict[str, float | list[float]]:
    return {"mean": float(values.mean()), "ci95": [float(np.quantile(values, .025)), float(np.quantile(values, .975))], "p_two_sided": float(2 * min((values <= 0).mean(), (values >= 0).mean()))}


def edge_bootstrap_chunked(labels: np.ndarray, left: np.ndarray, right: np.ndarray, indices: np.ndarray, metric: str, chunk_size: int = 128) -> np.ndarray:
    """Chunked paired bootstrap for an edge metric without resampling Python objects."""
    result = []
    for start in range(0, len(indices), chunk_size):
        counts = np.zeros((len(indices[start:start + chunk_size]), indices.shape[1]), dtype=np.int16)
        np.add.at(counts, (np.arange(len(counts))[:, None], indices[start:start + chunk_size]), 1)
        result.append(weighted_edge_metric(labels, left, counts, metric) - weighted_edge_metric(labels, right, counts, metric))
    return np.concatenate(result)
