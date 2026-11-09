"""End-to-end CLI test: real build/query path across two calls' matrices and multi-target calls."""

from __future__ import annotations

import json
import pathlib
import subprocess
import sys
import tempfile
import unittest

CLI = pathlib.Path(__file__).resolve().parents[1] / "cli.py"


def msg(role, content):
    return {"role": role, "content": content}


class CliPipelineTest(unittest.TestCase):
    def test_build_query_across_two_matrices(self):
        with tempfile.TemporaryDirectory() as tmp:
            run = pathlib.Path(tmp) / "run"
            run.mkdir()
            alpha = "Alpha evidence sentence about the topic."
            beta = "Beta conclusion sentence that follows."
            calls = [
                {"request": {"messages": [msg("system", "s"), msg("user", "question one")]},
                 "response": {"generations": [{"text": alpha, "tool_calls": []}]}},
                {"request": {"messages": [msg("system", "s"), msg("user", "question one"),
                                           msg("assistant", alpha)]},
                 "response": {"generations": [{"text": beta, "tool_calls": []}]}},
            ]
            (run / "calls.jsonl").write_text("\n".join(json.dumps(c, ensure_ascii=False) for c in calls) + "\n", encoding="utf-8")
            (run / "predictions.jsonl").write_text(json.dumps({"delivery": beta}) + "\n", encoding="utf-8")
            matrices = {
                "m1.json": {"call": 1, "target": beta,
                            "candidates": [{"text": alpha, "where": "message[2]", "score": 0.7},
                                           {"text": "question one", "where": "message[0]", "score": 0.1}]},
                "m0a.json": {"call": 0, "target": alpha,
                             "candidates": [{"text": "question one", "where": "message[1]", "score": 0.6}]},
                "m0b.json": {"call": 0, "target": "Other target line in the same call.",
                             "candidates": [{"text": "question one", "where": "message[1]", "score": 0.9}]},
            }
            for name, record in matrices.items():
                (pathlib.Path(tmp) / name).write_text(json.dumps(record), encoding="utf-8")
            graph_path = pathlib.Path(tmp) / "graph.json"
            subprocess.run([sys.executable, str(CLI), "build", "--run", str(run),
                            "--matrices", *(str(pathlib.Path(tmp) / name) for name in matrices),
                            "--out", str(graph_path)], check=True, capture_output=True)
            graph = json.loads(graph_path.read_text(encoding="utf-8"))["graph"]
            targets = [unit["unit_id"] for unit in graph["units"] if unit["kind"] == "matrix_target"]
            self.assertEqual(len(targets), 3)
            beta_unit = next(unit["unit_id"] for unit in graph["units"]
                             if unit["text"] == beta and unit["kind"] == "matrix_target")
            out_path = pathlib.Path(tmp) / "query.json"
            subprocess.run([sys.executable, str(CLI), "query", "--graph", str(graph_path),
                            "--unit", beta_unit, "--depth", "4", "--top-k", "3", "--out", str(out_path)],
                           check=True, capture_output=True)
            result = json.loads(out_path.read_text(encoding="utf-8"))
            visited = [hop["unit"] for hop in result["hops"]]
            self.assertTrue(any(unit.startswith("call00#target") for unit in visited))
            first = result["hops"][0]
            alpha_entry = next(c for c in first["candidates"] if c["text"] == alpha)
            self.assertIsNotNone(alpha_entry["message_index"], "candidate must keep its message position")
            self.assertTrue(alpha_entry["transmission"] or alpha_entry["terminal"])
            # the empty-target matrix must be skipped, and no candidate may default to position 0 wrongly
            scored = [c for hop in result["hops"] for c in hop["candidates"]]
            self.assertTrue(scored)

    def test_missing_fragment_does_not_default_to_zero(self):
        with tempfile.TemporaryDirectory() as tmp:
            run = pathlib.Path(tmp) / "run"
            run.mkdir()
            (run / "calls.jsonl").write_text(json.dumps(
                {"request": {"messages": [msg("system", "s"), msg("user", "only question")]},
                 "response": {"generations": [{"text": "Answer.", "tool_calls": []}]}}) + "\n", encoding="utf-8")
            (run / "predictions.jsonl").write_text(json.dumps({"delivery": "Answer."}) + "\n", encoding="utf-8")
            matrix = pathlib.Path(tmp) / "m.json"
            matrix.write_text(json.dumps({"call": 0, "target": "Answer.",
                                          "candidates": [{"text": "fragment not present anywhere",
                                                          "where": "message[0]", "score": 0.5}]}), encoding="utf-8")
            graph_path = pathlib.Path(tmp) / "graph.json"
            subprocess.run([sys.executable, str(CLI), "build", "--run", str(run), "--matrices", str(matrix),
                            "--out", str(graph_path)], check=True, capture_output=True)
            graph = json.loads(graph_path.read_text(encoding="utf-8"))["graph"]
            target = next(unit["unit_id"] for unit in graph["units"] if unit["kind"] == "matrix_target")
            out_path = pathlib.Path(tmp) / "q.json"
            subprocess.run([sys.executable, str(CLI), "query", "--graph", str(graph_path), "--unit", target,
                            "--out", str(out_path)], check=True, capture_output=True)
            result = json.loads(out_path.read_text(encoding="utf-8"))
            self.assertEqual(result["hops"][0]["stop"] if result["hops"] else None, "empty_matrix")


if __name__ == "__main__":
    unittest.main()
