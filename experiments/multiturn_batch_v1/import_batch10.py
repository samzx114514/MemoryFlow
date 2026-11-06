#!/usr/bin/env python3
"""Import contextual64_v4 targets into the unified two-round format.

Selection is per trajectory. Each recipe fixes the target, the evidence group,
A (round-1 evidence), B (round-2 evidence), optional same-group context, and a
controlled intermediate conclusion. The original candidate pool is deduplicated
by normalized source text: the same material at another position is one source,
and all its positions are kept as occurrences/alternatives.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import cases

UNIT_RE = re.compile(r"^(?P<artifact>.+):u(?P<start>\d+)-(?P<end>\d+)$")


def parse_unit(unit_id: str) -> dict:
    match = UNIT_RE.match(unit_id)
    if not match:
        raise SystemExit(f"cannot parse unit id: {unit_id}")
    return {
        "unit_id": unit_id,
        "artifact_id": match.group("artifact"),
        "start": int(match.group("start")),
        "end": int(match.group("end")),
        "canonical_id": cases.canonical_id(match.group("artifact"), int(match.group("start")), int(match.group("end"))),
    }


def load_units(case_dir: Path) -> dict[str, dict]:
    units = {}
    with (case_dir / "source_units.jsonl").open(encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                unit = json.loads(line)
                units[unit["id"]] = unit
    return units


def source_key(text: str) -> str:
    return hashlib.sha256(cases.normalise(text).encode("utf-8")).hexdigest()


def build_source_pool(units: dict[str, dict]) -> dict[str, dict]:
    """One representative per normalized source text; all positions kept."""
    pool: dict[str, dict] = {}
    for unit in units.values():
        key = source_key(unit["text"])
        entry = pool.get(key)
        if entry is None:
            entry = {
                "source_key": key,
                "representative": unit,
                "text": unit["text"],
                "units": [],
            }
            pool[key] = entry
        entry["units"].append(unit)
        current = entry["representative"]
        if (unit["event_index"], unit["id"]) < (current["event_index"], current["id"]):
            entry["representative"] = unit
    return pool


def representative(pool: dict[str, dict], unit: dict) -> dict:
    return pool[source_key(unit["text"])]["representative"]


def material(unit: dict, role: str, index: int) -> dict:
    return {
        "unit_id": unit["id"],
        "artifact_id": unit["artifact_id"],
        "start": unit["start"],
        "end": unit["end"],
        "text": unit["text"],
        "role": role,
        "position": {"slot": "material", "index": index},
    }


def merge_same_source_items(items: list[dict]) -> list[dict]:
    """Merge truncated duplicates of the same title/material inside one group."""
    def norm_alt(alt: dict) -> str:
        text = cases.normalise(alt.get("text") or "")
        return text.rstrip(".… ")

    merged: list[dict] = []
    consumed: set[int] = set()
    for index, item in enumerate(items):
        if index in consumed:
            continue
        alternatives = list(item["alternatives"])
        texts = [norm_alt(alt) for alt in alternatives]
        for other_index in range(index + 1, len(items)):
            if other_index in consumed:
                continue
            other = items[other_index]
            other_alts = list(other["alternatives"])
            other_texts = [norm_alt(alt) for alt in other_alts]
            related = False
            for left in texts:
                for right in other_texts:
                    if len(left) >= 30 and len(right) >= 30 and (left.startswith(right) or right.startswith(left)):
                        related = True
                        break
                if related:
                    break
            if related:
                alternatives.extend(other_alts)
                consumed.add(other_index)
        merged.append({"primary": item["primary"], "alternatives": alternatives})
    return merged


def build_case(recipe: dict, units: dict[str, dict], gt_entry: dict, pool: dict[str, dict], case_dir: Path) -> dict:
    case_id = recipe["target_id"]
    target = gt_entry["target"]
    a_unit = units[recipe["A"]]
    b_unit = units[recipe["B"]]
    a_rep = representative(pool, a_unit)
    b_rep = representative(pool, b_unit)
    a_key = source_key(a_unit["text"])
    b_key = source_key(b_unit["text"])
    a_text = cases.normalise(a_unit["text"])
    b_text = cases.normalise(b_unit["text"])

    # evidence source keys are never used as distractors
    evidence_keys: set[str] = set()
    groups = []
    for group in gt_entry.get("answer_groups") or []:
        items = []
        for item in group.get("all_of") or []:
            primary = item["primary"]
            primary_key = source_key(primary["text"])
            evidence_keys.add(primary_key)
            alternatives = []
            for variant in pool[primary_key]["units"]:
                alternatives.append(
                    {"artifact_id": variant["artifact_id"], "start": variant["start"],
                     "end": variant["end"], "text": variant["text"]}
                )
            for occurrence in item.get("equivalent_occurrences") or []:
                alternatives.append(
                    {"artifact_id": occurrence["artifact_id"], "start": occurrence["start"],
                     "end": occurrence["end"], "text": occurrence.get("text", "")}
                )
                evidence_keys.add(source_key(occurrence.get("text", "")))
            items.append({
                "primary": {"artifact_id": primary["artifact_id"], "start": primary["start"],
                            "end": primary["end"], "text": primary["text"]},
                "alternatives": alternatives,
            })
        groups.append({"group_id": group["id"], "coverage": group.get("coverage", "full"), "items": merge_same_source_items(items) if recipe.get("merge_same_source", True) else items})

    # deterministic distractors from non-evidence, non-A/B sources
    def key_hash(value: str) -> str:
        return hashlib.sha256(value.encode("utf-8")).hexdigest()

    distractors = []
    for key, entry in sorted(pool.items(), key=lambda item: key_hash(item[0])):
        if key in evidence_keys or key in (a_key, b_key):
            continue
        text = cases.normalise(entry["text"])
        if not text or a_text in text or text in a_text or b_text in text or text in b_text:
            continue
        if len(text) < 25:
            continue
        distractors.append(entry["representative"])
        if len(distractors) >= 8:
            break

    def round_materials(primary: dict, primary_role: str, extras: list[str], exclude_key: str) -> list[dict]:
        chosen = [primary]
        seen = {source_key(primary["text"])}
        for unit_id in extras:
            unit = units[unit_id]
            key = source_key(unit["text"])
            if key == exclude_key or key in seen:
                continue
            seen.add(key)
            chosen.append(representative(pool, unit))
        for unit in distractors:
            key = source_key(unit["text"])
            if key == exclude_key or key in seen:
                continue
            seen.add(key)
            chosen.append(unit)
        return [material(unit, primary_role if index == 0 else "distractor", index)
                for index, unit in enumerate(chosen, start=1)]

    r1_materials = round_materials(a_rep, "evidence_a", recipe.get("r1_extras", []), b_key)
    r2_materials = round_materials(b_rep, "evidence_b", recipe.get("r2_extras", []), a_key)
    rounds = [
        {
            "round": 1,
            "question": recipe.get("r1_question", "According to the materials, what is the key earlier statement?"),
            "inputs": r1_materials,
            "output": {"text": recipe["intermediate"], "sha256": cases.sha256_text(recipe["intermediate"]),
                       "origin": "controlled_output"},
            "transmission": [],
        },
        {
            "round": 2,
            "question": recipe.get("r2_question", "Using the earlier statement and the new material, write the final sentence."),
            "inputs": r2_materials,
            "output": {"text": target["text"], "sha256": cases.sha256_text(target["text"]),
                       "origin": "recorded_target"},
            "transmission": [
                {"from_round": 1, "unit_id": "round1_output", "text": recipe["intermediate"],
                 "sha256": cases.sha256_text(recipe["intermediate"]),
                 "position": {"slot": "earlier_finding", "index": 0}}
            ],
        },
    ]

    candidates = []
    used: dict[str, list[dict]] = {}
    for round_record in rounds:
        for index, item in enumerate(round_record["inputs"], start=1):
            key = source_key(item["text"])
            used.setdefault(key, []).append(
                {"round": round_record["round"], "unit_id": item["unit_id"], "role": item["role"],
                 "position": {"slot": "material", "index": index}}
            )
    for key, entry in sorted(pool.items()):
        candidates.append({
            "canonical_id": cases.canonical_id(entry["representative"]["artifact_id"],
                                               entry["representative"]["start"], entry["representative"]["end"]),
            "artifact_id": entry["representative"]["artifact_id"],
            "start": entry["representative"]["start"],
            "end": entry["representative"]["end"],
            "text": entry["text"],
            "occurrences": used.get(key, []),
            "pool_only": key not in used,
        })

    # check no A source text leaks into round 2
    leak = []
    for item in r2_materials:
        text = cases.normalise(item["text"])
        if a_text in text or text in a_text:
            leak.append(item["unit_id"])

    case = {
        "schema": cases.SCHEMA,
        "case_id": case_id,
        "trajectory_id": case_id.split(":")[0],
        "trajectory_case": recipe["case"],
        "split": "dev",
        "record_type": "controlled",
        "control": recipe.get("control"),
        "analysis_pool": recipe.get("analysis_pool", "all"),
        "target": {
            "text": target["text"], "sha256": cases.sha256_text(target["text"]),
            "origin": "recorded_target",
            "artifact_id": target["artifact_id"], "start": target["start"], "end": target["end"],
            "original_target": {"text": target["text"], "artifact_id": target["artifact_id"],
                                "start": target["start"], "end": target["end"],
                                "event_index": target.get("event_index")},
        },
        "rounds": rounds,
        "candidates": candidates,
        "evidence_groups": groups,
        "labels": {
            "A": [cases.canonical_id(a_rep["artifact_id"], a_rep["start"], a_rep["end"])],
            "B": [cases.canonical_id(b_rep["artifact_id"], b_rep["start"], b_rep["end"])],
        },
        "provenance": {
            "case_dir": str(case_dir),
            "target_id": case_id,
            "group_id": recipe.get("group_id"),
            "A_unit": recipe["A"], "B_unit": recipe["B"],
            "same_source_policy": "normalized source text; representative unit + all occurrences",
            "round2_a_source_leaks": leak,
            "note": "two-round controlled construction from contextual64_v4; not an original request snapshot",
        },
    }
    return case


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--subset", required=True, help="contextual64_v4 root")
    parser.add_argument("--recipe", required=True, help="recipe json (list or single object)")
    parser.add_argument("--out", required=True)
    args = parser.parse_args(argv)

    subset = Path(args.subset)
    recipes = cases.read_json(args.recipe)
    if isinstance(recipes, dict):
        recipes = [recipes]
    out = Path(args.out)
    case_dir = out / "cases"
    case_dir.mkdir(parents=True, exist_ok=True)
    index = []
    for recipe in recipes:
        case = recipe["case"]
        units = load_units(subset / case)
        gt = {entry["target_id"]: entry for entry in cases.read_json(subset / case / "ground_truth.json")}
        entry = gt[recipe["target_id"]]
        pool = build_source_pool(units)
        built = build_case(recipe, units, entry, pool, subset / case)
        issues = cases.validate_case(built)
        if issues:
            raise SystemExit(f"{recipe['target_id']}: validation failed: {issues}")
        slug = f"{recipe['case']}_{recipe['target_id'].split(':')[-1]}"
        path = case_dir / f"{slug}.json"
        cases.write_json(path, built)
        index.append({
            "short": slug,
            "case_id": built["case_id"],
            "trajectory_id": built["trajectory_id"],
            "trajectory_case": built["trajectory_case"],
            "split": built["split"],
            "record_type": built["record_type"],
            "control": built["control"],
            "rounds": len(built["rounds"]),
            "candidates": len(built["candidates"]),
            "evidence_groups": len(built["evidence_groups"]),
            "case_path": path.relative_to(out).as_posix(),
            "matrix_path": f"matrices/{slug}.json",
            "case_sha256": cases.case_hash(built),
            "registry": cases.missing_registry(built),
        })
    manifest = {
        "schema": "memoryflow.multiturn_batch.manifest.v1",
        "created": "2026-11-06",
        "final_budget": cases.FINAL_BUDGET,
        "hop_budget": cases.HOP_BUDGET,
        "cases": index,
        "totals": {
            "cases": len(index),
            "controlled": sum(1 for row in index if row["record_type"] == "controlled"),
            "real_request": sum(1 for row in index if row["record_type"] == "real_request"),
            "dev": sum(1 for row in index if row["split"] == "dev"),
            "eval": sum(1 for row in index if row["split"] == "eval"),
            "controls": sum(1 for row in index if row["control"]),
            "trajectories": len({row["trajectory_id"] for row in index}),
        },
    }
    cases.write_json(out / "manifest.json", manifest)
    print(json.dumps({"out": str(out), "totals": manifest["totals"],
                      "cases": [row["short"] for row in index]}, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

