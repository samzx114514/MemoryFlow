import re

from memoryflow.citation_dataset import (
    build_candidate_sets,
    build_source_catalog,
    candidate_position_report,
    extract_examples,
    split_by_run,
)
from memoryflow.schema import FactStructRun


def make_run(run_id: str = "run1") -> FactStructRun:
    return FactStructRun(
        run_id=run_id,
        query="What?",
        thread_id=run_id,
        sources={
            "1": {"title": "One", "url": "https://one", "content": "raw one", "observation": {"topic": "Topic one", "points": ["Point A"]}},
            "2": {"title": "Two", "url": "https://two", "content": "Fallback body", "observation": None},
            "3": {"title": "Three", "content": "Other body", "observation": {"topic": "Topic three", "points": ["Point C"]}},
        },
        final_report=(
            "# Heading\n\nLong enough sentence with one source [1]. "
            "Tiny [1][3]. Another sufficiently long sentence cites two sources [1, 2]."
        ),
        parser_warnings=[],
        raw_log_provenance=[],
    )


def test_three_citation_formats_multigold_and_no_leakage() -> None:
    examples = extract_examples(make_run())
    assert len(examples) == 3
    assert [item.rsplit("_", 1)[-1] for item in examples[1]["gold_source_ids"]] == ["1", "3"]
    assert [item.rsplit("_", 1)[-1] for item in examples[2]["gold_source_ids"]] == ["1", "2"]
    assert all(not re.search(r"\[\s*\d", e["target"]["text"]) for e in examples)
    assert "Long enough sentence" in examples[1]["target"]["text"]
    assert examples[0]["sources"][0]["memory_text"] == "Topic one\nPoint A"
    assert all("https://" not in s["memory_text"] for e in examples for s in e["sources"])


def test_candidate_pools_keep_all_positives_and_share_no_text() -> None:
    examples = []
    for index in range(12):
        run_id = f"run{index}"
        examples.extend(extract_examples(make_run(run_id))[:1])
    catalog = build_source_catalog(examples)
    pools, stats = build_candidate_sets(examples, catalog, seed=20260727)
    for example, pool in zip(examples, pools):
        for size, ids in pool["candidate_sets"].items():
            if ids:
                assert set(example["gold_source_ids"]).issubset(ids)
                assert len(ids) == int(size)
                assert len(ids) == len(set(ids))
    assert stats["available"]["4"] == len(examples)


def test_candidate_shuffle_is_reproducible_order_independent_and_not_fixed_gold() -> None:
    examples = []
    for index in range(20):
        examples.extend(extract_examples(make_run(f"shuffle{index}"))[:1])
    catalog = build_source_catalog(examples)
    first, _ = build_candidate_sets(examples, catalog, seed=20260727)
    second, _ = build_candidate_sets(examples, catalog, seed=20260727)
    reversed_rows, _ = build_candidate_sets(list(reversed(examples)), catalog, seed=20260727)
    assert first == second
    assert {row["example_id"]: row for row in first} == {row["example_id"]: row for row in reversed_rows}
    positions = []
    orders = set()
    for example, row in zip(examples, first):
        pool = row["candidate_sets"]["4"]
        positions.append(pool.index(example["gold_source_ids"][0]))
        orders.add(tuple(pool))
        assert set(example["gold_source_ids"]).issubset(pool)
    assert len(orders) > 1
    assert set(positions) != {0}
    report = candidate_position_report(examples, first)
    assert report["4"]["position_bias_max_ratio"] < 1.0


def test_pool_unavailable_when_gold_count_exceeds_k() -> None:
    run = make_run("manygold")
    run.sources["4"] = {"title": "Four", "content": "Fourth source", "observation": None}
    run.sources["5"] = {"title": "Five", "content": "Fifth source", "observation": None}
    run.final_report = "One target cites five distinct sources [1, 2, 3, 4, 5]."
    examples = extract_examples(run)
    for index in range(12):
        examples.extend(extract_examples(make_run(f"many{index}"))[:1])
    example = examples[0]
    catalog = build_source_catalog(examples)
    rows, stats = build_candidate_sets(examples, catalog, seed=20260727)
    assert rows[0]["candidate_sets"]["4"] == []
    assert rows[0]["unavailable"]["4"] == "gold_count_exceeds_candidate_count"
    assert stats["unavailable_gold_exceeds"]["4"] == 1
    assert len(rows[0]["candidate_sets"]["8"]) == 8


def test_source_catalog_is_global_resolvable_and_rejects_conflicts() -> None:
    examples = extract_examples(make_run("catalog"))
    source_id = examples[0]["sources"][0]["id"]
    catalog = build_source_catalog(examples, {source_id: {"url": "https://audit-only"}})
    assert len({source["id"] for source in catalog}) == len(catalog)
    assert next(source for source in catalog if source["id"] == source_id)["url"] == "https://audit-only"
    conflicting = [dict(examples[0])]
    conflicting[0]["sources"] = [dict(examples[0]["sources"][0], memory_text="conflict")]
    try:
        build_source_catalog(examples + conflicting)
    except ValueError as exc:
        assert source_id in str(exc)
    else:
        raise AssertionError("conflicting Source text must stop catalog construction")


def test_run_level_split_has_two_dev_and_no_train() -> None:
    examples = []
    for run_id in ("a", "b", "c", "d"):
        examples.extend(extract_examples(make_run(run_id)))
    splits = split_by_run(examples, seed=20260727)
    assert splits["train"] == []
    assert len(splits["dev_runs"]) == 2
    assert set(splits["dev_runs"]).isdisjoint(splits["test_runs"])
    dev_example_runs = {eid.split(":")[1] for eid in splits["dev"]}
    assert dev_example_runs == set(splits["dev_runs"])


def test_reference_section_and_url_path_are_not_targets() -> None:
    run = make_run()
    run.final_report = (
        "Valid sufficiently long statement for evaluation [1].\n\n"
        "## References\n\n- example.com/paper - Paper title [1]."
    )
    examples = extract_examples(run)
    assert len(examples) == 1
    assert examples[0]["target"]["text"].startswith("Valid sufficiently")


def test_source_numeric_range_citation_is_removed() -> None:
    run = make_run()
    run.sources["2"]["content"] = "Evidence discussed in prior work [3-4, 10-11]."
    examples = extract_examples(run)
    source = next(source for source in examples[2]["sources"] if source["id"].endswith("_2"))
    assert "[3-4" not in source["memory_text"]
