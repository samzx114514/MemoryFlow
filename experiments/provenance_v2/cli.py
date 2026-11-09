"""CLI: build a provenance graph from a trace run and query one target unit."""

from __future__ import annotations

import argparse
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from provenance_v2 import ProvenanceQuery, build_forest, from_trace_run
from provenance_v2.ingest import relink
from provenance_v2.model import Matrix, Unit, text_sha


def normalize_matrices(run_dir: pathlib.Path, records: list[dict]) -> list[dict]:
    """Accept replay JSONs with call index/target/candidates and bind them to call ids."""
    out = []
    for record in records:
        call = record.get("call")
        call_id = f"call{int(call):02d}" if isinstance(call, int) else str(call)
        out.append({"call": call_id, "target": record.get("target") or "",
                    "candidates": record.get("candidates") or [],
                    "model": record.get("model") or "qwen2.5", "layer": record.get("layer") or 19,
                    "head": record.get("head") or 15, "rows": record.get("target_tokens") or 0,
                    "source": record.get("source") or ""})
    return out


def build(args) -> None:
    run = pathlib.Path(args.run)
    records = []
    for path in args.matrices or []:
        data = json.loads(pathlib.Path(path).read_text(encoding="utf-8"))
        if isinstance(data, dict) and "candidates" in data:
            records.append(data)
        elif isinstance(data, list):
            records.extend(data)
    graph = from_trace_run(run, matrix_files=None)
    import re
    from provenance_v2.model import Candidate
    for record in records:
        call = record.get("call")
        call_id = f"call{int(call):02d}" if isinstance(call, int) else str(call)
        if call_id not in graph.calls:
            continue
        target = record.get("target") or ""
        if not target.strip():
            continue
        unit_id = f"{call_id}#target:{text_sha(target)[:8]}"
        response = graph.calls[call_id].full_response
        span = record.get("target_char_span")
        position = int(span[0]) if isinstance(span, list) and len(span) == 2 else response.find(target)
        graph.units[unit_id] = Unit(unit_id=unit_id, call_id=call_id, kind="matrix_target", text=target,
                                    sha256=text_sha(target),
                                    char_span=(position, position + len(target)) if position >= 0 else None)
        rich = any(("message_index" in item and ("message_char_span" in item or "char_span" in item))
                   or item.get("source") == "current_output_prefix"
                   for item in record.get("candidates") or [])
        scores = []
        for item in record["candidates"]:
            text = item.get("text") or ""
            if not text:
                continue
            if rich:
                message_index = item.get("message_index")
                token_span = tuple(item["token_span"]) if item.get("token_span") else None
                source = item.get("source")
                if message_index is not None:
                    message_index = int(message_index)
                    messages = graph.calls[call_id].messages
                    if message_index >= len(messages):
                        continue
                    message = messages[message_index]
                    content = str(message.get("content") or "")
                    span = item.get("message_char_span") or item.get("char_span")
                    if not (isinstance(span, list) and len(span) == 2):
                        continue
                    start_char, end_char = int(span[0]), int(span[1])
                    if not (0 <= start_char <= end_char <= len(content)):
                        continue
                    if content[start_char:end_char] != text:
                        # keep the stored identity but flag the mismatch; do not silently slice elsewhere
                        text = content[start_char:end_char] if end_char <= len(content) else text
                    prompt_span = tuple(item["prompt_char_span"]) if isinstance(item.get("prompt_char_span"), list) else None
                    candidate_id = f"{call_id}:msg{message_index}:{start_char}-{end_char}"
                    graph.candidates[candidate_id] = Candidate(
                        candidate_id=candidate_id, call_id=call_id, message_index=message_index,
                        role=str(message.get("role")), text=text, char_span=(start_char, end_char),
                        token_span=token_span, prompt_char_span=prompt_span, source=source)
                else:
                    response_span = tuple(item["response_char_span"]) if isinstance(item.get("response_char_span"), list) else None
                    candidate_id = f"{call_id}:response:{response_span[0] if response_span else 0}-{response_span[1] if response_span else len(text)}"
                    graph.candidates[candidate_id] = Candidate(
                        candidate_id=candidate_id, call_id=call_id, message_index=None,
                        role=str(item.get("role") or "assistant"), text=text, char_span=None,
                        token_span=token_span, response_char_span=response_span, source=source)
            else:
                where = str(item.get("where") or "")
                match = re.search(r"message\[(\d+)\]", where)
                if not match:
                    continue
                message_index = int(match.group(1))
                messages = graph.calls[call_id].messages
                if message_index >= len(messages):
                    continue
                message = messages[message_index]
                content = str(message.get("content") or "")
                position = content.find(text[:60])
                if position < 0:
                    continue
                candidate_id = f"{call_id}:msg{message_index}:span{position}"
                graph.candidates[candidate_id] = Candidate(
                    candidate_id=candidate_id, call_id=call_id, message_index=message_index,
                    role=str(message.get("role")), text=text,
                    char_span=(position, position + len(text)))
            scores.append((candidate_id, float(item.get("score") or 0.0)))
        graph.matrices[unit_id] = Matrix(matrix_id=f"{call_id}:matrix:{unit_id[-8:]}", call_id=call_id,
                                         unit_id=unit_id,
                                         model=str(record.get("model") or args.model),
                                         layer=int(record.get("layer") or args.layer),
                                         head=int(record.get("head") or args.head),
                                         rows=int(record.get("rows") or record.get("target_tokens") or 0),
                                         scores=scores, source=str(record.get("source") or ""))
    relink(graph)
    forest = build_forest(graph)
    payload = {"graph": graph.to_dict(), "forest": {
        "parents": forest.parents, "roots": forest.roots, "ambiguous": forest.ambiguous,
        "sessions": forest.sessions, "transfers": forest.transfers, "evidence": forest.evidence}}
    out = pathlib.Path(args.out)
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps({"event": "BUILT", "out": str(out), "calls": len(graph.calls),
                      "matrices": len(graph.matrices), "units": len(graph.units),
                      "links": len(graph.links)}, ensure_ascii=False))


def query(args) -> None:
    from provenance_v2.model import Call, Candidate, Link, ProvenanceGraph

    payload = json.loads(pathlib.Path(args.graph).read_text(encoding="utf-8"))
    raw = payload["graph"]
    graph = ProvenanceGraph(task_id=raw["task_id"])
    for item in raw["calls"]:
        graph.calls[item["call_id"]] = Call(**item)
    for item in raw["units"]:
        item = dict(item)
        item["char_span"] = tuple(item["char_span"]) if item.get("char_span") else None
        graph.units[item["unit_id"]] = Unit(**item)
    for item in raw["candidates"]:
        item = dict(item)
        item["char_span"] = tuple(item["char_span"]) if item.get("char_span") else None
        item["token_span"] = tuple(item["token_span"]) if item.get("token_span") else None
        graph.candidates[item["candidate_id"]] = Candidate(**item)
    for item in raw["matrices"]:
        item = dict(item)
        item["scores"] = [tuple(pair) for pair in item["scores"]]
        graph.matrices[item["unit_id"]] = Matrix(**item)
    for item in raw["links"]:
        graph.links.append(Link(**item))
    relink(graph)
    forest = build_forest(graph)
    result = ProvenanceQuery(graph, forest, top_k=args.top_k, max_depth=args.depth).expand(args.unit)
    out = pathlib.Path(args.out)
    out.write_text(json.dumps(result.to_dict(), ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps({"event": "QUERY", "out": str(out), "hops": len(result.hops),
                      "stop": result.stop_reason}, ensure_ascii=False))


def main() -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    build_parser = sub.add_parser("build")
    build_parser.add_argument("--run", required=True)
    build_parser.add_argument("--matrices", nargs="*")
    build_parser.add_argument("--out", required=True)
    build_parser.add_argument("--model", default="qwen2.5-7b")
    build_parser.add_argument("--layer", type=int, default=19)
    build_parser.add_argument("--head", type=int, default=15)
    build_parser.set_defaults(func=build)
    query_parser = sub.add_parser("query")
    query_parser.add_argument("--graph", required=True)
    query_parser.add_argument("--unit", required=True)
    query_parser.add_argument("--depth", type=int, default=6)
    query_parser.add_argument("--top-k", type=int, default=5)
    query_parser.add_argument("--out", required=True)
    query_parser.set_defaults(func=query)
    args = parser.parse_args()
    args.func(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
