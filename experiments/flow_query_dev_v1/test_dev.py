import tempfile
import unittest
from pathlib import Path

from .cohort import freeze, sha, write
from .run import measured


class DevelopmentProtocolTest(unittest.TestCase):
    def test_whole_trajectories_and_unscored_targets_stay_on_one_side(self):
        def case(sample, name, items):
            return {"sample_id":sample,"case_id":name,
                    "evidence_groups":[{"items":[{}]*items}] if items else []}
        rows = [case("coach","c1",1), case("coach","c2",0), case("a","a1",3),
                case("b","b1",1), case("b","b2",4), case("z","z1",2)]
        with tempfile.TemporaryDirectory() as work:
            root=Path(work)
            write(root/"common/cases.json",rows)
            write(root/"common/inputs/records.json",[])
            write(root/"common/identity.json",{"cases_sha256":sha(root/"common/cases.json")})
            write(root/"config.json",{"mandatory_sample":"coach"})
            p=freeze(root/"common",root/"config.json",root/"frozen")
            self.assertEqual(p["development_samples"],["coach","a","b"])
            self.assertEqual(p["not_run_samples"],["z"])
            self.assertEqual(p["retained_unscored_dev_ids"],["c2"])
            self.assertEqual(set(p["development_target_ids"]),{"c1","a1","b1","b2"})

    def test_same_budget_keeps_actual_return_and_slot_precision_distinct(self):
        a={"artifact_id":"a","start":0,"end":3,"text":"one"}
        b={"artifact_id":"b","start":0,"end":3,"text":"two"}
        c={"candidates":[{"canonical_id":"a",**a},{"canonical_id":"b",**b}],
           "evidence_groups":[{"items":[{"alternatives":[a]},{"alternatives":[b]}]}]}
        half=measured(c,["a"],2)
        self.assertEqual(half["returned"],1)
        self.assertEqual(half["precision"],1)
        self.assertEqual(half["fixed_budget_precision"],.5)
        self.assertEqual(half["recall"],.5)
        self.assertEqual(half["complete"],0)
        self.assertEqual(measured(c,["a","b"],2)["complete"],1)
