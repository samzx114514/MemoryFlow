from __future__ import annotations

import argparse
import json
from pathlib import Path

from memoryflow.citation_dataset import (
    build_candidate_sets,
    build_source_catalog,
    candidate_position_report,
    source_id,
)


def load_jsonl(path: Path) -> list[dict]:
    with path.open("r", encoding="utf-8") as handle:
        return [json.loads(line) for line in handle]


def write_jsonl(path: Path, rows: list[dict]) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")


def load_source_urls(runs_path: Path) -> dict[str, dict[str, str]]:
    metadata: dict[str, dict[str, str]] = {}
    with runs_path.open("r", encoding="utf-8") as handle:
        for line in handle:
            run = json.loads(line)
            run_id = run["run_id"]
            for source in run.get("factstruct_source_memories", []):
                item_id = source_id(run_id, str(source["citation_id"]))
                url = str(source.get("URL") or source.get("url") or "")
                existing = metadata.get(item_id)
                if existing is not None and existing["url"] != url:
                    raise ValueError(f"conflicting Source URL: {item_id}")
                metadata[item_id] = {"url": url}
    return metadata


def render_report(report: dict) -> str:
    stats = report["candidate_pool_stats"]
    lines = [
        "# Citation-source recovery dataset report V2", "",
        "This V2 report is an incremental correction over the processed Checkpoint A data; raw logs were not reread.", "",
        f"- Citation examples: {report['citation_example_count']}",
        f"- Source catalog: {report['source_catalog_count']} unique IDs; conflicts: {report['source_catalog_conflict_count']}",
        f"- Split examples (dev/test): {report['split_counts']['dev']}/{report['split_counts']['test']}", "",
        "## Candidate availability", "",
        "| K | Available | Gold count exceeds K | Insufficient catalog | All available lengths exactly K |",
        "|---:|---:|---:|---:|---|",
    ]
    for size in ("4", "8", "16", "32"):
        lines.append(
            f"| {size} | {stats['available'][size]} | {stats['unavailable_gold_exceeds'][size]} | "
            f"{stats['unavailable_insufficient_catalog'][size]} | {stats['strict_length_all'][size]} |"
        )
    lines.extend(["", "## Gold position distribution (single-positive examples)", ""])
    for size in ("4", "8", "16", "32"):
        item = report["candidate_position_report"][size]
        positions = ", ".join(
            f"p{index}={item[f'position_{index}_count']}" for index in range(int(size))
        )
        lines.append(
            f"- K={size}: n={item['single_positive_example_count']}; {positions}; "
            f"max-ratio={item['position_bias_max_ratio']:.6f}"
        )
    lines.extend([
        "", "URLs in `sources.jsonl` are audit-only and are excluded from model-visible candidate text.",
        "Labels remain `silver_inline_citation`; this is not a citation-support truth audit.",
    ])
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--processed-dir", type=Path, required=True)
    parser.add_argument("--runs", type=Path, required=True)
    parser.add_argument("--reports-dir", type=Path, required=True)
    args = parser.parse_args()
    examples = load_jsonl(args.processed_dir / "citation_examples.jsonl")
    audit_metadata = load_source_urls(args.runs)
    catalog = build_source_catalog(examples, audit_metadata)
    catalog_by_id = {source["id"]: source for source in catalog}
    for example in examples:
        example["sources"] = [{
            "id": source["id"],
            "title": catalog_by_id[source["id"]]["title"],
            "memory_text": catalog_by_id[source["id"]]["memory_text"],
        } for source in example["sources"]]
    candidate_rows, candidate_stats = build_candidate_sets(examples, catalog, seed=20260727)
    position_report = candidate_position_report(examples, candidate_rows)
    write_jsonl(args.processed_dir / "sources.jsonl", catalog)
    write_jsonl(args.processed_dir / "citation_examples.jsonl", examples)
    write_jsonl(args.processed_dir / "candidate_sets.jsonl", candidate_rows)
    args.reports_dir.mkdir(parents=True, exist_ok=True)
    (args.reports_dir / "candidate_position_report.json").write_text(
        json.dumps(position_report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    report_path = args.reports_dir / "dataset_report.json"
    report = json.loads(report_path.read_text(encoding="utf-8"))
    report.pop("manual_audit_30", None)
    report["version"] = "checkpoint_a_v2"
    report["incremental_from_processed_data"] = True
    report["raw_logs_reread"] = False
    report["source_catalog_count"] = len(catalog)
    report["source_catalog_conflict_count"] = 0
    report["candidate_pool_available_count"] = candidate_stats["available"]
    report["candidate_pool_unavailable_gold_exceeds_count"] = candidate_stats["unavailable_gold_exceeds"]
    report["candidate_pool_unavailable_insufficient_catalog_count"] = candidate_stats["unavailable_insufficient_catalog"]
    report["candidate_pool_strict_length_all"] = candidate_stats["strict_length_all"]
    report["candidate_pool_stats"] = candidate_stats
    report["candidate_position_report"] = position_report
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (args.reports_dir / "dataset_report.md").write_text(render_report(report), encoding="utf-8")


if __name__ == "__main__":
    main()
