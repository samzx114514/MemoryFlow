"""Create the mandatory human-readable 20-example parser audit."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from lc_sent15 import ParseError, iter_jsonl, parse_prompt, parse_response


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--examples", type=int, default=20)
    args = parser.parse_args()
    output = Path(args.output_dir)
    output.mkdir(parents=True, exist_ok=True)
    rows: list[dict] = []
    row_errors: list[dict] = []
    for row_index, row in iter_jsonl(args.source):
        try:
            prompt = parse_prompt(row["prompt"])
            valid_ids = {item.sentence_index for item in prompt.sources if item.text.strip()}
            statements = parse_response(row["response"], valid_ids)
        except (KeyError, ParseError) as error:
            row_errors.append({"row_index": row_index, "error": str(error)})
            continue
        source_map = {item.sentence_index: item.text for item in prompt.sources}
        for statement in statements:
            if statement.status != "valid":
                continue
            rows.append(
                {
                    "audit_index": len(rows),
                    "row_index": row_index,
                    "document_id": prompt.document_id,
                    "query": prompt.query,
                    "statement_index": statement.statement_index,
                    "target_text": statement.text,
                    "raw_citation_expression": statement.raw_citation_expression,
                    "expanded_source_indices": list(statement.citation_ids),
                    "positive_sources": [
                        {"sentence_index": source_id, "text": source_map[source_id]}
                        for source_id in statement.citation_ids
                    ],
                    "parser_judgment": "pending_human_read",
                    "notes": "",
                }
            )
            if len(rows) >= args.examples:
                break
        if len(rows) >= args.examples:
            break
    if len(rows) < args.examples:
        raise RuntimeError(f"only {len(rows)} valid examples found")
    jsonl_path = output / "parser_audit_20.jsonl"
    with jsonl_path.open("w", encoding="utf-8", newline="\n") as handle:
        for item in rows:
            handle.write(json.dumps(item, ensure_ascii=False, separators=(",", ":")) + "\n")
    md = ["# LC-Sent-15-v1 Parser Audit (20 examples)", ""]
    for item in rows:
        md.extend(
            [
                f"## {item['audit_index'] + 1}. row {item['row_index']} statement {item['statement_index']}",
                "",
                f"- Document: `{item['document_id']}`",
                f"- Query: {item['query']}",
                f"- Target: {item['target_text']}",
                f"- Citation: `{item['raw_citation_expression']}` → `{item['expanded_source_indices']}`",
                "- Positive official units:",
                "",
            ]
        )
        for source in item["positive_sources"]:
            md.append(f"  - `<C{source['sentence_index']}>` {source['text']}")
        md.extend(["", "- Human parser judgment: PENDING", "- Notes:", ""])
    (output / "parser_audit_20.md").write_text("\n".join(md), encoding="utf-8", newline="\n")
    (output / "parser_audit_row_errors.json").write_text(
        json.dumps(row_errors, ensure_ascii=False, indent=2), encoding="utf-8", newline="\n"
    )
    print(f"PARSER_AUDIT_READY examples={len(rows)} row_errors={len(row_errors)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
