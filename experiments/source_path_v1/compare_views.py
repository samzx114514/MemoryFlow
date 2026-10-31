"""Compare two query views for the same judgment: last-call-only vs full transmission chain."""

from __future__ import annotations

import json
import pathlib

REPO = pathlib.Path(r"F:\CodexProject\MemoryFlow-research")


def compare(data: dict, judgment: str = "report_span_0") -> list[str]:
    units = {unit["unit_id"]: unit for unit in data["units"]}
    edges = data["edges"]
    reporter = next((edge["from"] for edge in edges
                     if edge["to"] == judgment and edge["kind"] == "recorded_generation"), None)
    if reporter is None:
        return [f"judgment: {judgment}", "producer call: unresolved"]

    # A tool result is a history edge; a summary or sibling output that actually
    # appears in the request is stored as an input occurrence.  Count both, and
    # exclude the judgment's own generated copy.
    visible: dict[str, str] = {}
    for edge in edges:
        if edge["to"] == reporter and edge["kind"] == "history":
            visible[edge["from"]] = units[edge["from"]]["text"]
    for occurrence in data.get("input_occurrences", []):
        if occurrence.get("call") != reporter or occurrence.get("unit") == judgment:
            continue
        unit = units.get(occurrence["unit"])
        if unit:
            visible[occurrence["unit"]] = unit["text"]

    lines = [f"judgment: {judgment}", f"producer call: {reporter}",
             f"last-call-only sees: {len(visible)} units"]
    for unit_id, text in visible.items():
        lines.append(f"  - {unit_id} | {text.replace(chr(10), ' ')[:100]}")

    summary_edges = [edge for edge in edges
                     if edge["to"] == "summary_final" and edge["kind"] == "recorded_generation"]
    producer = summary_edges[0]["from"] if summary_edges else None
    upstream = [edge for edge in edges
                if edge["to"] == producer and edge["kind"] == "history"]
    lines.append(f"full chain: summary producer: {producer} | visible upstream chunks: {len(upstream)}")
    scores = sorted([edge for edge in edges
                     if edge["to"] == "summary_final" and edge["kind"] == "estimate"],
                    key=lambda edge: -edge["score"])[:3]
    lines.append("top replay scores for the summary: "
                 + str([(edge["from"][-12:], round(edge["score"], 4)) for edge in scores]))
    return lines


def main() -> int:
    data = json.loads((REPO / "experiments/source_path_v1/out/path_cuad.json").read_text(encoding="utf-8"))
    for line in compare(data):
        print(line)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
