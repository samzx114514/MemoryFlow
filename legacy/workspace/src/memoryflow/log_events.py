from __future__ import annotations

import codecs
import hashlib
import re
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Iterator

from .schema import LogEvent


EVENT_START_RE = re.compile(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d{3}) \|")
MULTIPART_RE = re.compile(r"llm_content\|part_(\d+)/(\d+)\|")
ADDRESS_RE = re.compile(r"0x[0-9a-fA-F]+")
UUID_RE = re.compile(r"\b[0-9a-fA-F]{8}-[0-9a-fA-F-]{27,}\b")


def detect_encoding(path: str | Path) -> str:
    with Path(path).open("rb") as handle:
        prefix = handle.read(4)
    if prefix.startswith(codecs.BOM_UTF8):
        return "utf-8-sig"
    if prefix.startswith(codecs.BOM_UTF16_LE):
        return "utf-16-le"
    if prefix.startswith(codecs.BOM_UTF16_BE):
        return "utf-16-be"
    return "utf-8"


def stable_event_hash(text: str) -> str:
    normalized = EVENT_START_RE.sub("<timestamp> |", text, count=1)
    normalized = ADDRESS_RE.sub("0x<addr>", normalized)
    normalized = UUID_RE.sub("<uuid>", normalized)
    return hashlib.sha256(normalized.strip().encode("utf-8")).hexdigest()


def _make_event(lines: list[str], start_line: int, end_line: int, truncated: bool) -> LogEvent:
    text = "\n".join(lines)
    match = EVENT_START_RE.match(lines[0]) if lines else None
    multipart_match = MULTIPART_RE.search(text)
    multipart = None
    if multipart_match:
        multipart = (int(multipart_match.group(1)), int(multipart_match.group(2)))
        if multipart[0] < multipart[1] and end_line == start_line:
            # A single first-part event at EOF is provably incomplete. Normal
            # multipart events are later corrected by the parser's assembler.
            truncated = truncated or multipart[0] == 1
    return LogEvent(
        text=text,
        start_line=start_line,
        end_line=end_line,
        timestamp=match.group(1) if match else None,
        truncated=truncated,
        multipart=multipart,
        stable_hash=stable_event_hash(text),
    )


def iter_log_events(path: str | Path) -> Iterator[LogEvent]:
    """Yield timestamp-delimited events while keeping only one event in memory."""
    current: list[str] = []
    start_line = 0
    current_is_preamble = False
    encoding = detect_encoding(path)
    with Path(path).open("r", encoding=encoding, errors="replace", newline="") as handle:
        for line_number, raw_line in enumerate(handle, 1):
            line = raw_line.rstrip("\r\n")
            is_start = bool(EVENT_START_RE.match(line))
            if is_start:
                if current:
                    yield _make_event(current, start_line, line_number - 1, current_is_preamble)
                current = [line]
                start_line = line_number
                current_is_preamble = False
            elif current:
                current.append(line)
            else:
                current = [line]
                start_line = line_number
                current_is_preamble = True
        if current:
            event = _make_event(current, start_line, line_number, current_is_preamble)
            if event.multipart and event.multipart[0] < event.multipart[1]:
                event = replace(event, truncated=True)
            yield event


def deduplicate_events(events: Iterable[LogEvent]) -> list[LogEvent]:
    seen: set[str] = set()
    result: list[LogEvent] = []
    for event in events:
        if event.stable_hash not in seen:
            seen.add(event.stable_hash)
            result.append(event)
    return result


def inventory_file(path: str | Path, source_root: str | Path, category: str) -> dict[str, object]:
    path = Path(path).resolve()
    source_root = Path(source_root).resolve()
    digest = hashlib.sha256()
    line_count = 0
    size = 0
    last_byte = b""
    decoder = codecs.getincrementaldecoder("utf-8")("strict")
    valid_utf8 = True
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            size += len(chunk)
            digest.update(chunk)
            line_count += chunk.count(b"\n")
            last_byte = chunk[-1:]
            if valid_utf8:
                try:
                    decoder.decode(chunk, final=False)
                except UnicodeDecodeError:
                    valid_utf8 = False
    if size and last_byte != b"\n":
        line_count += 1
    if valid_utf8:
        try:
            decoder.decode(b"", final=True)
        except UnicodeDecodeError:
            valid_utf8 = False
    stat = path.stat()
    return {
        "absolute_path": str(path),
        "relative_path_in_source_folder": str(path.relative_to(source_root)),
        "category": category,
        "size_bytes": size,
        "modified_time": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
        "sha256": digest.hexdigest(),
        "line_count": line_count,
        "encoding": "utf-8" if valid_utf8 else "unknown/binary",
    }

