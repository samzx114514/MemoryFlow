"""Build call-level session forests from a saved calls.jsonl.

Central calls and subagent calls are separate trees: a call continues its parent only when the
parent's full message list is a prefix of its own list and both share the same agent kind.
Cross-session links (which subagent ran a given delegate) are not recorded and stay unresolved.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import pathlib


def msg_hash(message: dict) -> str:
    body = json.dumps(message, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(body.encode("utf-8")).hexdigest()[:16]


def agent_of(system: str) -> str:
    """Classify from the role declaration line, not incidental text later."""
    first = ""
    for line in str(system or "").splitlines():
        if line.strip():
            first = line.strip().lower()
            break
    if "centralagent" in first or "central agent" in first:
        return "central"
    if "memory_recaller" in first:
        return "memory_recaller"
    if "perception subagent" in first:
        return "perception"
    if "coder subagent" in first:
        return "coder"
    if "reporter subagent" in first:
        return "reporter"
    return "other"


def build(rows: list[dict]) -> dict:
    calls = []
    for index, row in enumerate(rows):
        request = row.get("request") or {}
        messages = request.get("messages") or []
        system = next((str(m.get("content") or "") for m in messages if m.get("role") == "system"), "")
        generation = ((row.get("response") or {}).get("generations") or [{}])[0]
        calls.append({
            "call_id": f"call{index:02d}",
            "order": index,
            "agent": agent_of(system),
            "messages": [msg_hash(m) for m in messages],
            "finish": (generation.get("generation_info") or {}).get("finish_reason"),
            "tool_calls": [item.get("name") or (item.get("function") or {}).get("name")
                           for item in (generation.get("tool_calls") or [])],
        })
    for call in calls:
        parent, best = None, -1
        for other in calls:
            if other["order"] >= call["order"] or other["agent"] != call["agent"]:
                continue
            length = len(other["messages"])
            if length < len(call["messages"]) and call["messages"][:length] == other["messages"] and length > best:
                parent, best = other["call_id"], length
        call["parent"] = parent
    children: dict[str, list[str]] = {}
    for call in calls:
        if call["parent"]:
            children.setdefault(call["parent"], []).append(call["call_id"])
    return {
        "schema": "memoryflow.session_forest.v2",
        "calls": {call["call_id"]: {"order": call["order"], "agent": call["agent"], "parent": call["parent"],
                                    "messages": len(call["messages"]), "finish": call["finish"],
                                    "tool_calls": call["tool_calls"]} for call in calls},
        "roots": {agent: [call["call_id"] for call in calls if not call["parent"] and call["agent"] == agent]
                  for agent in sorted({call["agent"] for call in calls})},
        "branches": {parent: kids for parent, kids in children.items() if len(kids) > 1},
        "notes": [
            "message-level forest; API token ids are unavailable",
            "parent selection is restricted to earlier calls of the same role",
            "full request-message identity is used for prefix comparison",
            "native session/delegation ids are absent; subagent trees are separated but delegate-to-subagent mapping is unresolved",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--calls", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--label", default="v6")
    args = parser.parse_args()
    rows = [json.loads(line) for line in pathlib.Path(args.calls).read_text(encoding="utf-8").splitlines() if line.strip()]
    forest = build(rows)
    raw = pathlib.Path(args.calls).read_bytes()
    forest["input"] = {"calls_sha256": hashlib.sha256(raw).hexdigest(), "calls": len(rows), "label": args.label}
    pathlib.Path(args.out).write_text(json.dumps(forest, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps({"out": args.out, "calls": len(rows), "agents": forest["roots"], "branches": len(forest["branches"])},
                     ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
