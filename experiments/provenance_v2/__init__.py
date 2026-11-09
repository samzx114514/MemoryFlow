"""Generic cross-call provenance pipeline (v1).

Data model (JSON-serialisable):
- calls: one model call each (request messages, response text/tool calls).
- units: analyzable output units (assistant text, tool-call arguments, delivery sentences).
- candidates: spans of the call's own visible request that a matrix scores.
- matrices: local source scores for one unit over its candidates.
- links: transmission edges (same content produced earlier) and generation edges (matrix scores).

The pipeline is provider-agnostic: ingest adapters produce the same structures, and the query
engine never looks at task-specific text.
"""

from .model import (
    Call,
    Candidate,
    Matrix,
    Unit,
    Link,
    ProvenanceGraph,
)
from .ingest import from_trace_run, from_synthetic
from .forest import build_forest
from .query import ProvenanceQuery

__all__ = [
    "Call",
    "Candidate",
    "Matrix",
    "Unit",
    "Link",
    "ProvenanceGraph",
    "from_trace_run",
    "from_synthetic",
    "build_forest",
    "ProvenanceQuery",
]
