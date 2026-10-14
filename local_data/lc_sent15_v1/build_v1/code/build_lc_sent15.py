"""Two-pass streaming builder for the frozen LC-Sent-15-v1 protocol."""

from __future__ import annotations

import argparse
import collections
import hashlib
import json
import os
import shutil
import sys
import time
from pathlib import Path

from lc_sent15 import (
    ParseError,
    detect_language,
    deterministic_candidates,
    normalize_text,
    parse_prompt,
    parse_response,
    sha256_text,
    source_id,
    split_for_document,
    target_id,
)


SCHEMA_VERSION = "lc-sent-15-v1"
LABEL_TYPE = "silver_longcite"
TARGET_QUOTAS = {"train": 854, "dev": 228, "reserve": 218}
EXPECTED_SOURCE_SIZE = 5_726_201_192
EXPECTED_SOURCE_SHA256 = "8eb96dad6496d8d28d983982e6f623adc1e44ffa9dce215ffc7d56fd0336623b"


def json_line(value: dict) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":")) + "\n"


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            block = handle.read(8 * 1024 * 1024)
            if not block:
                break
            digest.update(block)
    return digest.hexdigest()


def load_row(line: str, row_index: int) -> tuple[dict | None, str | None]:
    if not line.strip():
        return None, "blank_jsonl_line"
    try:
        row = json.loads(line)
    except json.JSONDecodeError:
        return None, "json_decode_error"
    if not isinstance(row, dict) or not isinstance(row.get("prompt"), str) or not isinstance(row.get("response"), str):
        return None, "missing_prompt_or_response"
    return row, None


def classify_statement(statement, valid_sources: dict[int, str]) -> tuple[str, str | None]:
    if statement.status != "valid":
        return statement.status, statement.error
    positive_count = len(statement.citation_ids)
    if positive_count == 1:
        if len(valid_sources) < 15:
            return "single_ineligible", "fewer_than_15_valid_sources"
        if len(valid_sources) - 1 < 14:
            return "single_ineligible", "fewer_than_14_negatives"
        return "single_eligible", None
    if positive_count >= 2:
        if positive_count > 15:
            return "multi_ineligible", "positive_count_exceeds_15"
        if len(valid_sources) - positive_count < 15 - positive_count:
            return "multi_ineligible", "insufficient_negatives_for_15"
        return "multi_eligible", None
    return "no_citation", None


def parse_row(row: dict):
    prompt = parse_prompt(row["prompt"])
    valid_sources = {unit.sentence_index: unit.text for unit in prompt.sources if unit.text.strip()}
    statements = parse_response(row["response"], set(valid_sources))
    return prompt, valid_sources, statements


def selection_hash(split: str, example_id: str, target_text: str) -> str:
    return sha256_text(f"LC-Sent-15-v1:select:{split}:{example_id}:{target_text}")


def first_pass(source: Path) -> dict:
    stats = collections.Counter()
    reason_counts = collections.Counter()
    document_assignments: dict[str, dict] = {}
    eligible_single: dict[str, list[tuple[str, int, int, str]]] = {key: [] for key in TARGET_QUOTAS}
    eligible_multi = collections.Counter()
    started = time.monotonic()
    with source.open("r", encoding="utf-8") as handle:
        for row_index, line in enumerate(handle):
            stats["total_jsonl_lines"] += 1
            row, error = load_row(line, row_index)
            if error:
                stats["row_format_errors"] += 1
                reason_counts[error] += 1
                continue
            try:
                prompt, valid_sources, statements = parse_row(row)
            except ParseError as parse_error:
                stats["row_format_errors"] += 1
                reason_counts[str(parse_error)] += 1
                continue
            stats["parsed_rows"] += 1
            split = split_for_document(prompt.document_id)
            prior = document_assignments.get(prompt.document_id)
            assignment = {
                "schema_version": SCHEMA_VERSION,
                "document_id": prompt.document_id,
                "document_sha256": prompt.document_sha256,
                "split": split,
                "first_row_index": row_index,
                "official_source_unit_count": len(prompt.sources),
                "valid_source_unit_count": len(valid_sources),
            }
            if prior is None:
                document_assignments[prompt.document_id] = assignment
                stats[f"assigned_documents_{split}"] += 1
            else:
                stats["repeated_document_rows"] += 1
                if prior["split"] != split or prior["document_sha256"] != prompt.document_sha256:
                    raise AssertionError("document_assignment_conflict")
            for statement in statements:
                stats["statements_total"] += 1
                category, reason = classify_statement(statement, valid_sources)
                stats[f"statements_{category}"] += 1
                if reason:
                    reason_counts[reason] += 1
                if category == "single_eligible":
                    example_id = target_id(row_index, statement.statement_index)
                    eligible_single[split].append(
                        (selection_hash(split, example_id, statement.text), row_index, statement.statement_index, example_id)
                    )
                elif category == "multi_eligible":
                    eligible_multi[split] += 1
    selected: dict[str, list[tuple[str, int, int, str]]] = {}
    for split, entries in eligible_single.items():
        entries.sort(key=lambda item: (item[0], item[3]))
        selected[split] = entries[: TARGET_QUOTAS[split]]
    return {
        "stats": stats,
        "reason_counts": reason_counts,
        "document_assignments": document_assignments,
        "eligible_single": eligible_single,
        "eligible_multi": eligible_multi,
        "selected": selected,
        "elapsed_seconds": time.monotonic() - started,
    }


def build_example(row_index: int, prompt, valid_sources: dict[int, str], statement, split: str) -> tuple[dict, list[dict]]:
    example_id = target_id(row_index, statement.statement_index)
    source_ids_by_index = {
        index: source_id(prompt.document_sha256, index) for index in valid_sources
    }
    positive_ids = [source_ids_by_index[index] for index in statement.citation_ids]
    candidate_ids = deterministic_candidates(example_id, positive_ids, source_ids_by_index.values(), 15)
    positive_set = set(positive_ids)
    candidates = [
        {"source_id": candidate_id, "label": 1 if candidate_id in positive_set else 0}
        for candidate_id in candidate_ids
    ]
    source_index_by_id = {value: key for key, value in source_ids_by_index.items()}
    full_candidates = [
        {
            "position": position,
            "source_id": candidate_id,
            "sentence_index": source_index_by_id[candidate_id],
            "text": valid_sources[source_index_by_id[candidate_id]],
            "label": 1 if candidate_id in positive_set else 0,
        }
        for position, candidate_id in enumerate(candidate_ids)
    ]
    example = {
        "schema_version": SCHEMA_VERSION,
        "example_id": example_id,
        "instance_id": f"lc45k-row:{row_index}",
        "document_id": prompt.document_id,
        "context_id": prompt.document_id,
        "split": split,
        "query": prompt.query,
        "language": detect_language(prompt.query),
        "target": {
            "id": example_id,
            "statement_index": statement.statement_index,
            "text": statement.text,
        },
        "raw_citation_expression": statement.raw_citation_expression,
        "expanded_positive_sentence_indices": list(statement.citation_ids),
        "gold_source_ids": positive_ids,
        "candidates": candidates,
        "candidate_count": 15,
        "label_type": LABEL_TYPE,
    }
    return example, full_candidates


def emit_source(
    handle,
    seen: set[str],
    split: str,
    document_id: str,
    document_sha: str,
    sentence_index: int,
    text: str,
) -> None:
    item_id = source_id(document_sha, sentence_index)
    if item_id in seen:
        return
    seen.add(item_id)
    handle.write(
        json_line(
            {
                "schema_version": SCHEMA_VERSION,
                "id": item_id,
                "document_id": document_id,
                "split": split,
                "sentence_index": sentence_index,
                "text": text,
                "text_sha256": sha256_text(text),
            }
        )
    )


def second_pass(source: Path, output: Path, pass_one: dict) -> dict:
    staging = output / "_staging"
    if staging.exists():
        raise RuntimeError(f"staging path already exists: {staging}")
    for subdir in ("train", "dev", "sealed_reserve", "samples"):
        (staging / subdir).mkdir(parents=True, exist_ok=False)
    selected_ids = {split: {entry[3] for entry in entries} for split, entries in pass_one["selected"].items()}
    sample_ids = {split: {entry[3] for entry in pass_one["selected"][split][:3]} for split in ("train", "dev")}
    split_dir = {"train": "train", "dev": "dev", "reserve": "sealed_reserve"}
    single_handles = {
        split: (staging / split_dir[split] / "single_positive_15.jsonl").open("w", encoding="utf-8", newline="\n")
        for split in split_dir
    }
    source_handles = {
        split: (staging / split_dir[split] / "source_catalog.jsonl").open("w", encoding="utf-8", newline="\n")
        for split in split_dir
    }
    multi_handles = {
        split: (staging / split / "multi_positive_sidecar.jsonl").open("w", encoding="utf-8", newline="\n")
        for split in ("train", "dev")
    }
    sample_handles = {
        split: (staging / "samples" / f"{split}_examples_3.jsonl").open("w", encoding="utf-8", newline="\n")
        for split in ("train", "dev")
    }
    seen_sources = {split: set() for split in split_dir}
    output_stats = collections.Counter()
    language_counts = collections.Counter()
    position_counts = {"train": [0] * 15, "dev": [0] * 15, "reserve": [0] * 15}
    selected_documents = {split: set() for split in split_dir}
    sidecar_documents = {"train": set(), "dev": set()}
    normalized_targets = {split: set() for split in split_dir}
    normalized_sources = {split: set() for split in split_dir}
    normalized_pairs = {split: set() for split in split_dir}
    target_ids = {split: set() for split in split_dir}
    pair_ids = {split: set() for split in split_dir}
    started = time.monotonic()
    try:
        with source.open("r", encoding="utf-8") as handle:
            for row_index, line in enumerate(handle):
                row, error = load_row(line, row_index)
                if error:
                    continue
                try:
                    prompt, valid_sources, statements = parse_row(row)
                except ParseError:
                    continue
                split = split_for_document(prompt.document_id)
                for statement in statements:
                    category, _ = classify_statement(statement, valid_sources)
                    example_id = target_id(row_index, statement.statement_index)
                    emit = False
                    track = None
                    if category == "single_eligible" and example_id in selected_ids[split]:
                        emit = True
                        track = "single"
                    elif category == "multi_eligible" and split in multi_handles:
                        emit = True
                        track = "multi"
                    if not emit:
                        continue
                    example, full_candidates = build_example(row_index, prompt, valid_sources, statement, split)
                    candidate_ids = [item["source_id"] for item in example["candidates"]]
                    if track == "single":
                        single_handles[split].write(json_line(example))
                        output_stats[f"single_targets_{split}"] += 1
                        output_stats[f"single_pairs_{split}"] += 15
                        language_counts[f"single_{split}_{example['language']}"] += 1
                        selected_documents[split].add(prompt.document_id)
                        gold_position = next(i for i, item in enumerate(example["candidates"]) if item["label"] == 1)
                        position_counts[split][gold_position] += 1
                        if split in sample_handles and example_id in sample_ids[split]:
                            sample_handles[split].write(
                                json_line(
                                    {
                                        **example,
                                        "positive_sources": [item for item in full_candidates if item["label"] == 1],
                                        "candidates_with_text": full_candidates,
                                    }
                                )
                            )
                            output_stats[f"readable_samples_{split}"] += 1
                    else:
                        multi_handles[split].write(json_line(example))
                        output_stats[f"multi_targets_{split}"] += 1
                        output_stats[f"multi_pairs_{split}"] += 15
                        sidecar_documents[split].add(prompt.document_id)
                    target_ids[split].add(example_id)
                    target_norm_hash = sha256_text(normalize_text(statement.text))
                    normalized_targets[split].add(target_norm_hash)
                    source_index_by_id = {
                        source_id(prompt.document_sha256, index): index for index in valid_sources
                    }
                    for candidate_id in candidate_ids:
                        index = source_index_by_id[candidate_id]
                        source_text = valid_sources[index]
                        emit_source(
                            source_handles[split],
                            seen_sources[split],
                            split,
                            prompt.document_id,
                            prompt.document_sha256,
                            index,
                            source_text,
                        )
                        source_norm_hash = sha256_text(normalize_text(source_text))
                        normalized_sources[split].add(source_norm_hash)
                        normalized_pairs[split].add(sha256_text(target_norm_hash + ":" + source_norm_hash))
                        pair_ids[split].add(example_id + "::" + candidate_id)
    finally:
        for group in (single_handles, source_handles, multi_handles, sample_handles):
            for handle in group.values():
                handle.close()
    for split in split_dir:
        output_stats[f"catalog_sources_{split}"] = len(seen_sources[split])
        output_stats[f"single_documents_{split}"] = len(selected_documents[split])
    for split in sidecar_documents:
        output_stats[f"multi_documents_{split}"] = len(sidecar_documents[split])
    duplicate_audit = {
        "document_id_intersections": {
            "train_dev": 0,
            "train_reserve": 0,
            "dev_reserve": 0,
        },
        "target_id_intersections": intersection_counts(target_ids),
        "source_id_intersections": intersection_counts(seen_sources),
        "pair_id_intersections": intersection_counts(pair_ids),
        "normalized_target_text_intersections": intersection_counts(normalized_targets),
        "normalized_source_text_intersections": intersection_counts(normalized_sources),
        "normalized_target_source_pair_intersections": intersection_counts(normalized_pairs),
        "handling_rule": "IDs are never deleted. Normalized-text duplicate counts are reported; document grouping remains the frozen exact-context SHA assignment.",
    }
    metrics = {
        "schema_version": SCHEMA_VERSION,
        "output_stats": dict(sorted(output_stats.items())),
        "language_counts": dict(sorted(language_counts.items())),
        "single_positive_position_counts_train_dev": {
            "train": position_counts["train"],
            "dev": position_counts["dev"],
        },
        "duplicate_audit": duplicate_audit,
        "elapsed_seconds": time.monotonic() - started,
    }
    (staging / "build_metrics.json").write_text(
        json.dumps(metrics, ensure_ascii=False, indent=2), encoding="utf-8", newline="\n"
    )
    assignments_path = staging / "split_assignments.jsonl"
    with assignments_path.open("w", encoding="utf-8", newline="\n") as assignment_handle:
        for document_id in sorted(pass_one["document_assignments"]):
            assignment_handle.write(json_line(pass_one["document_assignments"][document_id]))
    reserve_manifest = {
        "schema_version": SCHEMA_VERSION,
        "role": "sealed_reserve",
        "target_count": output_stats["single_targets_reserve"],
        "document_count": output_stats["single_documents_reserve"],
        "source_count": output_stats["catalog_sources_reserve"],
        "readable_examples_generated": False,
        "excluded_from_remote_bundle": True,
    }
    (staging / "sealed_reserve" / "RESERVE_MANIFEST.json").write_text(
        json.dumps(reserve_manifest, ensure_ascii=False, indent=2), encoding="utf-8", newline="\n"
    )
    publish_staging(staging, output)
    return metrics


def intersection_counts(values: dict[str, set[str]]) -> dict[str, int]:
    return {
        "train_dev": len(values.get("train", set()) & values.get("dev", set())),
        "train_reserve": len(values.get("train", set()) & values.get("reserve", set())),
        "dev_reserve": len(values.get("dev", set()) & values.get("reserve", set())),
    }


def publish_staging(staging: Path, output: Path) -> None:
    files = sorted(path for path in staging.rglob("*") if path.is_file())
    for source_path in files:
        relative = source_path.relative_to(staging)
        destination = output / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.exists():
            raise RuntimeError(f"create-only conflict: {destination}")
        os.replace(source_path, destination)
    for directory in sorted((path for path in staging.rglob("*") if path.is_dir()), reverse=True):
        directory.rmdir()
    staging.rmdir()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--skip-source-hash", action="store_true")
    args = parser.parse_args()
    source = Path(args.source)
    output = Path(args.output_dir)
    output.mkdir(parents=True, exist_ok=True)
    if source.stat().st_size != EXPECTED_SOURCE_SIZE:
        raise RuntimeError("official_source_size_mismatch")
    actual_sha = EXPECTED_SOURCE_SHA256 if args.skip_source_hash else file_sha256(source)
    if actual_sha != EXPECTED_SOURCE_SHA256:
        raise RuntimeError("official_source_sha256_mismatch")
    pass_one = first_pass(source)
    quota_gate = {
        split: len(pass_one["eligible_single"][split]) >= quota for split, quota in TARGET_QUOTAS.items()
    }
    metrics = second_pass(source, output, pass_one)
    summary = {
        "schema_version": SCHEMA_VERSION,
        "source": {
            "path": str(source.resolve()),
            "size_bytes": source.stat().st_size,
            "sha256": actual_sha,
            "revision": "b776b01faf6e132a3d9cc373de1b46cd6630d772",
            "top_level_fields": ["prompt", "response"],
        },
        "protocol": {
            "candidate_count": 15,
            "split_thresholds": {"train": [0.0, 0.66], "dev": [0.66, 0.84], "reserve": [0.84, 1.0]},
            "target_quotas": TARGET_QUOTAS,
            "negative_seed": "SHA256(LC-Sent-15-v1:negative:<example_id>:15)",
            "order_seed": "SHA256(LC-Sent-15-v1:order:<example_id>:15)",
            "selection_rule": "ascending SHA256(LC-Sent-15-v1:select:<split>:<example_id>:<exact_target_text>)",
            "language_rule": "zh if query contains CJK; en if no CJK and contains Latin; otherwise other",
        },
        "first_pass": {
            "stats": dict(sorted(pass_one["stats"].items())),
            "reason_counts": dict(sorted(pass_one["reason_counts"].items())),
            "eligible_single_by_split": {key: len(value) for key, value in pass_one["eligible_single"].items()},
            "eligible_multi_by_split": dict(pass_one["eligible_multi"]),
            "quota_gate": quota_gate,
            "elapsed_seconds": pass_one["elapsed_seconds"],
        },
        "outputs": metrics,
        "status": "pass" if all(quota_gate.values()) else "quantity_gate_blocked",
    }
    summary_path = output / "build_summary.json"
    if summary_path.exists():
        raise RuntimeError(f"create-only conflict: {summary_path}")
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8", newline="\n")
    print("LC_SENT15_BUILD_PASS" if all(quota_gate.values()) else "LC_SENT15_QUANTITY_GATE_BLOCKED")
    return 0 if all(quota_gate.values()) else 2


if __name__ == "__main__":
    sys.exit(main())
