"""Ingest adapters: any run that can be mapped to calls/messages/units/matrices."""

from __future__ import annotations

import json
import pathlib
import re
from typing import Any

from .model import Call, Candidate, Link, Matrix, ProvenanceGraph, Unit, text_sha


def _load_calls(run_dir: pathlib.Path) -> list[Call]:
    rows = [json.loads(line) for line in (run_dir / "calls.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    calls = []
    for index, row in enumerate(rows):
        request = row.get("request") or {}
        response = (row.get("response") or {}).get("generations") or [{}]
        generation = response[0] if response else {}
        calls.append(Call(
            call_id=f"call{index:02d}",
            task_id=str(row.get("task_id") or run_dir.name),
            session_id=str(row.get("thread_id") or row.get("user_id") or run_dir.name),
            index=index,
            ts=row.get("ts"),
            messages=list(request.get("messages") or []),
            response_text=generation.get("text") or "",
            response_tool_calls=list(generation.get("tool_calls") or []),
            finish_reason=((generation.get("generation_info") or {}).get("finish_reason")),
            request_sha256=text_sha(json.dumps(request, ensure_ascii=False, sort_keys=True)),
            response_sha256=text_sha((generation.get("text") or "") + json.dumps(generation.get("tool_calls") or [], sort_keys=True)),
            session_source="thread_id",
        ))
    return calls


def _delivery_units(prediction: dict[str, Any]) -> list[Unit]:
    delivery = prediction.get("delivery") or ""
    units = []
    for index, sentence in enumerate(s for s in re.split(r"(?<=[.!?])\s+", delivery) if s.strip()):
        units.append(Unit(unit_id=f"delivery#s{index:02d}", call_id="delivery", kind="delivery_sentence",
                          text=sentence.strip(), sha256=text_sha(sentence.strip()), char_span=(0, len(sentence))))
    return units


def _find_span(haystack: str, needle: str, start: int = 0) -> tuple[int, int] | None:
    position = haystack.find(needle, start)
    if position < 0:
        return None
    return position, position + len(needle)


def from_trace_run(run_dir: str | pathlib.Path, matrix_files: list[str | pathlib.Path] | None = None,
                   include_delivery: bool = True) -> ProvenanceGraph:
    """Ingest a native trace run: calls.jsonl + predictions.jsonl (+ replay matrix JSONs)."""
    run = pathlib.Path(run_dir)
    graph = ProvenanceGraph(task_id=run.name)
    for call in _load_calls(run):
        graph.calls[call.call_id] = call
        unit_id = f"{call.call_id}#response"
        graph.units[unit_id] = Unit(unit_id=unit_id, call_id=call.call_id, kind="assistant_text",
                                    text=call.full_response, sha256=text_sha(call.full_response),
                                    char_span=(0, len(call.full_response)))

    prediction = None
    if (run / "predictions.jsonl").exists():
        prediction = json.loads((run / "predictions.jsonl").read_text(encoding="utf-8").splitlines()[-1])
        if include_delivery and prediction.get("delivery"):
            for unit in _delivery_units(prediction):
                graph.units[unit.unit_id] = unit

    for call in graph.calls.values():
        for message_index, message in enumerate(call.messages):
            if message.get("role") == "system":
                continue
            content = str(message.get("content") or "")
            candidate_id = f"{call.call_id}:msg{message_index}"
            graph.candidates[candidate_id] = Candidate(
                candidate_id=candidate_id, call_id=call.call_id, message_index=message_index,
                role=str(message.get("role")), text=content, char_span=(0, len(content)))

    for matrix_path in matrix_files or []:
        record = json.loads(pathlib.Path(matrix_path).read_text(encoding="utf-8"))
        call_id = record.get("call")
        if not call_id:
            continue
        call = graph.calls.get(call_id)
        if call is None:
            continue
        target = record.get("target") or ""
        unit_id = f"{call_id}#target:{text_sha(target)[:8]}"
        graph.units[unit_id] = Unit(unit_id=unit_id, call_id=call_id, kind="matrix_target", text=target,
                                    sha256=text_sha(target), char_span=_find_span(call.full_response, target))
        scores = []
        for rank, candidate in enumerate(record.get("candidates") or [], start=1):
            text = candidate.get("text") or ""
            bound = None
            for existing in graph.candidates.values():
                if existing.call_id == call_id and text[:60] and text[:60] in existing.text:
                    bound = existing
                    break
            if bound is None:
                continue
            scores.append((bound.candidate_id, float(candidate.get("score") or 0.0)))
        graph.matrices[unit_id] = Matrix(matrix_id=f"{call_id}:matrix", call_id=call_id, unit_id=unit_id,
                                         model=str(record.get("model") or "qwen2.5"), layer=int(record.get("head", 0) and 0 or 0),
                                         head=15, rows=int(record.get("target_tokens") or 0), scores=scores,
                                         source=str(matrix_path))

    relink(graph)
    graph.notes["ingest"] = {"run": str(run), "calls": len(graph.calls),
                             "matrices": len(graph.matrices), "delivery": bool(prediction and prediction.get("delivery"))}
    return graph


def relink(graph: ProvenanceGraph) -> None:
    """Rebuild delivery and transmission links after all candidates/matrices exist.

    - delivery sentence: link to every call response that contains it; the latest producer is
      marked preferred (the actual delivery source), earlier occurrences stay as ambiguity.
    - candidate: link to the producing *unit* when the candidate text matches a matrix target
      text of that call (kind copy/embedded); otherwise to the producer response unit
      (unresolved=True) so the query can stop at an unbound transfer.
    """
    graph.links = [link for link in graph.links if link.kind in {"program"}]

    for unit in sorted(graph.units.values(), key=lambda u: u.unit_id):
        if unit.kind != "delivery_sentence" or len(unit.text.strip()) < 20:
            continue
        targets = []
        for matrix in graph.matrices.values():
            target_unit = graph.units.get(matrix.unit_id)
            if target_unit and (unit.text.strip() in target_unit.text or target_unit.text in unit.text):
                targets.append(target_unit)
        for target_unit in targets:
            graph.links.append(Link(link_id=f"{unit.unit_id}->{target_unit.unit_id}",
                                    from_id=unit.unit_id, to_id=target_unit.unit_id, kind="copy",
                                    evidence={"delivery_sentence_sha": text_sha(unit.text.strip()),
                                              "target_unit": target_unit.unit_id,
                                              "preferred": True, "relation": "delivery_to_matrix_target"},
                                    locality="cross_call"))
        matches = [call for call in sorted(graph.calls.values(), key=lambda c: c.index)
                   if unit.text.strip() in call.full_response]
        for position, call in enumerate(matches):
            preferred = position == len(matches) - 1
            graph.links.append(Link(link_id=f"{unit.unit_id}->{call.call_id}#response",
                                    from_id=unit.unit_id, to_id=f"{call.call_id}#response",
                                    kind="copy",
                                    evidence={"delivery_sentence_sha": text_sha(unit.text.strip()),
                                              "producer_call": call.call_id,
                                              "occurrence": position,
                                              "preferred": preferred},
                                    locality="cross_call"))

    ordered = sorted(graph.calls.values(), key=lambda c: c.index)
    matrices_by_call: dict[str, list] = {}
    for matrix in graph.matrices.values():
        matrices_by_call.setdefault(matrix.call_id, []).append(matrix)

    for call in ordered:
        for candidate in list(graph.candidates.values()):
            if candidate.call_id != call.call_id:
                continue
            text = candidate.text.strip()
            if len(text) < 20 or candidate.role not in {"assistant", "tool"}:
                continue
            if candidate.source == "current_output_prefix" or candidate.message_index is None:
                continue
            for producer in ordered:
                if producer.index >= call.index:
                    break
                response = producer.full_response.strip()
                if not response:
                    continue
                hit = None
                for matrix in matrices_by_call.get(producer.call_id, []):
                    unit = graph.units.get(matrix.unit_id)
                    if unit is None:
                        continue
                    unit_text = unit.text.strip()
                    if len(unit_text) >= 20 and (unit_text == text or unit_text in text or text in unit_text):
                        relation = "exact" if unit_text == text else ("contains" if unit_text in text else "contained_in")
                        kind = "copy" if candidate.role == "assistant" else "embedded"
                        hit = (unit.unit_id, kind, relation)
                        break
                if hit:
                    graph.links.append(Link(link_id=f"{candidate.candidate_id}->{hit[0]}",
                                            from_id=candidate.candidate_id, to_id=hit[0], kind=hit[1],
                                            evidence={"producer_call": producer.call_id,
                                                      "candidate_sha": text_sha(text),
                                                      "matched": "matrix_target",
                                                      "relation": hit[2]},
                                            locality="cross_call"))
                elif text in response:
                    graph.links.append(Link(link_id=f"{candidate.candidate_id}->{producer.call_id}#response",
                                            from_id=candidate.candidate_id,
                                            to_id=f"{producer.call_id}#response", kind="copy",
                                            evidence={"producer_call": producer.call_id,
                                                      "candidate_sha": text_sha(text),
                                                      "unresolved": True},
                                            locality="cross_call"))


def from_synthetic(calls: list[dict[str, Any]], matrices: list[dict[str, Any]] | None = None) -> ProvenanceGraph:
    """Minimal fixture adapter used by tests and demos.

    calls: [{id, messages:[{role, content}], response, tool_calls?}]
    matrices: [{call, target, candidates:[{text, score}]}]
    """
    graph = ProvenanceGraph(task_id="synthetic")
    for index, item in enumerate(calls):
        call_id = item["id"]
        call = Call(call_id=call_id, task_id="synthetic", session_id=item.get("session", "s"),
                    index=index, ts=item.get("ts"), messages=list(item.get("messages") or []),
                    response_text=item.get("response") or "", response_tool_calls=list(item.get("tool_calls") or []),
                    session_source=item.get("session_source", "fixture"))
        graph.calls[call_id] = call
        graph.units[f"{call_id}#response"] = Unit(unit_id=f"{call_id}#response", call_id=call_id, kind="assistant_text",
                                                  text=call.full_response, sha256=text_sha(call.full_response))
        for message_index, message in enumerate(call.messages):
            if message.get("role") == "system":
                continue
            graph.candidates[f"{call_id}:msg{message_index}"] = Candidate(
                candidate_id=f"{call_id}:msg{message_index}", call_id=call_id, message_index=message_index,
                role=str(message.get("role")), text=str(message.get("content") or ""),
                char_span=(0, len(str(message.get("content") or ""))))
    for index, record in enumerate(matrices or []):
        call_id = record["call"]
        target = record["target"]
        unit_id = f"{call_id}#target{index}"
        graph.units[unit_id] = Unit(unit_id=unit_id, call_id=call_id, kind="matrix_target", text=target,
                                    sha256=text_sha(target))
        scores = []
        for item in record.get("candidates") or []:
            text = item["text"]
            bound = next((c for c in graph.candidates.values() if c.call_id == call_id and text[:40] in c.text), None)
            if bound:
                scores.append((bound.candidate_id, float(item.get("score") or 0.0)))
        graph.matrices[unit_id] = Matrix(matrix_id=f"{call_id}:m{index}", call_id=call_id, unit_id=unit_id,
                                         model=record.get("model", "synthetic"), layer=record.get("layer", 0),
                                         head=record.get("head", 0), rows=record.get("rows", 0), scores=scores,
                                         source=record.get("source"))
    relink(graph)
    return graph
