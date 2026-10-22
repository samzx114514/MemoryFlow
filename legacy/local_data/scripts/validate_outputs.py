from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from memoryflow.citation_dataset import candidate_position_report
from memoryflow.v2_delivery import verify_manifest


LEAK = re.compile(r"\[\s*\d|【\s*链接\s*\d+\s*】|\b(?:citation|source|ref|url)\s*#?\d+\s*[:\-]", re.I)
URL = re.compile(
    r"https?://|https?\s*:\s*/\s*/|\bwww\s*\.|\b(?:www\.)?[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.(?:com|org|net|cn|edu|gov)(?:/|\b)",
    re.I,
)


def clean(text: str) -> bool:
    return not LEAK.search(text) and not URL.search(text)


def load_jsonl(path: Path) -> list[dict]:
    with path.open("r", encoding="utf-8") as handle:
        return [json.loads(line) for line in handle]


def validate_processed(data_dir: Path) -> dict:
    examples_list = load_jsonl(data_dir / "citation_examples.jsonl")
    examples = {item["example_id"]: item for item in examples_list}
    source_rows = load_jsonl(data_dir / "sources.jsonl")
    sources: dict[str, dict] = {}
    for line_number, source in enumerate(source_rows, 1):
        source_id = source["id"]
        if source_id in sources and sources[source_id] != source:
            raise SystemExit(f"conflicting Source catalog row {line_number}: {source_id}")
        if not clean(source["title"]) or not clean(source["memory_text"]):
            raise SystemExit(f"Source model-text leakage line {line_number}: {source_id}")
        sources[source_id] = source
    for line_number, example in enumerate(examples_list, 1):
        if not clean(example["target"]["text"]):
            raise SystemExit(f"Target leakage line {line_number}")
        if not set(example["gold_source_ids"]).issubset(sources):
            raise SystemExit(f"gold does not resolve in catalog line {line_number}")
    candidate_rows = load_jsonl(data_dir / "candidate_sets.jsonl")
    for line_number, row in enumerate(candidate_rows, 1):
        example = examples[row["example_id"]]
        unavailable = row.get("unavailable", {})
        for size in (4, 8, 16, 32):
            key = str(size)
            ids = row["candidate_sets"].get(key, [])
            if ids:
                if len(ids) != size or len(ids) != len(set(ids)):
                    raise SystemExit(f"candidate length/duplicate error line {line_number}, K={size}")
                if not set(example["gold_source_ids"]).issubset(ids):
                    raise SystemExit(f"candidate dropped positive line {line_number}, K={size}")
                if not set(ids).issubset(sources):
                    raise SystemExit(f"candidate Source unresolved line {line_number}, K={size}")
            elif key not in unavailable:
                raise SystemExit(f"empty pool lacks unavailable reason line {line_number}, K={size}")
            elif unavailable[key] == "gold_count_exceeds_candidate_count" and len(example["gold_source_ids"]) <= size:
                raise SystemExit(f"incorrect unavailable reason line {line_number}, K={size}")
    positions = candidate_position_report(examples_list, candidate_rows)
    for size, item in positions.items():
        if item["single_positive_example_count"] and item["position_bias_max_ratio"] >= 1.0:
            raise SystemExit(f"fixed gold position remains for K={size}")
    splits = json.loads((data_dir / "splits.json").read_text(encoding="utf-8"))
    if splits["train"] or set(splits["dev_runs"]).intersection(splits["test_runs"]):
        raise SystemExit("invalid run split")
    if set(splits["dev"] + splits["test"]) != set(examples):
        raise SystemExit("split examples do not cover dataset exactly")
    return {
        "example_count": len(examples),
        "source_count": len(sources),
        "candidate_row_count": len(candidate_rows),
        "position_report": positions,
    }


def validate_debug(bundle: Path, splits_path: Path) -> dict:
    rows = load_jsonl(bundle / "data/debug_examples.jsonl")
    splits = json.loads(splits_path.read_text(encoding="utf-8"))
    dev = set(splits["dev"])
    for line_number, row in enumerate(rows, 1):
        if row["example_id"] not in dev or row["split"] != "dev":
            raise SystemExit(f"debug row is not dev line {line_number}")
        if row["candidate_count"] != 4 or len(row["candidates"]) != 4:
            raise SystemExit(f"debug row does not have four candidates line {line_number}")
        candidate_ids = [source["id"] for source in row["candidates"]]
        if len(candidate_ids) != len(set(candidate_ids)) or not set(row["gold_source_ids"]).issubset(candidate_ids):
            raise SystemExit(f"debug candidate/gold error line {line_number}")
        if not clean(row["target"]["text"]):
            raise SystemExit(f"debug Target leakage line {line_number}")
        if any(not clean(source["title"]) or not clean(source["memory_text"]) for source in row["candidates"]):
            raise SystemExit(f"debug candidate text leakage line {line_number}")
        forbidden = {"raw_citation_ids", "citation_id", "url", "URL", "query", "raw_content"}
        if forbidden.intersection(row):
            raise SystemExit(f"debug forbidden top-level key line {line_number}")
    if len(rows) != 30:
        raise SystemExit(f"debug row count is {len(rows)}, expected 30")
    if not verify_manifest(bundle):
        raise SystemExit("debug MANIFEST failed")
    return {"debug_count": len(rows), "debug_run_count": len({row["run_id"] for row in rows})}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", type=Path, required=True)
    parser.add_argument("--full-bundle", type=Path)
    parser.add_argument("--debug-bundle", type=Path)
    parser.add_argument("--splits", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = validate_processed(args.data_dir)
    if args.full_bundle and not verify_manifest(args.full_bundle):
        raise SystemExit("full V2 MANIFEST failed")
    if args.full_bundle:
        report["full_manifest_verified"] = True
    if args.debug_bundle:
        if not args.splits:
            raise SystemExit("--splits is required with --debug-bundle")
        report.update(validate_debug(args.debug_bundle, args.splits))
    if args.output:
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    main()

