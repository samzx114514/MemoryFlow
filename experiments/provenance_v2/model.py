"""Core data structures for the generic provenance pipeline."""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any


@dataclass
class Call:
    call_id: str
    task_id: str
    session_id: str | None
    index: int
    ts: float | None
    messages: list[dict[str, Any]] = field(default_factory=list)
    response_text: str = ""
    response_tool_calls: list[dict[str, Any]] = field(default_factory=list)
    finish_reason: str | None = None
    request_sha256: str | None = None
    response_sha256: str | None = None
    session_source: str = "unknown"  # thread_id | inferred_system_prefix | single_session | unknown

    @property
    def full_response(self) -> str:
        parts = [self.response_text]
        for tool in self.response_tool_calls:
            args = tool.get("args")
            if args is None:
                args = (tool.get("function") or {}).get("arguments")
            if args is not None:
                parts.append(args if isinstance(args, str) else str(args))
        return "\n".join(part for part in parts if part)

    def visible_messages(self) -> list[dict[str, Any]]:
        return [m for m in self.messages if m.get("role") != "system"]


@dataclass
class Unit:
    unit_id: str
    call_id: str
    kind: str  # assistant_text | tool_args | delivery_sentence
    text: str
    sha256: str | None = None
    char_span: tuple[int, int] | None = None
    artifact_id: str | None = None


@dataclass
class Candidate:
    candidate_id: str
    call_id: str
    message_index: int
    role: str
    text: str
    char_span: tuple[int, int] | None = None  # message-local span
    token_span: tuple[int, int] | None = None
    prompt_char_span: tuple[int, int] | None = None
    response_char_span: tuple[int, int] | None = None
    source: str | None = None
    unit_id: str | None = None  # set when the candidate text is an earlier assistant output


@dataclass
class Matrix:
    matrix_id: str
    call_id: str
    unit_id: str
    model: str
    layer: int
    head: int
    rows: int
    scores: list[tuple[str, float]]  # (candidate_id, mass) in matrix order
    source: str | None = None
    causal: bool = True


@dataclass
class Link:
    link_id: str
    from_id: str  # unit or call
    to_id: str  # unit or call or candidate
    kind: str  # generation | copy | version | prefix | unknown
    evidence: dict[str, Any] = field(default_factory=dict)
    score: float | None = None
    rank: int | None = None
    locality: str = "local"  # local | cross_call


@dataclass
class ProvenanceGraph:
    task_id: str
    calls: dict[str, Call] = field(default_factory=dict)
    units: dict[str, Unit] = field(default_factory=dict)
    candidates: dict[str, Candidate] = field(default_factory=dict)
    matrices: dict[str, Matrix] = field(default_factory=dict)
    links: list[Link] = field(default_factory=list)
    notes: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "calls": [asdict(c) for c in self.calls.values()],
            "units": [asdict(u) for u in self.units.values()],
            "candidates": [asdict(c) for c in self.candidates.values()],
            "matrices": [
                {**asdict(m), "scores": [[cid, score] for cid, score in m.scores]}
                for m in self.matrices.values()
            ],
            "links": [asdict(link) for link in self.links],
            "notes": self.notes,
        }


def text_sha(text: str) -> str:
    import hashlib

    return hashlib.sha256(text.encode("utf-8")).hexdigest()
