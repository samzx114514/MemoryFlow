from __future__ import annotations

import hashlib
import json
import random
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable


DEFAULT_SEED = "memoryflow-b4-holdout-v1"


def _normalized_text(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def target_hash(text: str) -> str:
    return hashlib.sha256(_normalized_text(text).encode("utf-8")).hexdigest()


def candidate_fingerprint(text: str, candidate_ids: Iterable[str]) -> str:
    payload = json.dumps(
        {"target": _normalized_text(text), "candidate_ids": sorted(candidate_ids)},
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def shuffle_candidate_ids(candidate_ids: Iterable[str], seed: str, example_id: str) -> list[str]:
    output = list(candidate_ids)
    digest = hashlib.sha256(f"{seed}{example_id}".encode("utf-8")).digest()
    random.Random(int.from_bytes(digest, "big")).shuffle(output)
    return output


def _selection_rank(seed: str, example_id: str) -> str:
    return hashlib.sha256(f"{seed}:select:{example_id}".encode("utf-8")).hexdigest()


def _index_sources(source_catalog: Iterable[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    indexed: dict[str, dict[str, Any]] = {}
    for source in source_catalog:
        source_id = source.get("id")
        if not source_id:
            continue
        compact = {
            "id": source_id,
            "title": source.get("title", ""),
            "memory_text": source.get("memory_text", ""),
        }
        previous = indexed.get(source_id)
        if previous is not None and previous != compact:
            raise ValueError(f"conflicting source text for {source_id}")
        indexed[source_id] = compact
    return indexed


def _debug_keys(debug_rows: Iterable[dict[str, Any]]) -> tuple[set[str], set[str], set[str], set[str]]:
    example_ids, run_ids, target_hashes, fingerprints = set(), set(), set(), set()
    for row in debug_rows:
        example_ids.add(row.get("example_id", ""))
        run_ids.add(row.get("run_id", ""))
        text = row.get("target", {}).get("text", "")
        ids = [candidate.get("id", "") for candidate in row.get("candidates", [])]
        if text:
            target_hashes.add(target_hash(text))
            fingerprints.add(candidate_fingerprint(text, ids))
    return example_ids - {""}, run_ids - {""}, target_hashes, fingerprints


def _eligible_rows(
    examples: Iterable[dict[str, Any]],
    candidate_rows: Iterable[dict[str, Any]],
    source_by_id: dict[str, dict[str, Any]],
    splits: dict[str, Any],
    debug_rows: Iterable[dict[str, Any]],
    seed: str,
) -> tuple[list[dict[str, Any]], Counter[str]]:
    candidate_by_id = {row.get("example_id"): row for row in candidate_rows}
    test_ids = set(splits.get("test", []))
    test_runs = set(splits.get("test_runs", []))
    debug_ids, debug_runs, debug_targets, debug_pairs = _debug_keys(debug_rows)
    discards: Counter[str] = Counter()
    candidates: list[dict[str, Any]] = []

    for example in examples:
        example_id = example.get("example_id", "")
        run_id = example.get("run_id", "")
        if example_id not in test_ids or run_id not in test_runs:
            discards["not_in_test_split"] += 1
            continue
        if example_id in debug_ids:
            discards["debug_example_overlap"] += 1
            continue
        if not run_id or run_id in debug_runs:
            discards["debug_group_overlap_or_missing_group"] += 1
            continue
        text = example.get("target", {}).get("text", "")
        if not _normalized_text(text):
            discards["empty_target"] += 1
            continue
        row = candidate_by_id.get(example_id, {})
        ids = row.get("candidate_sets", {}).get("4", [])
        if len(ids) != 4:
            discards["candidate_count_not_four"] += 1
            continue
        if len(set(ids)) != 4:
            discards["duplicate_candidate_id"] += 1
            continue
        gold = list(dict.fromkeys(example.get("gold_source_ids", [])))
        if not gold:
            discards["missing_gold"] += 1
            continue
        if not set(gold).issubset(ids):
            discards["gold_not_in_candidates"] += 1
            continue
        if any(source_id not in source_by_id for source_id in ids):
            discards["unresolved_candidate_source"] += 1
            continue
        if any(not _normalized_text(source_by_id[source_id]["memory_text"]) for source_id in ids):
            discards["empty_source_text"] += 1
            continue
        text_digest = target_hash(text)
        pair_digest = candidate_fingerprint(text, ids)
        if text_digest in debug_targets:
            discards["debug_target_hash_overlap"] += 1
            continue
        if pair_digest in debug_pairs:
            discards["debug_target_candidate_overlap"] += 1
            continue
        candidates.append({
            "example": example,
            "candidate_ids": ids,
            "gold_source_ids": gold,
            "target_hash": text_digest,
            "pair_hash": pair_digest,
            "rank": _selection_rank(seed, example_id),
        })

    # Deterministically retain only one row for each exact target and target/candidate-set pair.
    candidates.sort(key=lambda item: (item["rank"], item["example"]["example_id"]))
    unique: list[dict[str, Any]] = []
    seen_targets, seen_pairs = set(), set()
    for item in candidates:
        if item["target_hash"] in seen_targets:
            discards["duplicate_target_text"] += 1
            continue
        if item["pair_hash"] in seen_pairs:
            discards["duplicate_target_candidate_set"] += 1
            continue
        seen_targets.add(item["target_hash"])
        seen_pairs.add(item["pair_hash"])
        unique.append(item)
    return unique, discards


def _select_with_quotas(
    eligible: list[dict[str, Any]], target_single: int, target_multi: int, per_group_cap: int
) -> list[dict[str, Any]]:
    buckets = {
        "single": [item for item in eligible if len(item["gold_source_ids"]) == 1],
        "multi": [item for item in eligible if len(item["gold_source_ids"]) > 1],
    }
    goals = {"single": target_single, "multi": target_multi}
    positions = {"single": 0, "multi": 0}
    counts = Counter()
    selected: list[dict[str, Any]] = []
    selected_ids: set[str] = set()
    selected_class_counts = Counter()

    # Alternate classes so neither class consumes the group cap first.
    while True:
        progressed = False
        for label in ("single", "multi"):
            if selected_class_counts[label] >= goals[label]:
                continue
            bucket = buckets[label]
            while positions[label] < len(bucket):
                item = bucket[positions[label]]
                positions[label] += 1
                run_id = item["example"]["run_id"]
                if counts[run_id] >= per_group_cap:
                    continue
                selected.append(item)
                selected_ids.add(item["example"]["example_id"])
                counts[run_id] += 1
                selected_class_counts[label] += 1
                progressed = True
                break
        if not progressed:
            break
        if selected_class_counts["single"] >= target_single and selected_class_counts["multi"] >= target_multi:
            break

    # If one class is short, fill the requested total from the other class.
    target_total = target_single + target_multi
    for item in sorted(eligible, key=lambda value: (value["rank"], value["example"]["example_id"])):
        if len(selected) >= target_total:
            break
        example_id = item["example"]["example_id"]
        run_id = item["example"]["run_id"]
        if example_id in selected_ids or counts[run_id] >= per_group_cap:
            continue
        selected.append(item)
        selected_ids.add(example_id)
        counts[run_id] += 1
    return sorted(selected, key=lambda item: (item["rank"], item["example"]["example_id"]))


def build_holdout(
    examples: list[dict[str, Any]],
    candidate_rows: list[dict[str, Any]],
    source_catalog: list[dict[str, Any]],
    splits: dict[str, Any],
    debug_rows: list[dict[str, Any]],
    *,
    seed: str = DEFAULT_SEED,
    target_single: int = 100,
    target_multi: int = 100,
    per_group_cap: int = 2,
) -> dict[str, Any]:
    source_by_id = _index_sources(source_catalog)
    eligible, discards = _eligible_rows(examples, candidate_rows, source_by_id, splits, debug_rows, seed)
    selected = _select_with_quotas(eligible, target_single, target_multi, per_group_cap)
    rows: list[dict[str, Any]] = []
    referenced_sources: set[str] = set()
    for item in selected:
        example = item["example"]
        shuffled = shuffle_candidate_ids(item["candidate_ids"], seed, example["example_id"])
        referenced_sources.update(shuffled)
        rows.append({
            "example_id": example["example_id"],
            "run_id": example["run_id"],
            "split": "test",
            "target": example["target"],
            "candidates": [source_by_id[source_id] for source_id in shuffled],
            "gold_source_ids": item["gold_source_ids"],
            "candidate_count": 4,
            "label_type": example.get("label_type", "silver_inline_citation"),
        })

    single_count = sum(len(row["gold_source_ids"]) == 1 for row in rows)
    slot_candidates = [0, 0, 0, 0]
    slot_gold = [0, 0, 0, 0]
    single_positions = [0, 0, 0, 0]
    for row in rows:
        gold = set(row["gold_source_ids"])
        for slot, source in enumerate(row["candidates"]):
            slot_candidates[slot] += 1
            if source["id"] in gold:
                slot_gold[slot] += 1
                if len(gold) == 1:
                    single_positions[slot] += 1
    return {
        "examples": rows,
        "sources": [source_by_id[source_id] for source_id in sorted(referenced_sources)],
        "report": {
            "seed": seed,
            "group_field": "run_id",
            "request_id_available": False,
            "target_single": target_single,
            "target_multi": target_multi,
            "actual_single": single_count,
            "actual_multi": len(rows) - single_count,
            "example_count": len(rows),
            "independent_group_count": len({row["run_id"] for row in rows}),
            "max_examples_per_group": max(Counter(row["run_id"] for row in rows).values(), default=0),
            "eligible_single": sum(len(item["gold_source_ids"]) == 1 for item in eligible),
            "eligible_multi": sum(len(item["gold_source_ids"]) > 1 for item in eligible),
            "discard_reasons": dict(sorted(discards.items())),
            "slots": [
                {"slot": slot, "candidate_count": slot_candidates[slot], "gold_count": slot_gold[slot], "single_positive_gold_count": single_positions[slot]}
                for slot in range(4)
            ],
        },
    }


def _hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def write_checksums(root: Path) -> Path:
    lines = []
    for path in sorted(item for item in root.rglob("*") if item.is_file() and item.name != "checksums.sha256"):
        lines.append(f"{_hash_file(path)}  {path.relative_to(root).as_posix()}")
    output = root / "checksums.sha256"
    output.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return output


def verify_checksums(root: Path) -> bool:
    checksum_path = root / "checksums.sha256"
    if not checksum_path.is_file():
        return False
    for line in checksum_path.read_text(encoding="utf-8").splitlines():
        expected, relative = line.split("  ", 1)
        path = root / relative
        if not path.is_file() or _hash_file(path) != expected:
            return False
    return True


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def validate_bundle(root: Path, debug_rows: list[dict[str, Any]]) -> dict[str, Any]:
    try:
        rows = _read_jsonl(root / "examples.jsonl")
        sources = _read_jsonl(root / "source_catalog.jsonl")
        json.loads((root / "manifest.json").read_text(encoding="utf-8"))
        json_parseable = True
    except (OSError, ValueError, json.JSONDecodeError):
        rows, sources, json_parseable = [], [], False
    source_ids = {source.get("id") for source in sources}
    source_id_rows: dict[str, set[tuple[str, str]]] = defaultdict(set)
    for source in sources:
        source_id_rows[source.get("id", "")].add((source.get("title", ""), source.get("memory_text", "")))
    source_catalog_duplicate_id_count = len(sources) - len(source_ids)
    source_catalog_conflict_count = sum(len(values) > 1 for values in source_id_rows.values())
    debug_ids, debug_runs, debug_targets, debug_pairs = _debug_keys(debug_rows)
    example_ids = [row.get("example_id", "") for row in rows]
    run_ids = [row.get("run_id", "") for row in rows]
    row_targets = [target_hash(row.get("target", {}).get("text", "")) for row in rows]
    row_pairs = [candidate_fingerprint(row.get("target", {}).get("text", ""), [x.get("id", "") for x in row.get("candidates", [])]) for row in rows]
    exact_four = sum(len(row.get("candidates", [])) == 4 and row.get("candidate_count") == 4 for row in rows)
    candidates_unique = all(len({item.get("id") for item in row.get("candidates", [])}) == 4 for row in rows)
    all_candidates_resolve = all(item.get("id") in source_ids for row in rows for item in row.get("candidates", []))
    all_gold_resolve = all(set(row.get("gold_source_ids", [])).issubset({item.get("id") for item in row.get("candidates", [])}) for row in rows)
    nonempty_sources = all(_normalized_text(item.get("memory_text", "")) for row in rows for item in row.get("candidates", []))
    group_counts = Counter(run_ids)
    gold_first_count = sum(bool(row.get("candidates")) and row["candidates"][0].get("id") in set(row.get("gold_source_ids", [])) for row in rows)
    checksums_valid = verify_checksums(root)
    result = {
        "json_parseable": json_parseable,
        "example_count": len(rows),
        "duplicate_example_id_count": len(example_ids) - len(set(example_ids)),
        "duplicate_target_hash_count": len(row_targets) - len(set(row_targets)),
        "duplicate_target_candidate_fingerprint_count": len(row_pairs) - len(set(row_pairs)),
        "debug_example_id_overlap": len(set(example_ids) & debug_ids),
        "debug_group_overlap": len(set(run_ids) & debug_runs),
        "debug_target_hash_overlap": len(set(row_targets) & debug_targets),
        "debug_target_candidate_fingerprint_overlap": len(set(row_pairs) & debug_pairs),
        "exact_four_candidates": exact_four,
        "candidate_ids_unique": candidates_unique,
        "source_catalog_duplicate_id_count": source_catalog_duplicate_id_count,
        "source_catalog_conflict_count": source_catalog_conflict_count,
        "all_candidates_resolve": all_candidates_resolve,
        "all_gold_resolve": all_gold_resolve,
        "gold_resolution_rate": 1.0 if all_gold_resolve else 0.0,
        "nonempty_source_text": nonempty_sources,
        "max_examples_per_group": max(group_counts.values(), default=0),
        "gold_first_count": gold_first_count,
        "gold_first_all": bool(rows) and gold_first_count == len(rows),
        "checksums_valid": checksums_valid,
    }
    result["passed"] = bool(rows) and all((
        json_parseable,
        result["duplicate_example_id_count"] == 0,
        result["duplicate_target_hash_count"] == 0,
        result["duplicate_target_candidate_fingerprint_count"] == 0,
        result["debug_example_id_overlap"] == 0,
        result["debug_group_overlap"] == 0,
        result["debug_target_hash_overlap"] == 0,
        result["debug_target_candidate_fingerprint_overlap"] == 0,
        exact_four == len(rows),
        candidates_unique,
        source_catalog_duplicate_id_count == 0,
        source_catalog_conflict_count == 0,
        all_candidates_resolve,
        all_gold_resolve,
        nonempty_sources,
        result["max_examples_per_group"] <= 2,
        not result["gold_first_all"],
        checksums_valid,
    ))
    return result
