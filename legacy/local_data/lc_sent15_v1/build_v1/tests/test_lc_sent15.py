import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "code"))

from lc_sent15 import (  # noqa: E402
    ParseError,
    deterministic_candidates,
    expand_ranges,
    parse_prompt,
    parse_response,
    source_id,
    split_for_document,
)


def test_prompt_preserves_official_units_and_query():
    prompt = "prefix\n[Document Start]\n<C0> first\n<C1>second \n[Document End]\n\nQuestion?"
    parsed = parse_prompt(prompt)
    assert parsed.query == "Question?"
    assert [(x.sentence_index, x.text) for x in parsed.sources] == [(0, " first\n"), (1, "second \n")]


def test_citation_range_expands_to_individual_sources_and_deduplicates():
    assert expand_ranges([(12, 14), (14, 15)]) == (12, 13, 14, 15)


def test_response_parses_multiple_ranges():
    response = "<statement>Claim<cite>[1-2][4-4]</cite></statement>"
    parsed = parse_response(response, {0, 1, 2, 3, 4})[0]
    assert parsed.status == "valid"
    assert parsed.citation_ids == (1, 2, 4)
    assert parsed.text == "Claim"


def test_no_citation_is_explicitly_classified():
    parsed = parse_response("<statement>Lead<cite></cite></statement>", {0})[0]
    assert parsed.status == "no_citation"


def test_out_of_range_is_not_repaired():
    parsed = parse_response("<statement>Claim<cite>[2-3]</cite></statement>", {0, 1, 2})[0]
    assert parsed.status == "out_of_range"
    assert parsed.citation_ids == (2, 3)


def test_reversed_range_is_malformed():
    parsed = parse_response("<statement>Claim<cite>[3-1]</cite></statement>", {1, 2, 3})[0]
    assert parsed.status == "malformed"


def test_text_outside_statements_rejects_row():
    try:
        parse_response("prefix<statement>Claim<cite>[0-0]</cite></statement>", {0})
    except ParseError as error:
        assert str(error) == "text_outside_statement_tags"
    else:
        raise AssertionError("expected ParseError")


def test_candidates_are_deterministic_unique_and_keep_all_positives():
    sources = [f"s{i}" for i in range(30)]
    first = deterministic_candidates("example", ["s3", "s7"], sources)
    second = deterministic_candidates("example", ["s3", "s7"], reversed(sources))
    assert first == second
    assert len(first) == 15
    assert len(set(first)) == 15
    assert {"s3", "s7"}.issubset(first)


def test_single_positive_has_exactly_one_positive_and_fourteen_negatives():
    sources = [f"s{i}" for i in range(20)]
    candidates = deterministic_candidates("single", ["s4"], sources)
    assert len(candidates) == 15
    assert sum(item == "s4" for item in candidates) == 1


def test_source_and_split_ids_are_reproducible():
    assert source_id("abc", 12) == "lc15:dabc:c12"
    assert split_for_document("doc") == split_for_document("doc")
