"""Log-driven analysis queue for task-level timing (G3, CPU-only prototype).

This module separates three quantities that must not be conflated:
generation time, source-analysis time, and the answer-ready time.  It consumes
already-completed call records; E2 is therefore a replay simulation, not a
claim that the original generation was actually overlapped online.

Schema (JSON):
{
  "task_id": str, "attempt": str, "started_at": float, "finished_at": float,
  "calls": [{
    "call_id": str, "started_at": float, "completed_at": float,
    "analysis_seconds": float, "analysis_units": int,
    "status": "completed"|"failed", "unit_scope": [str], "candidates": int
  }]
}
"""

from __future__ import annotations

import argparse
import json
import pathlib
from dataclasses import dataclass, field


@dataclass
class CallRecord:
    call_id: str
    started_at: float
    completed_at: float
    analysis_seconds: float
    analysis_units: int = 1
    status: str = "completed"
    unit_scope: list[str] = field(default_factory=list)
    candidates: int = 0


@dataclass
class TaskRecord:
    task_id: str
    attempt: str
    started_at: float
    finished_at: float
    calls: list[CallRecord]


def load_task(path: str | pathlib.Path) -> TaskRecord:
    raw = json.loads(pathlib.Path(path).read_text(encoding="utf-8"))
    calls = [CallRecord(**{
        "call_id": item["call_id"],
        "started_at": float(item["started_at"]),
        "completed_at": float(item["completed_at"]),
        "analysis_seconds": float(item.get("analysis_seconds", 0.0)),
        "analysis_units": int(item.get("analysis_units", 1)),
        "status": item.get("status", "completed"),
        "unit_scope": list(item.get("unit_scope") or []),
        "candidates": int(item.get("candidates", 0)),
    }) for item in raw.get("calls", [])]
    return TaskRecord(
        task_id=str(raw["task_id"]),
        attempt=str(raw.get("attempt", "")),
        started_at=float(raw["started_at"]),
        finished_at=float(raw["finished_at"]),
        calls=calls,
    )


def _eligible(task: TaskRecord) -> list[CallRecord]:
    return sorted(
        (call for call in task.calls if call.status == "completed" and call.analysis_seconds > 0),
        key=lambda call: (call.completed_at, call.call_id),
    )


def simulate(task: TaskRecord, mode: str) -> dict:
    if mode not in {"E0", "E1", "E2"}:
        raise ValueError(f"unknown mode: {mode}")
    if task.finished_at < task.started_at:
        raise ValueError("finished_at precedes started_at")
    generation_seconds = task.finished_at - task.started_at
    jobs = _eligible(task)
    analyzed_units = sum(call.analysis_units for call in jobs)
    excluded = [
        {"call_id": call.call_id, "reason": call.status if call.status != "completed" else "no analysis scope"}
        for call in task.calls if call not in jobs
    ]
    base = {
        "task_id": task.task_id,
        "attempt": task.attempt,
        "mode": mode,
        "generation_start": task.started_at,
        "generation_finished": task.finished_at,
        "generation_seconds": generation_seconds,
        "analysis_candidates": len(jobs),
        "jobs": len(jobs),
        "analysis_units": analyzed_units,
        "excluded": excluded,
        "replay_only": True,
    }
    if mode == "E0":
        base.update({
            "jobs": 0,
            "analysis_units": 0,
            "source_ready": task.finished_at,
            "answer_ready": task.finished_at,
            "answer_wall_seconds": generation_seconds,
            "analysis_span_seconds": 0.0,
            "queue_wait_seconds": 0.0,
            "max_backlog": 0,
            "job_timeline": [],
        })
        return base

    if mode == "E1":
        worker_free = task.finished_at
        max_backlog = len(jobs)
        queue_wait = 0.0
        timeline = []
        for call in jobs:
            start = worker_free
            end = start + call.analysis_seconds
            queue_wait += start - task.finished_at
            timeline.append({
                "call_id": call.call_id,
                "arrived": task.finished_at,
                "started": start,
                "ended": end,
                "analysis_seconds": call.analysis_seconds,
                "analysis_units": call.analysis_units,
            })
            worker_free = end
    elif mode == "E2":
        # Job arrivals are the recorded call completions; the worker is a
        # single CPU-side analyzer.  Generation continues independently.
        worker_free = task.started_at
        queue_wait = 0.0
        timeline = []
        for call in jobs:
            arrival = call.completed_at
            start = max(worker_free, arrival)
            end = start + call.analysis_seconds
            queue_wait += start - arrival
            timeline.append({
                "call_id": call.call_id,
                "arrived": arrival,
                "started": start,
                "ended": end,
                "analysis_seconds": call.analysis_seconds,
                "analysis_units": call.analysis_units,
            })
            worker_free = end
        # Backlog at an arrival includes the arriving job plus every earlier
        # job whose analysis has not yet ended.
        max_backlog = 0
        for index, job in enumerate(timeline):
            active = sum(1 for earlier in timeline[:index] if earlier["ended"] > job["arrived"])
            max_backlog = max(max_backlog, active + 1)

    analysis_span = (
        worker_free - timeline[0]["started"] if timeline else 0.0
    )
    source_ready = max(task.finished_at, worker_free)
    base.update({
        "source_ready": source_ready,
        "answer_ready": source_ready,
        "answer_wall_seconds": source_ready - task.started_at,
        "analysis_span_seconds": max(0.0, analysis_span),
        "queue_wait_seconds": queue_wait,
        "max_backlog": max_backlog,
        "job_timeline": timeline,
    })
    return base


def from_calls_jsonl(path: str | pathlib.Path, analysis_seconds: float, task_id: str = "v6-calls") -> TaskRecord:
    """Adapter for the saved DCCv2 call log; analysis cost is an explicit input.

    The log has completion timestamps and per-call elapsed times, not an
    analysis cost.  Supplying `analysis_seconds` makes the timing model
    reproducible but does not turn it into a measured analyzer result.
    """
    rows = [json.loads(line) for line in pathlib.Path(path).read_text(encoding="utf-8").splitlines() if line.strip()]
    calls = []
    for index, row in enumerate(rows):
        completed = float(row["ts"])
        elapsed = float(row.get("elapsed") or 0.0)
        calls.append(CallRecord(
            call_id=f"call{index:02d}",
            started_at=completed - elapsed,
            completed_at=completed,
            analysis_seconds=float(analysis_seconds),
            analysis_units=1,
            status="completed",
            unit_scope=[f"call{index:02d}:output"],
            candidates=0,
        ))
    if not calls:
        raise ValueError("empty calls log")
    return TaskRecord(task_id=task_id, attempt="v6", started_at=min(c.started_at for c in calls),
                      finished_at=max(c.completed_at for c in calls), calls=calls)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--events", help="task JSON in the schema above")
    parser.add_argument("--calls")
    parser.add_argument("--analysis-seconds", type=float, default=0.25)
    parser.add_argument("--out")
    args = parser.parse_args()
    if args.events:
        task = load_task(args.events)
    elif args.calls:
        task = from_calls_jsonl(args.calls, args.analysis_seconds)
    else:
        raise SystemExit("need --events or --calls")
    result = {
        "schema": "memoryflow.task_timing.v1",
        "task": {"task_id": task.task_id, "attempt": task.attempt},
        "analysis_seconds_assumption": None if args.events else args.analysis_seconds,
        "modes": {mode: simulate(task, mode) for mode in ("E0", "E1", "E2")},
    }
    text = json.dumps(result, ensure_ascii=False, indent=2)
    if args.out:
        pathlib.Path(args.out).write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
