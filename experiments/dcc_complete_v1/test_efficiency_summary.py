import json
import tempfile
import unittest
from pathlib import Path

from .summarize_efficiency import summarize


class EfficiencySummaryTest(unittest.TestCase):
    def test_parallel_pairs_keep_failures_and_exclude_warmup(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            for mode, prefix in [("execution", root), ("serial", root / "pair")]:
                for index, seconds in enumerate([1, 3, 100, 999]):
                    run = prefix / f"{mode}_{index}"
                    (run / "gateway").mkdir(parents=True)
                    (run / "gateway/identity.json").write_text(json.dumps({"analysis_model": "7b"}))
                    (run / "result.json").write_text(json.dumps({"mode": mode, "task_id": "case",
                        "warmup": index == 3, "completed": mode == "execution" or index != 2,
                        "task_total_seconds": seconds}))
            result = summarize(root)
            self.assertEqual(len(result["attempts"]), 6)
            serial = next(row for row in result["table"] if row["mode"] == "serial")
            self.assertEqual((serial["attempts"], serial["completed"]), (3, 2))
            self.assertEqual(serial["task_total_seconds"], 2)
            self.assertFalse(serial["all_three_complete"])
            baseline = next(row for row in result["table"] if row["mode"] == "execution")
            self.assertTrue(baseline["all_three_complete"])


if __name__ == "__main__":
    unittest.main()
