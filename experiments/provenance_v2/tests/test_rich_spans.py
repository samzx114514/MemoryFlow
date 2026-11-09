"""Minimal regression: duplicate same-text positions and current-output prefix identity."""

from __future__ import annotations

import json
import pathlib
import subprocess
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from source_path_v1.replay_rich import scan_fragments  # noqa: E402

CLI = ROOT / "provenance_v2/cli.py"


class RichSpanTest(unittest.TestCase):
    def test_duplicate_same_text_keeps_distinct_positions(self):
        content = "Same sentence here.\nOther line.\nSame sentence here."
        fragments, _ = scan_fragments(content)
        same = [item for item in fragments if item[2] == "Same sentence here."]
        self.assertEqual(len(same), 2)
        self.assertNotEqual(same[0][0], same[1][0])

    def test_current_output_prefix_is_not_a_history_link(self):
        with tempfile.TemporaryDirectory() as tmp:
            run = pathlib.Path(tmp) / "run"
            run.mkdir()
            calls = [
                {"request": {"messages": [{"role": "system", "content": "s"},
                                           {"role": "user", "content": "q"}]},
                 "response": {"generations": [{"text": "Earlier answer text.", "tool_calls": []}]}},
                {"request": {"messages": [{"role": "system", "content": "s"},
                                           {"role": "user", "content": "q"},
                                           {"role": "assistant", "content": "Earlier answer text."}]},
                 "response": {"generations": [{"text": "Now the prefix.\nThen target sentence.", "tool_calls": []}]}},
            ]
            (run / "calls.jsonl").write_text("\n".join(json.dumps(c) for c in calls) + "\n", encoding="utf-8")
            (run / "predictions.jsonl").write_text(json.dumps({"delivery": "Then target sentence."}) + "\n", encoding="utf-8")
            matrix = {"call": 1, "target": "Then target sentence.", "model": "synthetic", "layer": 19, "head": 15,
                      "rows": 3, "target_char_span": [19, 38],
                      "candidates": [{"text": "Now the prefix.", "class": "prior_output_current", "role": "assistant",
                                      "message_index": None, "message_char_span": [0, 15],
                                      "prompt_char_span": None, "token_span": [10, 12],
                                      "response_char_span": [0, 15], "source": "current_output_prefix", "score": 1.0}]}
            path = pathlib.Path(tmp) / "m.json"
            path.write_text(json.dumps(matrix), encoding="utf-8")
            graph_path = pathlib.Path(tmp) / "g.json"
            subprocess.run([sys.executable, str(CLI), "build", "--run", str(run), "--matrices", str(path),
                            "--out", str(graph_path)], check=True, capture_output=True)
            graph = json.loads(graph_path.read_text(encoding="utf-8"))["graph"]
            prefix = [c for c in graph["candidates"] if c.get("message_index") is None]
            self.assertTrue(prefix, "current prefix candidate must be kept")
            cid = prefix[0]["candidate_id"]
            links = [link for link in graph["links"] if link["from_id"] == cid]
            self.assertEqual(links, [], "current prefix must not link to a history unit")


if __name__ == "__main__":
    unittest.main()
