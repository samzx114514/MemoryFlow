import json
from pathlib import Path

from memoryflow.citation_dataset import build_candidate_sets, build_source_catalog, extract_examples
from memoryflow.v2_delivery import (
    materialize_debug_rows,
    select_debug_example_ids,
    verify_manifest,
    write_manifest,
)
from test_citation_dataset import make_run


def test_debug_subset_is_dev_exact_four_and_self_contained() -> None:
    examples = []
    for index in range(4):
        examples.extend(extract_examples(make_run(f"devrun{index}")))
    catalog = build_source_catalog(examples)
    candidates, _ = build_candidate_sets(examples, catalog, seed=20260727)
    dev_runs = ["devrun0", "devrun1"]
    dev = [example["example_id"] for example in examples if example["run_id"] in dev_runs]
    splits = {"dev_runs": dev_runs, "dev": dev, "test_runs": ["devrun2", "devrun3"], "test": []}
    selected = select_debug_example_ids(examples, candidates, splits, size=6)
    rows = materialize_debug_rows(selected, examples, candidates, catalog)
    assert len(rows) == 6
    assert {row["run_id"] for row in rows} == set(dev_runs)
    assert all(row["split"] == "dev" and len(row["candidates"]) == 4 for row in rows)
    assert all(set(row["gold_source_ids"]).issubset({item["id"] for item in row["candidates"]}) for row in rows)
    assert all("url" not in item for row in rows for item in row["candidates"])


def test_manifest_round_trip_and_detects_change(tmp_path: Path) -> None:
    (tmp_path / "a.txt").write_text("a", encoding="utf-8")
    write_manifest(tmp_path)
    assert verify_manifest(tmp_path)
    (tmp_path / "a.txt").write_text("changed", encoding="utf-8")
    assert not verify_manifest(tmp_path)
