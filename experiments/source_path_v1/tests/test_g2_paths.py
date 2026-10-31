"""CPU-only regressions for G2 query, forest, and last-input comparison."""

from __future__ import annotations

import json
import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import build_forest  # noqa: E402
import compare_views  # noqa: E402
import query  # noqa: E402


def _row(system: str, messages: list[dict], finish: str = "stop") -> dict:
    return {
        "request": {"messages": [{"role": "system", "content": system}, *messages]},
        "response": {"generations": [{"generation_info": {"finish_reason": finish}, "text": "", "tool_calls": []}]},
    }


class AgentClassificationTest(unittest.TestCase):
    def test_subagent_role_wins_over_later_central_mention(self) -> None:
        system = (
            "You are the StackPlanner perception subagent running inside DeerFlow 2.0.\n"
            "The CentralAgent may delegate tasks to you."
        )
        self.assertEqual(build_forest.agent_of(system), "perception")

    def test_central_and_memory_recaller_are_distinct(self) -> None:
        self.assertEqual(build_forest.agent_of("You are the StackPlanner 2.0 CentralAgent.\n..."), "central")
        self.assertEqual(build_forest.agent_of("You are memory_recaller, a read-only ..."), "memory_recaller")

    def test_unknown_is_not_silently_central(self) -> None:
        self.assertEqual(build_forest.agent_of("You are a generic helper."), "other")


class ForestTest(unittest.TestCase):
    def test_current_call_cannot_parent_a_future_call(self) -> None:
        rows = [
            _row("You are the StackPlanner 2.0 CentralAgent.", [{"role": "user", "content": "a"}]),
            _row("You are the StackPlanner 2.0 CentralAgent.", [{"role": "user", "content": "a"}]),
        ]
        forest = build_forest.build(rows)
        self.assertIsNone(forest["calls"]["call00"]["parent"])
        self.assertIsNone(forest["calls"]["call01"]["parent"])
        self.assertEqual(forest["roots"]["central"], ["call00", "call01"])

    def test_same_role_prefix_builds_parent_and_branch(self) -> None:
        rows = [
            _row("You are the StackPlanner 2.0 CentralAgent.", [{"role": "user", "content": "a"}]),
            _row("You are the StackPlanner 2.0 CentralAgent.", [{"role": "user", "content": "a"}, {"role": "assistant", "content": "b"}]),
            _row("You are the StackPlanner 2.0 CentralAgent.", [{"role": "user", "content": "a"}, {"role": "assistant", "content": "b"}, {"role": "tool", "content": "c"}]),
            _row("You are the StackPlanner 2.0 CentralAgent.", [{"role": "user", "content": "a"}, {"role": "assistant", "content": "b"}, {"role": "tool", "content": "d"}]),
        ]
        forest = build_forest.build(rows)
        self.assertEqual(forest["calls"]["call01"]["parent"], "call00")
        self.assertEqual(forest["calls"]["call02"]["parent"], "call01")
        self.assertEqual(forest["calls"]["call03"]["parent"], "call01")
        self.assertEqual(forest["branches"], {"call01": ["call02", "call03"]})

    def test_subagent_roots_are_separate(self) -> None:
        rows = [
            _row("You are the StackPlanner 2.0 CentralAgent.", [{"role": "user", "content": "a"}]),
            _row("You are the StackPlanner perception subagent running inside DeerFlow 2.0.", [{"role": "user", "content": "a"}]),
        ]
        forest = build_forest.build(rows)
        self.assertEqual(forest["roots"]["central"], ["call00"])
        self.assertEqual(forest["roots"]["perception"], ["call01"])


class QueryTest(unittest.TestCase):
    def test_estimate_edges_are_followed_to_upstream(self) -> None:
        data = {
            "task": {"id": "synthetic", "source": "test", "attempt": "v1"},
            "calls": [],
            "units": [
                {"unit_id": "report", "kind": "judgment", "text": "report"},
                {"unit_id": "summary", "kind": "summary", "text": "summary"},
                {"unit_id": "chunk", "kind": "source", "text": "source chunk"},
            ],
            "edges": [
                {"from": "summary", "to": "report", "kind": "estimate", "score": 0.643686},
                {"from": "chunk", "to": "summary", "kind": "estimate", "score": 0.756921},
            ],
            "gaps": [],
            "input_occurrences": [],
        }
        lines = query.trace(data, "report", depth=4)
        text = "\n".join(lines)
        self.assertIn("score=0.6437", text)
        self.assertIn("summary", text)
        self.assertIn("score=0.7569", text)
        self.assertIn("source chunk", text)

    def test_cycle_is_stopped_without_suppressing_other_branch(self) -> None:
        data = {
            "task": {"id": "synthetic", "source": "test", "attempt": "v1"},
            "calls": [],
            "units": [
                {"unit_id": "a", "kind": "judgment", "text": "a"},
                {"unit_id": "b", "kind": "summary", "text": "b"},
            ],
            "edges": [
                {"from": "b", "to": "a", "kind": "estimate", "score": 0.5},
                {"from": "a", "to": "b", "kind": "estimate", "score": 0.4},
            ],
            "gaps": [],
            "input_occurrences": [],
        }
        text = "\n".join(query.trace(data, "a", depth=5))
        self.assertIn("cycle stopped", text)

    def test_actual_cuad_path_reaches_summary_upstream(self) -> None:
        path = ROOT / "out/path_cuad.json"
        if not path.exists():
            self.skipTest("CUAD path artifact not present")
        data = json.loads(path.read_text(encoding="utf-8"))
        text = "\n".join(query.trace(data, "report_span_0", depth=4, max_paths=80))
        self.assertIn("summary_final", text)
        self.assertIn("score=0.6437", text)
        self.assertIn("score=0.7569", text)
        self.assertIn("2593:3850", text)


class CompareViewsTest(unittest.TestCase):
    def test_last_call_counts_summary_and_source(self) -> None:
        data = {
            "units": [
                {"unit_id": "report", "kind": "judgment", "text": "report"},
                {"unit_id": "summary", "kind": "summary", "text": "summary"},
                {"unit_id": "chunk", "kind": "source", "text": "source chunk"},
            ],
            "calls": [{"call_id": "writer", "agent": "reporter", "recorded": True}],
            "edges": [
                {"from": "writer", "to": "report", "kind": "recorded_generation"},
                {"from": "chunk", "to": "writer", "kind": "history"},
                {"from": "summary", "to": "report", "kind": "estimate", "score": 0.6},
            ],
            "input_occurrences": [
                {"unit": "summary", "call": "writer"},
                {"unit": "chunk", "call": "writer"},
                {"unit": "report", "call": "writer"},
            ],
            "gaps": [],
        }
        lines = compare_views.compare(data, judgment="report")
        text = "\n".join(lines)
        self.assertIn("last-call-only sees: 2 units", text)
        self.assertIn("summary", text)
        self.assertIn("source chunk", text)


if __name__ == "__main__":
    unittest.main()
