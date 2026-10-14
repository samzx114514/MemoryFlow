from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path

from memoryflow.citation_dataset import (
    CITATION_RE, CID_RE, build_candidate_sets, build_source_catalog, candidate_position_report,
    extract_examples, iter_cited_sentences, split_by_run,
)
from memoryflow.schema import FactStructRun


def load_runs(path: Path):
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            raw = json.loads(line)
            sources = {str(item["citation_id"]): item for item in raw.get("factstruct_source_memories", [])}
            yield FactStructRun(
                run_id=raw["run_id"], query=raw.get("original_query", ""), thread_id=raw.get("thread_id"),
                sources=sources, final_report=raw.get("final_report", ""),
                parser_warnings=raw.get("parser_warnings", []),
                raw_log_provenance=raw.get("raw_log_provenance", []),
                raw_event_count=raw.get("raw_event_count", 0),
                deduplicated_event_count=raw.get("deduplicated_event_count", 0),
            )


def write_jsonl(path: Path, rows) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runs", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    args = parser.parse_args()
    runs = list(load_runs(args.runs))
    examples = []
    discard = Counter()
    total_citation_ids = 0
    resolved_citation_ids = 0
    unresolved_targets = 0
    reporter_complete = [run for run in runs if run.final_report]
    for run in runs:
        if not run.completed:
            discard["incomplete_run"] += 1
            continue
        raw_ids = CID_RE.findall("".join(CITATION_RE.findall(run.final_report)))
        total_citation_ids += len(raw_ids)
        resolved_citation_ids += sum(citation_id in run.sources for citation_id in raw_ids)
        unresolved_targets += sum(
            1 for _, citation_ids, _ in iter_cited_sentences(run.final_report)
            if not set(citation_ids).issubset(run.sources)
        )
        run_examples = extract_examples(run)
        if not run_examples:
            discard["no_resolved_cited_target"] += 1
        examples.extend(run_examples)
    catalog = build_source_catalog(examples)
    pools, candidate_stats = build_candidate_sets(examples, catalog, seed=20260727)
    availability = candidate_stats["available"]
    positions = candidate_position_report(examples, pools)
    splits = split_by_run(examples, seed=20260727)
    processed = args.output_root / "data/processed"
    reports = args.output_root / "reports"
    write_jsonl(processed / "citation_examples.jsonl", examples)
    write_jsonl(processed / "candidate_sets.jsonl", pools)
    write_jsonl(processed / "sources.jsonl", catalog)
    (processed / "splits.json").write_text(json.dumps(splits, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    field_complete = sum(run.completed for run in reporter_complete)
    report = {
        "seed": 20260727,
        "run_count": len(runs),
        "reporter_complete_run_count": len(reporter_complete),
        "completed_run_count": sum(run.completed for run in runs),
        "completed_state_full_recovery_rate": field_complete / len(reporter_complete) if reporter_complete else 0.0,
        "query_recovery_rate": sum(bool(run.query) for run in reporter_complete) / len(reporter_complete) if reporter_complete else 0.0,
        "source_map_recovery_rate": sum(bool(run.sources) for run in reporter_complete) / len(reporter_complete) if reporter_complete else 0.0,
        "final_report_recovery_rate": 1.0 if reporter_complete else 0.0,
        "citation_id_total": total_citation_ids,
        "citation_id_resolved": resolved_citation_ids,
        "citation_resolution_rate": resolved_citation_ids / total_citation_ids if total_citation_ids else 0.0,
        "citation_example_count": len(examples),
        "candidate_pool_available_count": availability,
        "candidate_pool_stats": candidate_stats,
        "candidate_position_report": positions,
        "split_counts": {"train": 0, "dev": len(splits["dev"]), "test": len(splits["test"])},
        "discard_reasons": {
            **dict(discard),
            "missing_source_map_run": sum(not run.sources for run in runs),
            "missing_final_report_run": sum(not run.final_report for run in runs),
            "unresolved_citation_target": unresolved_targets,
            "unresolved_citation_id_occurrence": total_citation_ids - resolved_citation_ids,
        },
        "token_limit_method": "deterministic conservative CJK/word/punctuation units; no model tokenizer invoked",
    }
    reports.mkdir(parents=True, exist_ok=True)
    (reports / "dataset_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    md = [
        "# Citation-source recovery dataset report", "",
        f"- Parsed runs: {report['run_count']}",
        f"- Completed runs: {report['completed_run_count']}",
        f"- Completed-state full recovery: {report['completed_state_full_recovery_rate']:.2%}",
        f"- Citation resolution: {report['citation_id_resolved']}/{report['citation_id_total']} ({report['citation_resolution_rate']:.2%})",
        f"- Citation examples: {report['citation_example_count']}",
        f"- Candidate pools available (4/8/16/32): {availability['4']}/{availability['8']}/{availability['16']}/{availability['32']}",
        f"- Split examples (dev/test): {len(splits['dev'])}/{len(splits['test'])}",
        f"- Discard reasons: `{json.dumps(report['discard_reasons'], ensure_ascii=False)}`", "",
        "The labels are silver inline-citation mappings. They are not citation-truth judgments.",
    ]
    (reports / "dataset_report.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    if report["completed_state_full_recovery_rate"] < 0.95:
        raise SystemExit("completed-state recovery is below 95%")
    if report["citation_resolution_rate"] < 0.98:
        raise SystemExit("citation resolution is below 98%")


if __name__ == "__main__":
    main()
