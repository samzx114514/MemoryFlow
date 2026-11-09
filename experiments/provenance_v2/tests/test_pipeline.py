"""Tests for the generic provenance pipeline (no GPU, synthetic fixtures)."""

from __future__ import annotations

import json
import pathlib
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

from provenance_v2 import from_synthetic, build_forest, ProvenanceQuery


def msg(role, content):
    return {"role": role, "content": content}


def cases():
    A = "Alpha finding: the cap room is 4.588 million dollars."
    B = "Beta step: because the room is 4.588 million, the offer is above it."
    C = "Gamma conclusion: the offer violates the room limit."
    calls = [
        {"id": "c0", "messages": [msg("user", "question one")], "response": A},
        {"id": "c1", "messages": [msg("user", "question one"), msg("assistant", A)], "response": B},
        {"id": "c2", "messages": [msg("user", "question one"), msg("assistant", A), msg("assistant", B)], "response": C},
    ]
    matrices = [
        {"call": "c1", "target": B, "candidates": [{"text": A, "score": 0.6}, {"text": "question one", "score": 0.1}]},
        {"call": "c2", "target": C, "candidates": [{"text": B, "score": 0.5}, {"text": A, "score": 0.2}]},
    ]
    return calls, matrices


class PipelineTests(unittest.TestCase):
    def test_copy_chain(self):
        calls, matrices = cases()
        graph = from_synthetic(calls, matrices)
        forest = build_forest(graph)
        self.assertEqual(forest.parents["c1"], ["c0"])
        self.assertEqual(forest.parents["c2"], ["c1"])
        unit = next(unit_id for unit_id, matrix in graph.matrices.items() if matrix.call_id == "c2")
        result = ProvenanceQuery(graph, forest).expand(unit)
        first = result.hops[0]
        self.assertTrue(any(c["text"].startswith("Beta step:") for c in first.candidates))
        candidate = next(c for c in first.candidates if c["text"].startswith("Beta step:"))
        self.assertTrue(candidate["transmission"])
        self.assertTrue(any(hop.unit_id.startswith("c1#target") for hop in result.hops))

    def test_direct_and_indirect(self):
        calls, matrices = cases()
        graph = from_synthetic(calls, matrices)
        # add a direct matrix on c2 pointing at A as well
        unit = next(unit_id for unit_id, matrix in graph.matrices.items() if matrix.call_id == "c2")
        graph.matrices[unit].scores.append(("c2:msg1", 0.9))
        query = ProvenanceQuery(graph, build_forest(graph))
        result = query.expand(unit)
        first = result.hops[0]
        alpha = next((c for c in first.candidates if c["text"].startswith("Alpha finding:")), None)
        self.assertIsNotNone(alpha)
        direct = [t for t in alpha["transmission"] if t["to"] == "c0#response"]
        self.assertTrue(direct)

    def test_branch_visibility(self):
        A = "Shared history sentence about the document."
        calls = [
            {"id": "root", "messages": [msg("user", "q")], "response": A},
            {"id": "b1", "messages": [msg("user", "q"), msg("assistant", A)], "response": "Branch one result."},
            {"id": "b2", "messages": [msg("user", "q"), msg("assistant", A)], "response": "Branch two result."},
        ]
        matrices = [{"call": "b1", "target": "Branch one result.", "candidates": [{"text": A, "score": 0.7}]}]
        graph = from_synthetic(calls, matrices)
        forest = build_forest(graph)
        self.assertEqual(forest.parents["b1"], ["root"])
        self.assertEqual(forest.parents["b2"], ["root"])
        result = ProvenanceQuery(graph, forest).expand("b1#target0")
        joined = " ".join(hop.unit_id for hop in result.hops)
        self.assertNotIn("b2", joined)

    def test_cycle_and_limit(self):
        A = "Cycle sentence one that is long enough."
        B = "Cycle sentence two that is long enough."
        calls = [
            {"id": "x", "messages": [msg("user", "q")], "response": A},
            {"id": "y", "messages": [msg("user", "q"), msg("assistant", A)], "response": B},
        ]
        matrices = [
            {"call": "y", "target": B, "candidates": [{"text": A, "score": 0.5}]},
            {"call": "x", "target": A, "candidates": [{"text": "q", "score": 0.5}]},
        ]
        graph = from_synthetic(calls, matrices)
        from provenance_v2.model import Link
        y_unit = next(unit_id for unit_id, matrix in graph.matrices.items() if matrix.call_id == "y")
        graph.links.append(Link(link_id="fake-cycle", from_id="x:msg0", to_id=y_unit, kind="copy", evidence={"fixture": "artificial forward edge"}))
        unit = next(unit_id for unit_id, matrix in graph.matrices.items() if matrix.call_id == "y")
        result = ProvenanceQuery(graph, build_forest(graph), max_depth=3).expand(unit)
        self.assertTrue(any(hop.stop == "cycle" for hop in result.hops))
        limited = ProvenanceQuery(graph, build_forest(graph), max_depth=1).expand(unit)
        self.assertLessEqual(len(limited.hops), 2)

    def test_trace_ingest(self):
        with tempfile.TemporaryDirectory() as tmp:
            run = pathlib.Path(tmp)
            calls = [
                {"request": {"messages": [msg("system", "sys"), msg("user", "q")]},
                 "response": {"generations": [{"text": "First answer sentence.", "tool_calls": []}]}},
                {"request": {"messages": [msg("system", "sys"), msg("user", "q"), msg("assistant", "First answer sentence.")]},
                 "response": {"generations": [{"text": "Second answer sentence.", "tool_calls": []}]}},
            ]
            (run / "calls.jsonl").write_text("\n".join(json.dumps(c) for c in calls) + "\n", encoding="utf-8")
            (run / "predictions.jsonl").write_text(json.dumps({"delivery": "Final conclusion sentence."}) + "\n", encoding="utf-8")
            from provenance_v2.ingest import from_trace_run
            graph = from_trace_run(run)
            self.assertEqual(len(graph.calls), 2)
            self.assertIn("delivery#s00", graph.units)
            forest = build_forest(graph)
            self.assertEqual(forest.parents["call01"], ["call00"])


if __name__ == "__main__":
    unittest.main()
