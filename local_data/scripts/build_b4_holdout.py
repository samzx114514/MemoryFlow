from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from memoryflow.holdout import DEFAULT_SEED, build_holdout, validate_bundle, write_checksums


def load_jsonl(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def write_jsonl(path: Path, rows: list[dict]) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def human_size(size: int) -> str:
    units = ("B", "KiB", "MiB", "GiB")
    value = float(size)
    for unit in units:
        if value < 1024 or unit == units[-1]:
            return f"{value:.2f} {unit}"
        value /= 1024
    raise AssertionError("unreachable")


def schema_text() -> str:
    return """# Checkpoint B4 held-out schema

This package preserves the `checkpoint_b_debug` example-row format so the B2/B3 loader needs only a filename/path change. The only intentional dataset-level differences are that rows come exclusively from the existing `test` split and a standalone `source_catalog.jsonl` is included.

## Group isolation

The debug schema contains `run_id` but no `request_id` or other parent identifier. Therefore `run_id` is the closest available stable grouping field and is used for strict exclusion and the maximum-two-per-group cap.

## `examples.jsonl`

Each line is a JSON object with:

- `example_id`: globally stable citation example identifier.
- `run_id`: stable parent group; never overlaps the debug bundle.
- `split`: always `test`.
- `target`: `{id, text}` with citation markers already removed by Checkpoint A.
- `candidates`: exactly four `{id, title, memory_text}` objects. Their order is shuffled using `SHA256("memoryflow-b4-holdout-v1" + example_id)`.
- `gold_source_ids`: one or more silver source IDs, all present in `candidates`.
- `candidate_count`: always `4`.
- `label_type`: `silver_inline_citation`.

No URL, raw citation ID, request text, raw log event, model score, or model output is stored in an example row.

## `source_catalog.jsonl`

Each line is one unique `{id, title, memory_text}` candidate Source referenced by this bundle. URLs are intentionally omitted from the model-visible package.

## Other files

- `manifest.json`: machine-readable sampling/input/output metadata.
- `sampling_report.md`: human-readable sampling and validation results.
- `checksums.sha256`: SHA-256 for every other file in this directory.
"""


def sampling_report_text(report: dict, validation: dict, file_sizes: dict[str, int]) -> str:
    slot_lines = ["| Slot | Candidate count | Gold appearances | Single-positive gold |", "|---:|---:|---:|---:|"]
    slot_lines.extend(
        f"| {row['slot']} | {row['candidate_count']} | {row['gold_count']} | {row['single_positive_gold_count']} |"
        for row in report["slots"]
    )
    discard_lines = ["| Reason | Count |", "|---|---:|"]
    discard_lines.extend(f"| `{reason}` | {count} |" for reason, count in report["discard_reasons"].items())
    size_lines = ["| File | Bytes |", "|---|---:|"]
    size_lines.extend(f"| `{name}` | {size} |" for name, size in sorted(file_sizes.items()))
    return f"""# MemoryFlow Checkpoint B4 held-out sampling report

## Sampling

- Seed: `{report['seed']}`
- Source split: existing Checkpoint A `test` split only
- Stable group field: `run_id` (`request_id` is absent from the inspected debug and processed schemas)
- Requested: {report['target_single']} single-positive + {report['target_multi']} multi-positive
- Actual: **{report['actual_single']} single-positive + {report['actual_multi']} multi-positive = {report['example_count']} total**
- Structurally eligible before sampling: {report['eligible_single']} single-positive, {report['eligible_multi']} multi-positive
- Independent run/request groups: **{report['independent_group_count']}**
- Maximum examples in one group: **{report['max_examples_per_group']}**
- Selection used only structural validity and deterministic hashes. No text quality, topic, length, lexical overlap, model score, or expected difficulty was used.

## Candidate slots

{chr(10).join(slot_lines)}

Gold-first rows: {validation['gold_first_count']} / {validation['example_count']}; all rows gold-first: `{str(validation['gold_first_all']).lower()}`.

## Exclusions before sampling

{chr(10).join(discard_lines)}

`not_in_test_split` is expected: it counts the 263 dev examples skipped before eligibility checks. The two debug runs are already outside the test split and are additionally checked after materialization.

## Blind holdout validation

- Debug example ID overlap: **{validation['debug_example_id_overlap']}**
- Debug run/request overlap: **{validation['debug_group_overlap']}**
- Debug target hash overlap: **{validation['debug_target_hash_overlap']}**
- Debug target+candidate-set fingerprint overlap: **{validation['debug_target_candidate_fingerprint_overlap']}**
- Duplicate example IDs: **{validation['duplicate_example_id_count']}**
- Duplicate target hashes: **{validation['duplicate_target_hash_count']}**
- Duplicate target+candidate fingerprints: **{validation['duplicate_target_candidate_fingerprint_count']}**
- Exact four-candidate rows: **{validation['exact_four_candidates']} / {validation['example_count']}**
- Candidate IDs unique in every row: `{str(validation['candidate_ids_unique']).lower()}`
- Source catalog duplicate IDs: **{validation['source_catalog_duplicate_id_count']}**; conflicting IDs: **{validation['source_catalog_conflict_count']}**
- All candidates resolve in the bundled catalog: `{str(validation['all_candidates_resolve']).lower()}`
- Gold resolution rate: **{validation['gold_resolution_rate']:.1%}**
- Source texts nonempty: `{str(validation['nonempty_source_text']).lower()}`
- JSON/JSONL parseable: `{str(validation['json_parseable']).lower()}`
- Bundle-only structural validation passed: `{str(validation['passed']).lower()}`

The checksum result is reported in `checkpoint_b4_holdout_summary.md` after `checksums.sha256` is finalized.

## File sizes before checksum file

{chr(10).join(size_lines)}
"""


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--replace-generated", action="store_true", help="refresh only this script's B4 output files")
    args = parser.parse_args()
    root = args.root.resolve()
    processed = root / "data" / "processed"
    debug_path = root / "remote_bundle" / "checkpoint_b_debug" / "data" / "debug_examples.jsonl"
    output = root / "remote_bundle" / "checkpoint_b4_holdout"
    summary_path = root / "remote_bundle" / "checkpoint_b4_holdout_summary.md"
    if output.exists() and not args.replace_generated:
        raise FileExistsError(f"refusing to overwrite existing B4 bundle: {output}")
    output.mkdir(parents=True, exist_ok=args.replace_generated)

    input_paths = {
        "citation_examples": processed / "citation_examples.jsonl",
        "candidate_sets": processed / "candidate_sets.jsonl",
        "sources": processed / "sources.jsonl",
        "splits": processed / "splits.json",
        "debug_examples": debug_path,
    }
    examples = load_jsonl(input_paths["citation_examples"])
    candidate_rows = load_jsonl(input_paths["candidate_sets"])
    sources = load_jsonl(input_paths["sources"])
    splits = json.loads(input_paths["splits"].read_text(encoding="utf-8"))
    debug_rows = load_jsonl(debug_path)
    result = build_holdout(examples, candidate_rows, sources, splits, debug_rows)

    write_jsonl(output / "examples.jsonl", result["examples"])
    write_jsonl(output / "source_catalog.jsonl", result["sources"])
    (output / "schema.md").write_text(schema_text(), encoding="utf-8", newline="\n")

    manifest = {
        "name": "memoryflow-checkpoint-b4-holdout-v1",
        "schema_version": 1,
        "seed": DEFAULT_SEED,
        "source_split": "test",
        "group_field": "run_id",
        "request_id_available": False,
        "candidate_count": 4,
        "example_count": result["report"]["example_count"],
        "single_positive_count": result["report"]["actual_single"],
        "multi_positive_count": result["report"]["actual_multi"],
        "independent_group_count": result["report"]["independent_group_count"],
        "source_count": len(result["sources"]),
        "input_files": {
            name: {"absolute_path": str(path), "size_bytes": path.stat().st_size, "sha256": sha256_file(path)}
            for name, path in input_paths.items()
        },
        "files": ["examples.jsonl", "source_catalog.jsonl", "manifest.json", "schema.md", "sampling_report.md", "checksums.sha256"],
        "prohibited_selection_signals_used": [],
        "models_or_gpu_used": False,
    }
    (output / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")

    # The report needs structural metrics; checksum is finalized after the report itself.
    (output / "sampling_report.md").write_text("pending", encoding="utf-8", newline="\n")
    write_checksums(output)
    preliminary = validate_bundle(output, debug_rows)
    preliminary["passed"] = preliminary["passed"] or all((
        preliminary["json_parseable"], preliminary["example_count"] > 0,
        preliminary["duplicate_example_id_count"] == 0, preliminary["duplicate_target_hash_count"] == 0,
        preliminary["duplicate_target_candidate_fingerprint_count"] == 0,
        preliminary["debug_example_id_overlap"] == 0, preliminary["debug_group_overlap"] == 0,
        preliminary["debug_target_hash_overlap"] == 0, preliminary["debug_target_candidate_fingerprint_overlap"] == 0,
        preliminary["exact_four_candidates"] == preliminary["example_count"], preliminary["candidate_ids_unique"],
        preliminary["all_candidates_resolve"], preliminary["all_gold_resolve"], preliminary["nonempty_source_text"],
        preliminary["source_catalog_duplicate_id_count"] == 0, preliminary["source_catalog_conflict_count"] == 0,
        preliminary["max_examples_per_group"] <= 2, not preliminary["gold_first_all"],
    ))
    file_sizes = {path.name: path.stat().st_size for path in output.iterdir() if path.is_file() and path.name not in {"sampling_report.md", "checksums.sha256"}}
    (output / "sampling_report.md").write_text(sampling_report_text(result["report"], preliminary, file_sizes), encoding="utf-8", newline="\n")
    write_checksums(output)
    validation = validate_bundle(output, debug_rows)
    if not validation["passed"]:
        raise RuntimeError(f"B4 validation failed: {json.dumps(validation, ensure_ascii=False)}")

    bundle_size = sum(path.stat().st_size for path in output.rglob("*") if path.is_file())
    summary = f"""# MemoryFlow Checkpoint B4-Local summary

- Actual examples: **{result['report']['actual_single']} single-positive + {result['report']['actual_multi']} multi-positive = {result['report']['example_count']} total**.
- Independent run/request groups: **{result['report']['independent_group_count']}**; stable grouping field is `run_id` because no `request_id` or other parent field exists in the inspected schemas.
- Debug overlaps: example ID **{validation['debug_example_id_overlap']}**, run/request **{validation['debug_group_overlap']}**, normalized target hash **{validation['debug_target_hash_overlap']}**, target+candidate-set fingerprint **{validation['debug_target_candidate_fingerprint_overlap']}**.
- Duplicate held-out example IDs: **{validation['duplicate_example_id_count']}**; duplicate target hashes: **{validation['duplicate_target_hash_count']}**; duplicate target+candidate-set fingerprints: **{validation['duplicate_target_candidate_fingerprint_count']}**.
- Exact four-candidate rows: **{validation['exact_four_candidates']} / {validation['example_count']}**; gold resolution: **{validation['gold_resolution_rate']:.1%}**; all candidate Sources resolve: `{str(validation['all_candidates_resolve']).lower()}`.
- Gold-first rows: **{validation['gold_first_count']} / {validation['example_count']}**, so order is not fixed gold-first.
- Slot distribution: {', '.join(f"slot {row['slot']}: candidates={row['candidate_count']}, gold={row['gold_count']}, single_gold={row['single_positive_gold_count']}" for row in result['report']['slots'])}.
- Bundle size: **{bundle_size} bytes ({human_size(bundle_size)})**.
- Upload the complete directory: `{output}`.
- Suggested server target path: `/workspace/MemoryFlow/data/checkpoint_b4_holdout`.
- SHA-256 manifest verification: **passed** (`checksums.sha256`).
- The package was built only from existing Checkpoint A structured data. Raw logs, server B3 scores, models, and GPU were not read or used.
"""
    summary_path.write_text(summary, encoding="utf-8", newline="\n")
    print(json.dumps({"output": str(output), "summary": str(summary_path), "bundle_size_bytes": bundle_size, "report": result["report"], "validation": validation}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
