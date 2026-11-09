"""Context forest: session-scoped inheritance, content transfer, branches, ambiguity."""

from __future__ import annotations

from dataclasses import dataclass, field

from .model import ProvenanceGraph, text_sha


@dataclass
class Forest:
    parents: dict[str, list[str]] = field(default_factory=dict)      # context parents (same session)
    children: dict[str, list[str]] = field(default_factory=dict)
    roots: list[str] = field(default_factory=list)
    ambiguous: dict[str, int] = field(default_factory=dict)
    sessions: dict[str, str] = field(default_factory=dict)
    transfers: list[dict] = field(default_factory=list)               # cross-session content transfers
    evidence: dict[str, dict] = field(default_factory=dict)

    def parent_of(self, call_id: str) -> str | None:
        parents = self.parents.get(call_id) or []
        return parents[0] if len(parents) == 1 else None


def build_forest(graph: ProvenanceGraph) -> Forest:
    """Parent = the earlier same-session call that produced the last assistant message visible
    in the request. Cross-session matches are recorded as transfers, never as parents."""
    forest = Forest()
    ordered = sorted(graph.calls.values(), key=lambda c: c.index)
    for call in ordered:
        session = call.session_id or f"session_unknown_{call.call_id}"
        forest.sessions[call.call_id] = session
        last_assistant = None
        for message in call.messages:
            if message.get("role") == "assistant" and str(message.get("content") or "").strip():
                last_assistant = str(message.get("content")).strip()
        producers: list[str] = []
        if last_assistant and len(last_assistant) >= 20:
            for earlier in ordered:
                if earlier.index >= call.index:
                    break
                if last_assistant in earlier.full_response:
                    producers.append(earlier.call_id)
        context_parents, transfers = [], []
        for producer in producers:
            if forest.sessions.get(producer) == session:
                context_parents.append(producer)
            else:
                transfers.append({"from": producer, "to": call.call_id, "kind": "content_transfer",
                                  "evidence": {"last_assistant_sha": text_sha(last_assistant),
                                               "producer_session": forest.sessions.get(producer)}})
        forest.transfers.extend(transfers)
        if len(context_parents) == 1:
            forest.parents[call.call_id] = context_parents
            forest.children.setdefault(context_parents[0], []).append(call.call_id)
        elif len(context_parents) > 1:
            forest.parents[call.call_id] = context_parents
            forest.ambiguous[call.call_id] = len(context_parents)
            for parent in context_parents:
                forest.children.setdefault(parent, []).append(call.call_id)
        else:
            forest.roots.append(call.call_id)
        if last_assistant:
            forest.evidence[call.call_id] = {"last_assistant_sha": text_sha(last_assistant),
                                             "producers": producers,
                                             "context_parents": context_parents,
                                             "transfers": transfers}
    return forest
