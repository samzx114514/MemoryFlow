import hashlib
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "code"))

from lc_sent15 import deterministic_candidates  # noqa: E402


SOURCE = Path(
    r"F:\CodexProject\MemoryFlow\datasets\LongCite-45k\b776b01faf6e132a3d9cc373de1b46cd6630d772\long.jsonl"
)
EXPECTED_SIZE = 5_726_201_192
EXPECTED_SHA = "8eb96dad6496d8d28d983982e6f623adc1e44ffa9dce215ffc7d56fd0336623b"


def rows(path: Path):
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            value = json.loads(line)
            assert isinstance(value, dict), (path, line_number)
            yield value


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def test_official_source_contract_still_matches():
    assert SOURCE.stat().st_size == EXPECTED_SIZE
    assert sha256_file(SOURCE) == EXPECTED_SHA


@pytest.mark.parametrize(
    "relative,expected_count",
    [
        ("train/single_positive_15.jsonl", 854),
        ("dev/single_positive_15.jsonl", 228),
        ("sealed_reserve/single_positive_15.jsonl", 218),
    ],
)
def test_single_track_has_exactly_15_candidates_and_one_positive(relative, expected_count):
    count = 0
    for example in rows(ROOT / relative):
        count += 1
        candidates = example["candidates"]
        ids = [item["source_id"] for item in candidates]
        positives = [item["source_id"] for item in candidates if item["label"] == 1]
        negatives = [item["source_id"] for item in candidates if item["label"] == 0]
        assert example["candidate_count"] == 15
        assert len(ids) == len(set(ids)) == 15
        assert len(positives) == 1
        assert len(negatives) == 14
        assert positives == example["gold_source_ids"]
        assert set(positives).isdisjoint(negatives)
        assert tuple(ids) == deterministic_candidates(example["example_id"], positives, ids, 15)
    assert count == expected_count


@pytest.mark.parametrize("split", ["train", "dev"])
def test_multi_sidecar_keeps_all_positives(split):
    count = 0
    for example in rows(ROOT / split / "multi_positive_sidecar.jsonl"):
        count += 1
        ids = [item["source_id"] for item in example["candidates"]]
        positives = [item["source_id"] for item in example["candidates"] if item["label"] == 1]
        negatives = [item["source_id"] for item in example["candidates"] if item["label"] == 0]
        assert len(ids) == len(set(ids)) == 15
        assert len(positives) >= 2
        assert set(positives) == set(example["gold_source_ids"])
        assert set(positives).isdisjoint(negatives)
        assert tuple(ids) == deterministic_candidates(example["example_id"], positives, ids, 15)
    assert count > 0


def test_all_candidate_ids_resolve_and_splits_are_physical():
    source_sets = {}
    target_sets = {}
    document_sets = {}
    for split, directory in (("train", "train"), ("dev", "dev"), ("reserve", "sealed_reserve")):
        source_sets[split] = set()
        document_sets[split] = set()
        catalog_count = 0
        for item in rows(ROOT / directory / "source_catalog.jsonl"):
            catalog_count += 1
            assert item["split"] == split
            source_sets[split].add(item["id"])
            document_sets[split].add(item["document_id"])
        assert len(source_sets[split]) == catalog_count
        targets = list(rows(ROOT / directory / "single_positive_15.jsonl"))
        target_sets[split] = {item["example_id"] for item in targets}
        assert len(target_sets[split]) == len(targets)
        assert all(item["split"] == split for item in targets)
        for item in targets:
            assert all(candidate["source_id"] in source_sets[split] for candidate in item["candidates"])
            assert set(item["gold_source_ids"]).issubset(source_sets[split])
    for left, right in (("train", "dev"), ("train", "reserve"), ("dev", "reserve")):
        assert source_sets[left].isdisjoint(source_sets[right])
        assert target_sets[left].isdisjoint(target_sets[right])
        assert document_sets[left].isdisjoint(document_sets[right])


def test_reserve_never_appears_in_train_or_dev_outputs():
    for split in ("train", "dev"):
        for name in ("single_positive_15.jsonl", "multi_positive_sidecar.jsonl", "source_catalog.jsonl"):
            assert all(item["split"] == split for item in rows(ROOT / split / name))
    assert not (ROOT / "samples" / "reserve_examples_3.jsonl").exists()


def test_six_complete_readable_samples_exist_and_have_text():
    for split in ("train", "dev"):
        examples = list(rows(ROOT / "samples" / f"{split}_examples_3.jsonl"))
        assert len(examples) == 3
        for item in examples:
            assert item["query"] and item["target"]["text"] and item["raw_citation_expression"]
            assert len(item["candidates_with_text"]) == 15
            assert all(candidate["text"] for candidate in item["candidates_with_text"])
            assert [candidate["position"] for candidate in item["candidates_with_text"]] == list(range(15))


def test_gold_positions_are_not_constant():
    metrics = json.loads((ROOT / "build_metrics.json").read_text(encoding="utf-8"))
    for split in ("train", "dev"):
        counts = metrics["single_positive_position_counts_train_dev"][split]
        assert len(counts) == 15
        assert sum(counts) in {854, 228}
        assert sum(value > 0 for value in counts) == 15
