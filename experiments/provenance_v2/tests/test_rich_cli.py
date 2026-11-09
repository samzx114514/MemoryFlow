"""CLI test for rich candidates: assistant history included, exact spans, cross-matrix link."""

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


class RichCandidateTest(unittest.TestCase):
    def test_assistant_history_is_scored_and_linked(self):
        with tempfile.TemporaryDirectory() as tmp:
            run = pathlib.Path(tmp) / "run"
            run.mkdir()
            analysis = "1. Duplicate section numbering: two sections are numbered 6."
            final = "duplicate section numbering (structural)"
            calls = [
                {"request": {"messages": [msg("system", "s"), msg("user", "contract task"),
                                           msg("tool", "Contract text: section 6 appears twice.")]},
                 "response": {"generations": [{"text": analysis, "tool_calls": []}]}},
                {"request": {"messages": [msg("system", "s"), msg("user", "contract task"),
                                           msg("tool", "Contract text: section 6 appears twice."),
                                           msg("assistant", analysis), msg("tool", "written")]},
                 "response": {"generations": [{"text": final, "tool_calls": []}]}},
            ]
            (run / "calls.jsonl").write_text("\n".join(json.dumps(c, ensure_ascii=False) for c in calls) + "\n", encoding="utf-8")
            (run / "predictions.jsonl").write_text(json.dumps({"delivery": final}) + "\n", encoding="utf-8")
            call1 = calls[1]["request"]["messages"]
            analysis_content = call1[3]["content"]
            analysis_start = analysis_content.find("Duplicate section numbering")
            m1 = {"call": 1, "target": final, "model": "synthetic", "layer": 19, "head": 15, "rows": 4,
                  "candidates": [{"text": "Duplicate section numbering", "role": "assistant", "message_index": 3,
                                  "char_span": [analysis_start, analysis_start + len("Duplicate section numbering")],
                                  "score": 2.0}]}
            m0 = {"call": 0, "target": "Duplicate section numbering", "model": "synthetic", "layer": 19, "head": 15,
                  "rows": 3, "candidates": [{"text": "section 6 appears twice", "role": "tool", "message_index": 2,
                                             "char_span": [0, len("section 6 appears twice")], "score": 3.0}]}
            (pathlib.Path(tmp) / "m1.json").write_text(json.dumps(m1), encoding="utf-8")
            (pathlib.Path(tmp) / "m0.json").write_text(json.dumps(m0), encoding="utf-8")
            graph_path = pathlib.Path(tmp) / "graph.json"
            subprocess.run([sys.executable, str(CLI), "build", "--run", str(run),
                            "--matrices", str(pathlib.Path(tmp) / "m1.json"), str(pathlib.Path(tmp) / "m0.json"),
                            "--out", str(graph_path)], check=True, capture_output=True)
            graph = json.loads(graph_path.read_text(encoding="utf-8"))["graph"]
            assistant = [c for c in graph["candidates"] if c["role"] == "assistant"]
            self.assertTrue(assistant, "assistant history must be in the candidate set")
            target = next(u["unit_id"] for u in graph["units"] if u["kind"] == "matrix_target" and u["text"] == final)
            query_path = pathlib.Path(tmp) / "q.json"
            subprocess.run([sys.executable, str(CLI), "query", "--graph", str(graph_path), "--unit", target,
                            "--depth", "4", "--top-k", "3", "--out", str(query_path)], check=True, capture_output=True)
            result = json.loads(query_path.read_text(encoding="utf-8"))
            visited = [hop["unit"] for hop in result["hops"]]
            self.assertTrue(any(unit.startswith("call00#target") for unit in visited))
            first = result["hops"][0]["candidates"][0]
            self.assertEqual(first["role"], "assistant")
            self.assertTrue(first["transmission"], "assistant candidate must link to the upstream unit")


if __name__ == "__main__":
    unittest.main()
