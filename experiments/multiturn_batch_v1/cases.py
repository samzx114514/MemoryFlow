#!/usr/bin/env python3
"""Unified multi-turn case format, validation and evidence-coverage rules.

A case is one target sentence produced at the end of a multi-round episode. It
records the trajectory, the target position, every round's inputs/outputs, the
intermediate transmissions, the original candidate pool and the supporting
evidence groups. ``record_type`` separates real recorded requests from
controlled reconstructions.

Coverage follows the frozen evaluation rule used for the 47-target table:
  * a selected window covers a fragment only when every non-whitespace character
    of the fragment lies inside the union of selected windows on the same artifact;
  * a group is complete when every item has at least one alternative covered;
  * a target is complete when at least one ``full`` group is complete (groups are OR).
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

SCHEMA = "memoryflow.multiturn_case.v1"
MATRIX_SCHEMA = "memoryflow.multiturn_matrices.v1"
FINAL_BUDGET = 10
HOP_BUDGET = 5
TIE_TOLERANCE = 1e-6


# --------------------------------------------------------------------------- ids


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def canonical_id(artifact_id: str, start: int, end: int) -> str:
    return f"{artifact_id}#{start}-{end}"


def read_json(path: str | Path) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_json(path: str | Path, value: Any) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def case_hash(case: dict) -> str:
    return sha256_text(json.dumps(case, ensure_ascii=False, sort_keys=True))


# --------------------------------------------------------------------------- validation


def validate_case(case: dict) -> list[str]:
    """Return blocking problems; an empty list means the case is importable."""
    issues: list[str] = []
    if case.get("schema") != SCHEMA:
        issues.append(f"schema must be {SCHEMA}")
    for key in ("case_id", "trajectory_id", "trajectory_case", "split", "record_type"):
        if not case.get(key):
            issues.append(f"missing {key}")
    if case.get("record_type") not in {"controlled", "real_request"}:
        issues.append("record_type must be controlled or real_request")
    target = case.get("target") or {}
    if not (target.get("text") or "").strip():
        issues.append("target.text is empty")
    if target.get("origin") not in {"recorded_target", "controlled_output"}:
        issues.append("target.origin must be recorded_target or controlled_output")
    if case.get("record_type") == "real_request" and target.get("origin") == "recorded_target":
        if target.get("artifact_id") is None or target.get("start") is None or target.get("end") is None:
            issues.append("recorded target needs artifact_id/start/end")

    rounds = case.get("rounds") or []
    if len(rounds) < 2:
        issues.append("at least two rounds are required")
    previous_outputs: dict[int, str] = {}
    for index, round_record in enumerate(rounds, start=1):
        if round_record.get("round") != index:
            issues.append(f"round numbers must be sequential; got {round_record.get('round')} at position {index}")
        inputs = round_record.get("inputs") or []
        if not inputs:
            issues.append(f"round {index} has no inputs")
        output = round_record.get("output") or {}
        if not (output.get("text") or "").strip():
            issues.append(f"round {index} has no output text")
        for material in inputs:
            for key in ("unit_id", "artifact_id", "start", "end", "text", "role"):
                if material.get(key) in (None, ""):
                    issues.append(f"round {index} material lacks {key}")
            if material.get("start", 0) >= material.get("end", 0):
                issues.append(f"round {index} material has empty span")
        for transmission in round_record.get("transmission") or []:
            source_round = transmission.get("from_round")
            if source_round not in previous_outputs:
                issues.append(f"round {index} transmission references missing round {source_round}")
            elif previous_outputs[source_round] != transmission.get("text"):
                issues.append(f"round {index} transmission text differs from round {source_round} output")
            if not transmission.get("position"):
                issues.append(f"round {index} transmission lacks position")
        previous_outputs[index] = output.get("text", "")

    candidates = case.get("candidates") or []
    if not candidates:
        issues.append("candidate pool is empty")
    seen: set[str] = set()
    for candidate in candidates:
        cid = candidate.get("canonical_id")
        if not cid:
            issues.append("candidate lacks canonical_id")
            continue
        if cid in seen:
            issues.append(f"duplicate canonical candidate: {cid}")
        seen.add(cid)
        for key in ("artifact_id", "start", "end", "text"):
            if candidate.get(key) in (None, ""):
                issues.append(f"candidate {cid} lacks {key}")
        if candidate.get("start", 0) >= candidate.get("end", 0):
            issues.append(f"candidate {cid} has empty span")

    for round_record in rounds:
        for material in round_record.get("inputs") or []:
            cid = canonical_id(material["artifact_id"], material["start"], material["end"])
            if cid not in seen:
                issues.append(f"round {round_record['round']} material missing from candidates: {cid}")

    groups = case.get("evidence_groups") or []
    if not groups:
        issues.append("evidence_groups is empty")
    for group in groups:
        if group.get("coverage") not in {"full", "partial"}:
            issues.append(f"group {group.get('group_id')} coverage must be full or partial")
        items = group.get("items") or []
        if not items:
            issues.append(f"group {group.get('group_id')} has no items")
        for item in items:
            primary = item.get("primary") or {}
            for key in ("artifact_id", "start", "end", "text"):
                if primary.get(key) in (None, ""):
                    issues.append(f"group {group.get('group_id')} item primary lacks {key}")
            alternatives = item.get("alternatives") or []
            if not alternatives:
                issues.append(f"group {group.get('group_id')} item has no alternatives")
    return issues


def missing_registry(case: dict) -> dict:
    """Non-blocking gaps that must be registered before scoring."""
    registry: dict[str, list[str]] = {"missing_inputs": [], "missing_labels": [], "warnings": []}
    rounds = case.get("rounds") or []
    for index, round_record in enumerate(rounds, start=1):
        if not round_record.get("inputs"):
            registry["missing_inputs"].append(f"round{index}:inputs")
        if not (round_record.get("output") or {}).get("text"):
            registry["missing_inputs"].append(f"round{index}:output")
        if index > 1 and not (round_record.get("transmission") or []):
            registry["missing_inputs"].append(f"round{index}:transmission")
    if not case.get("evidence_groups"):
        registry["missing_labels"].append("evidence_groups")
    if not case.get("candidates"):
        registry["missing_inputs"].append("candidates")
    if case.get("record_type") == "controlled":
        registry["warnings"].append("controlled construction; not an original request snapshot")
    return registry


# --------------------------------------------------------------------------- coverage


def nonws(text: str) -> int:
    return sum(1 for character in text if not character.isspace())


def covered_fragment(fragment: dict, windows: list[tuple[str, int, int]]) -> bool:
    artifact_id = fragment["artifact_id"]
    start = int(fragment["start"])
    end = int(fragment["end"])
    text = fragment.get("text") or ""
    total = nonws(text)
    if total == 0:
        return False
    spans = sorted(
        (max(start, left), min(end, right))
        for wid, left, right in windows
        if wid == artifact_id and min(end, right) > max(start, left)
    )
    merged: list[list[int]] = []
    for left, right in spans:
        if merged and left <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], right)
        else:
            merged.append([left, right])
    covered = 0
    for left, right in merged:
        covered += nonws(text[left - start : right - start])
    return covered == total


def group_complete(group: dict, windows: list[tuple[str, int, int]]) -> bool:
    for item in group["items"]:
        alternatives = item.get("alternatives") or [item.get("primary")]
        if not any(covered_fragment(alt, windows) for alt in alternatives if alt):
            return False
    return True


def complete_at(groups: list[dict], windows: list[tuple[str, int, int]]) -> bool:
    full = [group for group in groups if group.get("coverage") == "full" and group.get("items")]
    return any(group_complete(group, windows) for group in full)


def fragment_hit_at(groups: list[dict], windows: list[tuple[str, int, int]]) -> bool:
    for group in groups:
        if group.get("coverage") != "full":
            continue
        for item in group["items"]:
            for alternative in item.get("alternatives") or [item.get("primary")]:
                if alternative and covered_fragment(alternative, windows):
                    return True
    return False


def first_fragment_rank(groups: list[dict], ranked_ids: list[str], index: dict[str, dict], limit: int) -> int | None:
    windows: list[tuple[str, int, int]] = []
    for rank, cid in enumerate(ranked_ids[:limit], start=1):
        candidate = index[cid]
        windows.append((candidate["artifact_id"], candidate["start"], candidate["end"]))
        if fragment_hit_at(groups, windows):
            return rank
    return None


def first_complete_rank(groups: list[dict], ranked_ids: list[str], index: dict[str, dict], limit: int) -> int | None:
    windows: list[tuple[str, int, int]] = []
    for rank, cid in enumerate(ranked_ids[:limit], start=1):
        candidate = index[cid]
        windows.append((candidate["artifact_id"], candidate["start"], candidate["end"]))
        if complete_at(groups, windows):
            return rank
    return None


# --------------------------------------------------------------------------- ranking helpers


def stable_ranking(source_ids: list[str], scores: dict[str, float], tolerance: float = TIE_TOLERANCE) -> list[str]:
    ordered = sorted(source_ids, key=lambda cid: (-scores[cid], cid))
    groups: list[list[str]] = []
    for cid in ordered:
        if not groups or abs(scores[cid] - scores[groups[-1][0]]) >= tolerance:
            groups.append([cid])
        else:
            groups[-1].append(cid)
    result: list[str] = []
    for group in groups:
        result.extend(sorted(group, key=lambda cid: hashlib.sha256(cid.encode("utf-8")).hexdigest()))
    return result


def evidence_groups_from_truth(entry: dict) -> list[dict]:
    groups = []
    for group in entry.get("answer_groups") or []:
        items = []
        for row in group.get("all_of") or []:
            primary = row["primary"]
            alternatives = [
                {
                    "artifact_id": primary["artifact_id"],
                    "start": primary["start"],
                    "end": primary["end"],
                    "text": primary["text"],
                }
            ]
            for occurrence in row.get("equivalent_occurrences") or []:
                alternatives.append(
                    {
                        "artifact_id": occurrence["artifact_id"],
                        "start": occurrence["start"],
                        "end": occurrence["end"],
                        "text": occurrence.get("text", ""),
                    }
                )
            items.append({"primary": alternatives[0], "alternatives": alternatives})
        groups.append(
            {
                "group_id": group["id"],
                "coverage": group.get("coverage", "full"),
                "items": items,
            }
        )
    return groups


def build_candidate_pool(rounds: list[dict]) -> list[dict]:
    pool: dict[str, dict] = {}
    for round_record in rounds:
        round_number = round_record["round"]
        for index, material in enumerate(round_record["inputs"], start=1):
            cid = canonical_id(material["artifact_id"], material["start"], material["end"])
            entry = pool.setdefault(
                cid,
                {
                    "canonical_id": cid,
                    "artifact_id": material["artifact_id"],
                    "start": material["start"],
                    "end": material["end"],
                    "text": material["text"],
                    "occurrences": [],
                },
            )
            entry["occurrences"].append(
                {
                    "round": round_number,
                    "unit_id": material["unit_id"],
                    "role": material.get("role"),
                    "position": material.get("position") or {"slot": "material", "index": index},
                }
            )
    return [pool[key] for key in sorted(pool)]
