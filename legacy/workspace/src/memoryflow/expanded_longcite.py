"""Deterministic C3B helpers for expanded LongCite Anchor-training data."""

from __future__ import annotations

from collections import Counter
from difflib import SequenceMatcher
import hashlib
import re
from typing import Mapping, Sequence

from memoryflow.longcite import normalize_candidate_text, source_noise_reason


RULE_VERSION = "longcite-anchor-expanded-v1"
SPLIT_SEED = "memoryflow-anchor-expanded-v1"
MIX_CYCLE = ("bm25_hard", "bm25_hard", "qwen_hard", "qwen_hard", "random")
BLOCKED_AUDIT = {"ambiguous_possible_support", "duplicate_gold"}


def stable_hex(*parts: object) -> str:
    return hashlib.sha256("\x1f".join(map(str, parts)).encode("utf-8")).hexdigest()


def document_content_hash(sources: Sequence[tuple[int, str]]) -> str:
    payload = "\n".join(f"{index}\t{text}" for index, text in sorted(sources))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def automatic_negative_exclusion(negative: str, positives: Sequence[str]) -> str | None:
    """Apply only preregistered duplicate/noise protections."""
    if source_noise_reason(negative):
        return "known_noise_source"
    key = normalize_candidate_text(negative)
    for positive in positives:
        positive_key = normalize_candidate_text(positive)
        if key == positive_key:
            return "normalized_exact_positive_duplicate"
        shorter, longer = sorted((key, positive_key), key=len)
        if len(shorter) >= 20 and shorter in longer:
            return "normalized_containment_positive_duplicate"
        maximum_possible_ratio = 2 * len(shorter) / max(1, len(key) + len(positive_key))
        if len(shorter) >= 20 and maximum_possible_ratio >= 0.95 and SequenceMatcher(None, key, positive_key).ratio() >= 0.95:
            return "highly_repeated_positive_copy"
    return None


def guarded_text_similarity(left: str, right: str, *, threshold_floor: float = 0.75) -> float:
    """Compute exact similarity only when lengths permit reaching the risk threshold."""
    if not left and not right:
        return 1.0
    maximum_possible_ratio = 2 * min(len(left), len(right)) / max(1, len(left) + len(right))
    if maximum_possible_ratio < threshold_floor:
        return 0.0
    return SequenceMatcher(None, left, right).ratio()


def risk_flags(
    target: str,
    negative: str,
    *,
    bm25_rank: int,
    qwen_rank: int,
    text_similarity: float,
) -> list[str]:
    flags = []
    if bm25_rank <= 3:
        flags.append("top3_bm25")
    if qwen_rank <= 3:
        flags.append("top3_qwen")
    if text_similarity >= 0.75:
        flags.append("high_text_similarity")
    target_numbers = set(re.findall(r"\d+(?:\.\d+)?", target))
    negative_numbers = set(re.findall(r"\d+(?:\.\d+)?", negative))
    if target_numbers and target_numbers & negative_numbers:
        flags.append("shared_number")
    return flags


def split_documents(
    target_counts: Mapping[str, int],
    *,
    train_target: int = 850,
    dev_target: int = 225,
) -> dict[str, list[str]]:
    """Stable document-only split; no label or score is an input."""
    ordered = sorted(target_counts, key=lambda doc: stable_hex(SPLIT_SEED, doc))
    result = {"train": [], "dev": [], "blind_test": []}
    train_count = dev_count = 0
    for document_id in ordered:
        count = int(target_counts[document_id])
        if train_count < train_target:
            result["train"].append(document_id); train_count += count
        elif dev_count < dev_target:
            result["dev"].append(document_id); dev_count += count
        else:
            result["blind_test"].append(document_id)
    return result


def mixed_master_negatives(
    candidates: Sequence[Mapping[str, object]],
    *,
    target_group_id: str,
    audit_decisions: Mapping[str, str] | None = None,
) -> list[dict]:
    """Interleave BM25/BM25/Qwen/Qwen/random with deterministic queues."""
    decisions = audit_decisions or {}
    allowed = {str(row["source_id"]): dict(row) for row in candidates if decisions.get(str(row["source_id"])) not in BLOCKED_AUDIT}
    if len(allowed) != len([row for row in candidates if decisions.get(str(row["source_id"])) not in BLOCKED_AUDIT]):
        raise ValueError("duplicate negative source IDs")
    queues = {
        "bm25_hard": sorted(allowed, key=lambda key: (-float(allowed[key]["bm25_score"]), stable_hex("bm25", target_group_id, key))),
        "qwen_hard": sorted(allowed, key=lambda key: (-float(allowed[key]["qwen_similarity"]), stable_hex("qwen", target_group_id, key))),
        "random": sorted(allowed, key=lambda key: stable_hex("random", target_group_id, key)),
    }
    positions = Counter(); used = set(); output = []
    while len(used) < len(allowed):
        progressed = False
        for reason in MIX_CYCLE:
            queue = queues[reason]
            while positions[reason] < len(queue) and queue[positions[reason]] in used:
                positions[reason] += 1
            if positions[reason] >= len(queue):
                continue
            source_id = queue[positions[reason]]; positions[reason] += 1
            used.add(source_id); row = dict(allowed[source_id]); row["selection_reason"] = reason
            row["audit_decision"] = decisions.get(source_id); output.append(row); progressed = True
        if not progressed:
            break
    return output


def stable_candidate_order(candidate_ids: Sequence[str], target_group_id: str) -> list[str]:
    return sorted(candidate_ids, key=lambda source_id: stable_hex(RULE_VERSION, "order", target_group_id, source_id))


def deterministic_target_cap(rows: Sequence[Mapping], target_count: int) -> list[Mapping]:
    """Keep every document represented, then fill by stable target ID hash."""
    by_document: dict[str, list[Mapping]] = {}
    for row in rows:
        by_document.setdefault(str(row["document_group_id"]), []).append(row)
    if target_count < len(by_document) or target_count > len(rows):
        raise ValueError("target cap must retain at least one row per document")
    selected = []
    remaining = []
    for document_id in sorted(by_document):
        ordered = sorted(by_document[document_id], key=lambda row: stable_hex(SPLIT_SEED, "blind-cap", row["target_group_id"]))
        selected.append(ordered[0]); remaining.extend(ordered[1:])
    remaining.sort(key=lambda row: stable_hex(SPLIT_SEED, "blind-fill", row["target_group_id"]))
    selected.extend(remaining[:target_count - len(selected)])
    return sorted(selected, key=lambda row: str(row["target_group_id"]))


def validate_expanded_rows(examples: Sequence[Mapping], sources: Sequence[Mapping]) -> dict:
    source_by_id = {row["source_id"]: row for row in sources}
    if len(source_by_id) != len(sources):
        raise ValueError("duplicate source_id")
    documents = set(); targets = set()
    for example in examples:
        candidates = list(example["candidate_source_ids"]); gold = set(example["gold_source_ids"])
        if len(candidates) != 8 or len(candidates) != len(set(candidates)):
            raise ValueError("candidate set must contain 8 unique IDs")
        if not gold or not gold <= set(candidates):
            raise ValueError("gold sources missing")
        if candidates != stable_candidate_order(candidates, example["target_group_id"]):
            raise ValueError("candidate order policy mismatch")
        rows = [source_by_id[source_id] for source_id in candidates]
        if any(row["document_group_id"] != example["document_group_id"] for row in rows):
            raise ValueError("cross-document candidate")
        negatives = [row["text"] for row in rows if row["source_id"] not in gold]
        positives = [row["text"] for row in rows if row["source_id"] in gold]
        if any(automatic_negative_exclusion(text, positives) for text in negatives):
            raise ValueError("automatically blocked pseudo-negative remains")
        documents.add(example["document_group_id"]); targets.add(example["target_group_id"])
    return {"example_count": len(examples), "document_count": len(documents), "target_count": len(targets)}
