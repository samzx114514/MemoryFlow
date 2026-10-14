from __future__ import annotations

import argparse
import json
import random
import re
from pathlib import Path

"""Legacy filename; this script performs only automatic structural checks."""


CITATION = re.compile(r"\[\s*\d|【\s*链接\s*\d+\s*】|\b(?:citation|source|ref|url)\s*#?\d+\s*[:\-]", re.I)
URL = re.compile(r"https?://", re.I)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--examples", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--dataset-report", type=Path)
    parser.add_argument("--dataset-report-md", type=Path)
    args = parser.parse_args()
    with args.examples.open("r", encoding="utf-8") as handle:
        examples = [json.loads(line) for line in handle]
    rng = random.Random(20260727)
    sample = rng.sample(examples, min(30, len(examples)))
    rows = []
    for example in sample:
        target = example["target"]["text"]
        source_by_id = {source["id"]: source for source in example["sources"]}
        gold_resolves = all(source_id in source_by_id for source_id in example["gold_source_ids"])
        target_clean = not CITATION.search(target) and not URL.search(target)
        source_clean = all(
            not CITATION.search(source["memory_text"]) and not URL.search(source["memory_text"])
            for source in example["sources"]
        )
        leakage = not (target_clean and source_clean)
        understandable = bool(target.strip()) and gold_resolves and all(
            source_by_id[source_id]["memory_text"].strip() for source_id in example["gold_source_ids"] if source_id in source_by_id
        )
        issues = []
        if not target_clean:
            issues.append("target_label_or_url_leakage")
        if not source_clean:
            issues.append("source_label_or_url_leakage")
        if not gold_resolves:
            issues.append("gold_source_missing")
        rows.append({
            "audit_type": "automatic_structure_check",
            "example_id": example["example_id"],
            "target_clean": target_clean,
            "source_clean": source_clean,
            "gold_resolves": gold_resolves,
            "pair_is_understandable": understandable,
            "label_leakage": leakage,
            "parser_issue": ";".join(issues) or None,
            "notes": "",
        })
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    summary = {
        "sample_size": len(rows),
        "target_clean": sum(row["target_clean"] for row in rows),
        "source_clean": sum(row["source_clean"] for row in rows),
        "gold_resolves": sum(row["gold_resolves"] for row in rows),
        "pair_is_understandable": sum(row["pair_is_understandable"] for row in rows),
        "label_leakage": sum(row["label_leakage"] for row in rows),
        "parser_issue": sum(row["parser_issue"] is not None for row in rows),
    }
    if args.dataset_report:
        report = json.loads(args.dataset_report.read_text(encoding="utf-8"))
        report.pop("manual_audit_30", None)
        report["automatic_structure_audit_30"] = summary
        args.dataset_report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if args.dataset_report_md:
        with args.dataset_report_md.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(
                "\n## Automatic structure audit (seed 20260727)\n\n"
                f"- Sample: {summary['sample_size']}\n"
                f"- Target/source clean: {summary['target_clean']}/{summary['source_clean']}\n"
                f"- Gold resolves: {summary['gold_resolves']}\n"
                f"- Pair understandable: {summary['pair_is_understandable']}\n"
                f"- Label leakage/parser issues: {summary['label_leakage']}/{summary['parser_issue']}\n"
            )
    if len(rows) != 30 or summary["label_leakage"] != 0 or summary["pair_is_understandable"] < 27:
        raise SystemExit(f"manual audit gate failed: {summary}")


if __name__ == "__main__":
    main()
