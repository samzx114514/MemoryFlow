from __future__ import annotations

import ast
import hashlib
import re
from pathlib import Path
from typing import Any, Iterable, Iterator

from .log_events import MULTIPART_RE, iter_log_events
from .schema import FactStructRun, LogEvent


REQUEST_RE = re.compile(r"request param details:")
GRAPH_RE = re.compile(r"graph_format=['\"]([^'\"]+)['\"]")
THREAD_RE = re.compile(r"['\"]?thread_id['\"]?\s*[:=]\s*['\"]([^'\"]+)['\"]")
QUERY_RE = re.compile(r"ChatMessage\(role=['\"]user['\"],\s*content=")
REFERENCE_MARKERS = ("before reference_map:", "before ref_map:")


def _extract_quoted_literal(text: str, start: int) -> tuple[str | None, int]:
    while start < len(text) and text[start].isspace():
        start += 1
    if start >= len(text) or text[start] not in "'\"":
        return None, start
    quote = text[start]
    cursor = start + 1
    escaped = False
    while cursor < len(text):
        char = text[cursor]
        if escaped:
            escaped = False
        elif char == "\\":
            escaped = True
        elif char == quote:
            literal = text[start : cursor + 1]
            try:
                value = ast.literal_eval(literal)
                return str(value), cursor + 1
            except (SyntaxError, ValueError):
                return None, cursor + 1
        cursor += 1
    return None, cursor


def _extract_balanced_dict(text: str, start: int) -> str | None:
    brace = text.find("{", start)
    if brace < 0:
        return None
    depth = 0
    quote: str | None = None
    escaped = False
    for cursor in range(brace, len(text)):
        char = text[cursor]
        if quote:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == quote:
                quote = None
            continue
        if char in "'\"":
            quote = char
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return text[brace : cursor + 1]
    return None


def parse_reference_map(text: str) -> tuple[dict[str, Any], list[str]]:
    marker_pos = -1
    marker = ""
    for candidate in REFERENCE_MARKERS:
        position = text.find(candidate)
        if position >= 0:
            marker_pos, marker = position, candidate
            break
    if marker_pos < 0:
        return {}, ["reference_map_marker_missing"]
    literal = _extract_balanced_dict(text, marker_pos + len(marker))
    if literal is None:
        return {}, ["reference_map_truncated_or_unbalanced"]
    try:
        parsed = ast.literal_eval(literal)
    except (SyntaxError, ValueError) as exc:
        return {}, [f"reference_map_literal_parse_failed:{type(exc).__name__}"]
    if not isinstance(parsed, dict):
        return {}, ["reference_map_not_dict"]
    return {str(key): value for key, value in parsed.items() if isinstance(value, dict)}, []


def _clean_content(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    value = re.sub(r"【链接\s*\d+】", "", value)
    return re.sub(r"\s+", " ", value).strip()


def _normalize_sources(source_map: dict[str, Any]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for citation_id, raw in source_map.items():
        observation = raw.get("observation") if isinstance(raw.get("observation"), dict) else None
        points = observation.get("points", []) if observation else []
        if not isinstance(points, list):
            points = [str(points)]
        result[str(citation_id)] = {
            "citation_id": str(citation_id),
            "title": str(raw.get("title") or "").strip(),
            "URL": str(raw.get("url") or raw.get("URL") or "").strip(),
            "observation": ({
                "topic": str(observation.get("topic") or "").strip(),
                "points": [str(point).strip() for point in points if str(point).strip()],
            } if observation else None),
            "cleaned_source_content": _clean_content(raw.get("content") or raw.get("text") or ""),
        }
    return result


def _query_from_request(text: str) -> str:
    match = QUERY_RE.search(text)
    if not match:
        return ""
    value, _ = _extract_quoted_literal(text, match.end())
    return value or ""


def _final_report_from_text(text: str) -> str:
    positions = [match.end() for match in re.finditer(r"['\"]final_report['\"]\s*:\s*", text)]
    for start in reversed(positions):
        value, _ = _extract_quoted_literal(text, start)
        if value:
            return value
    return ""


def _multipart_payload(event: LogEvent) -> str:
    match = MULTIPART_RE.search(event.text)
    return event.text[match.end() :] if match else event.text


class _RunBuilder:
    def __init__(self, event: LogEvent, path: Path) -> None:
        self.path = path.resolve()
        self.query = _query_from_request(event.text)
        self.thread_id: str | None = None
        self.sources: dict[str, dict[str, Any]] = {}
        self.final_report = ""
        self.warnings: list[str] = []
        self.raw_count = 0
        self.unique_hashes: set[str] = set()
        self.start_line = event.start_line
        self.end_line = event.end_line
        self.request_timestamp = event.timestamp
        self.pending_parts: list[str] = []
        self.pending_total = 0
        self.pending_next = 0
        self.consume(event)

    def _process_text(self, text: str) -> None:
        thread_ids = THREAD_RE.findall(text)
        for thread_id in thread_ids:
            if thread_id not in {"__default__", "default", ""}:
                self.thread_id = self.thread_id or thread_id
        if any(marker in text for marker in REFERENCE_MARKERS):
            source_map, warnings = parse_reference_map(text)
            if source_map:
                self.sources = _normalize_sources(source_map)
            self.warnings.extend(warnings)
        report = _final_report_from_text(text)
        if report:
            self.final_report = report
        if "| ERROR" in text or " | ERROR " in text:
            self.warnings.append(f"operational_error_event:{hashlib.sha256(text.encode('utf-8')).hexdigest()[:16]}")

    def _flush_pending(self, incomplete: bool) -> None:
        if not self.pending_parts:
            return
        if incomplete:
            self.warnings.append(f"multipart_incomplete:{self.pending_next - 1}/{self.pending_total}")
        self._process_text("".join(self.pending_parts))
        self.pending_parts = []
        self.pending_total = 0
        self.pending_next = 0

    def consume(self, event: LogEvent) -> None:
        self.raw_count += 1
        self.unique_hashes.add(event.stable_hash)
        self.end_line = event.end_line
        if event.truncated and not event.multipart:
            self.warnings.append(f"truncated_event_line:{event.start_line}")
        if event.multipart:
            part, total = event.multipart
            if part == 1:
                self._flush_pending(incomplete=True)
                self.pending_parts = [_multipart_payload(event)]
                self.pending_total = total
                self.pending_next = 2
                if total == 1:
                    self._flush_pending(incomplete=False)
            elif self.pending_parts and total == self.pending_total and part == self.pending_next:
                self.pending_parts.append(_multipart_payload(event))
                self.pending_next += 1
                if part == total:
                    self._flush_pending(incomplete=False)
            else:
                self.warnings.append(f"multipart_orphan:{part}/{total}:line_{event.start_line}")
            return
        if self.pending_parts:
            self._flush_pending(incomplete=True)
        self._process_text(event.text)

    def finish(self) -> FactStructRun:
        self._flush_pending(incomplete=True)
        normalized_query = " ".join(self.query.split())
        if self.thread_id:
            run_id = self.thread_id
        else:
            run_id = hashlib.sha256(f"{normalized_query}\n{self.final_report}".encode("utf-8")).hexdigest()
        if not self.query:
            self.warnings.append("query_missing")
        if not self.sources:
            self.warnings.append("source_map_missing")
        if not self.final_report:
            self.warnings.append("final_report_missing")
        return FactStructRun(
            run_id=run_id,
            query=self.query,
            thread_id=self.thread_id,
            sources=self.sources,
            final_report=self.final_report,
            parser_warnings=list(dict.fromkeys(self.warnings)),
            raw_log_provenance=[{
                "absolute_path": str(self.path),
                "request_timestamp": self.request_timestamp,
                "start_line": self.start_line,
                "end_line": self.end_line,
            }],
            raw_event_count=self.raw_count,
            deduplicated_event_count=len(self.unique_hashes),
        )


def parse_factstruct_files(paths: Iterable[str | Path]) -> Iterator[FactStructRun]:
    for raw_path in paths:
        path = Path(raw_path)
        builder: _RunBuilder | None = None
        for event in iter_log_events(path):
            if REQUEST_RE.search(event.text):
                if builder is not None:
                    yield builder.finish()
                graph_match = GRAPH_RE.search(event.text)
                builder = _RunBuilder(event, path) if graph_match and graph_match.group(1).lower() == "factstruct" else None
            elif builder is not None:
                builder.consume(event)
        if builder is not None:
            yield builder.finish()
