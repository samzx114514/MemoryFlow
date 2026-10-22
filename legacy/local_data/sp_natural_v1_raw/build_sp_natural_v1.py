from __future__ import annotations

import argparse
import hashlib
import importlib.machinery
import importlib.util
import json
import os
import re
import statistics
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


SCHEMA_VERSION = "sp-natural-v1"
PARSER_VERSION = "c5b-local-1.0.0"
PROJECT_ROOT = Path(r"F:\CodexProject\MemoryFlow")
AUDIT_DIR = PROJECT_ROOT / "smallest_experiment" / "data_rebuild_v2" / "sp_audit"
INVENTORY_PATH = AUDIT_DIR / "sp_run_inventory.jsonl"
TRACE_PATH = AUDIT_DIR / "sp_memory_trace.jsonl"
AUDIT_REPORT_PATH = AUDIT_DIR / "sp_memory_recoverability_report.md"
FROZEN20_DIR = PROJECT_ROOT / "smallest_experiment" / "data_rebuild_v2" / "sp_natural_v1_frozen20"
AUDIT_PYC = AUDIT_DIR / "__pycache__" / "_build_sp_audit.cpython-312.pyc"
DEFAULT_OUTPUT = PROJECT_ROOT / "smallest_experiment" / "data" / "sp_natural_v1_raw"

CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
PURE_NUMBER_RE = re.compile(r"^[\s+\-−]?(?:\d+(?:[.,]\d+)*)[%％]?$", re.UNICODE)
HEADING_RE = re.compile(r"^\s{0,3}#{1,6}\s+\S")
TRACEBACK_RE = re.compile(r"(?:Traceback \(most recent call last\)|\bException\b|\bError:)", re.I)
PARAGRAPH_RE = re.compile(r"\S(?:.*?\S)?(?=\r?\n\s*\r?\n|\Z)", re.S)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def sha256_text(text: str) -> str:
    return sha256_bytes(text.encode("utf-8"))


def clean_text(text: str) -> str:
    """Only normalize control characters and whitespace; never paraphrase."""
    text = CONTROL_RE.sub("", text.replace("\r\n", "\n").replace("\r", "\n"))
    return "\n".join(line.rstrip() for line in text.split("\n")).strip()


def quality_flags(text: str, *, kind: str = "") -> list[str]:
    cleaned = clean_text(text)
    flags: list[str] = []
    if not cleaned:
        flags.append("empty_text")
    if cleaned and PURE_NUMBER_RE.fullmatch(cleaned):
        flags.extend(["pure_numeric", "not_evaluation_target"])
    if cleaned and len(cleaned) < 20:
        flags.append("anomalously_short")
    if len(cleaned) > 20_000:
        flags.append("very_long_text")
    if kind == "report_paragraph" and HEADING_RE.fullmatch(cleaned):
        flags.extend(["heading_only", "not_evaluation_target"])
    if TRACEBACK_RE.search(cleaned) or kind == "error":
        flags.append("error_stack")
    return list(dict.fromkeys(flags))


def load_audit_parser():
    if sys.version_info[:2] != (3, 12):
        raise RuntimeError("audited parser requires Python 3.12")
    if not AUDIT_PYC.exists():
        raise FileNotFoundError(f"audited parser missing: {AUDIT_PYC}")
    src_root = PROJECT_ROOT / "smallest_experiment" / "src"
    sys.path.insert(0, str(src_root))
    loader = importlib.machinery.SourcelessFileLoader("memoryflow_sp_audit_reuse", str(AUDIT_PYC))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    if spec is None:
        raise RuntimeError("could not create audited-parser import spec")
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def event_locator(event: dict[str, Any] | None, field: str, fallback_line: int = 0) -> str:
    if not event:
        return f"line:{fallback_line};field:{field}"
    return (
        f"line:{event.get('start_line', fallback_line)}-{event.get('end_line', fallback_line)};"
        f"event:{event.get('event_position', 'unknown')};field:{field}"
    )


def event_position(event: dict[str, Any] | None, fallback: int) -> int:
    if not event:
        return fallback
    value = event.get("event_position")
    return value if isinstance(value, int) else fallback


def recursive_contains(value: Any, needle: str) -> bool:
    if isinstance(value, str):
        return value == needle or (len(needle) >= 32 and needle in value)
    if isinstance(value, dict):
        return any(recursive_contains(item, needle) for item in value.values())
    if isinstance(value, list):
        return any(recursive_contains(item, needle) for item in value)
    return False


def make_node(
    *,
    case_id: str,
    agent_name: str,
    step_type: str,
    text_raw: str,
    source_file: str,
    source_locator: str,
    timestamp: str | None,
    position: int,
    ordinal: int,
    parent_ids: list[str] | None = None,
    edge_evidence: list[dict[str, Any]] | None = None,
    extra_flags: Iterable[str] = (),
    kind: str = "",
) -> dict[str, Any]:
    parents = parent_ids or []
    evidence = edge_evidence or []
    evidence_types = {item.get("evidence_type") for item in evidence}
    if "explicit" in evidence_types:
        evidence_type, confidence = "explicit", 1.0
    elif "inferred" in evidence_types:
        evidence_type, confidence = "inferred", 0.65
    else:
        evidence_type, confidence = "none", 0.0
    identity = f"{case_id}\0{step_type}\0{position}\0{ordinal}\0{sha256_text(text_raw)}"
    node_id = f"spn:{case_id}:{step_type}:{sha256_text(identity)[:20]}"
    flags = list(dict.fromkeys([*quality_flags(text_raw, kind=kind or step_type), *extra_flags]))
    return {
        "schema_version": SCHEMA_VERSION,
        "case_id": case_id,
        "node_id": node_id,
        "agent_name": agent_name,
        "step_type": step_type,
        "timestamp": timestamp,
        "order": 0,
        "text_raw": text_raw,
        "text_clean": clean_text(text_raw),
        "source_file": source_file,
        "source_locator": source_locator,
        "parent_ids": parents,
        "edge_evidence": evidence,
        "evidence_type": evidence_type,
        "confidence": confidence,
        "quality_flags": flags,
        "_position": position,
        "_ordinal": ordinal,
    }


def paragraph_spans(text: str) -> list[tuple[int, int, str]]:
    return [(match.start(), match.end(), match.group(0)) for match in PARAGRAPH_RE.finditer(text)]


def _matching_memory_entry(
    entries: list[dict[str, Any]], agent_type: str, text: str
) -> dict[str, Any] | None:
    for entry in entries:
        if str(entry.get("agent_type", "")).lower() != agent_type:
            continue
        if recursive_contains(entry.get("result"), text):
            return entry
    return None


def trace_to_nodes(trace: dict[str, Any]) -> tuple[list[dict[str, Any]], list[str]]:
    provenance = trace.get("raw_log_provenance") or {}
    source_file = str(provenance.get("absolute_path") or "")
    explicit_run_id = str(trace.get("run_id") or "").strip()
    case_warnings: list[str] = []
    if explicit_run_id:
        case_id = explicit_run_id
        boundary_flags: list[str] = []
    else:
        material = f"{source_file}:{provenance.get('request_start_line')}:{trace.get('query', '')}"
        case_id = f"inferred-{sha256_text(material)[:24]}"
        boundary_flags = ["inferred_case_boundary"]
        case_warnings.append("missing explicit run/thread id; stable request-boundary fallback used")

    nodes: list[dict[str, Any]] = []
    request_line = int(provenance.get("request_start_line") or 0)
    query = trace.get("query") if isinstance(trace.get("query"), str) else ""
    query_node = make_node(
        case_id=case_id,
        agent_name="user",
        step_type="query",
        text_raw=query,
        source_file=source_file,
        source_locator=event_locator(None, "request.messages[user].content", request_line),
        timestamp=None,
        # The query opens the request. Raw line numbers and logical event positions
        # use different coordinate systems, so use an explicit pre-event sentinel.
        position=-1,
        ordinal=0,
        extra_flags=boundary_flags,
    )
    nodes.append(query_node)

    delegates: list[tuple[dict[str, Any], dict[str, Any]]] = []
    for index, delegate in enumerate(trace.get("delegates") or []):
        event = delegate.get("raw_event") or {}
        target = str(delegate.get("target_agent") or "unknown").lower()
        task = delegate.get("task_description") if isinstance(delegate.get("task_description"), str) else ""
        edge = {
            "parent_id": query_node["node_id"],
            "evidence_type": "inferred",
            "evidence": "same explicit run and stable Central→delegate workflow order; no logged parent field",
            "source_locator": event_locator(event, "DelegateParams.task_description"),
        }
        node = make_node(
            case_id=case_id,
            agent_name="central",
            step_type="consult" if target == "consult" else "other",
            text_raw=task,
            source_file=source_file,
            source_locator=event_locator(event, "DelegateParams.task_description"),
            timestamp=delegate.get("timestamp") or event.get("timestamp"),
            position=event_position(event, request_line * 1000 + index + 1),
            ordinal=index,
            parent_ids=[query_node["node_id"]],
            edge_evidence=[edge],
            extra_flags=["delegate_action"],
        )
        nodes.append(node)
        delegates.append((delegate, node))

    # Preserve non-delegate Central decisions, including a structured consult if one exists.
    known_event_hashes = {
        (item.get("raw_event") or {}).get("content_sha256") for item, _ in delegates
    }
    for index, decision in enumerate(trace.get("central_decisions") or []):
        event = decision.get("raw_event") or {}
        if event.get("content_sha256") in known_event_hashes:
            continue
        action = str(decision.get("action") or "other").lower()
        text = decision.get("task_description") or decision.get("reasoning") or ""
        node = make_node(
            case_id=case_id,
            agent_name="central",
            step_type="consult" if action == "consult" else "other",
            text_raw=text if isinstance(text, str) else json.dumps(text, ensure_ascii=False),
            source_file=source_file,
            source_locator=event_locator(event, f"central_decision.{action}"),
            timestamp=event.get("timestamp"),
            position=event_position(event, request_line * 1000 + 100 + index),
            ordinal=100 + index,
            parent_ids=[query_node["node_id"]],
            edge_evidence=[{
                "parent_id": query_node["node_id"],
                "evidence_type": "inferred",
                "evidence": "same explicit run; log does not expose a parent id",
                "source_locator": event_locator(event, f"central_decision.{action}"),
            }],
            extra_flags=[f"central_action:{action}"],
        )
        nodes.append(node)

    entries = (trace.get("memory_stack_summary") or {}).get("entries") or []

    outline = trace.get("outline") or {}
    if outline.get("present"):
        text = outline.get("full_output") if isinstance(outline.get("full_output"), str) else ""
        event = outline.get("raw_event") or outline.get("state_event") or {}
        candidates = [(d, n) for d, n in delegates if str(d.get("target_agent", "")).lower() == "outline"]
        parent_ids: list[str] = []
        edges: list[dict[str, Any]] = []
        if candidates:
            _, parent = candidates[-1]
            parent_ids = [parent["node_id"]]
            edges = [{
                "parent_id": parent["node_id"],
                "evidence_type": "inferred",
                "evidence": "Outline output follows an explicit delegation to Outline; no result id is logged",
                "source_locator": event_locator(event, "outline.full_output"),
            }]
        node = make_node(
            case_id=case_id,
            agent_name="outline",
            step_type="outline",
            text_raw=text,
            source_file=source_file,
            source_locator=event_locator(event, "outline.full_output"),
            timestamp=event.get("timestamp"),
            position=event_position(event, request_line * 1000 + 300),
            ordinal=0,
            parent_ids=parent_ids,
            edge_evidence=edges,
        )
        if (
            outline.get("outline_output_matches_state") is not False
            and outline.get("content_sha256")
            and sha256_text(text) != outline.get("content_sha256")
        ):
            node["quality_flags"].append("source_hash_mismatch")
            case_warnings.append("outline hash mismatch")
        elif outline.get("outline_output_matches_state") is False:
            node["quality_flags"].append("outline_state_divergence")
        nodes.append(node)

    observations = trace.get("observations") or []
    if trace.get("observations_field_seen") and not observations:
        state_event = (trace.get("memory_stack_summary") or {}).get("raw_event") or {}
        nodes.append(make_node(
            case_id=case_id,
            agent_name="researcher",
            step_type="retrieval_observation",
            text_raw="",
            source_file=source_file,
            source_locator=event_locator(state_event, "state.observations(empty)"),
            timestamp=state_event.get("timestamp"),
            position=event_position(state_event, request_line * 1000 + 400),
            ordinal=0,
            extra_flags=["explicit_empty_observation_state"],
        ))
    for index, observation in enumerate(observations):
        text = observation.get("text") if isinstance(observation.get("text"), str) else ""
        event = observation.get("producer_event") or (trace.get("memory_stack_summary") or {}).get("raw_event") or {}
        memory_entry = _matching_memory_entry(entries, "researcher", text)
        researcher_delegates = [(d, n) for d, n in delegates if str(d.get("target_agent", "")).lower() == "researcher"]
        parent_ids: list[str] = []
        edges: list[dict[str, Any]] = []
        if researcher_delegates:
            matching = None
            if memory_entry:
                content = str(memory_entry.get("content") or "")
                matching = next(
                    ((d, n) for d, n in reversed(researcher_delegates) if str(d.get("task_description") or "") in content),
                    None,
                )
            delegate, parent = matching or researcher_delegates[-1]
            parent_ids = [parent["node_id"]]
            explicit = memory_entry is not None and matching is not None
            edges = [{
                "parent_id": parent["node_id"],
                "evidence_type": "explicit" if explicit else "inferred",
                "evidence": (
                    "memory_stack delegate entry explicitly stores this Researcher observation result"
                    if explicit else
                    "Observation follows a Researcher delegation; no exact delegate/result link was recoverable"
                ),
                "source_locator": event_locator(event, f"observations[{index}]"),
            }]
        node = make_node(
            case_id=case_id,
            agent_name="researcher",
            step_type="retrieval_observation",
            text_raw=text,
            source_file=source_file,
            source_locator=event_locator(event, f"observations[{index}]"),
            timestamp=event.get("timestamp"),
            position=event_position(event, request_line * 1000 + 400 + index),
            ordinal=index,
            parent_ids=parent_ids,
            edge_evidence=edges,
        )
        if observation.get("content_sha256") and sha256_text(text) != observation.get("content_sha256"):
            node["quality_flags"].append("source_hash_mismatch")
            case_warnings.append(f"observation {index} hash mismatch")
        nodes.append(node)

    final = trace.get("final_report") or {}
    report_text = final.get("text") if isinstance(final.get("text"), str) else ""
    if final.get("present"):
        event = final.get("raw_event") or {}
        reporter_delegates = [(d, n) for d, n in delegates if str(d.get("target_agent", "")).lower() == "reporter"]
        report_entry = _matching_memory_entry(entries, "reporter", report_text)
        for index, (start, end, paragraph) in enumerate(paragraph_spans(report_text)):
            parent_ids: list[str] = []
            edges: list[dict[str, Any]] = []
            if reporter_delegates:
                _, parent = reporter_delegates[-1]
                parent_ids = [parent["node_id"]]
                explicit = report_entry is not None
                edges = [{
                    "parent_id": parent["node_id"],
                    "evidence_type": "explicit" if explicit else "inferred",
                    "evidence": (
                        "memory_stack Reporter delegate result explicitly contains this final report"
                        if explicit else
                        "Final report follows a Reporter delegation; no exact delegate/result link was recoverable"
                    ),
                    "source_locator": event_locator(event, f"final_report[{start}:{end}]"),
                }]
            nodes.append(make_node(
                case_id=case_id,
                agent_name="reporter",
                step_type="report_paragraph",
                text_raw=paragraph,
                source_file=source_file,
                source_locator=event_locator(event, f"final_report[{start}:{end}]"),
                timestamp=event.get("timestamp"),
                position=event_position(event, request_line * 1000 + 500),
                ordinal=index,
                parent_ids=parent_ids,
                edge_evidence=edges,
                kind="report_paragraph",
            ))
        if final.get("content_sha256") and sha256_text(report_text) != final.get("content_sha256"):
            case_warnings.append("final report hash mismatch")

    for index, error in enumerate(trace.get("natural_errors") or []):
        event = error.get("raw_event") if isinstance(error, dict) else {}
        if isinstance(error, dict):
            text = error.get("text") or error.get("content") or (event or {}).get("content") or json.dumps(error, ensure_ascii=False)
        else:
            text = str(error)
        nodes.append(make_node(
            case_id=case_id,
            agent_name="system",
            step_type="other",
            text_raw=text,
            source_file=source_file,
            source_locator=event_locator(event, f"natural_errors[{index}]"),
            timestamp=(event or {}).get("timestamp"),
            position=event_position(event, request_line * 1000 + 900 + index),
            ordinal=900 + index,
            extra_flags=["error_stack"],
            kind="error",
        ))

    nodes.sort(key=lambda node: (node["_position"], node["_ordinal"], node["node_id"]))
    for order, node in enumerate(nodes):
        node["order"] = order
        node.pop("_position", None)
        node.pop("_ordinal", None)
    return nodes, case_warnings


def choose_pilot(cases: dict[str, list[dict[str, Any]]], inventory: dict[str, dict[str, Any]]) -> list[str]:
    def features(case_id: str) -> tuple[int, int, int, int, int, str]:
        nodes = cases[case_id]
        types = {node["step_type"] for node in nodes if node["text_clean"]}
        complete = all(kind in types for kind in ("query", "retrieval_observation", "outline", "report_paragraph"))
        row = inventory.get(case_id, {})
        explicit_edges = sum(
            item.get("evidence_type") == "explicit" for node in nodes for item in node["edge_evidence"]
        )
        quality_penalty = sum(bool(node["quality_flags"]) for node in nodes)
        text_chars = sum(len(node["text_raw"]) for node in nodes)
        stable_order = bool(row.get("agent_order"))
        return (int(complete), int(stable_order), explicit_edges, -quality_penalty, text_chars, case_id)

    complete_ids = [case_id for case_id in cases if features(case_id)[0]]
    ranked = sorted(complete_ids, key=features, reverse=True)
    buckets: dict[tuple[str, int], list[str]] = defaultdict(list)
    lengths = sorted(sum(len(n["text_raw"]) for n in cases[c]) for c in ranked)
    q1 = lengths[len(lengths) // 3] if lengths else 0
    q2 = lengths[(2 * len(lengths)) // 3] if lengths else 0
    for case_id in ranked:
        row = inventory.get(case_id, {})
        name = Path((row.get("source_log") or {}).get("absolute_path", "unknown")).name
        size = sum(len(n["text_raw"]) for n in cases[case_id])
        bucket = 0 if size <= q1 else 1 if size <= q2 else 2
        buckets[(name, bucket)].append(case_id)
    selected: list[str] = []
    keys = sorted(buckets)
    while len(selected) < 20 and any(buckets.values()):
        for key in keys:
            if buckets[key] and len(selected) < 20:
                selected.append(buckets[key].pop(0))
    return selected


def validate(nodes: list[dict[str, Any]], traces: dict[str, dict[str, Any]]) -> dict[str, Any]:
    ids = [node["node_id"] for node in nodes]
    id_set = set(ids)
    checks: dict[str, Any] = {
        "jsonl_rows_parseable": True,
        "duplicate_node_id_count": len(ids) - len(id_set),
        "empty_case_id_count": sum(not node["case_id"] for node in nodes),
        "unsortable_case_order_count": 0,
        "missing_parent_id_count": 0,
        "explicit_edge_without_evidence_count": 0,
        "raw_replay_failure_count": 0,
        "uniform_prefix_truncation_logic_present": False,
        "pure_numeric_evaluation_target_count": 0,
        "citation_candidate_node_count": 0,
    }
    by_case: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for node in nodes:
        by_case[node["case_id"]].append(node)
        checks["missing_parent_id_count"] += sum(parent not in id_set for parent in node["parent_ids"])
        for edge in node["edge_evidence"]:
            if edge.get("evidence_type") == "explicit" and not edge.get("evidence"):
                checks["explicit_edge_without_evidence_count"] += 1
        if "pure_numeric" in node["quality_flags"] and "not_evaluation_target" not in node["quality_flags"]:
            checks["pure_numeric_evaluation_target_count"] += 1
        if "citation" in node["step_type"] or "candidate" in node["step_type"]:
            checks["citation_candidate_node_count"] += 1
    for case_id, case_nodes in by_case.items():
        orders = [node["order"] for node in case_nodes]
        if orders != sorted(orders) or len(orders) != len(set(orders)):
            checks["unsortable_case_order_count"] += 1
        trace = traces[case_id]
        outline = trace.get("outline") or {}
        if outline.get("present"):
            exported = [n for n in case_nodes if n["step_type"] == "outline"]
            if len(exported) != 1 or exported[0]["text_raw"] != outline.get("full_output"):
                checks["raw_replay_failure_count"] += 1
        obs = trace.get("observations") or []
        exported_obs = [n["text_raw"] for n in case_nodes if n["step_type"] == "retrieval_observation" and n["text_raw"]]
        if exported_obs != [item.get("text", "") for item in obs]:
            checks["raw_replay_failure_count"] += 1
        final = trace.get("final_report") or {}
        if final.get("present"):
            text = final.get("text", "")
            for node in [n for n in case_nodes if n["step_type"] == "report_paragraph"]:
                if node["text_raw"] not in text:
                    checks["raw_replay_failure_count"] += 1
    checks["passed"] = all(
        value in (0, False, True)
        for key, value in checks.items()
        if key != "passed"
    ) and all(
        checks[key] == 0
        for key in checks
        if key.endswith("_count")
    ) and checks["jsonl_rows_parseable"] and not checks["uniform_prefix_truncation_logic_present"]
    return checks


def length_stats(nodes: list[dict[str, Any]]) -> dict[str, dict[str, float | int]]:
    grouped: dict[str, list[int]] = defaultdict(list)
    for node in nodes:
        grouped[node["step_type"]].append(len(node["text_raw"]))
    return {
        kind: {
            "count": len(values),
            "average_chars": round(sum(values) / len(values), 2),
            "min_chars": min(values),
            "max_chars": max(values),
        }
        for kind, values in sorted(grouped.items())
    }


def build(output_dir: Path = DEFAULT_OUTPUT) -> dict[str, Any]:
    started = datetime.now(timezone.utc)
    output_dir.mkdir(parents=True, exist_ok=True)
    audit_inventory = read_jsonl(INVENTORY_PATH)
    inventory_by_id = {row["run_id"]: row for row in audit_inventory}
    raw_files = sorted({row["source_log"]["absolute_path"] for row in audit_inventory})
    parser = load_audit_parser()
    all_nodes: list[dict[str, Any]] = []
    all_traces: dict[str, dict[str, Any]] = {}
    parse_success: list[dict[str, Any]] = []
    parse_failures: list[dict[str, Any]] = []
    case_warnings: dict[str, list[str]] = {}

    for raw_name in raw_files:
        raw_path = Path(raw_name)
        expected = [row for row in audit_inventory if row["source_log"]["absolute_path"] == raw_name]
        try:
            file_meta = dict(expected[0]["source_log"])
            grouped = list(parser.runs_from_file(raw_path))
            parsed_count = 0
            for events in grouped:
                _, trace = parser.parse_run(events, file_meta, True)
                case_id = str(trace.get("run_id") or "")
                nodes, warnings = trace_to_nodes(trace)
                actual_id = nodes[0]["case_id"]
                if actual_id in all_traces:
                    raise ValueError(f"duplicate case_id: {actual_id}")
                all_traces[actual_id] = trace
                all_nodes.extend(nodes)
                case_warnings[actual_id] = warnings
                parsed_count += 1
            if parsed_count != len(expected):
                raise ValueError(f"request count mismatch: parsed={parsed_count}, audited={len(expected)}")
            expected_sha = file_meta.get("sha256")
            actual_sha = sha256_file(raw_path)
            if expected_sha and actual_sha != expected_sha:
                raise ValueError(f"raw file SHA-256 changed: expected={expected_sha}, actual={actual_sha}")
            parse_success.append({
                "absolute_path": raw_name,
                "case_count": parsed_count,
                "sha256": actual_sha,
                "sha256_verified_against_audit_inventory": bool(expected_sha),
            })
        except Exception as exc:  # Continue other files and report the exact failure.
            parse_failures.append({"absolute_path": raw_name, "reason": f"{type(exc).__name__}: {exc}"})

    all_nodes.sort(key=lambda node: (node["case_id"], node["order"], node["node_id"]))
    cases: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for node in all_nodes:
        cases[node["case_id"]].append(node)
    pilot = choose_pilot(cases, inventory_by_id)
    checks = validate(all_nodes, all_traces)

    nodes_path = output_dir / "sp_nodes.jsonl"
    with nodes_path.open("w", encoding="utf-8", newline="\n") as handle:
        for node in all_nodes:
            handle.write(json.dumps(node, ensure_ascii=False, separators=(",", ":")) + "\n")

    step_counts = Counter(node["step_type"] for node in all_nodes)
    quality_counts = Counter(flag for node in all_nodes for flag in node["quality_flags"])
    edge_counts = Counter()
    for node in all_nodes:
        if node["edge_evidence"]:
            edge_counts.update(item["evidence_type"] for item in node["edge_evidence"])
        else:
            edge_counts["none"] += 1

    def case_has(case_nodes: list[dict[str, Any]], kind: str) -> bool:
        return any(node["step_type"] == kind and bool(node["text_clean"]) for node in case_nodes)

    complete_case_ids = [
        case_id for case_id, case_nodes in cases.items()
        if all(case_has(case_nodes, kind) for kind in ("query", "retrieval_observation", "outline", "report_paragraph"))
    ]
    finished = datetime.now(timezone.utc)
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "parser_version": PARSER_VERSION,
        "execution_time_utc": started.isoformat(),
        "execution_duration_seconds": round((finished - started).total_seconds(), 3),
        "raw_data_root": os.path.commonpath(raw_files) if raw_files else "",
        "raw_files": {
            "count": len(raw_files),
            "successfully_parsed_count": len(parse_success),
            "failed_count": len(parse_failures),
            "successes": parse_success,
            "failures": parse_failures,
        },
        "case_count": len(cases),
        "node_count": len(all_nodes),
        "step_type_counts": dict(sorted(step_counts.items())),
        "case_coverage": {
            "with_query": sum(case_has(nodes, "query") for nodes in cases.values()),
            "with_observation": sum(case_has(nodes, "retrieval_observation") for nodes in cases.values()),
            "with_outline": sum(case_has(nodes, "outline") for nodes in cases.values()),
            "with_report": sum(case_has(nodes, "report_paragraph") for nodes in cases.values()),
            "complete_query_observation_outline_report": len(complete_case_ids),
        },
        "edge_evidence_counts": {key: edge_counts.get(key, 0) for key in ("explicit", "inferred", "none")},
        "quality_flag_counts": dict(sorted(quality_counts.items())),
        "required_quality_counts": {
            "empty_text": quality_counts["empty_text"],
            "pure_numeric": quality_counts["pure_numeric"],
            "anomalously_short": quality_counts["anomalously_short"],
            "very_long_text": quality_counts["very_long_text"],
        },
        "node_length_stats": length_stats(all_nodes),
        "pilot_case_ids": pilot,
        "pilot_requested_count": 20,
        "pilot_actual_count": len(pilot),
        "pilot_shortfall": max(0, 20 - len(pilot)),
        "pilot_selection": "structural completeness, stable agent order, explicit-edge count, quality flags, then deterministic source-file/length-bucket round robin; no model or similarity score",
        "case_warnings": {key: value for key, value in sorted(case_warnings.items()) if value},
        "integrity_checks": checks,
        "reuse_provenance": [
            {"path": str(INVENTORY_PATH.resolve()), "sha256": sha256_file(INVENTORY_PATH), "role": "audited 253-request boundaries and metadata"},
            {"path": str(TRACE_PATH.resolve()), "sha256": sha256_file(TRACE_PATH), "role": "20-case field/provenance audit reference"},
            {"path": str(AUDIT_REPORT_PATH.resolve()), "sha256": sha256_file(AUDIT_REPORT_PATH), "role": "recoverability evidence-level definitions"},
            {"path": str(AUDIT_PYC.resolve()), "sha256": sha256_file(AUDIT_PYC), "role": "audited streaming parser implementation"},
            {"path": str(FROZEN20_DIR.resolve()), "role": "schema/provenance cross-check only; no citation edges imported"},
        ],
        "prohibited_transform_checks": {
            "semantic_chunking_used": False,
            "text_similarity_parent_inference_used": False,
            "citation_edges_imported": False,
            "fixed_prefix_truncation_used": False,
            "language_model_used": False,
            "gpu_used": False,
        },
        "output_files": [str(nodes_path.resolve()), str((output_dir / "manifest.json").resolve()), str((output_dir / "checksums.sha256").resolve())],
    }
    manifest_path = output_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    checksums_path = output_dir / "checksums.sha256"
    checksums_path.write_text(
        f"{sha256_file(nodes_path)}  sp_nodes.jsonl\n{sha256_file(manifest_path)}  manifest.json\n",
        encoding="ascii",
        newline="\n",
    )
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    manifest = build(args.output)
    print(json.dumps({
        "case_count": manifest["case_count"],
        "complete_case_count": manifest["case_coverage"]["complete_query_observation_outline_report"],
        "node_count": manifest["node_count"],
        "pilot_actual_count": manifest["pilot_actual_count"],
        "integrity_passed": manifest["integrity_checks"]["passed"],
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
