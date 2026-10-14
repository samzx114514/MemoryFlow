"""Deterministic nested candidate construction for LongCite C4A."""

from __future__ import annotations

from typing import Mapping, Sequence

from memoryflow.expanded_longcite import automatic_negative_exclusion, mixed_master_negatives, stable_hex


RULE_VERSION = "longcite-anchor-scaling-v1"
SIZES = (8, 16, 32)


def scaling_order(source_ids: Sequence[str], target_group_id: str, size: int) -> list[str]:
    if len(source_ids) != len(set(source_ids)):
        raise ValueError("duplicate source ID")
    return sorted(source_ids, key=lambda sid: stable_hex(RULE_VERSION, target_group_id, size, sid))


def build_nested_sets(
    prepared: Mapping,
    original_eight: Sequence[str],
    *,
    conservative: bool,
    blocked_source_ids: set[str] | None = None,
) -> tuple[dict[int, list[str]], dict[str, dict]]:
    """Preserve c8 and extend it using only frozen C3B pool fields."""
    blocked = blocked_source_ids or set()
    positives = {str(row["source_id"]): dict(row) for row in prepared["positive_sources"]}
    positive_texts = [str(row["text"]) for row in positives.values()]
    pool = []
    for row in prepared["negative_pool"]:
        sid = str(row["source_id"])
        if sid in blocked:
            continue
        if conservative and row.get("risk_flags"):
            continue
        if automatic_negative_exclusion(str(row["text"]), positive_texts):
            continue
        pool.append(row)
    master = mixed_master_negatives(pool, target_group_id=str(prepared["target_group_id"]))
    metadata = {**positives, **{str(row["source_id"]): dict(row) for row in master}}
    base = list(original_eight)
    if len(base) != 8 or len(set(base)) != 8 or not set(positives) <= set(base):
        raise ValueError("invalid original c8 set")
    if not set(base) <= set(metadata):
        raise ValueError("original c8 is absent from prepared pool")
    unused = [str(row["source_id"]) for row in master if str(row["source_id"]) not in set(base)]
    nested: dict[int, list[str]] = {}
    current = list(base)
    for size in SIZES:
        needed = size - len(current)
        if needed > len(unused):
            break
        current.extend(unused[:needed]); unused = unused[needed:]
        nested[size] = scaling_order(current, str(prepared["target_group_id"]), size)
    return nested, metadata


def validate_nested_examples(examples_by_size: Mapping[int, Sequence[Mapping]], source_rows: Sequence[Mapping], *, conservative: bool) -> dict:
    by_source = {str(row["source_id"]): row for row in source_rows}
    by_size = {size: {row["target_group_id"]: row for row in rows} for size, rows in examples_by_size.items()}
    common = set.intersection(*(set(rows) for rows in by_size.values())) if by_size else set()
    for target in common:
        previous: set[str] = set()
        for size in SIZES:
            row = by_size[size][target]; ids = list(row["candidate_source_ids"]); current = set(ids)
            if len(ids) != size or len(current) != size or not previous <= current:
                raise ValueError("nested candidate invariant failed")
            if not set(row["gold_source_ids"]) <= current:
                raise ValueError("positive missing")
            sources = [by_source[sid] for sid in ids]
            if any(src["document_group_id"] != row["document_group_id"] for src in sources):
                raise ValueError("cross-document source")
            if conservative and any(src.get("risk_flags") for src in sources if sid_not_gold(src, row)):
                raise ValueError("risky conservative negative")
            previous = current
    return {"targets_all_sizes": len(common), "source_count": len(source_rows)}


def sid_not_gold(source: Mapping, example: Mapping) -> bool:
    return str(source["source_id"]) not in set(example["gold_source_ids"])


def kendall_tau_rankings(left: Sequence[str], right: Sequence[str]) -> float:
    """Kendall tau-a for two complete rankings without ties."""
    if len(left) != len(right) or len(set(left)) != len(left) or set(left) != set(right):
        raise ValueError("rankings must contain the same unique items")
    if len(left) < 2:
        return 1.0
    right_position = {item: index for index, item in enumerate(right)}
    discordant = sum(
        right_position[left[i]] > right_position[left[j]]
        for i in range(len(left)) for j in range(i + 1, len(left))
    )
    return 1.0 - 4.0 * discordant / (len(left) * (len(left) - 1))
