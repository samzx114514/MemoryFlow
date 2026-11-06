#!/usr/bin/env python3
"""Coverage metrics, per-question ranks and paired comparisons for the batch."""

from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import cases
import methods


def rank_of_labels(ranked: list[str], labels: dict[str, list[str]]) -> dict[str, int | None]:
    out = {}
    for label, ids in labels.items():
        positions = [ranked.index(cid) + 1 for cid in ids if cid in ranked]
        out[label] = min(positions) if positions else None
    return out


def evaluate_method(case: dict, ranked: list[str], final_budget: int) -> dict:
    index = {candidate["canonical_id"]: candidate for candidate in case["candidates"]}
    groups = case["evidence_groups"]
    windows = [
        (index[cid]["artifact_id"], index[cid]["start"], index[cid]["end"])
        for cid in ranked[:final_budget]
        if cid in index
    ]
    top3 = windows[:3]
    top5 = windows[:5]
    top10 = windows[:10]
    group_complete_at = {}
    for group in groups:
        group_complete_at[group["group_id"]] = {
            "at_5": cases.group_complete(group, top5),
            "at_10": cases.group_complete(group, top10),
        }
    return {
        "ranked": ranked,
        "hit_at_3": cases.fragment_hit_at(groups, top3),
        "complete_at_5": cases.complete_at(groups, top5),
        "complete_at_10": cases.complete_at(groups, top10),
        "hit_rank": cases.first_fragment_rank(groups, ranked, index, final_budget),
        "complete_rank": cases.first_complete_rank(groups, ranked, index, final_budget),
        "group_complete": group_complete_at,
        "label_ranks": rank_of_labels(ranked, case.get("labels") or {}),
    }


def evaluate_case(case: dict, method_output: dict) -> dict:
    final_budget = method_output["final_budget"]
    rows = {}
    for method in methods.METHODS:
        payload = method_output["methods"][method]
        evaluated = evaluate_method(case, payload["ranked"], final_budget)
        evaluated["hops"] = payload.get("hops")
        rows[method] = evaluated
    return {
        "case_id": case["case_id"],
        "trajectory_id": case["trajectory_id"],
        "trajectory_case": case["trajectory_case"],
        "split": case["split"],
        "record_type": case["record_type"],
        "control": case.get("control"),
        "final_budget": final_budget,
        "hop_budget": method_output["hop_budget"],
        "methods": rows,
    }


def _rank_value(rank: int | None, final_budget: int) -> int:
    return rank if rank is not None else final_budget + 1


def aggregate(case_rows: list[dict], final_budget: int) -> dict:
    if not case_rows:
        return {"cases": 0}
    out = {"cases": len(case_rows), "methods": {}}
    for method in methods.METHODS:
        rows = [row["methods"][method] for row in case_rows]
        out["methods"][method] = {
            "hit_at_3": sum(1 for row in rows if row["hit_at_3"]) / len(rows),
            "complete_at_5": sum(1 for row in rows if row["complete_at_5"]) / len(rows),
            "complete_at_10": sum(1 for row in rows if row["complete_at_10"]) / len(rows),
            "hit_at_3_count": sum(1 for row in rows if row["hit_at_3"]),
            "complete_at_5_count": sum(1 for row in rows if row["complete_at_5"]),
            "complete_at_10_count": sum(1 for row in rows if row["complete_at_10"]),
            "mean_complete_rank": sum(_rank_value(row["complete_rank"], final_budget) for row in rows) / len(rows),
            "mean_hit_rank": sum(_rank_value(row["hit_rank"], final_budget) for row in rows) / len(rows),
        }
    return out


def paired(case_rows: list[dict], final_budget: int) -> dict:
    out = {}
    for baseline in methods.METHODS:
        if baseline == "memoryflow":
            continue
        wins = ties = losses = 0
        hit_wins = hit_ties = hit_losses = 0
        for row in case_rows:
            memory = row["methods"]["memoryflow"]
            other = row["methods"][baseline]
            a = _rank_value(memory["complete_rank"], final_budget)
            b = _rank_value(other["complete_rank"], final_budget)
            if a < b:
                wins += 1
            elif a == b:
                ties += 1
            else:
                losses += 1
            ha = _rank_value(memory["hit_rank"], final_budget)
            hb = _rank_value(other["hit_rank"], final_budget)
            if ha < hb:
                hit_wins += 1
            elif ha == hb:
                hit_ties += 1
            else:
                hit_losses += 1
        out[baseline] = {
            "complete_rank": {"win": wins, "tie": ties, "loss": losses},
            "hit_rank": {"win": hit_wins, "tie": hit_ties, "loss": hit_losses},
        }
    return out


def summarize(case_rows: list[dict], final_budget: int) -> dict:
    main_rows = [row for row in case_rows if not row.get("control")]
    control_rows = [row for row in case_rows if row.get("control")]
    return {
        "final_budget": final_budget,
        "main": aggregate(main_rows, final_budget),
        "control": aggregate(control_rows, final_budget),
        "all": aggregate(case_rows, final_budget),
        "paired_main": paired(main_rows, final_budget),
        "paired_all": paired(case_rows, final_budget),
        "main_case_ids": [row["case_id"] for row in main_rows],
        "control_case_ids": [row["case_id"] for row in control_rows],
    }
