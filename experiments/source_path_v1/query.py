"""Query one unit in a `memoryflow.source_path.v2` file and print its traceable path.

Recorded and estimated edges are both traversed.  The path guard is local to a
branch, so a second legal route to the same unit is kept instead of being
silently consumed as a global-cycle repeat.
"""

from __future__ import annotations

import argparse
import json
import pathlib

MAX_TEXT = 110
LABELS = {
    "recorded_generation": "记录·生成归属",
    "history": "记录·历史沿用",
    "containment": "记录·区间包含",
    "estimate": "回放估计",
}
EDGE_ORDER = {kind: index for index, kind in enumerate(LABELS)}


def short(text: str) -> str:
    text = " ".join(str(text or "").split())
    return text if len(text) <= MAX_TEXT else text[:MAX_TEXT] + "…"


def trace(data: dict, target: str, depth: int = 3, max_paths: int = 128) -> list[str]:
    """Return an indented, branch-local trace for one target unit."""
    units = {unit["unit_id"]: unit for unit in data["units"]}
    calls = {call["call_id"]: call for call in data.get("calls", [])}
    if target not in units and target not in calls:
        raise KeyError(f"unknown unit: {target}")
    incoming: dict[str, list[dict]] = {}
    for edge in data["edges"]:
        incoming.setdefault(edge["to"], []).append(edge)

    def source_text(node_id: str) -> str | None:
        unit = units.get(node_id)
        if unit is not None:
            return short(unit["text"])
        call = calls.get(node_id)
        if call is not None:
            tools = [str(item.get("name") or "?") for item in call.get("tool_calls") or []]
            return f"[call {node_id}] agent={call.get('agent')} recorded={call.get('recorded')} tools={tools}"
        return None

    lines: list[str] = []
    seen: set[str] = set()
    edge_count = 0
    omitted = False

    def emit(line: str) -> None:
        lines.append(line)

    def walk(unit_id: str, remaining: int, indent: str, path: tuple[str, ...]) -> None:
        nonlocal edge_count, omitted
        seen.add(unit_id)
        if remaining <= 0:
            emit(f"{indent}└ (depth limit)")
            return
        parents = incoming.get(unit_id) or []
        if not parents:
            emit(f"{indent}└ (no upstream record)")
            return
        ordered = sorted(parents, key=lambda item: EDGE_ORDER.get(item["kind"], 99))
        for edge in ordered:
            if edge_count >= max_paths:
                omitted = True
                break
            edge_count += 1
            label = LABELS.get(edge["kind"], edge["kind"])
            extra = f" score={edge.get('score'):.4f}" if edge.get("score") is not None else ""
            emit(f"{indent}· [{label}]{extra} → {edge['from']}")
            text = source_text(edge["from"])
            if text is None:
                emit(f"{indent}  (boundary: source unit not in file)")
                continue
            emit(f"{indent}  {text}")
            if edge["from"] in path or edge["from"] == unit_id:
                emit(f"{indent}  (cycle stopped)")
                continue
            walk(edge["from"], remaining - 1, indent + "  ", path + (unit_id,))

    walk(target, depth, "", ())
    if omitted:
        emit(f"… paths omitted at max_paths={max_paths}")
    gaps = [gap for gap in data.get("gaps", []) if gap.get("unit_id") in seen]
    occurrences = [occ for occ in data.get("input_occurrences", []) if occ.get("unit") == target]
    return lines + [
        *[f"gap[{gap.get('unit_id')}]: {gap['reason']}" for gap in gaps],
        *[f"input_occurrence: {occ}" for occ in occurrences],
    ]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", required=True)
    parser.add_argument("--unit")
    parser.add_argument("--text")
    parser.add_argument("--depth", type=int, default=4)
    parser.add_argument("--max-paths", type=int, default=128)
    args = parser.parse_args()
    data = json.loads(pathlib.Path(args.data).read_text(encoding="utf-8"))
    units = {unit["unit_id"]: unit for unit in data["units"]}
    calls = {call["call_id"]: call for call in data.get("calls", [])}

    if args.unit:
        target = args.unit
    elif args.text:
        matches = [unit for unit in data["units"] if args.text.lower() in unit["text"].lower()]
        if not matches:
            print("no unit matches the text")
            return 1
        target = matches[0]["unit_id"]
    else:
        print("need --unit or --text")
        return 2
    if target not in units and target not in calls:
        print(f"unknown unit: {target}")
        return 1

    print(f"task: {data['task']['id']} | source: {data['task']['source']} | attempt: {data['task']['attempt']}")
    if target in units:
        print(f"unit: {target} | kind: {units[target]['kind']}")
        print(f"text: {short(units[target]['text'])}")
    else:
        call = calls[target]
        print(f"call: {target} | agent: {call.get('agent')} | recorded: {call.get('recorded')}")
    print()
    for line in trace(data, target, depth=args.depth, max_paths=args.max_paths):
        print(line)
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
