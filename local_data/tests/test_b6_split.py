import json
from collections import Counter
from pathlib import Path

from memoryflow.b6_split import (
    build_eligible_pool,
    candidate_set_hash,
    deduplicate_partition_pools,
    discover_run_roles,
    materialize_rows,
    sample_partition,
    split_exposed_runs,
    validate_cross_splits,
    write_bundle,
)


def _example(run_id: str, index: int, gold_count: int = 1, text: str | None = None) -> dict:
    return {
        "example_id": f"factstruct:{run_id}:target_{index:04d}",
        "run_id": run_id,
        "target": {"id": f"target_{index:04d}", "text": text or f"Target {run_id} {index}"},
        "gold_source_ids": [f"{run_id}_{index}_s{x}" for x in range(gold_count)],
        "label_type": "silver_inline_citation",
    }


def _fixture(run_count: int = 12, rows_per_run: int = 6) -> tuple[list[dict], list[dict], list[dict]]:
    examples, candidate_rows, sources = [], [], []
    for run_index in range(run_count):
        run_id = f"run{run_index:02d}"
        for index in range(rows_per_run):
            example = _example(run_id, index, 1 if index % 2 == 0 else 2)
            ids = [f"{run_id}_{index}_s{x}" for x in range(4)]
            examples.append(example)
            candidate_rows.append({"example_id": example["example_id"], "candidate_sets": {"4": ids}})
            sources.extend({"id": source_id, "title": f"Title {source_id}", "memory_text": f"Memory {source_id}"} for source_id in ids)
    return examples, candidate_rows, sources


def test_run_roles_and_group_split_are_disjoint_and_deterministic() -> None:
    examples, _, _ = _fixture(10, 2)
    debug = [{"run_id": "run00"}, {"run_id": "run01"}]
    b4 = [{"run_id": "run02"}, {"run_id": "run03"}, {"run_id": "run04"}]
    exposed, unseen = discover_run_roles(examples, debug, b4)
    assert exposed == {"run00", "run01", "run02", "run03", "run04"}
    assert unseen == {"run05", "run06", "run07", "run08", "run09"}
    train, validation = split_exposed_runs(exposed, "memoryflow-b6-group-split-v1")
    assert (train, validation) == split_exposed_runs(exposed, "memoryflow-b6-group-split-v1")
    assert len(train) == 4 and len(validation) == 1
    assert train.isdisjoint(validation) and train | validation == exposed


def test_structural_pool_and_priority_deduplication() -> None:
    examples, candidate_rows, sources = _fixture(3, 3)
    # Same normalized target across final and validation; final must reserve it.
    examples[3]["target"]["text"] = examples[6]["target"]["text"]
    # Same candidate membership across validation and train; validation must reserve it.
    candidate_rows[0]["candidate_sets"]["4"] = list(candidate_rows[4]["candidate_sets"]["4"])
    examples[0]["gold_source_ids"] = [candidate_rows[4]["candidate_sets"]["4"][0]]
    pools = {
        "train": build_eligible_pool(examples, candidate_rows, sources, {"run00"}),
        "validation": build_eligible_pool(examples, candidate_rows, sources, {"run01"}),
        "final_test": build_eligible_pool(examples, candidate_rows, sources, {"run02"}),
    }
    deduped, report = deduplicate_partition_pools(pools)
    final_targets = {x["target_hash"] for x in deduped["final_test"]}
    validation_targets = {x["target_hash"] for x in deduped["validation"]}
    validation_sets = {x["candidate_set_hash"] for x in deduped["validation"]}
    train_sets = {x["candidate_set_hash"] for x in deduped["train"]}
    assert final_targets.isdisjoint(validation_targets)
    assert validation_sets.isdisjoint(train_sets)
    assert report["validation"]["cross_partition_target_hash"] == 1
    assert report["train"]["cross_partition_candidate_set_hash"] == 1


def test_sampling_meets_quotas_caps_and_falls_back_deterministically() -> None:
    examples, candidate_rows, sources = _fixture(6, 8)
    pool = build_eligible_pool(examples, candidate_rows, sources, {f"run{x:02d}" for x in range(6)})
    selected = sample_partition(pool, target_single=10, target_multi=10, per_run_cap=4, seed="sample")
    assert selected == sample_partition(pool, target_single=10, target_multi=10, per_run_cap=4, seed="sample")
    assert len(selected) == 20
    assert sum(len(x["gold_source_ids"]) == 1 for x in selected) == 10
    assert sum(len(x["gold_source_ids"]) > 1 for x in selected) == 10
    assert max(Counter(x["run_id"] for x in selected).values()) <= 4

    single_only = [x for x in pool if len(x["gold_source_ids"]) == 1]
    fallback = sample_partition(single_only, target_single=4, target_multi=4, per_run_cap=2, seed="fallback")
    assert len(fallback) == 8 and all(len(x["gold_source_ids"]) == 1 for x in fallback)

    constrained = [
        row for row in pool
        if (row["run_id"] == "run00" or (row["run_id"] == "run01" and len(row["gold_source_ids"]) == 1))
    ]
    scarce_first = sample_partition(constrained, target_single=4, target_multi=4, per_run_cap=4, seed="scarce")
    assert sum(len(row["gold_source_ids"]) > 1 for row in scarce_first) == 4
    assert sum(len(row["gold_source_ids"]) == 1 for row in scarce_first) == 4


def test_materialization_uses_split_seed_and_keeps_gold() -> None:
    examples, candidate_rows, sources = _fixture(2, 4)
    pool = build_eligible_pool(examples, candidate_rows, sources, {"run00", "run01"})
    selected = sample_partition(pool, 2, 2, 3, "sample")
    train = materialize_rows(selected, sources, "train", "memoryflow-b6-train-order-v1")
    validation = materialize_rows(selected, sources, "validation", "memoryflow-b6-validation-order-v1")
    assert train == materialize_rows(selected, sources, "train", "memoryflow-b6-train-order-v1")
    assert any([x["id"] for x in a["candidates"]] != [x["id"] for x in b["candidates"]] for a, b in zip(train, validation))
    assert all(len(row["candidates"]) == 4 for row in train)
    assert all(set(row["gold_source_ids"]) <= {x["id"] for x in row["candidates"]} for row in train)


def test_cross_split_validation_catches_all_overlap_types() -> None:
    examples, candidate_rows, sources = _fixture(3, 2)
    pools = {
        name: build_eligible_pool(examples, candidate_rows, sources, {run})
        for name, run in (("train", "run00"), ("validation", "run01"), ("final_test", "run02"))
    }
    rows = {name: materialize_rows(items, sources, name, f"seed-{name}") for name, items in pools.items()}
    report = validate_cross_splits(rows)
    assert report["passed"]
    rows["train"].append(rows["validation"][0])
    assert not validate_cross_splits(rows)["passed"]


def test_bundle_is_self_contained_and_sealed_report_omits_slots(tmp_path: Path) -> None:
    examples, candidate_rows, sources = _fixture(2, 4)
    pool = build_eligible_pool(examples, candidate_rows, sources, {"run00", "run01"})
    rows = materialize_rows(sample_partition(pool, 2, 2, 3, "sample"), sources, "final_test", "order")
    result = write_bundle(tmp_path, rows, seed="order", group_seed="group", sealed=True)
    assert result["checksums_valid"]
    assert "slot" not in (tmp_path / "sampling_report.md").read_text(encoding="utf-8").lower()
    catalog = {json.loads(line)["id"] for line in (tmp_path / "source_catalog.jsonl").read_text(encoding="utf-8").splitlines()}
    assert all(candidate["id"] in catalog for row in rows for candidate in row["candidates"])
    assert all(candidate_set_hash([x["id"] for x in row["candidates"]]) for row in rows)
