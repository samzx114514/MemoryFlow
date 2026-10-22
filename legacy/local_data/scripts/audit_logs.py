from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from memoryflow.log_events import MULTIPART_RE, inventory_file, iter_log_events


THREAD_RE = re.compile(r"['\"]?thread_id['\"]?\s*[:=]\s*['\"]([^'\"]+)['\"]")
GRAPH_RE = re.compile(r"graph_format=['\"]([^'\"]+)['\"]")


def category_for(path: Path) -> str:
    if "__MACOSX" in path.parts or path.name.startswith("._") or path.name == ".DS_Store":
        return "metadata"
    for category in ("FactStruct", "Query", "SP"):
        if category in path.parts:
            return category
    return "other"


def audit_file(path: Path, category: str) -> dict[str, object]:
    threads: set[str] = set()
    graph_formats: set[str] = set()
    hashes: set[str] = set()
    counters = Counter()
    last_multipart: tuple[int, int] | None = None
    for event in iter_log_events(path):
        counters["raw_event_count"] += 1
        hashes.add(event.stable_hash)
        text = event.text
        if "request param details:" in text:
            counters["request_count"] += 1
        for thread_id in THREAD_RE.findall(text):
            if thread_id not in {"", "default", "__default__"}:
                threads.add(thread_id)
        graph_formats.update(GRAPH_RE.findall(text))
        if ("before reference_map:" in text or "before ref_map:" in text) and not re.search(
            r"before (?:reference_map|ref_map):\s*\{\s*\}", text
        ):
            counters["nonempty_ref_map_count"] += 1
        if re.search(r"['\"]reporter['\"]\s*:.*?['\"]final_report['\"]\s*:\s*(['\"])(?!\1)", text):
            counters["final_report_count"] += 1
        if re.search(r"\bconsult\b|咨询", text, re.IGNORECASE):
            counters["consult_event_count"] += 1
        if " | ERROR " in text or "| ERROR" in text:
            counters["error_count"] += 1
        if event.truncated and not event.multipart:
            counters["truncated_event_count"] += 1
        last_multipart = event.multipart
    # Multipart streams can interleave between concurrent requests. Only an
    # unfinished final part is unambiguously truncated without a group ID.
    if last_multipart and last_multipart[0] < last_multipart[1]:
        counters["truncated_event_count"] += 1
    counters["deduplicated_event_count"] = len(hashes)
    return {
        "absolute_path": str(path.resolve()),
        "category": category,
        "request_count": counters["request_count"],
        "unique_thread_count": len(threads),
        "graph_formats": sorted(graph_formats),
        "nonempty_ref_map_count": counters["nonempty_ref_map_count"],
        "final_report_count": counters["final_report_count"],
        "consult_event_count": counters["consult_event_count"],
        "error_count": counters["error_count"],
        "truncated_event_count": counters["truncated_event_count"],
        "raw_event_count": counters["raw_event_count"],
        "deduplicated_event_count": counters["deduplicated_event_count"],
    }


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    args = parser.parse_args()
    source_root = args.source_root.resolve()
    output_root = args.output_root.resolve()
    files = sorted(path for path in source_root.rglob("*") if path.is_file())
    inventory = []
    for path in files:
        inventory.append(inventory_file(path, source_root, category_for(path)))
    generated_at = datetime.now(timezone.utc).isoformat()
    inventory_doc = {
        "source_root": str(source_root),
        "generated_at": generated_at,
        "file_count": len(inventory),
        "category_counts": dict(Counter(item["category"] for item in inventory)),
        "files": inventory,
    }
    write_json(output_root / "data/raw_manifest/log_inventory.json", inventory_doc)
    rows = [
        "# Log inventory",
        "",
        f"- Source root: `{source_root}`",
        f"- Files: {len(inventory)}",
        f"- Generated (UTC): {generated_at}",
        "",
        "| Category | Relative path | Bytes | Lines | Encoding | SHA-256 |",
        "|---|---|---:|---:|---|---|",
    ]
    for item in inventory:
        rows.append(
            f"| {item['category']} | `{item['relative_path_in_source_folder']}` | "
            f"{item['size_bytes']} | {item['line_count']} | {item['encoding']} | `{item['sha256']}` |"
        )
    (output_root / "data/raw_manifest/log_inventory.md").write_text("\n".join(rows) + "\n", encoding="utf-8")

    audits = []
    for path in files:
        category = category_for(path)
        if category in {"FactStruct", "SP"} and path.suffix.lower() == ".log":
            audits.append(audit_file(path, category))
    totals: dict[str, dict[str, object]] = {}
    numeric_fields = (
        "request_count", "unique_thread_count", "nonempty_ref_map_count", "final_report_count",
        "consult_event_count", "error_count", "truncated_event_count", "raw_event_count",
        "deduplicated_event_count",
    )
    for category in ("FactStruct", "SP"):
        group = [item for item in audits if item["category"] == category]
        totals[category] = {field: sum(int(item[field]) for item in group) for field in numeric_fields}
        totals[category]["file_count"] = len(group)
        totals[category]["graph_formats"] = sorted({fmt for item in group for fmt in item["graph_formats"]})
    audit_doc = {"generated_at": generated_at, "source_root": str(source_root), "totals": totals, "files": audits}
    write_json(output_root / "data/interim/run_audit.json", audit_doc)
    report = ["# Run audit", "", f"Generated (UTC): {generated_at}", ""]
    for category in ("FactStruct", "SP"):
        values = totals[category]
        report.extend([
            f"## {category}", "",
            f"- Files: {values['file_count']}",
            f"- Requests: {values['request_count']}",
            f"- Unique threads: {values['unique_thread_count']}",
            f"- Final reports: {values['final_report_count']}",
            f"- Raw/deduplicated events: {values['raw_event_count']} / {values['deduplicated_event_count']}",
            f"- Errors/truncated events: {values['error_count']} / {values['truncated_event_count']}", "",
        ])
    (output_root / "reports/run_audit.md").write_text("\n".join(report), encoding="utf-8")


if __name__ == "__main__":
    main()
