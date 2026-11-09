"""Exact character views of recorded text and JSON string values."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass

from source_path_v1.replay_rich import scan_fragments

_LITERAL = re.compile(r'"(?:\\.|[^"\\])*"', re.S)
_ESCAPE = re.compile(r'\\u[dD][89aAbB][0-9a-fA-F]{2}\\u[dD][c-fC-F][0-9a-fA-F]{2}|\\u[0-9a-fA-F]{4}|\\.|.', re.S)


@dataclass
class View:
    text: str
    start: int
    offsets: list[int] | None = None

    def span(self, left: int, right: int) -> tuple[int, int]:
        if self.offsets is None:
            return self.start + left, self.start + right
        return self.offsets[left], self.offsets[right]


def views(text: str, start: int = 0, structured: bool = False) -> list[View]:
    if not structured:
        return [View(text, start)]
    out, cursor = [], 0
    for match in _LITERAL.finditer(text):
        if text[match.end():].lstrip().startswith(":"):
            continue
        try:
            decoded = json.loads(match[0])
        except ValueError:
            continue
        units = list(_ESCAPE.finditer(match[0][1:-1]))
        if len(units) != len(decoded):
            continue
        left, right = match.start() + 1, match.end() - 1
        if cursor < left:
            out.append(View(text[cursor:left], start + cursor))
        offsets = [start + left] + [start + left + unit.end() for unit in units]
        prefix = re.match(r"\[PARTIAL result:[^\]]+\]\s*", decoded)
        if prefix:
            split = prefix.end()
            out.append(View(decoded[:split], offsets[0], offsets[:split + 1]))
            decoded, offsets = decoded[split:], offsets[split:]
        out.append(View(decoded, offsets[0], offsets))
        cursor = right
    if cursor < len(text):
        out.append(View(text[cursor:], start + cursor))
    return out


def fragments(view: View):
    pieces, _ = scan_fragments(view.text, min_chars=1, cap=len(view.text) + 1)
    for left, right, text in pieces:
        yield text, view.span(left, right), view.offsets[left:right + 1] if view.offsets is not None else None
