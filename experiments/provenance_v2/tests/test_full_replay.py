"""Regression coverage for full-call row reuse and branching span queries."""

import json
import tempfile
import unittest
from contextlib import ExitStack
from pathlib import Path

import numpy as np

from provenance_v2.full_batch import digest, write_json
from provenance_v2.full_forest import build_run
from provenance_v2.full_query import FullQuery, target_span
from provenance_v2.span_views import views


class FullReplayTest(unittest.TestCase):
    def test_exact_repeated_target_and_json_coordinates(self):
        with self.assertRaisesRegex(ValueError, "repeats"):
            target_span("same same", "same")
        self.assertEqual(target_span("same same", "same", 2), (5, 9))
        raw = json.dumps({"result": "first\nsecond 😀"})
        value = next(view for view in views(raw, structured=True) if view.text == "first\nsecond 😀")
        left, right = value.span(6, len(value.text))
        self.assertEqual(json.loads('"' + raw[left:right] + '"'), "second 😀")

    def test_three_call_branching_preserves_rows_and_roots(self):
        first = "Original date evidence states September."
        second = "Confirmed the month of September; this is a separate unused tail."
        selected = "Confirmed the month of September"
        alternate = "The independent location evidence is available."
        final = "The joint conclusion has two supporting branches.\nA different output target."
        raw_calls = [
            ([("tool", "The archive gives the September date.")], first),
            ([("assistant", first), ("tool", "A separate direct archive note supports the date.")], second),
            ([("tool", "The register identifies the original place.")], alternate),
            ([("assistant", selected), ("assistant", alternate), ("tool", "The original joint task provides a direct source.")], final),
        ]
        with tempfile.TemporaryDirectory() as work, ExitStack() as cleanup:
            root = Path(work)
            logs = root / "calls.jsonl"
            rows = []
            matrices = {}
            for index, (inputs, output) in enumerate(raw_calls):
                call_id = f"call{index:02d}"
                rows.append({"thread_id": "fixture", "request": {"messages": [{"role": role, "content": text} for role, text in inputs]},
                             "response": {"generations": [{"text": output, "tool_calls": []}]}})
                columns = [{"column": i, "message_index": i, "role": role, "section": "content",
                            "text": text, "match_text": text, "message_char_span": [0, len(text)],
                            "prompt_char_span": [0, len(text)], "token_span": [0, 1]}
                           for i, (role, text) in enumerate(inputs)]
                metadata = root / f"{call_id}.json"
                scores = root / f"{call_id}.npy"
                masses = np.full((len(output), len(columns)), 0.1, dtype=np.float32)
                if index == 1:
                    masses[len(selected):, 0] = 0.0
                if index == 3:
                    masses[final.index("A different"):, :2] = 0.0
                np.save(scores, masses, allow_pickle=False)
                write_json(metadata, {"output": output, "response_text_length": len(output),
                                      "columns": columns, "output_tokens": len(output),
                                      "output_offsets": [[i, i + 1] for i in range(len(output))],
                                      "prediction_rows": list(range(12, 12 + len(output)))})
                matrices[call_id] = {"metadata": metadata.name, "metadata_sha256": digest(metadata),
                                     "scores": scores.name, "scores_sha256": digest(scores)}
            logs.write_text("\n".join(json.dumps(row) for row in rows), encoding="utf-8")
            write_json(root / "manifest.json", {"user_id": None, "calls_sha256": digest(logs), "calls": matrices})
            forest = root / "forest.json"
            build_run(root, root, forest)
            engine = FullQuery(forest, root, top_k=3, depth=3)
            cleanup.callback(engine.matrices.clear)
            sentence = final.splitlines()[0]
            out = engine.walk("call03", target_span(final, sentence))
            root_paths = {tuple(s["call_id"] for s in p["steps"]): p for p in out["paths"] if p["stop"] == "material_input"}
            self.assertIn(("call03", "call01", "call00"), root_paths)
            self.assertIn(("call03", "call02"), root_paths)
            self.assertIn(("call03",), root_paths)
            self.assertEqual(root_paths[("call03", "call01", "call00")]["steps"][1]["row_slice"], [0, len(selected)])
            different = engine.walk("call03", target_span(final, "A different output target."))
            self.assertEqual(len(different["paths"]), 1)
            self.assertEqual(different["paths"][0]["steps"][0]["candidate"]["column"], 2)
            self.assertEqual(digest(root / "call03.npy"), matrices["call03"]["scores_sha256"])
            shared_rule = FullQuery(forest, root, top_k=1, depth=3,
                                    candidate_selector=lambda masses, eligible: eligible[-1:])
            cleanup.callback(shared_rule.matrices.clear)
            filtered = shared_rule.walk("call03", target_span(final, sentence))
            self.assertEqual(len(filtered["paths"]), 1)
            self.assertEqual(filtered["paths"][0]["steps"][0]["candidate"]["column"], 2)
