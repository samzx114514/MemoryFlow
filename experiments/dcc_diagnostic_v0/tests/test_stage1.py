import copy
import hashlib
import json
import unittest
from pathlib import Path

from experiments.dcc_diagnostic_v0 import core


ROOT = Path(__file__).resolve().parents[1]


def rows(name):
    return [json.loads(line) for line in (ROOT / "data" / name).read_text(encoding="utf-8").splitlines() if line]


class LogicTests(unittest.TestCase):
    def test_three_valued_logic_all_pairs(self):
        values = ("TRUE", "FALSE", "UNKNOWN")
        expected_and = (("TRUE", "FALSE", "UNKNOWN"), ("FALSE", "FALSE", "FALSE"), ("UNKNOWN", "FALSE", "UNKNOWN"))
        expected_or = (("TRUE", "TRUE", "TRUE"), ("TRUE", "FALSE", "UNKNOWN"), ("TRUE", "UNKNOWN", "UNKNOWN"))
        for i, a in enumerate(values):
            for j, b in enumerate(values):
                self.assertEqual(core.tri_and(a, b), expected_and[i][j])
                self.assertEqual(core.tri_or(a, b), expected_or[i][j])
        self.assertEqual([core.tri_not(v) for v in values], ["FALSE", "TRUE", "UNKNOWN"])

    def test_all_obligation_state_pairs(self):
        expected = {
            "FALSE": ["NOT_APPLICABLE"] * 3,
            "TRUE": ["COMPLIANT", "VIOLATION", "INSUFFICIENT_EVIDENCE"],
            "UNKNOWN": ["INSUFFICIENT_EVIDENCE"] * 3,
        }
        for applicable, outcomes in expected.items():
            for satisfied, outcome in zip(("TRUE", "FALSE", "UNKNOWN"), outcomes):
                self.assertEqual(core.decide_obligation(applicable, satisfied), outcome)

    def test_known_valid_alternative_wins_over_unknown(self):
        self.assertEqual(core.tri_or("TRUE", "UNKNOWN"), "TRUE")
        self.assertEqual(core.decide_obligation("TRUE", core.tri_or("TRUE", "UNKNOWN")), "COMPLIANT")


class DatasetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.public = rows("calibration_public.jsonl")
        cls.gold = rows("calibration_gold.jsonl")
        cls.assistance = rows("calibration_assistance.jsonl")
        cls.by_gold = {g["case_id"]: g for g in cls.gold}
        cls.by_assist = {a["case_id"]: a for a in cls.assistance}

    def test_eight_cases_and_deterministic_gold(self):
        self.assertEqual(len(self.public), 8)
        self.assertEqual(len(self.by_gold), 8)
        self.assertEqual(len(self.by_assist), 8)
        families = {}
        for public in self.public:
            gold, assist = self.by_gold[public["case_id"]], self.by_assist[public["case_id"]]
            self.assertEqual(core.validate_case(public, gold, assist), [])
            self.assertGreaterEqual(len(gold["objects"]), 4)
            self.assertEqual(gold["review"]["independent_human_status"], "NOT_REVIEWED")
            families.setdefault(gold["family_id"], []).append((public, gold))
        self.assertEqual({k: len(v) for k, v in families.items()}, {"T1": 4, "T2": 4})
        for cases in families.values():
            focal_states = {next(d["state"] for d in gold["decisions"] if d["object_id"] == gold["focal_object_id"]) for _, gold in cases}
            self.assertEqual(focal_states, set(core.STATES))

    def test_span_out_of_bounds_rejected(self):
        p, g, a = copy.deepcopy(self.public[0]), copy.deepcopy(self.gold[0]), copy.deepcopy(self.assistance[0])
        g["objects"][0]["source_span"]["end"] = 999999
        self.assertTrue(any("SPAN_RANGE" in error for error in core.validate_case(p, g, a)))

    def test_duplicate_id_rejected(self):
        p, g, a = copy.deepcopy(self.public[0]), copy.deepcopy(self.gold[0]), copy.deepcopy(self.assistance[0])
        g["objects"][1]["object_id"] = g["objects"][0]["object_id"]
        self.assertTrue(any("DUPLICATE_ID" in error for error in core.validate_case(p, g, a)))

    def test_register_contradiction_rejected(self):
        p, g, a = copy.deepcopy(self.public[0]), copy.deepcopy(self.gold[0]), copy.deepcopy(self.assistance[0])
        p["material_register"][0]["provided"] = False
        self.assertTrue(any("REGISTER_CONFLICT" in error for error in core.validate_case(p, g, a)))

    def test_text_and_register_completeness_conflict_rejected(self):
        p, g, a = next((copy.deepcopy(p), copy.deepcopy(self.by_gold[p["case_id"]]), copy.deepcopy(self.by_assist[p["case_id"]])) for p in self.public if self.by_gold[p["case_id"]]["family_id"] == "T2" and self.by_gold[p["case_id"]]["variant_id"] == "v4")
        p["documents"][-1]["text"] = p["documents"][-1]["text"].replace("partial extract for TX-01", "complete for all listed TX events")
        self.assertTrue(any("REGISTER_CONFLICT" in error for error in core.validate_case(p, g, a)))

    def test_gold_record_must_match_public_text(self):
        p, g, a = next((copy.deepcopy(p), copy.deepcopy(self.by_gold[p["case_id"]]), copy.deepcopy(self.by_assist[p["case_id"]])) for p in self.public if self.by_gold[p["case_id"]]["family_id"] == "T2")
        g["objects"][0]["order_record"]["scope"] = "Dataset Invented"
        self.assertTrue(any("RECORD_SOURCE_MISMATCH" in error for error in core.validate_case(p, g, a)))

    def test_t1_gold_fact_must_match_public_clause(self):
        p, g, a = copy.deepcopy(self.public[0]), copy.deepcopy(self.gold[0]), copy.deepcopy(self.assistance[0])
        fact = next(f for f in g["facts"] if f["proposition"] == "target_present" and f["value"] == "TRUE")
        fact["value"] = "FALSE"
        self.assertTrue(any("FACT_REFERENCE_MISMATCH" in error for error in core.validate_case(p, g, a)))

    def test_ambiguous_case_rejected(self):
        p, g, a = copy.deepcopy(self.public[0]), copy.deepcopy(self.gold[0]), copy.deepcopy(self.assistance[0])
        g["ambiguity"] = {"flag": True, "reason": "Unresolved source identity"}
        self.assertTrue(any("AMBIGUOUS" in error for error in core.validate_case(p, g, a)))

    def test_illegal_state_rejected(self):
        p, g, a = copy.deepcopy(self.public[0]), copy.deepcopy(self.gold[0]), copy.deepcopy(self.assistance[0])
        g["decisions"][0]["state"] = "MAYBE"
        self.assertTrue(any("STATE_INVALID" in error for error in core.validate_case(p, g, a)))

    def test_violation_needs_complete_absence_scope(self):
        selected = next((p, self.by_gold[p["case_id"]], self.by_assist[p["case_id"]]) for p in self.public if any(d["state"] == "VIOLATION" for d in self.by_gold[p["case_id"]]["decisions"]))
        p, g, a = copy.deepcopy(selected)
        next(d for d in g["decisions"] if d["state"] == "VIOLATION")["absence_scope_ids"] = []
        self.assertTrue(any("ABSENCE_SCOPE" in error for error in core.validate_case(p, g, a)))

    def test_unknown_registry_cannot_prove_violation(self):
        p, g = next((p, self.by_gold[p["case_id"]]) for p in self.public if self.by_gold[p["case_id"]]["family_id"] == "T2" and self.by_gold[p["case_id"]]["variant_id"] == "v4")
        focal = next(o for o in g["objects"] if o["object_id"] == g["focal_object_id"])
        self.assertEqual(core.evaluate_object(p, g, focal), "INSUFFICIENT_EVIDENCE")

    def test_render_isolation_and_candidate_layout(self):
        for p in self.public:
            a = self.by_assist[p["case_id"]]
            base = core.render_public(p)
            self.assertTrue(core.render_input(p, None, "A").startswith(base))
            self.assertTrue(core.render_input(p, a, "B").startswith(base))
            self.assertEqual(len(a["object_index"]), 4)
            leaked = copy.deepcopy(p)
            leaked["state"] = "VIOLATION"
            leaked["focal_object_id"] = "LEAK"
            self.assertEqual(core.render_input(p, a, "B"), core.render_input(leaked, a, "B"))
            altered_gold = copy.deepcopy(self.by_gold[p["case_id"]])
            altered_gold["focal_object_id"] = "changed"
            altered_gold["decisions"][0]["state"] = "VIOLATION"
            before = hashlib.sha256(core.render_input(p, a, "B").encode()).hexdigest()
            leaked.update({key: altered_gold[key] for key in ("focal_object_id", "decisions")})
            after = hashlib.sha256(core.render_input(leaked, a, "B").encode()).hexdigest()
            self.assertEqual(before, after)
            poisoned_assistance = copy.deepcopy(a)
            poisoned_assistance["state"] = "COMPLIANT"
            poisoned_assistance["object_index"][0]["focal"] = True
            self.assertEqual(core.render_input(p, a, "B"), core.render_input(p, poisoned_assistance, "B"))
            if p["task_type"] == "reference_existence":
                with self.assertRaisesRegex(ValueError, "T1_C_FORBIDDEN"):
                    core.render_input(p, a, "C")
            else:
                self.assertTrue(core.render_input(p, a, "C").startswith(base))
                self.assertEqual({len(row["candidate_spans"]) for row in a["evidence_index"]}, {5})

    def test_prediction_matching_uses_occurrence_and_no_duplicate_credit(self):
        p, g = self.public[0], self.gold[0]
        obj = g["objects"][0]
        state = next(d["state"] for d in g["decisions"] if d["object_id"] == obj["object_id"])
        check = {"object_id": None, "source_span": obj["source_span"], "state": state, "evidence_spans": [], "brief_basis": "Fixture."}
        result = core.assess_prediction(p, g, {"checks": [check, check]})
        self.assertEqual(result["state_correct"], 1)
        self.assertEqual(result["duplicate"], 1)
        self.assertEqual(result["missing"], 3)
        mismatch = copy.deepcopy(check)
        mismatch["object_id"] = "wrong"
        self.assertEqual(core.assess_prediction(p, g, {"checks": [mismatch]})["conflict"], 1)

    def test_utc_interval_endpoints_inclusive(self):
        event = {"event_id": "x", "subject": "s", "scope": "d", "sent_at": "2026-04-10T10:00:00Z"}
        rec = {"event_id": "x", "subject": "s", "scope": "d", "valid_from": event["sent_at"], "valid_until": event["sent_at"], "effective": True}
        self.assertEqual(core._record_matches(event, rec)["time_match"], "TRUE")


class MemoryAuditTests(unittest.TestCase):
    def test_six_fixture_categories_and_denominator(self):
        records = [json.loads(s) for s in (ROOT / "tests/fixtures/memory_audit.jsonl").read_text(encoding="utf-8").splitlines() if s]
        self.assertGreaterEqual(len(records), 6)
        self.assertTrue(all(r["record_kind"] == "TEST_FIXTURE" for r in records))
        categories = [core.classify_transition(r["pre_status"], r["post_status"]) for r in records]
        self.assertEqual(set(categories), set(core.TRANSITIONS))
        self.assertEqual(sum(r["pre_status"] == "CORRECT" for r in records), 2)
        self.assertEqual(len(records), len(categories))


if __name__ == "__main__":
    unittest.main()
