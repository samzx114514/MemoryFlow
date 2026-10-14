from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any, Iterable

from memoryflow.holdout import shuffle_candidate_ids, target_hash, verify_checksums, write_checksums


GROUP_SEED = "memoryflow-b6-group-split-v1"
ORDER_SEEDS = {
    "train": "memoryflow-b6-train-order-v1",
    "validation": "memoryflow-b6-validation-order-v1",
    "final_test": "memoryflow-b6-final-test-order-v1",
}


def _normalized_text(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def candidate_set_hash(candidate_ids: Iterable[str]) -> str:
    payload = json.dumps(sorted(candidate_ids), ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def target_candidate_hash(text: str, candidate_ids: Iterable[str]) -> str:
    payload = json.dumps(
        {"target": _normalized_text(text), "candidate_ids": sorted(candidate_ids)},
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def discover_run_roles(
    examples: Iterable[dict[str, Any]],
    debug_rows: Iterable[dict[str, Any]],
    b4_rows: Iterable[dict[str, Any]],
) -> tuple[set[str], set[str]]:
    all_runs = {row.get("run_id", "") for row in examples} - {""}
    exposed = ({row.get("run_id", "") for row in debug_rows} | {row.get("run_id", "") for row in b4_rows}) - {""}
    missing = exposed - all_runs
    if missing:
        raise ValueError(f"exposed runs missing from processed examples: {sorted(missing)}")
    unseen = all_runs - exposed
    if exposed & unseen or exposed | unseen != all_runs:
        raise AssertionError("run role partition is invalid")
    return exposed, unseen


def split_exposed_runs(
    exposed_runs: Iterable[str], seed: str = GROUP_SEED, validation_ratio: float = 0.2
) -> tuple[set[str], set[str]]:
    runs = sorted(
        set(exposed_runs),
        key=lambda run_id: (hashlib.sha256(f"{seed}:{run_id}".encode("utf-8")).hexdigest(), run_id),
    )
    if not runs:
        return set(), set()
    validation_count = round(len(runs) * validation_ratio)
    if len(runs) > 1:
        validation_count = min(len(runs) - 1, max(1, validation_count))
    validation = set(runs[:validation_count])
    train = set(runs[validation_count:])
    return train, validation


def _index_sources(source_catalog: Iterable[dict[str, Any]]) -> dict[str, dict[str, str]]:
    output: dict[str, dict[str, str]] = {}
    for row in source_catalog:
        source_id = row.get("id", "")
        compact = {"id": source_id, "title": row.get("title", ""), "memory_text": row.get("memory_text", "")}
        if source_id in output and output[source_id] != compact:
            raise ValueError(f"conflicting source text for {source_id}")
        if source_id:
            output[source_id] = compact
    return output


def build_eligible_pool(
    examples: Iterable[dict[str, Any]],
    candidate_rows: Iterable[dict[str, Any]],
    source_catalog: Iterable[dict[str, Any]],
    run_ids: set[str],
) -> list[dict[str, Any]]:
    candidate_by_id = {row.get("example_id"): row for row in candidate_rows}
    source_by_id = _index_sources(source_catalog)
    output = []
    for example in examples:
        run_id = example.get("run_id", "")
        if run_id not in run_ids:
            continue
        example_id = example.get("example_id", "")
        text = example.get("target", {}).get("text", "")
        ids = candidate_by_id.get(example_id, {}).get("candidate_sets", {}).get("4", [])
        gold = list(dict.fromkeys(example.get("gold_source_ids", [])))
        if not example_id or not _normalized_text(text):
            continue
        if len(ids) != 4 or len(set(ids)) != 4:
            continue
        if not gold or not set(gold).issubset(ids):
            continue
        if any(source_id not in source_by_id or not _normalized_text(source_by_id[source_id]["memory_text"]) for source_id in ids):
            continue
        output.append({
            "example_id": example_id,
            "run_id": run_id,
            "target": example["target"],
            "candidate_ids": list(ids),
            "gold_source_ids": gold,
            "label_type": example.get("label_type", "silver_inline_citation"),
            "target_hash": target_hash(text),
            "target_candidate_hash": target_candidate_hash(text, ids),
            "candidate_set_hash": candidate_set_hash(ids),
        })
    return output


def _stable_rank(seed: str, example_id: str) -> str:
    return hashlib.sha256(f"{seed}:{example_id}".encode("utf-8")).hexdigest()


def deduplicate_partition_pools(
    pools: dict[str, list[dict[str, Any]]]
) -> tuple[dict[str, list[dict[str, Any]]], dict[str, dict[str, int]]]:
    priority = ("final_test", "validation", "train")
    globally_seen = {"target_hash": set(), "target_candidate_hash": set(), "candidate_set_hash": set()}
    output: dict[str, list[dict[str, Any]]] = {}
    reports: dict[str, dict[str, int]] = {}
    for partition in priority:
        kept = []
        reasons: Counter[str] = Counter()
        partition_values = {key: set() for key in globally_seen}
        rows = sorted(pools.get(partition, []), key=lambda row: (_stable_rank(f"b6-dedup-{partition}", row["example_id"]), row["example_id"]))
        for row in rows:
            rejected = False
            for key in ("target_hash", "target_candidate_hash", "candidate_set_hash"):
                if row[key] in globally_seen[key]:
                    reasons[f"cross_partition_{key}"] += 1
                    rejected = True
                    break
            if rejected:
                continue
            kept.append(row)
            for key in partition_values:
                partition_values[key].add(row[key])
        for key in globally_seen:
            globally_seen[key].update(partition_values[key])
        output[partition] = kept
        reports[partition] = dict(sorted(reasons.items()))
    return output, reports


def sample_partition(
    pool: list[dict[str, Any]],
    target_single: int,
    target_multi: int,
    per_run_cap: int,
    seed: str,
) -> list[dict[str, Any]]:
    buckets = {
        "single": sorted((row for row in pool if len(row["gold_source_ids"]) == 1), key=lambda row: (_stable_rank(seed, row["example_id"]), row["example_id"])),
        "multi": sorted((row for row in pool if len(row["gold_source_ids"]) > 1), key=lambda row: (_stable_rank(seed, row["example_id"]), row["example_id"])),
    }
    goals = {"single": target_single, "multi": target_multi}
    per_run_class = {"single": Counter(), "multi": Counter()}
    for label, rows in buckets.items():
        per_run_class[label].update(row["run_id"] for row in rows)
    capacities = {
        label: sum(min(count, per_run_cap) for count in counts.values())
        for label, counts in per_run_class.items()
    }
    class_order = sorted(
        ("single", "multi"),
        key=lambda label: (capacities[label] / goals[label] if goals[label] else float("inf"), label),
    )
    run_counts = Counter()
    selected: list[dict[str, Any]] = []
    selected_ids: set[str] = set()
    for label in class_order:
        selected_in_class = 0
        for row in buckets[label]:
            if selected_in_class >= goals[label]:
                break
            if run_counts[row["run_id"]] >= per_run_cap:
                continue
            selected.append(row)
            selected_ids.add(row["example_id"])
            run_counts[row["run_id"]] += 1
            selected_in_class += 1

    target_total = target_single + target_multi
    for row in sorted(pool, key=lambda item: (_stable_rank(f"{seed}:fallback", item["example_id"]), item["example_id"])):
        if len(selected) >= target_total:
            break
        if row["example_id"] in selected_ids or run_counts[row["run_id"]] >= per_run_cap:
            continue
        selected.append(row)
        selected_ids.add(row["example_id"])
        run_counts[row["run_id"]] += 1
    return sorted(selected, key=lambda row: (_stable_rank(f"{seed}:output", row["example_id"]), row["example_id"]))


def materialize_rows(
    selected: Iterable[dict[str, Any]],
    source_catalog: Iterable[dict[str, Any]],
    split: str,
    order_seed: str,
) -> list[dict[str, Any]]:
    source_by_id = _index_sources(source_catalog)
    output = []
    for row in selected:
        candidate_ids = shuffle_candidate_ids(row["candidate_ids"], order_seed, row["example_id"])
        output.append({
            "example_id": row["example_id"],
            "run_id": row["run_id"],
            "split": split,
            "target": row["target"],
            "candidates": [source_by_id[source_id] for source_id in candidate_ids],
            "gold_source_ids": row["gold_source_ids"],
            "candidate_count": 4,
            "label_type": row["label_type"],
        })
    return output


def _row_keys(row: dict[str, Any]) -> dict[str, str]:
    ids = [candidate.get("id", "") for candidate in row.get("candidates", [])]
    text = row.get("target", {}).get("text", "")
    return {
        "run_id": row.get("run_id", ""),
        "example_id": row.get("example_id", ""),
        "target_hash": target_hash(text),
        "target_candidate_hash": target_candidate_hash(text, ids),
        "candidate_set_hash": candidate_set_hash(ids),
    }


def validate_cross_splits(rows_by_split: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    split_checks: dict[str, dict[str, Any]] = {}
    keys_by_split: dict[str, dict[str, set[str]]] = {}
    for split, rows in rows_by_split.items():
        keys = [_row_keys(row) for row in rows]
        keys_by_split[split] = {key: {row[key] for row in keys} for key in keys[0]} if keys else {key: set() for key in ("run_id", "example_id", "target_hash", "target_candidate_hash", "candidate_set_hash")}
        split_checks[split] = {
            "example_count": len(rows),
            "duplicate_example_id_count": len(rows) - len(keys_by_split[split]["example_id"]),
            "exact_four_candidates": sum(row.get("candidate_count") == 4 and len(row.get("candidates", [])) == 4 for row in rows),
            "candidate_ids_unique": all(len({x.get("id") for x in row.get("candidates", [])}) == 4 for row in rows),
            "gold_resolves": all(set(row.get("gold_source_ids", [])) <= {x.get("id") for x in row.get("candidates", [])} for row in rows),
            "source_text_nonempty": all(_normalized_text(x.get("memory_text", "")) for row in rows for x in row.get("candidates", [])),
        }
    overlaps = {}
    names = sorted(rows_by_split)
    for index, left in enumerate(names):
        for right in names[index + 1:]:
            overlaps[f"{left}__{right}"] = {
                key: len(keys_by_split[left][key] & keys_by_split[right][key])
                for key in ("run_id", "example_id", "target_hash", "target_candidate_hash", "candidate_set_hash")
            }
    passed = all(
        check["duplicate_example_id_count"] == 0
        and check["exact_four_candidates"] == check["example_count"]
        and check["candidate_ids_unique"]
        and check["gold_resolves"]
        and check["source_text_nonempty"]
        for check in split_checks.values()
    ) and all(not any(values.values()) for values in overlaps.values())
    return {"passed": passed, "splits": split_checks, "cross_split_overlaps": overlaps}


def slot_distribution(rows: Iterable[dict[str, Any]]) -> list[dict[str, int]]:
    counts = [{"slot": index, "candidate_count": 0, "gold_count": 0, "single_positive_gold_count": 0} for index in range(4)]
    for row in rows:
        gold = set(row["gold_source_ids"])
        for index, candidate in enumerate(row["candidates"]):
            counts[index]["candidate_count"] += 1
            if candidate["id"] in gold:
                counts[index]["gold_count"] += 1
                if len(gold) == 1:
                    counts[index]["single_positive_gold_count"] += 1
    return counts


def _write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")


def _bundle_schema(sealed: bool) -> str:
    note = "This final-test package is locally sealed and must not be uploaded before configuration freeze." if sealed else "This package is intended for the B6 learning stage."
    return f"""# MemoryFlow B6 bundle schema

{note}

`examples.jsonl` follows the Checkpoint B4 row format: `example_id`, `run_id`, `split`, `target`, exactly four self-contained `candidates`, `gold_source_ids`, `candidate_count`, and `label_type`.

`source_catalog.jsonl` contains every unique `{chr(123)}id, title, memory_text{chr(125)}` referenced by this bundle. URLs, raw citation IDs, raw logs, model outputs, and scores are excluded.

`manifest.json` records group/sample seeds, counts, and sealed status. `checksums.sha256` covers every other file in the directory.
"""


def _sampling_report(rows: list[dict[str, Any]], seed: str, group_seed: str, sealed: bool) -> str:
    single = sum(len(row["gold_source_ids"]) == 1 for row in rows)
    header = f"""# MemoryFlow B6 {'sealed final-test' if sealed else 'learning'} sampling report

- Group seed: `{group_seed}`
- Candidate order seed: `{seed}`
- Examples: **{len(rows)}**
- Single-positive: **{single}**
- Multi-positive: **{len(rows) - single}**
- Independent runs: **{len({row['run_id'] for row in rows})}**
- Exact K=4 and gold resolution are validated before delivery.
"""
    if sealed:
        return header + "\nThis report intentionally omits candidate-position details. Do not upload or evaluate this package before the B6 method and configuration are frozen.\n"
    table = ["| Position | Candidates | Gold appearances | Single-positive gold |", "|---:|---:|---:|---:|"]
    table.extend(f"| {item['slot']} | {item['candidate_count']} | {item['gold_count']} | {item['single_positive_gold_count']} |" for item in slot_distribution(rows))
    return header + "\n## Candidate-position distribution\n\n" + "\n".join(table) + "\n"


def write_bundle(
    root: Path,
    rows: list[dict[str, Any]],
    *,
    seed: str,
    group_seed: str,
    sealed: bool,
    replace_generated: bool = False,
) -> dict[str, Any]:
    expected_names = {"examples.jsonl", "source_catalog.jsonl", "manifest.json", "schema.md", "sampling_report.md", "checksums.sha256"}
    if root.exists() and any(root.iterdir()):
        existing_names = {path.name for path in root.iterdir()}
        if not replace_generated or not existing_names <= expected_names:
            raise FileExistsError(f"refusing to overwrite nonempty bundle: {root}")
    root.mkdir(parents=True, exist_ok=True)
    source_by_id: dict[str, dict[str, str]] = {}
    for row in rows:
        for source in row["candidates"]:
            previous = source_by_id.get(source["id"])
            if previous is not None and previous != source:
                raise ValueError(f"conflicting source text for {source['id']}")
            source_by_id[source["id"]] = source
    _write_jsonl(root / "examples.jsonl", rows)
    _write_jsonl(root / "source_catalog.jsonl", (source_by_id[source_id] for source_id in sorted(source_by_id)))
    single = sum(len(row["gold_source_ids"]) == 1 for row in rows)
    manifest = {
        "schema_version": 1,
        "split": rows[0]["split"] if rows else "",
        "group_field": "run_id",
        "group_seed": group_seed,
        "candidate_order_seed": seed,
        "sealed": sealed,
        "example_count": len(rows),
        "single_positive_count": single,
        "multi_positive_count": len(rows) - single,
        "run_count": len({row["run_id"] for row in rows}),
        "source_count": len(source_by_id),
        "models_or_scores_used": False,
    }
    (root / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    (root / "schema.md").write_text(_bundle_schema(sealed), encoding="utf-8", newline="\n")
    (root / "sampling_report.md").write_text(_sampling_report(rows, seed, group_seed, sealed), encoding="utf-8", newline="\n")
    checksum_path = write_checksums(root)
    return {
        "checksums_valid": verify_checksums(root),
        "bundle_checksum": hashlib.sha256(checksum_path.read_bytes()).hexdigest(),
        "size_bytes": sum(path.stat().st_size for path in root.rglob("*") if path.is_file()),
        "manifest": manifest,
    }
