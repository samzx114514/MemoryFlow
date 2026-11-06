#!/usr/bin/env python3
"""Four multi-turn baselines over one unified case.

* last_round       fixed-head replay of the final round only, raw materials
* bm25_history     BM25 over every original candidate in the whole history
* head_full_history fixed head (L19H15) replay over the flat history pool
* memoryflow       follow transmitted conclusions hop by hop, product path scores,
                   sum path scores per original evidence, global final ranking
"""

from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import cases

ROOT = HERE.parents[1]
LEGACY_SRC = ROOT / "legacy/workspace/src"
if str(LEGACY_SRC) not in sys.path:
    sys.path.insert(0, str(LEGACY_SRC))

METHODS = ("last_round", "bm25_history", "head_full_history", "memoryflow")


def _canonical_scores(matrix: dict, exclude_transmission: bool) -> dict[str, float]:
    scores: dict[str, float] = {}
    for row in matrix["candidates"]:
        cid = row["canonical_id"]
        if exclude_transmission and cid.startswith("transmission:"):
            continue
        scores[cid] = float(row["score"])
    return scores


def rank_last_round(case: dict, matrices: dict, budget: int) -> list[str]:
    matrix = matrices["matrices"][matrices["final_round"]]
    scores = _canonical_scores(matrix, exclude_transmission=True)
    return cases.stable_ranking(list(scores), scores)[:budget]


def rank_bm25(case: dict, matrices: dict, budget: int) -> list[str]:
    from memoryflow.lc_sent15_bm25 import GroupBM25

    documents = {candidate["canonical_id"]: candidate["text"] for candidate in case["candidates"]}
    query = case["target"]["text"]
    scores = GroupBM25(documents).score(query)
    return cases.stable_ranking(list(scores), scores)[:budget]


def rank_head_full_history(case: dict, matrices: dict, budget: int) -> list[str]:
    matrix = matrices["matrices"]["flat"]
    scores = _canonical_scores(matrix, exclude_transmission=False)
    return cases.stable_ranking(list(scores), scores)[:budget]


def rank_memoryflow(case: dict, matrices: dict, budget: int, hop_budget: int) -> tuple[list[str], list[dict]]:
    matrices_map = matrices["matrices"]
    final_round = matrices["final_round"]
    merged: dict[str, float] = {}
    best_path: dict[str, float] = {}
    hops: list[dict] = []

    def expand(round_key: str, factor: float, path: tuple[str, ...]) -> None:
        matrix = matrices_map.get(round_key)
        if matrix is None:
            hops.append({"round": round_key, "factor": factor, "stop": "missing_matrix", "top": []})
            return
        ranked = sorted(matrix["candidates"], key=lambda row: (-float(row["score"]), row["canonical_id"]))[:hop_budget]
        hops.append(
            {
                "round": round_key,
                "factor": round(factor, 9),
                "path": list(path),
                "top": [
                    {"canonical_id": row["canonical_id"], "score": float(row["score"])} for row in ranked
                ],
            }
        )
        for row in ranked:
            cid = row["canonical_id"]
            value = factor * float(row["score"])
            if cid.startswith("transmission:"):
                previous = cid.split(":", 1)[1]
                if previous in path:
                    hops.append({"round": previous, "factor": value, "stop": "cycle", "top": []})
                    continue
                expand(previous, value, path + (previous,))
                continue
            merged[cid] = merged.get(cid, 0.0) + value
            best_path[cid] = max(best_path.get(cid, 0.0), value)

    expand(final_round, 1.0, (final_round,))
    order = sorted(merged, key=lambda cid: (-merged[cid], -best_path.get(cid, 0.0), cid))
    return order[:budget], hops


def run(case: dict, matrices: dict, final_budget: int = cases.FINAL_BUDGET,
        hop_budget: int = cases.HOP_BUDGET) -> dict:
    result = {
        "case_id": case["case_id"],
        "final_budget": final_budget,
        "hop_budget": hop_budget,
        "methods": {},
    }
    result["methods"]["last_round"] = {"ranked": rank_last_round(case, matrices, final_budget)}
    result["methods"]["bm25_history"] = {"ranked": rank_bm25(case, matrices, final_budget)}
    result["methods"]["head_full_history"] = {"ranked": rank_head_full_history(case, matrices, final_budget)}
    ranked, hops = rank_memoryflow(case, matrices, final_budget, hop_budget)
    result["methods"]["memoryflow"] = {"ranked": ranked, "hops": hops}
    return result
