"""CPU tests for the G3 log-driven analysis queue."""

from __future__ import annotations

import pathlib
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from analysis_queue import CallRecord, TaskRecord, from_calls_jsonl, simulate  # noqa: E402


def task(calls: list[CallRecord], finish: float = 10.0) -> TaskRecord:
    return TaskRecord(task_id="t", attempt="a1", started_at=0.0, finished_at=finish, calls=calls)


class QueueTest(unittest.TestCase):
    def test_e0_has_no_analysis(self) -> None:
        result = simulate(task([CallRecord("c1", 1, 2, 2.0)]), "E0")
        self.assertEqual(result["answer_ready"], 10.0)
        self.assertEqual(result["jobs"], 0)
        self.assertEqual(result["max_backlog"], 0)

    def test_e1_waits_for_post_task_analysis(self) -> None:
        result = simulate(task([
            CallRecord("c1", 1, 2, 2.0),
            CallRecord("c2", 3, 4, 2.0),
        ]), "E1")
        self.assertEqual(result["answer_ready"], 14.0)
        self.assertEqual(result["queue_wait_seconds"], 2.0)
        self.assertEqual(result["max_backlog"], 2)
        self.assertEqual([job["started"] for job in result["job_timeline"]], [10.0, 12.0])

    def test_e1_excludes_failed_calls(self) -> None:
        result = simulate(task([
            CallRecord("ok", 1, 2, 2.0),
            CallRecord("bad", 2, 3, 2.0, status="failed"),
        ]), "E1")
        self.assertEqual(result["jobs"], 1)
        self.assertEqual(result["excluded"], [{"call_id": "bad", "reason": "failed"}])
        self.assertEqual(result["answer_ready"], 12.0)

    def test_e2_overlaps_generation_and_analysis(self) -> None:
        result = simulate(task([
            CallRecord("c1", 0.5, 2.0, 2.0),
            CallRecord("c2", 3.0, 8.0, 2.0),
        ]), "E2")
        self.assertEqual(result["answer_ready"], 10.0)
        self.assertEqual(result["queue_wait_seconds"], 0.0)
        self.assertEqual(result["max_backlog"], 1)
        self.assertEqual(result["job_timeline"][0]["started"], 2.0)

    def test_e2_reports_real_queue_delay(self) -> None:
        result = simulate(task([
            CallRecord("c1", 1.0, 9.0, 1.5),
            CallRecord("c2", 2.0, 9.2, 1.5),
        ]), "E2")
        self.assertEqual(result["answer_ready"], 12.0)
        self.assertEqual(result["max_backlog"], 2)
        self.assertEqual(result["job_timeline"][1]["started"], 10.5)

    def test_calls_adapter_keeps_recorded_completion_times(self) -> None:
        rows = [
            {"ts": 100.0, "elapsed": 4.0},
            {"ts": 110.0, "elapsed": 2.0},
        ]
        handle, name = tempfile.mkstemp(suffix=".jsonl")
        path = pathlib.Path(name)
        try:
            with __import__("os").fdopen(handle, "w", encoding="utf-8") as stream:
                stream.write("\n".join(__import__("json").dumps(row) for row in rows) + "\n")
            task_record = from_calls_jsonl(path, analysis_seconds=0.5)
            self.assertEqual(task_record.started_at, 96.0)
            self.assertEqual(task_record.finished_at, 110.0)
            self.assertEqual([call.completed_at for call in task_record.calls], [100.0, 110.0])
        finally:
            path.unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
