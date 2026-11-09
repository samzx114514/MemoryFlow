"""Deterministic per-hop query over the provenance graph (fixed rules, explicit stops)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .forest import Forest, build_forest
from .model import ProvenanceGraph

TRANSMISSION_KINDS = {"copy", "exact", "prefix", "embedded"}


@dataclass
class Hop:
    unit_id: str
    call_id: str
    matrix_id: str | None
    candidates: list[dict[str, Any]]
    stop: str | None = None
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {"unit": self.unit_id, "call": self.call_id, "matrix": self.matrix_id,
                "candidates": self.candidates, "stop": self.stop, "notes": self.notes}


@dataclass
class Path:
    hops: list[Hop] = field(default_factory=list)
    stop_reason: str | None = None
    visited: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {"hops": [hop.to_dict() for hop in self.hops], "stop_reason": self.stop_reason,
                "visited": self.visited}


class ProvenanceQuery:
    def __init__(self, graph: ProvenanceGraph, forest: Forest | None = None, top_k: int = 5,
                 max_depth: int = 6):
        self.graph = graph
        self.forest = forest or build_forest(graph)
        self.top_k = top_k
        self.max_depth = max_depth

    def _outgoing(self, unit_id: str) -> list:
        links = [link for link in self.graph.links
                 if link.from_id == unit_id and link.kind in TRANSMISSION_KINDS]
        preferred = [link for link in links if link.evidence.get("preferred")]
        return preferred or links

    def _candidate_links(self, candidate_id: str) -> list:
        return [link for link in self.graph.links
                if link.from_id == candidate_id and link.kind in TRANSMISSION_KINDS]

    def expand(self, unit_id: str, max_depth: int | None = None) -> Path:
        limit = self.max_depth if max_depth is None else max_depth
        path = Path()
        stack: list[tuple[str, int, frozenset[str]]] = [(unit_id, 0, frozenset())]
        seen: set[str] = set()
        while stack:
            current, depth, branch = stack.pop()
            if current in branch:
                path.hops.append(Hop(unit_id=current, call_id=self._call_of(current), matrix_id=None,
                                     candidates=[], stop="cycle"))
                continue
            matrix = self.graph.matrices.get(current)
            if matrix is None:
                outgoing = self._outgoing(current)
                if not outgoing:
                    path.hops.append(Hop(unit_id=current, call_id=self._call_of(current), matrix_id=None,
                                         candidates=[], stop="no_matrix"))
                    path.stop_reason = path.stop_reason or "no_matrix"
                    continue
                path.hops.append(Hop(unit_id=current, call_id=self._call_of(current), matrix_id=None,
                                     candidates=[], stop=None,
                                     notes=["transmission only"]))
                if depth + 1 > limit:
                    path.stop_reason = "depth_limit"
                    continue
                if len(outgoing) > 1:
                    path.hops[-1].notes.append(f"multiple_producers:{len(outgoing)}")
                for link in outgoing:
                    stack.append((link.to_id, depth + 1, branch | {current}))
                continue
            if current in seen:
                path.hops.append(Hop(unit_id=current, call_id=self._call_of(current), matrix_id=matrix.matrix_id,
                                     candidates=[], stop="revisit"))
                continue
            seen.add(current)
            path.visited.append(current)
            ranked = sorted(matrix.scores, key=lambda item: -item[1])[: self.top_k]
            candidates = []
            for rank, (candidate_id, score) in enumerate(ranked, start=1):
                candidate = self.graph.candidates.get(candidate_id)
                links = self._candidate_links(candidate_id)
                entry = {
                    "candidate_id": candidate_id,
                    "text": (candidate.text[:300] if candidate else ""),
                    "message_index": candidate.message_index if candidate else None,
                    "role": candidate.role if candidate else None,
                    "score": round(score, 6), "rank": rank,
                    "transmission": [{"kind": link.kind, "to": link.to_id,
                                      "preferred": bool(link.evidence.get("preferred")),
                                      "evidence": link.evidence} for link in links],
                    "terminal": None if links else ("material_input" if candidate and candidate.role in {"user", "tool"} else "no_upstream_record"),
                    "source": "matrix",
                }
                candidates.append(entry)
                for link in links:
                    if depth + 1 <= limit:
                        stack.append((link.to_id, depth + 1, branch | {current}))
                    else:
                        path.stop_reason = path.stop_reason or "depth_limit"
            path.hops.append(Hop(unit_id=current, call_id=matrix.call_id, matrix_id=matrix.matrix_id,
                                 candidates=candidates, stop=None if ranked else "empty_matrix"))
            if not ranked:
                path.stop_reason = path.stop_reason or "empty_matrix"
        return path

    def _call_of(self, unit_id: str) -> str:
        unit = self.graph.units.get(unit_id)
        return unit.call_id if unit else ""

    def expand_to_json(self, unit_id: str, max_depth: int | None = None) -> dict[str, Any]:
        return self.expand(unit_id, max_depth).to_dict()
