import json
from collections import Counter
from pathlib import Path

import pytest

from memoryflow.holdout import (
    build_holdout,
    candidate_fingerprint,
    shuffle_candidate_ids,
    target_hash,
    validate_bundle,
    write_checksums,
)


def _source(source_id: str) -> dict:
    return {"id": source_id, "title": f"Title {source_id}", "memory_text": f"Memory {source_id}"}


def _example(run: str, index: int, gold_count: int = 1, text: str | None = None) -> dict:
    candidate_ids = [f"{run}_s{index}_{slot}" for slot in range(4)]
    return {
        "example_id": f"factstruct:{run}:target_{index:04d}",
        "run_id": run,
        "target": {"id": f"target_{index:04d}", "text": text or f"Target {run} {index}"},
        "gold_source_ids": candidate_ids[:gold_count],
        "label_type": "silver_inline_citation",
    }


def _fixture_rows(run_count: int = 8) -> tuple[list[dict], list[dict], list[dict], dict]:
    examples, candidates, sources = [], [], []
    for run_index in range(run_count):
        run = f"run{run_index}"
        for index, gold_count in enumerate((1, 2)):
            example = _example(run, index, gold_count)
            ids = [f"{run}_s{index}_{slot}" for slot in range(4)]
            examples.append(example)
            candidates.append({"example_id": example["example_id"], "candidate_sets": {"4": ids}})
            sources.extend(_source(source_id) for source_id in ids)
    splits = {"test": [row["example_id"] for row in examples], "test_runs": [f"run{x}" for x in range(run_count)]}
    return examples, candidates, sources, splits


def test_shuffle_is_deterministic_and_example_specific() -> None:
    ids = ["a", "b", "c", "d"]
    first = shuffle_candidate_ids(ids, "memoryflow-b4-holdout-v1", "example-a")
    assert first == shuffle_candidate_ids(ids, "memoryflow-b4-holdout-v1", "example-a")
    assert first != shuffle_candidate_ids(ids, "memoryflow-b4-holdout-v1", "example-b")
    assert set(first) == set(ids)


def test_hashes_normalize_target_and_ignore_candidate_order() -> None:
    assert target_hash("a  b\n") == target_hash(" a b ")
    assert candidate_fingerprint("Target", ["b", "a"]) == candidate_fingerprint("Target", ["a", "b"])


def test_selection_excludes_debug_and_duplicate_fingerprints_and_caps_runs() -> None:
    examples, candidates, sources, splits = _fixture_rows()
    debug = [{
        "example_id": "debug-id",
        "run_id": "run0",
        "target": {"text": "debug target"},
        "candidates": [_source(x) for x in ("d1", "d2", "d3", "d4")],
    }]
    # Duplicate an eligible target and its candidate membership under another ID.
    duplicate = dict(examples[-1])
    duplicate["example_id"] = "duplicate-id"
    examples.append(duplicate)
    candidates.append({"example_id": "duplicate-id", "candidate_sets": {"4": candidates[-1]["candidate_sets"]["4"]}})
    splits["test"].append("duplicate-id")

    result = build_holdout(examples, candidates, sources, splits, debug, target_single=5, target_multi=5)
    repeated = build_holdout(examples, candidates, sources, splits, debug, target_single=5, target_multi=5)
    rows = result["examples"]
    assert rows == repeated["examples"]
    assert all(row["run_id"] != "run0" for row in rows)
    assert len(rows) == 10
    assert Counter(row["run_id"] for row in rows).most_common(1)[0][1] <= 2
    assert len({target_hash(row["target"]["text"]) for row in rows}) == len(rows)
    assert len({candidate_fingerprint(row["target"]["text"], [x["id"] for x in row["candidates"]]) for row in rows}) == len(rows)
    assert sum(len(row["gold_source_ids"]) == 1 for row in rows) == 5
    assert sum(len(row["gold_source_ids"]) > 1 for row in rows) == 5


def test_only_structurally_valid_rows_are_selected() -> None:
    examples, candidates, sources, splits = _fixture_rows(4)
    examples[0]["target"]["text"] = ""
    candidates[1]["candidate_sets"]["4"] = candidates[1]["candidate_sets"]["4"][:3]
    examples[2]["gold_source_ids"] = ["missing-gold"]
    candidates[3]["candidate_sets"]["4"][3] = candidates[3]["candidate_sets"]["4"][0]
    sources[16]["memory_text"] = ""
    result = build_holdout(examples, candidates, sources, splits, [], target_single=2, target_multi=1)
    for row in result["examples"]:
        ids = [item["id"] for item in row["candidates"]]
        assert len(ids) == len(set(ids)) == 4
        assert set(row["gold_source_ids"]).issubset(ids)
        assert all(item["memory_text"] for item in row["candidates"])


def test_source_conflict_is_not_silently_resolved() -> None:
    examples, candidates, sources, splits = _fixture_rows(2)
    sources.append({**sources[0], "memory_text": "conflict"})
    with pytest.raises(ValueError, match="conflicting source"):
        build_holdout(examples, candidates, sources, splits, [], target_single=1, target_multi=1)


def test_bundle_validation_is_self_contained_and_checksums_detect_changes(tmp_path: Path) -> None:
    examples, candidates, sources, splits = _fixture_rows(4)
    result = build_holdout(examples, candidates, sources, splits, [], target_single=3, target_multi=3)
    (tmp_path / "examples.jsonl").write_text("".join(json.dumps(x) + "\n" for x in result["examples"]), encoding="utf-8")
    (tmp_path / "source_catalog.jsonl").write_text("".join(json.dumps(x) + "\n" for x in result["sources"]), encoding="utf-8")
    (tmp_path / "manifest.json").write_text(json.dumps({"example_count": 6}), encoding="utf-8")
    (tmp_path / "schema.md").write_text("schema", encoding="utf-8")
    (tmp_path / "sampling_report.md").write_text("report", encoding="utf-8")
    write_checksums(tmp_path)
    validation = validate_bundle(tmp_path, debug_rows=[])
    assert validation["passed"]
    assert validation["exact_four_candidates"] == 6
    assert validation["source_catalog_duplicate_id_count"] == 0
    assert validation["source_catalog_conflict_count"] == 0
    (tmp_path / "schema.md").write_text("changed", encoding="utf-8")
    assert not validate_bundle(tmp_path, debug_rows=[])["checksums_valid"]
