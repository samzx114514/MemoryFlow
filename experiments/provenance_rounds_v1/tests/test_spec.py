"""Structure tests for the controlled two-round sample (no model, no GPU).

Run: python -m unittest discover -s experiments/provenance_rounds_v1/tests -p test_*.py
"""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
PACKAGE = HERE.parent
ROOT = PACKAGE.parents[1]
sys.path.insert(0, str(PACKAGE))
sys.path.insert(0, str(ROOT / "experiments"))

import core  # noqa: E402

SUBSET = ROOT / "artifacts/raw/genmem_batch10_v3/subset"
RECIPE = PACKAGE / "recipes/case_02_selected_03.json"


@unittest.skipUnless(SUBSET.exists(), "extracted batch10 subset not available on this machine")
class SpecTest(unittest.TestCase):
    def test_build_and_invariants(self) -> None:
        recipe = core.read_json(RECIPE)
        spec = core.build_spec(SUBSET, recipe)
        self.assertEqual(spec["source"]["target_id"], recipe["target_id"])
        self.assertEqual(len(spec["rounds"]), 2)
        self.assertEqual(spec["evidence"]["A"][0]["text"], "Secret Symphony is the fifth studio album by British singer-songwriter Katie Melua")
        self.assertEqual(spec["evidence"]["B"][0]["text"], "produced in collaboration with longtime musical partner Mike Batt")
        check = spec["checks"]["round2_without_evidence_a"]
        self.assertTrue(check["passed"])
        self.assertEqual(check["max_shared_shingles"], 0)
        self.assertLess(check["max_lcs_chars"], core.LCS_LIMIT)
        r1_units = {item["unit_id"] for item in spec["rounds"][0]["materials"]}
        r2_units = {item["unit_id"] for item in spec["rounds"][1]["materials"]}
        self.assertNotIn(spec["evidence"]["A"][0]["unit_id"], r2_units)
        self.assertIn(spec["evidence"]["A"][0]["unit_id"], r1_units)
        self.assertIn(spec["evidence"]["B"][0]["unit_id"], r2_units)
        self.assertNotIn(spec["evidence"]["B"][0]["unit_id"], r1_units)
        self.assertEqual(spec["checks"]["merged_raw_units"], sorted(r1_units | r2_units))
        self.assertIn("Materials:", spec["rounds"][0]["prompt"])
        self.assertIn("[[ROUND1_ANSWER]]", spec["rounds"][1]["prompt_template"])

    def test_rebuild_is_byte_stable(self) -> None:
        recipe = core.read_json(RECIPE)
        first = core.build_spec(SUBSET, recipe)
        second = core.build_spec(SUBSET, recipe)
        self.assertEqual(first["spec_sha256"], second["spec_sha256"])


class EquivalenceCheckTest(unittest.TestCase):
    def test_copy_is_rejected(self) -> None:
        evidence = ["Secret Symphony is the fifth studio album by British singer-songwriter Katie Melua"]
        materials = ["Secret Symphony is the fifth studio album by British singer-songwriter Katie Melua, and was released on 5 March 2012."]
        result = core.evidence_equivalence(evidence, materials)
        self.assertFalse(result["passed"])
        self.assertTrue(result["exact_containment_hits"])

    def test_paraphrase_with_shared_phrase_passes(self) -> None:
        evidence = ["Secret Symphony is the fifth studio album by British singer-songwriter Katie Melua"]
        materials = ["The album was produced in collaboration with longtime musical partner Mike Batt."]
        result = core.evidence_equivalence(evidence, materials)
        self.assertTrue(result["passed"])


@unittest.skipUnless(SUBSET.exists(), "extracted batch10 subset not available on this machine")
class AnalysisTest(unittest.TestCase):
    def test_chain_ranks_and_found(self) -> None:
        import analyze

        recipe = core.read_json(RECIPE)
        spec = core.build_spec(SUBSET, recipe)
        frozen = json.loads(json.dumps(spec))
        frozen["rounds"][0]["answer"] = "Katie Melua's fifth studio album is Secret Symphony."
        frozen["rounds"][1]["answer"] = "Secret Symphony is Katie Melua's fifth studio album, produced by Mike Batt."
        frozen["frozen_sha256"] = core.sha256_text(
            core.canonical({k: v for k, v in frozen.items() if k != "frozen_sha256"})
        )
        r1 = frozen["rounds"][0]["materials"]
        r2 = frozen["rounds"][1]["materials"]
        A = frozen["evidence"]["A"][0]["unit_id"]
        B = frozen["evidence"]["B"][0]["unit_id"]

        def make_matrix(target, items, special):
            rows = []
            for index, item in enumerate(items):
                score = special.get(item.get("unit_id"), 0.01 / (index + 2))
                rows.append({"id": item.get("unit_id"), "text": item.get("text"), "score": score,
                             "share": 0.0, "rank": 0})
            rows.sort(key=lambda row: -row["score"])
            for rank, row in enumerate(rows, start=1):
                row["rank"] = rank
            return {"target": target, "candidates": rows}

        m1 = make_matrix(frozen["rounds"][0]["answer"], r1, {A: 0.9})
        m2 = make_matrix(
            frozen["rounds"][1]["answer"],
            [{"unit_id": "conclusion:r1", "text": frozen["rounds"][0]["answer"]}] + list(r2),
            {"conclusion:r1": 0.95, B: 0.7},
        )
        merged, seen = [], set()
        for item in r1 + r2:
            if item["unit_id"] not in seen:
                seen.add(item["unit_id"])
                merged.append(item)
        flat = make_matrix(frozen["rounds"][1]["answer"], merged, {B: 0.8, A: 0.12})
        scores = {"matrices": {"m1": m1, "m2": m2, "mflat": flat}}

        graph = analyze.build_graph(frozen, scores)
        self.assertGreaterEqual(len(graph.links), 1)
        units = graph.notes["candidate_units"]
        self.assertIn("conclusion:r1", units.values())
        from provenance_v2 import ProvenanceQuery

        path = ProvenanceQuery(graph, top_k=5, max_depth=4).expand("call_r2#target1")
        self.assertEqual(path.hops[0].unit_id, "call_r2#target1")
        self.assertEqual(path.hops[1].unit_id, "call_r1#target0")
        hop1 = {units.get(entry["candidate_id"]): entry for entry in path.hops[0].candidates}
        hop2 = {units.get(entry["candidate_id"]): entry for entry in path.hops[1].candidates}
        self.assertEqual(hop1["conclusion:r1"]["rank"], 1)
        self.assertEqual(hop1[B]["rank"], 2)
        self.assertEqual(hop2[A]["rank"], 1)


if __name__ == "__main__":
    unittest.main()
