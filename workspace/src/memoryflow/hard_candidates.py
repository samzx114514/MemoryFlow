"""Deterministic, audit-aware hard-negative candidate construction."""

from __future__ import annotations

import hashlib
from typing import Mapping, Sequence


MIX_CYCLE = ("bm25_hard", "bm25_hard", "qwen_hard", "qwen_hard", "random")
BLOCKED_AUDIT_DECISIONS = {"ambiguous_possible_support", "duplicate_gold"}


def _stable_hex(*parts: object) -> str:
    payload = "\x1f".join(str(part) for part in parts).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def select_master_negatives(
    candidates: Sequence[Mapping[str, object]],
    *,
    target_group_id: str,
    audit_decisions: Mapping[str, str],
) -> list[dict[str, object]]:
    """Interleave 40/40/20 queues after applying semantic-audit decisions."""
    by_id = {str(candidate["source_id"]): dict(candidate) for candidate in candidates}
    if len(by_id) != len(candidates):
        raise ValueError("duplicate source_id in negative pool")
    allowed = {
        source_id: candidate
        for source_id, candidate in by_id.items()
        if audit_decisions.get(source_id) not in BLOCKED_AUDIT_DECISIONS
    }
    hard_allowed = {
        source_id: candidate
        for source_id, candidate in allowed.items()
        if audit_decisions.get(source_id) != "unrelated_not_hard"
    }
    bm25_queue = sorted(
        hard_allowed,
        key=lambda source_id: (
            -float(hard_allowed[source_id]["bm25_score"]),
            _stable_hex("bm25-tie", target_group_id, source_id),
        ),
    )
    qwen_queue = sorted(
        hard_allowed,
        key=lambda source_id: (
            -float(hard_allowed[source_id]["qwen_similarity"]),
            _stable_hex("qwen-tie", target_group_id, source_id),
        ),
    )
    random_queue = sorted(
        allowed,
        key=lambda source_id: _stable_hex("hard-random", target_group_id, source_id),
    )
    queues = {"bm25_hard": bm25_queue, "qwen_hard": qwen_queue, "random": random_queue}
    positions = {reason: 0 for reason in queues}
    selected: set[str] = set()
    result: list[dict[str, object]] = []
    cycle_position = 0
    unsuccessful_slots = 0
    while len(selected) < len(allowed) and unsuccessful_slots < len(MIX_CYCLE) * 2:
        reason = MIX_CYCLE[cycle_position % len(MIX_CYCLE)]
        cycle_position += 1
        queue = queues[reason]
        while positions[reason] < len(queue) and queue[positions[reason]] in selected:
            positions[reason] += 1
        if positions[reason] >= len(queue):
            unsuccessful_slots += 1
            continue
        source_id = queue[positions[reason]]
        positions[reason] += 1
        selected.add(source_id)
        item = dict(allowed[source_id])
        item["selection_reason"] = reason
        item["audit_decision"] = audit_decisions.get(source_id)
        result.append(item)
        unsuccessful_slots = 0
    if len(selected) != len(allowed):
        remaining = sorted(
            set(allowed) - selected,
            key=lambda source_id: _stable_hex("hard-remainder", target_group_id, source_id),
        )
        for source_id in remaining:
            item = dict(allowed[source_id])
            item["selection_reason"] = "random"
            item["audit_decision"] = audit_decisions.get(source_id)
            result.append(item)
    return result


def build_nested_candidate_sets(
    positive_ids: Sequence[str],
    master_negatives: Sequence[Mapping[str, object]],
    target_group_id: str,
    candidate_sizes: Sequence[int],
) -> dict[int, list[str]]:
    """Create exact-size nested sets and independently hash-shuffle their order."""
    if not positive_ids or len(positive_ids) != len(set(positive_ids)):
        raise ValueError("positive_ids must be nonempty and unique")
    negative_ids = [str(item["source_id"]) for item in master_negatives]
    if len(negative_ids) != len(set(negative_ids)) or set(positive_ids) & set(negative_ids):
        raise ValueError("negative source IDs must be unique and disjoint from positives")
    result: dict[int, list[str]] = {}
    for candidate_size in sorted(candidate_sizes):
        negative_count = candidate_size - len(positive_ids)
        if negative_count < 0 or negative_count > len(negative_ids):
            continue
        chosen = list(positive_ids) + negative_ids[:negative_count]
        result[candidate_size] = hash_order_candidate_ids(
            chosen, target_group_id=target_group_id, candidate_size=candidate_size
        )
    validate_hard_candidate_sets(result, set(positive_ids))
    return result


def validate_hard_candidate_sets(
    candidate_sets: Mapping[int, Sequence[str]], gold_source_ids: set[str]
) -> None:
    if not gold_source_ids:
        raise ValueError("gold sources are required")
    previous: set[str] | None = None
    for candidate_size in sorted(candidate_sets):
        candidates = list(candidate_sets[candidate_size])
        if len(candidates) != candidate_size:
            raise ValueError("candidate set size mismatch")
        if len(candidates) != len(set(candidates)):
            raise ValueError("duplicate candidate source_id")
        current = set(candidates)
        if not gold_source_ids <= current:
            raise ValueError("gold sources missing from candidate set")
        if previous is not None and not previous <= current:
            raise ValueError("candidate sets are not nested")
        previous = current


def hash_order_candidate_ids(
    candidate_ids: Sequence[str], *, target_group_id: str, candidate_size: int
) -> list[str]:
    """Shuffle candidates without consulting reason, score, index, or gold status."""
    return sorted(
        candidate_ids,
        key=lambda source_id: _stable_hex(
            "hard-candidate-order", target_group_id, candidate_size, source_id
        ),
    )
