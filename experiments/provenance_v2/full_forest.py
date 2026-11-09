"""Build span-level content links while keeping dispatch and context separate."""

from __future__ import annotations

import json
import re
from collections import defaultdict
from dataclasses import asdict
from pathlib import Path

from .forest import build_forest
from .full_batch import digest, select_calls, write_json
from .ingest import _load_calls
from .model import ProvenanceGraph
from .span_views import View, views


def action_id(messages):
    for message in messages:
        content = message.get("content") or ""
        if message.get("role") == "user" and "<sp-subagent-task>" in content:
            payload = content.split("<sp-subagent-task>", 1)[1].lstrip()
            try:
                task = json.JSONDecoder().raw_decode(payload)[0]
            except ValueError:
                continue
            if isinstance(task, dict) and isinstance(task.get("action_id"), str):
                return task["action_id"]
    return None


def matches(column, producer_views, min_chars):
    needle = column["match_text"]
    if len(needle) < min_chars or not any(ch.isalnum() for ch in needle):
        return []
    receiver = View(needle, column["prompt_char_span"][0],
                    column.get("match_offsets") and [column["prompt_char_span"][0] + position - column["match_offsets"][0]
                                                     for position in column["match_offsets"]])
    spans = []
    for view in producer_views:
        for match in re.finditer(f"(?={re.escape(needle)})", view.text):
            left = match.start()
            spans.append((receiver.span(0, len(needle)), view.span(left, left + len(needle))))
        value = view.text.strip()
        if min_chars <= len(value) < len(needle):
            for match in re.finditer(f"(?={re.escape(value)})", needle):
                left = match.start()
                start = len(view.text) - len(view.text.lstrip())
                spans.append((receiver.span(left, left + len(value)), view.span(start, start + len(value))))
    return sorted(set(spans))


def build_run(run: Path, matrix_dir: Path, out: Path):
    manifest = json.loads((matrix_dir / "manifest.json").read_text(encoding="utf-8"))
    chosen, user_id = select_calls(run, manifest["user_id"])
    if manifest["calls_sha256"] != digest(run / "calls.jsonl"):
        raise ValueError("Forest input differs from the matrix input")
    observed = {f"call{index:02d}": row for index, row in chosen}
    if observed.keys() != manifest["calls"].keys():
        raise ValueError("Matrices do not cover the selected episode")
    graph = ProvenanceGraph(task_id=run.name)
    tools, by_action, actions = {}, defaultdict(list), {}
    for call in _load_calls(run):
        if call.call_id not in observed:
            continue
        row = observed[call.call_id]
        action = action_id(call.messages)
        if action is not None:
            call.session_id, call.session_source = action, "recorded_action_id"
            by_action[action].append(call.call_id)
        elif row.get("thread_id"):
            call.session_id, call.session_source = str(row["thread_id"]), "recorded_thread_id"
        elif call.messages[0]["role"] == "system" and "CentralAgent" in (call.messages[0].get("content") or "").split("\n", 1)[0]:
            call.session_id, call.session_source = "central", "central_system_header"
        else:
            call.session_id, call.session_source = None, "unknown"
        graph.calls[call.call_id] = call
        actions[call.call_id] = action
        for tool in call.response_tool_calls:
            if tool.get("id"):
                if tool["id"] in tools:
                    raise ValueError("Duplicate recorded tool invocation ID")
                tools[tool["id"]] = (call.call_id, tool)

    forest = build_forest(graph)
    schedule, tool_results, transfers = [], [], []
    for action, chain in by_action.items():
        record = tools.get(action.removeprefix("spact_"))
        if record and graph.calls[record[0]].index < graph.calls[chain[0]].index:
            schedule.append({"producer_call": record[0], "recipient_call": chain[0], "action_id": action,
                             "tool_call_id": record[1]["id"], "tool_name": record[1].get("name"), "kind": "dispatch"})

    producer_views = {}
    serialized_calls = {}
    for call_id, call in graph.calls.items():
        item = manifest["calls"][call_id]
        metadata_path = matrix_dir / item["metadata"]
        if digest(metadata_path) != item["metadata_sha256"]:
            raise ValueError(f"Modified matrix metadata for {call_id}")
        matrix = json.loads(metadata_path.read_text(encoding="utf-8"))
        output = matrix["output"]
        split = matrix["response_text_length"]
        serialized_calls[call_id] = {**asdict(call), "recorded_request": observed[call_id]["request"],
                                     "recorded_response": observed[call_id]["response"], "replay_output": output}
        earlier = {key: value for key, value in producer_views.items() if graph.calls[key].index < call.index}

        # When a real tool-call ID identifies the latest assistant in this
        # session it also covers assistant turns with an empty text body.
        for message in reversed(call.messages):
            if message.get("role") != "assistant":
                continue
            origins = {tools[tool["id"]][0] for tool in message.get("tool_calls") or []
                       if tool.get("id") in tools and tools[tool["id"]][0] in earlier}
            origins = {origin for origin in origins if graph.calls[origin].session_id == call.session_id and call.session_id}
            if len(origins) == 1:
                forest.parents[call_id] = sorted(origins)
                forest.ambiguous.pop(call_id, None)
                forest.evidence[call_id] = {"method": "recorded_assistant_tool_id"}
                break
            if message.get("content"):
                break

        for index, message in enumerate(call.messages):
            if message.get("role") != "tool":
                continue
            tool_id = message.get("tool_call_id")
            if tool_id in tools and tools[tool_id][0] in earlier:
                producer, tool = tools[tool_id]
                tool_results.append({"invocation_call": producer, "recipient_call": call_id, "message_index": index,
                                     "tool_call_id": tool_id, "name": tool.get("name"), "args": tool.get("args"),
                                     "child_calls": [c for c in by_action.get("spact_" + tool_id, []) if c in earlier]})

        for column in matrix["columns"]:
            index = column["message_index"]
            if index is None:
                continue
            message = call.messages[index]
            role = message["role"]
            provenance, kind = "exact_text", "copy"
            sources = list(earlier)
            if role == "assistant":
                origins = {tools[tool["id"]][0] for tool in message.get("tool_calls") or []
                           if tool.get("id") in tools and tools[tool["id"]][0] in earlier}
                exact = {c for c in earlier if message.get("content") and message["content"] == graph.calls[c].response_text}
                if origins or exact:
                    sources = sorted(origins or exact)
                    provenance = "recorded_tool_id" if origins else "exact_assistant_message"
            elif role == "tool":
                kind = "embedded"
                child_calls = by_action.get("spact_" + str(message.get("tool_call_id")), [])
                if child_calls:
                    sources = [c for c in child_calls if c in earlier]
                    provenance = "delegation_result"
            elif role == "user" and actions[call_id]:
                kind = "forwarded"
            elif role != "user":
                continue
            hits = []
            for producer in sources:
                for receiver_span, producer_span in matches(column, earlier[producer], 8 if provenance != "exact_text" else 20):
                    message_span = column["message_char_span"]
                    offset = column["prompt_char_span"][0] - message_span[0] if message_span else None
                    hits.append({"producer_call": producer, "producer_span": producer_span, "recipient_call": call_id,
                                 "recipient_prompt_span": receiver_span,
                                 "recipient_message_span": [value - offset for value in receiver_span] if offset is not None else None,
                                 "message_index": index, "column": column["column"], "kind": kind, "basis": provenance})
            # Keep competing occurrences visible rather than asserting a unique origin.
            for hit in hits:
                hit["ambiguous"] = len(hits) > 1
                transfers.append(hit)
        producer_views[call_id] = [*views(output[:split]), *views(output[split:], start=split, structured=True)]

    forest.children = {}
    for child, parents in forest.parents.items():
        for parent in parents:
            forest.children.setdefault(parent, []).append(child)
    forest.roots = [call_id for call_id in graph.calls if not forest.parents.get(call_id)]
    forest.transfers = []
    payload = {"schema": "memoryflow.full_forest.v1", "manifest_sha256": digest(matrix_dir / "manifest.json"),
               "calls_sha256": manifest["calls_sha256"], "user_id": user_id, "calls": serialized_calls,
               "forest": asdict(forest), "dispatch": schedule, "tool_results": tool_results, "content_transfers": transfers}
    write_json(out, payload)
    return payload
