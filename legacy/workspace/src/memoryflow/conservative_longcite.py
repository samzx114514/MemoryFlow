"""Deterministic helpers for the C3B.1 conservative LongCite view."""

from __future__ import annotations

from collections import Counter
from typing import Mapping, Sequence

from memoryflow.expanded_longcite import (
    BLOCKED_AUDIT,
    automatic_negative_exclusion,
    mixed_master_negatives,
    stable_candidate_order,
    stable_hex,
)


RULE_VERSION = "longcite-anchor-expanded-v1-conservative-v1"
RESIDUAL_AUDIT_SEED = "memoryflow-c3b1-residual-audit-v1"


def select_conservative_candidates(
    prepared: Mapping,
    *,
    blocked_source_ids: set[str] | None = None,
) -> tuple[list[dict], dict]:
    """Keep positives and refill with unflagged, structurally safe negatives."""
    blocked = blocked_source_ids or set()
    positives = [{**row, "selection_reason": "positive", "risk_flags": []} for row in prepared["positive_sources"]]
    positive_texts = [str(row["text"]) for row in positives]
    safe = []
    rejected = Counter()
    for candidate in prepared["negative_pool"]:
        source_id = str(candidate["source_id"])
        if source_id in blocked:
            rejected["blocked_audit"] += 1
        elif candidate.get("risk_flags"):
            rejected["risk_flag"] += 1
        elif automatic_negative_exclusion(str(candidate["text"]), positive_texts):
            rejected["structural_duplicate_or_noise"] += 1
        else:
            safe.append(candidate)
    needed = 8 - len(positives)
    if needed < 0:
        raise ValueError("more than eight positives")
    master = mixed_master_negatives(safe, target_group_id=str(prepared["target_group_id"]))
    if len(master) < needed:
        return [], {"needed": needed, "available": len(master), "rejected": dict(rejected)}
    selected = positives + master[:needed]
    by_id = {str(row["source_id"]): row for row in selected}
    ordered_ids = stable_candidate_order(list(by_id), str(prepared["target_group_id"]))
    return [by_id[source_id] for source_id in ordered_ids], {
        "needed": needed,
        "available": len(master),
        "rejected": dict(rejected),
    }


def residual_audit_priority(prepared: Mapping, candidate: Mapping) -> tuple:
    """Rank safe candidates using only frozen C3B scores, never labels beyond exclusion."""
    pool = list(prepared["negative_pool"])
    bm25 = sorted(pool, key=lambda row: (-float(row["bm25_score"]), str(row["source_id"])))
    qwen = sorted(pool, key=lambda row: (-float(row["qwen_similarity"]), str(row["source_id"])))
    bm_rank = {str(row["source_id"]): rank for rank, row in enumerate(bm25)}
    qw_rank = {str(row["source_id"]): rank for rank, row in enumerate(qwen)}
    source_id = str(candidate["source_id"])
    return (
        min(bm_rank[source_id], qw_rank[source_id]),
        -float(candidate.get("text_similarity") or 0.0),
        stable_hex(RESIDUAL_AUDIT_SEED, prepared["target_group_id"], source_id),
    )


def select_residual_audit_rows(rows: Sequence[Mapping], count: int) -> list[tuple[Mapping, Mapping]]:
    """Select at most one unflagged selected negative per target."""
    ranked = []
    for prepared in rows:
        selected = prepared.get("conservative_selected", [])
        negatives = [row for row in selected if row.get("selection_reason") != "positive"]
        if not negatives:
            continue
        candidate = min(negatives, key=lambda row: residual_audit_priority(prepared, row))
        priority = residual_audit_priority(prepared, candidate)
        ranked.append((priority, prepared, candidate))
    ranked.sort(key=lambda item: (item[0], stable_hex(RESIDUAL_AUDIT_SEED, item[1]["target_group_id"])))
    return [(prepared, candidate) for _, prepared, candidate in ranked[:count]]


def validate_no_risky_negatives(examples: Sequence[Mapping], sources: Sequence[Mapping]) -> dict:
    by_id = {str(row["source_id"]): row for row in sources}
    if len(by_id) != len(sources):
        raise ValueError("duplicate source IDs")
    documents = set()
    for example in examples:
        candidates = list(example["candidate_source_ids"])
        gold = set(example["gold_source_ids"])
        if len(candidates) != 8 or len(set(candidates)) != 8:
            raise ValueError("each example must have eight unique candidates")
        if not gold or not gold <= set(candidates):
            raise ValueError("positive source missing")
        rows = [by_id[source_id] for source_id in candidates]
        if any(row["document_group_id"] != example["document_group_id"] for row in rows):
            raise ValueError("cross-document source")
        if any(row.get("risk_flags") for row in rows if row["source_id"] not in gold):
            raise ValueError("risk-flagged negative remains")
        documents.add(example["document_group_id"])
    return {"examples": len(examples), "documents": len(documents), "risk_negative_count": 0}
