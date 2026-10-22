from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(slots=True)
class LogEvent:
    text: str
    start_line: int
    end_line: int
    timestamp: str | None
    truncated: bool = False
    multipart: tuple[int, int] | None = None
    stable_hash: str = ""


@dataclass(slots=True)
class FactStructRun:
    run_id: str
    query: str
    thread_id: str | None
    sources: dict[str, dict[str, Any]]
    final_report: str
    parser_warnings: list[str] = field(default_factory=list)
    raw_log_provenance: list[dict[str, Any]] = field(default_factory=list)
    raw_event_count: int = 0
    deduplicated_event_count: int = 0

    @property
    def completed(self) -> bool:
        return bool(self.query and self.sources and self.final_report)

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["original_query"] = result.pop("query")
        result["factstruct_source_memories"] = list(result.pop("sources").values())
        result["completed"] = self.completed
        return result

