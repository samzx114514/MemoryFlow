"""Compare compact graph aggregation with the original path enumerator."""
import json
import tempfile
import unittest
from collections import defaultdict
from contextlib import ExitStack
from pathlib import Path

import numpy as np

from provenance_v2.compact_query import CompactQuery
from provenance_v2.full_batch import digest, write_json
from provenance_v2.full_query import FullQuery


def fixture(root, plans, links):
    entries = {}
    for call, output, columns, scores in plans:
        for i, col in enumerate(columns):
            col.update(column=i, message_index=i, section="content", text=f"source {call}/{i}",
                       message_char_span=[0, 1], prompt_char_span=[0, 1])
            col.setdefault("token_span", [0, 1])
        np.save(root/f"{call}.npy", np.asarray(scores, dtype=np.float32))
        write_json(root/f"{call}.json", {"output": output, "output_tokens": len(output),
                   "output_offsets": [[i, i+1] for i in range(len(output))],
                   "prediction_rows": list(range(100, 100+len(output))), "columns": columns})
        entries[call] = {"metadata": f"{call}.json", "scores": f"{call}.npy",
                         "metadata_sha256": digest(root/f"{call}.json"), "scores_sha256": digest(root/f"{call}.npy")}
    write_json(root/"manifest.json", {"calls": entries})
    write_json(root/"forest.json", {"manifest_sha256": digest(root/"manifest.json"),
               "content_transfers": links, "tool_results": []})


def summed(result, root_key=lambda root: root["root_id"]):
    roots = {r["root_id"]: r for r in result["roots"]}
    totals = defaultdict(float)
    for route in result["paths"]:
        if route["stop"] == "material_input":
            totals[root_key(roots[route["root_id"]])] += route["path_score"]
    return dict(totals)


class CompactQueryTest(unittest.TestCase):
    def diamond(self, root, ambiguous=False):
        plans = [("c0", "ab", [{"role": "tool"}, {"role": "tool"}], [[.4, .3]]*2),
                 ("c1", "ab", [{"role": "assistant"}, {"role": "tool"}], [[.5, .2]]*2),
                 ("c2", "ab", [{"role": "assistant"}, {"role": "tool"}], [[.6, .1]]*2),
                 ("c3", "ab", [{"role": "assistant"}, {"role": "assistant"}], [[.7, .3]]*2)]
        links = [{"recipient_call": current, "column": col, "producer_call": earlier, "producer_span": [0, 2]}
                 for current, col, earlier in [("c1", 0, "c0"), ("c2", 0, "c0"), ("c3", 0, "c1"), ("c3", 1, "c2")]]
        if ambiguous:
            links.append({"recipient_call": "c3", "column": 0, "producer_call": "c2", "producer_span": [0, 2]})
        fixture(root, plans, links)

    def test_shared_subgraph_depth_and_alias_sums_match_enumeration(self):
        with tempfile.TemporaryDirectory() as work, ExitStack() as cleanup:
            root = Path(work)
            self.diamond(root)
            for depth in [1, 2, 3, 16]:
                old = FullQuery(root/"forest.json", root, 10, depth)
                new = CompactQuery(root/"forest.json", root, 10, depth)
                cleanup.callback(old.matrices.clear)
                cleanup.callback(new.matrices.clear)
                key = lambda r: "shared-material" if r["call_id"] == "c0" else r["root_id"]
                explicit = old.walk("c3", (0, 2))
                compact = new.walk("c3", (0, 2), root_key=key)
                self.assertEqual(compact["status"], "complete")
                self.assertEqual(compact["path_count"], len(explicit["paths"]))
                expected = summed(explicit, key)
                self.assertEqual(set(expected), set(compact["root_scores"]))
                for k in expected:
                    self.assertAlmostEqual(expected[k], compact["root_scores"][k], places=12)
                if depth == 16:
                    self.assertGreater(compact["stats"]["state_cache_hits"], 0)
                    self.assertEqual(compact["expanded_spans"], 4)

    def test_ambiguous_transfers_keep_each_original_weight(self):
        with tempfile.TemporaryDirectory() as work, ExitStack() as cleanup:
            root = Path(work)
            self.diamond(root, ambiguous=True)
            old = FullQuery(root/"forest.json", root, 10, 16)
            new = CompactQuery(root/"forest.json", root, 10, 16)
            cleanup.callback(old.matrices.clear)
            cleanup.callback(new.matrices.clear)
            explicit, compact = old.walk("c3", (0, 2)), new.walk("c3", (0, 2))
            self.assertEqual(compact["path_count"], len(explicit["paths"]))
            for k, value in summed(explicit).items():
                self.assertAlmostEqual(value, compact["root_scores"][k], places=12)

    def test_same_fragment_at_different_remaining_depths_is_not_conflated(self):
        with tempfile.TemporaryDirectory() as work, ExitStack() as cleanup:
            root = Path(work)
            self.diamond(root)
            old = FullQuery(root/"forest.json", root, 10, 2)
            new = CompactQuery(root/"forest.json", root, 10, 2)
            cleanup.callback(old.matrices.clear)
            cleanup.callback(new.matrices.clear)
            for engine in [old, new]:
                engine.transfers["c3", 1] = [{"producer_call": "c0", "producer_span": [0, 2]}]
            expected, actual = old.walk("c3", (0, 2)), new.walk("c3", (0, 2))
            self.assertEqual(actual["path_count"], len(expected["paths"]))
            for key, score in summed(expected).items():
                self.assertAlmostEqual(score, actual["root_scores"][key], places=12)

    def test_many_paths_remain_exact_without_path_list_explosion(self):
        with tempfile.TemporaryDirectory() as work, ExitStack() as cleanup:
            root = Path(work)
            plans = [("c00", "ab", [{"role": "tool"}], [[.4]]*2)]
            links = []
            for i in range(1, 16):
                call = f"c{i:02d}"
                plans.append((call, "ab", [{"role": "assistant"}]*2, [[.5, .25]]*2))
                links.extend({"recipient_call": call, "column": col, "producer_call": f"c{i-1:02d}",
                              "producer_span": [0, 2]} for col in [0, 1])
            # Do not share mutable column dictionaries inside the synthetic input.
            plans = [(c, o, [dict(col) for col in cols], scores) for c, o, cols, scores in plans]
            fixture(root, plans, links)
            engine = CompactQuery(root/"forest.json", root, 10, 16)
            cleanup.callback(engine.matrices.clear)
            result = engine.walk("c15", (0, 2))
            self.assertEqual(result["path_count"], 2**15)
            self.assertEqual(len(result["paths"]), 1)
            self.assertEqual(result["stats"]["local_reads"], 16)
            self.assertAlmostEqual(result["root_scores"]["c00:column0"], float(np.float32(.4))*.75**15, places=12)

    def test_prior_output_visibility_and_selector_are_unchanged(self):
        with tempfile.TemporaryDirectory() as work, ExitStack() as cleanup:
            root = Path(work)
            fixture(root, [("c0", "abc", [{"role": "tool"},
                    {"role": "assistant", "response_char_span": [0, 1], "token_span": [100, 101]}],
                    [[.4, .9], [.4, .5], [.4, .5]])], [])
            for span in [(0, 1), (1, 3)]:
                old = FullQuery(root/"forest.json", root, 5, 16)
                new = CompactQuery(root/"forest.json", root, 5, 16)
                cleanup.callback(old.matrices.clear)
                cleanup.callback(new.matrices.clear)
                explicit, compact = old.walk("c0", span), new.walk("c0", span)
                self.assertEqual(compact["path_count"], len(explicit["paths"]))
                for k, value in summed(explicit).items():
                    self.assertAlmostEqual(value, compact["root_scores"][k], places=12)
            select = lambda masses, eligible: eligible[-1:]
            old = FullQuery(root/"forest.json", root, 1, 16, select)
            new = CompactQuery(root/"forest.json", root, 1, 16, select)
            cleanup.callback(old.matrices.clear)
            cleanup.callback(new.matrices.clear)
            self.assertAlmostEqual(summed(old.walk("c0", (1, 3)))["c0:column0"],
                                   new.walk("c0", (1, 3))["root_scores"]["c0:column0"], places=12)

    def test_budget_or_noncausal_link_never_returns_partial_scores_as_complete(self):
        with tempfile.TemporaryDirectory() as work, ExitStack() as cleanup:
            root = Path(work)
            self.diamond(root)
            engine = CompactQuery(root/"forest.json", root, 10, 16)
            cleanup.callback(engine.matrices.clear)
            limited = engine.walk("c3", (0, 2), limits={"max_nodes": 1})
            self.assertEqual(limited["status"], "unfinished")
            self.assertEqual(limited["root_scores"], {})
            engine.transfers["c1", 0] = [{"producer_call": "c3", "producer_span": [0, 2]}]
            engine.local_cache.clear()
            cyclic = engine.walk("c3", (0, 2))
            self.assertEqual(cyclic["status"], "unfinished")
            self.assertIn("noncausal", cyclic["reason"])
