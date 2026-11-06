#!/usr/bin/env python3
"""Build the two-call provenance graph and expand the final sentence hop by hop.

The graph and the expansion use ``experiments/provenance_v2`` unchanged: calls and
messages are ingested with ``from_synthetic``, matrices are attached to their target
units, and ``ProvenanceQuery`` performs the fixed top-k expansion over transmission
links (copy/exact/prefix/embedded) with cycle and depth stops.

The two-round design already knows the only cross-call transmission (the round-1 answer
is pasted verbatim into the round-2 prompt). That relation is recorded as an explicit
``copy`` link; every other link is whatever the generic relink step finds.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # experiments/

import core
from provenance_v2 import ProvenanceQuery, from_synthetic
from provenance_v2.model import Link, text_sha


def material_message(material: dict) -> dict:
    return {
        "role": "tool",
        "content": material["text"],
        "unit_id": material["unit_id"],
        "artifact_id": material["artifact_id"],
        "start": material["start"],
        "end": material["end"],
    }


def build_graph(frozen: dict, scores: dict):
    r1 = frozen["rounds"][0]
    r2 = frozen["rounds"][1]
    calls = [
        {
            "id": "call_r1",
            "messages": [material_message(item) for item in r1["materials"]],
            "response": r1["answer"],
        },
        {
            "id": "call_r2",
            "messages": [
                {"role": "assistant", "content": r1["answer"], "unit_id": "conclusion:r1",
                 "origin": "round1_answer_pasted_verbatim"}
            ]
            + [material_message(item) for item in r2["materials"]],
            "response": r2["answer"],
        },
    ]

    def candidates(matrix_id: str) -> list[dict]:
        return [
            {"text": entry["text"], "score": entry["score"], "unit_id": entry["id"]}
            for entry in scores["matrices"][matrix_id]["candidates"]
        ]

    matrices = [
        {"call": "call_r1", "target": r1["answer"], "candidates": candidates("m1")},
        {"call": "call_r2", "target": r2["answer"], "candidates": candidates("m2")},
    ]
    graph = from_synthetic(calls, matrices)

    # candidate id -> original unit id (from_synthetic names candidates by message position)
    unit_of_candidate: dict[str, str] = {}
    for call in calls:
        for index, message in enumerate(call["messages"]):
            candidate_id = f"{call['id']}:msg{index}"
            unit_of_candidate[candidate_id] = message["unit_id"]
    graph.notes["candidate_units"] = unit_of_candidate

    # from_synthetic binds matrix rows by a 40-character prefix; material texts can contain
    # each other, so rebind every row by exact message text before the query runs.
    from provenance_v2.model import Matrix

    for index, (call_id, matrix_id) in enumerate((("call_r1", "m1"), ("call_r2", "m2"))):
        unit_id = f"{call_id}#target{index}"
        matrix = graph.matrices[unit_id]
        by_text = {
            candidate.text.strip(): candidate.candidate_id
            for candidate in graph.candidates.values()
            if candidate.call_id == call_id
        }
        rebound = []
        for entry in scores["matrices"][matrix_id]["candidates"]:
            candidate_id = by_text.get(entry["text"].strip())
            if candidate_id is None:
                raise core.SpecError(f"matrix row does not match a call message: {entry['id']}")
            rebound.append((candidate_id, float(entry["score"])))
        graph.matrices[unit_id] = Matrix(
            matrix_id=matrix.matrix_id,
            call_id=matrix.call_id,
            unit_id=matrix.unit_id,
            model=matrix.model,
            layer=matrix.layer,
            head=matrix.head,
            rows=matrix.rows,
            scores=rebound,
            source=matrix.source,
            causal=matrix.causal,
        )

    # explicit controlled transmission: the round-1 answer was pasted verbatim into round 2
    r1_unit = "call_r1#target0"
    conclusion_candidates = [
        candidate
        for candidate in graph.candidates.values()
        if candidate.call_id == "call_r2" and candidate.text.strip() == r1["answer"].strip()
    ]
    explicit = 0
    for candidate in conclusion_candidates:
        existing = [
            link
            for link in graph.links
            if link.from_id == candidate.candidate_id and link.to_id == r1_unit
        ]
        if existing:
            for link in existing:
                link.evidence["preferred"] = True
                link.evidence["controlled"] = True
        else:
            graph.links.append(
                Link(
                    link_id=f"{candidate.candidate_id}->{r1_unit}",
                    from_id=candidate.candidate_id,
                    to_id=r1_unit,
                    kind="copy",
                    evidence={
                        "preferred": True,
                        "controlled": True,
                        "relation": "round1_answer_pasted_verbatim",
                        "candidate_sha": text_sha(candidate.text.strip()),
                    },
                    locality="cross_call",
                )
            )
        explicit += 1
    graph.notes["controlled_links"] = explicit
    return graph


def ranked_rows(matrix: dict, exclude: set[str] | None = None) -> list[dict]:
    rows = [entry for entry in matrix["candidates"] if not exclude or entry["id"] not in exclude]
    rows = sorted(rows, key=lambda entry: -entry["score"])
    for rank, entry in enumerate(rows, start=1):
        entry = dict(entry)
        entry["rank"] = rank
        rows[rank - 1] = entry
    return rows


def rank_map(matrix: dict, exclude: set[str] | None = None) -> dict[str, dict]:
    return {entry["id"]: entry for entry in ranked_rows(matrix, exclude)}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--frozen", required=True)
    parser.add_argument("--scores", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--top-k", type=int, default=None)
    args = parser.parse_args(argv)

    frozen = core.read_json(args.frozen)
    scores = core.read_json(args.scores)
    budget = args.top_k or frozen["protocol"]["return_budget"]
    A = [item["unit_id"] for item in frozen["evidence"]["A"]]
    B = [item["unit_id"] for item in frozen["evidence"]["B"]]

    graph = build_graph(frozen, scores)
    unit_of_candidate = graph.notes["candidate_units"]
    query = ProvenanceQuery(graph, top_k=budget, max_depth=4)
    path = query.expand("call_r2#target1")

    # group 1: only the last round; rank the raw originals it saw (conclusion is not an original)
    m2 = rank_map(scores["matrices"]["m2"], exclude={"conclusion:r1"})
    g1_rank_a = {unit: m2[unit]["rank"] for unit in A if unit in m2}
    g1_rank_b = {unit: m2[unit]["rank"] for unit in B if unit in m2}
    g1 = {
        "pool_units": len(m2),
        "pool": [entry["id"] for entry in ranked_rows(scores["matrices"]["m2"], exclude={"conclusion:r1"})],
        "evidence_a_visible": bool(g1_rank_a),
        "evidence_a_ranks": g1_rank_a,
        "evidence_b_ranks": g1_rank_b,
        "found_a": any(rank <= budget for rank in g1_rank_a.values()),
        "found_b": any(rank <= budget for rank in g1_rank_b.values()),
    }
    g1["found_all"] = g1["found_a"] and g1["found_b"]

    # group 2: flat pool of both rounds' raw materials, same budget
    flat = rank_map(scores["matrices"]["mflat"])
    g2_rank_a = {unit: flat[unit]["rank"] for unit in A if unit in flat}
    g2_rank_b = {unit: flat[unit]["rank"] for unit in B if unit in flat}
    g2 = {
        "pool_units": len(flat),
        "pool": [entry["id"] for entry in ranked_rows(scores["matrices"]["mflat"])],
        "evidence_a_ranks": g2_rank_a,
        "evidence_b_ranks": g2_rank_b,
        "found_a": any(rank <= budget for rank in g2_rank_a.values()),
        "found_b": any(rank <= budget for rank in g2_rank_b.values()),
    }
    g2["found_all"] = g2["found_a"] and g2["found_b"]

    # group 3: chain result from the query path, candidates keyed back to their unit ids
    hop_entries: dict[str, dict[str, dict]] = {}
    hop_raw: dict[str, list[dict]] = {}
    for hop in path.hops:
        for entry in hop.candidates:
            unit_id = unit_of_candidate.get(entry["candidate_id"], entry["candidate_id"])
            entry = dict(entry)
            entry["unit_id"] = unit_id
            hop_entries.setdefault(hop.unit_id, {})[unit_id] = entry
        hop_raw.setdefault(hop.unit_id, []).append(hop.to_dict())
    hop1 = hop_entries.get("call_r2#target1", {})
    hop2 = hop_entries.get("call_r1#target0", {})
    g3_rank_a = {unit: hop2[unit]["rank"] for unit in A if unit in hop2}
    g3_rank_b = {unit: hop1[unit]["rank"] for unit in B if unit in hop1}
    conclusion = hop1.get("conclusion:r1")
    g3 = {
        "hops": [hop.to_dict() for hop in path.hops],
        "hop_units": [hop.unit_id for hop in path.hops],
        "stop_reason": path.stop_reason,
        "visited": path.visited,
        "transmitted_conclusion_rank": conclusion["rank"] if conclusion else None,
        "evidence_b_ranks": g3_rank_b,
        "evidence_a_ranks": g3_rank_a,
        "found_a": any(rank <= budget for rank in g3_rank_a.values()),
        "found_b": any(rank <= budget for rank in g3_rank_b.values()),
        "chain_continued": bool(hop2),
    }
    g3["found_all"] = g3["found_a"] and g3["found_b"] and bool(conclusion)

    payload = {
        "schema": "provenance_rounds_v1.analysis.v1",
        "sample": frozen["source"]["target_id"],
        "frozen_sha256": frozen["frozen_sha256"],
        "scores_sha256": core.sha256_file(args.scores),
        "return_budget": budget,
        "round1_answer": frozen["rounds"][0]["answer"],
        "round2_answer": frozen["rounds"][1]["answer"],
        "evidence": frozen["evidence"],
        "groups": {"last_round_raw": g1, "flat_pool": g2, "memoryflow_chain": g3},
        "graph_summary": {
            "calls": len(graph.calls),
            "units": len(graph.units),
            "candidates": len(graph.candidates),
            "matrices": len(graph.matrices),
            "links": len(graph.links),
            "controlled_links": graph.notes.get("controlled_links"),
        },
        "path": path.to_dict(),
        "candidate_units": unit_of_candidate,
    }
    core.write_json(args.out, payload)

    print(
        json.dumps(
            {
                "A_ranks": {"last_round_raw": g1["evidence_a_ranks"], "flat_pool": g2["evidence_a_ranks"],
                            "chain": g3["evidence_a_ranks"]},
                "B_ranks": {"last_round_raw": g1["evidence_b_ranks"], "flat_pool": g2["evidence_b_ranks"],
                            "chain": g3["evidence_b_ranks"]},
                "conclusion_rank": g3["transmitted_conclusion_rank"],
                "found_all": {"last_round_raw": g1["found_all"], "flat_pool": g2["found_all"],
                              "chain": g3["found_all"]},
                "stop_reason": path.stop_reason,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
