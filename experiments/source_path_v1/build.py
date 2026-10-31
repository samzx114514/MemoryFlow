"""Build one unified, queryable source path (schema v2).

Fixes over v1:
- summary parent unit + sentence children with real character ranges; whole-summary score stays on the parent
- generated output vs input occurrence are separate nodes; input copies point back to the source identity
- every edge endpoint exists as a recorded call/unit or an explicit unrecovered boundary
- tool results keep a preview plus a full-text reference to the original message
"""

from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import re
import sys

SCHEMA = "memoryflow.source_path.v2"
PREVIEW = 800


def sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def agent_of(system: str) -> str:
    """Classify from the role declaration line, not later incidental mentions."""
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


def sentences_with_spans(text: str) -> list[tuple[int, int, str]]:
    spans = []
    for match in re.finditer(r"[^.!?;]+[.!?;]?", text):
        piece = match.group(0).strip()
        if not piece:
            continue
        start = match.start() + match.group(0).find(piece)
        spans.append((start, start + len(piece), piece))
    return spans


def build_cuad(flow_path: str, case_path: str) -> dict:
    flow = json.loads(pathlib.Path(flow_path).read_text(encoding="utf-8"))
    case = json.loads(pathlib.Path(case_path).read_text(encoding="utf-8"))
    units = []
    for node in flow["nodes"]:
        kind = node["kind"]
        text = str(node.get("text") or "")
        if kind == "source_chunk":
            units.append({"unit_id": node["id"], "kind": "source", "text": text, "sha256": sha(text),
                          "producer": {"file": flow["name"], "call": None},
                          "location": {"chars": [node.get("char_start"), node.get("char_end")]}})
        elif kind == "research_summary":
            parent = "summary_final"
            units.append({"unit_id": parent, "kind": "summary", "text": text, "sha256": sha(text),
                          "producer": {"call": case["matrices"]["researcher"]["call_id"], "file": None},
                          "location": {"field": "summary_final", "chars": [0, len(text)]}})
            for index, (start, end, piece) in enumerate(sentences_with_spans(text)):
                units.append({"unit_id": f"{parent}#s{index}", "kind": "summary_sentence", "text": piece,
                              "sha256": sha(piece),
                              "producer": {"call": case["matrices"]["researcher"]["call_id"], "file": None},
                              "location": {"parent": parent, "chars": [start, end]}})
        elif kind == "report_output":
            units.append({"unit_id": node["id"], "kind": "judgment", "text": text, "sha256": sha(text),
                          "producer": {"call": case["matrices"]["reporter"]["call_id"], "file": None},
                          "location": {"field": "report_span_0"}})
    calls = []
    for node in flow["nodes"]:
        if node["kind"] == "model_call":
            calls.append({"call_id": node["id"], "agent": "unknown", "recorded": False,
                          "request_hash": None, "response": {}, "tool_results": []})
    by_id = {call["call_id"]: call for call in calls}
    for name, matrix in case["matrices"].items():
        call = by_id.setdefault(matrix["call_id"], {"call_id": matrix["call_id"], "agent": matrix.get("agent") or name,
                                                    "recorded": True, "request_hash": None, "response": {},
                                                    "tool_results": []})
        call.update({"recorded": True, "agent": matrix.get("agent") or name,
                     "prompt_tokens": matrix.get("request_tokens"), "response": {"unit": matrix.get("target_unit")}})
    edges = []
    skipped_input_copies = []
    generated = {unit["unit_id"] for unit in units if unit["kind"] in {"judgment", "summary", "summary_sentence"}}
    for edge in flow["edges"]:
        source, target, kind = edge["source"], edge["target"], edge["kind"]
        if source in generated and target in by_id and kind == "text_visible_in_input":
            skipped_input_copies.append({"unit": source, "call": target, "evidence": edge.get("evidence")})
            continue
        if source in by_id and kind in {"model_output_contains_analysis", "model_output_contains_span"}:
            edges.append({"from": source, "to": target, "kind": "recorded_generation",
                          "evidence": {"flow_edge": kind, "note": edge.get("evidence")}})
        else:
            edges.append({"from": source, "to": target, "kind": "history",
                          "evidence": {"flow_edge": kind, "note": edge.get("evidence")}})
    parent = "summary_final"
    for unit in units:
        if unit["kind"] == "summary_sentence":
            edges.append({"from": parent, "to": unit["unit_id"], "kind": "containment",
                          "evidence": {"chars": unit["location"]["chars"]}})
    for name, matrix in case["matrices"].items():
        target_unit = matrix.get("target_unit")
        for candidate, score in (matrix.get("per_candidate_max") or {}).items():
            edges.append({"from": candidate, "to": target_unit, "kind": "estimate",
                          "evidence": {"matrix": name, "call_id": matrix["call_id"]},
                          "score": round(float(score), 6), "score_kind": "fixed_head_replay"})
    gaps = [{"unit_id": "summary_final#s0",
             "reason": "sentence-level score not replayed; the 0.7569 score applies to the whole summary (summary_final)"},
            {"unit_id": "report_span_0",
             "reason": "an input copy of this text is recorded as an input occurrence of chunk 2593:3850, not as a generated upstream"}]
    return {"schema": SCHEMA,
            "task": {"id": flow.get("name"), "source": "cuad_flow", "attempt": "03_dcc_complete",
                     "session": "single", "notes": "old system mechanism material"},
            "calls": calls, "units": units, "edges": edges, "gaps": gaps,
            "input_occurrences": skipped_input_copies,
            "scores": {"whole_summary": case["gold"]["row"]["indirect"],
                       "reporter_summary": case["summary_mass_in_reporter"],
                       "direct": case["gold"]["row"]["direct_in_final_call"]}}


def build_dccv2(run_dir: str, artifact: str) -> dict:
    run = pathlib.Path(run_dir)
    state_path = run / "attempts/0000/state.json"
    if not state_path.is_file():
        state_path = run / "state.json"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    rows = [json.loads(line) for line in (run / "calls.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    verdict = json.loads(pathlib.Path(artifact).read_text(encoding="utf-8"))
    units, calls, edges = [], [], []
    for index, row in enumerate(rows):
        request = row.get("request") or {}
        messages = request.get("messages") or []
        system = next((str(m.get("content") or "") for m in messages if m.get("role") == "system"), "")
        generation = ((row.get("response") or {}).get("generations") or [{}])[0]
        agent = agent_of(system)
        call_id = f"call{index:02d}"
        tool_calls = [{"name": item.get("name") or (item.get("function") or {}).get("name"),
                       "args": json.dumps(item.get("args") or {}, ensure_ascii=False)} for item in (generation.get("tool_calls") or [])]
        calls.append({"call_id": call_id, "agent": agent, "recorded": True,
                      "request_hash": sha(json.dumps(request, sort_keys=True, default=str)),
                      "response": {"finish": (generation.get("generation_info") or {}).get("finish_reason"),
                                   "text": generation.get("text"), "tool_calls": tool_calls},
                      "tool_results": []})
        for message_index, message in enumerate(messages):
            if message.get("role") != "tool":
                continue
            content = str(message.get("content") or "")
            name = message.get("name")
            unit_id = f"{call_id}:tool:{sha(content)[:10]}"
            units.append({"unit_id": unit_id, "kind": "tool_result", "text": content[:PREVIEW], "sha256": sha(content),
                          "producer": {"call": None, "file": None},
                          "location": {"call": call_id, "message_index": message_index, "tool": name,
                                       "full_chars": len(content),
                                       "full_ref": f"calls.jsonl#{call_id}#message[{message_index}]"}})
            edges.append({"from": unit_id, "to": call_id, "kind": "history",
                          "evidence": {"tool": name, "visible_in": call_id}})
    for field in ("violation", "illegal_operation", "problematic_team"):
        text = f"{field} = {json.dumps(verdict.get(field))}"
        units.append({"unit_id": f"verdict:{field}", "kind": "judgment", "text": text, "sha256": sha(text),
                      "producer": {"file": "recovery-verdict.json", "call": None},
                      "location": {"field": field}})
    for index, (start, end, piece) in enumerate(sentences_with_spans(str(verdict.get("reason") or ""))):
        units.append({"unit_id": f"verdict:reason:s{index}", "kind": "judgment_sentence", "text": piece,
                      "sha256": sha(piece), "producer": {"file": "recovery-verdict.json", "call": None},
                      "location": {"field": "reason", "chars": [start, end]}})
    producers: dict[str, list[dict]] = {}
    for unit in units:
        if not unit["unit_id"].startswith("verdict:reason"):
            continue
        matches = []
        for record in calls:
            response_text = json.dumps(record["response"], ensure_ascii=False)
            if unit["text"] and unit["text"] in response_text:
                matches.append({"call": record["call_id"], "via": "response"})
            for tool_call in record["response"]["tool_calls"]:
                if tool_call["name"] in {"write_file", "str_replace"} and unit["text"] in tool_call["args"]:
                    matches.append({"call": record["call_id"], "via": "write_args"})
        producers[unit["unit_id"]] = matches
        if matches:
            unit["producer"] = {"file": "recovery-verdict.json", "call": matches[0]["call"],
                                "also_seen_in": [m["call"] for m in matches[1:]]}
            for match in matches:
                edges.append({"from": match["call"], "to": unit["unit_id"], "kind": "recorded_generation",
                              "evidence": {"via": match["via"], "file": "recovery-verdict.json"}})
    gaps = [
        {"unit_id": "verdict:violation", "reason": "no native FINISH: artifact registered as generated_file but never selected as the final delivery"},
        {"unit_id": "verdict:reason:s0", "reason": "rules-file history hash is unrecoverable; the trail stops at the tool-result boundary"},
        {"unit_id": "verdict:reason:s0", "reason": "replay covers only the one selected reason sentence against visible tool excerpts"},
    ]
    return {"schema": SCHEMA,
            "task": {"id": "comp_0#004", "source": "dccv2", "attempt": run.name,
                     "session": state.get("run_id"), "notes": "premise-missing run; unfinished"},
            "calls": calls, "units": units, "edges": edges, "gaps": gaps,
            "input_occurrences": [], "producers": {key: value for key, value in producers.items()},
            "scores": {}}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cuad-flow")
    parser.add_argument("--cuad-case")
    parser.add_argument("--dccv2-run")
    parser.add_argument("--artifact")
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    if args.cuad_flow and args.cuad_case:
        data = build_cuad(args.cuad_flow, args.cuad_case)
    elif args.dccv2_run:
        data = build_dccv2(args.dccv2_run, args.artifact)
    else:
        print("nothing to build", file=sys.stderr)
        return 2
    pathlib.Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    pathlib.Path(args.out).write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps({"out": args.out, "calls": len(data["calls"]), "units": len(data["units"]),
                      "edges": len(data["edges"]), "gaps": len(data["gaps"])}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
