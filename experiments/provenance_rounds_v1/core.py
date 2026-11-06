"""Shared helpers for the controlled two-round provenance experiment.

The protocol is a *controlled* multi-round reconstruction on top of the GenMem
batch10 v3 archive. The archive does not keep per-request snapshots, so the two
rounds below are constructed here, frozen, and then replayed; they are not
recovered original requests.
"""

from __future__ import annotations

import hashlib
import json
import re
import zipfile
from pathlib import Path

SCHEMA_SPEC = "provenance_rounds_v1.spec.v1"
ARCHIVE_MEMBER_ROOT = "genmem_batch10_selection_v1"
SHINGLE = 8
LCS_LIMIT = 40
FIXED_QUERY = "Identify earlier text relevant to the supplied statement."


class SpecError(RuntimeError):
    """A frozen invariant of the controlled sample failed."""


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_text(text: str) -> str:
    return sha256_bytes(text.encode("utf-8"))


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def canonical(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def write_json(path: str | Path, value: object) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )


def read_json(path: str | Path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def read_jsonl(path: str | Path) -> list[dict]:
    with Path(path).open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


# --------------------------------------------------------------------------- archive


def _member_candidates(name: str) -> list[str]:
    return [f"{ARCHIVE_MEMBER_ROOT}/{name}", name]


def open_member(source: str | Path, name: str) -> bytes:
    """Read ``name`` from the zip archive or from an extracted directory."""
    source = Path(source)
    if source.is_dir():
        for candidate in _member_candidates(name):
            path = source / candidate
            if path.exists():
                return path.read_bytes()
        raise SpecError(f"member not found under {source}: {name}")
    with zipfile.ZipFile(source) as archive:
        for candidate in _member_candidates(name):
            try:
                return archive.read(candidate)
            except KeyError:
                continue
    raise SpecError(f"member not found in {source}: {name}")


def load_units(source: str | Path, case: str) -> dict[str, dict]:
    raw = open_member(source, f"contextual64_v4/{case}/source_units.jsonl").decode("utf-8")
    units: dict[str, dict] = {}
    for line in raw.splitlines():
        if line.strip():
            unit = json.loads(line)
            units[unit["id"]] = unit
    return units


def load_truth(source: str | Path, case: str) -> list[dict]:
    return json.loads(open_member(source, f"contextual64_v4/{case}/ground_truth.json").decode("utf-8"))


def load_targets(source: str | Path) -> dict[str, dict]:
    raw = open_member(source, "contextual64_v4/tasks.jsonl").decode("utf-8")
    targets: dict[str, dict] = {}
    for line in raw.splitlines():
        if line.strip():
            task = json.loads(line)
            targets[task["id"]] = task
    return targets


# --------------------------------------------------------------------------- text checks


def normalise(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().lower()


def tokens(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", normalise(text))


def shingles(words: list[str], size: int = SHINGLE) -> set[tuple[str, ...]]:
    return {tuple(words[index : index + size]) for index in range(max(0, len(words) - size + 1))}


def longest_common_substring(a: str, b: str) -> tuple[int, str]:
    """Length and text of the longest common contiguous character run."""
    if not a or not b:
        return 0, ""
    best = 0
    best_end = 0
    previous = [0] * (len(b) + 1)
    for i, char_a in enumerate(a, start=1):
        current = [0] * (len(b) + 1)
        for j, char_b in enumerate(b, start=1):
            if char_a == char_b:
                value = previous[j - 1] + 1
                current[j] = value
                if value > best:
                    best = value
                    best_end = i
        previous = current
    return best, a[best_end - best : best_end]


def evidence_equivalence(evidence_texts: list[str], material_texts: list[str]) -> dict:
    """Check that no raw second-round material repeats an evidence passage."""
    exact_hits = []
    for evidence in evidence_texts:
        needle = normalise(evidence)
        if not needle:
            continue
        for material in material_texts:
            if needle in normalise(material):
                exact_hits.append({"evidence": evidence[:120], "material": material[:120]})
    evidence_words = [tokens(text) for text in evidence_texts]
    evidence_sets = [shingles(words) for words in evidence_words]
    max_shingles = 0
    shingle_hits = []
    for material in material_texts:
        material_set = shingles(tokens(material))
        for index, (words, shingle_set) in enumerate(zip(evidence_words, evidence_sets)):
            shared = material_set & shingle_set
            max_shingles = max(max_shingles, len(shared))
            if shared:
                shingle_hits.append(
                    {
                        "evidence_index": index,
                        "material": material[:120],
                        "shared_shingles": [" ".join(item) for item in sorted(shared)[:3]],
                    }
                )
    max_lcs = 0
    max_lcs_pair = None
    for evidence in evidence_texts:
        for material in material_texts:
            length, text = longest_common_substring(normalise(evidence), normalise(material))
            if length > max_lcs:
                max_lcs = length
                max_lcs_pair = {"evidence": evidence[:120], "material": material[:120], "text": text}
    return {
        "exact_containment_hits": exact_hits,
        "shingle_size": SHINGLE,
        "max_shared_shingles": max_shingles,
        "shingle_hits": shingle_hits,
        "max_lcs_chars": max_lcs,
        "max_lcs_pair": max_lcs_pair,
        "lcs_limit_chars": LCS_LIMIT,
        "passed": not exact_hits and max_shingles == 0 and max_lcs < LCS_LIMIT,
    }


# --------------------------------------------------------------------------- prompts


def render_materials(materials: list[dict]) -> str:
    lines = []
    for index, material in enumerate(materials, start=1):
        lines.append(f"{index}. {material['text']}")
    return "\n".join(lines)


def prompt_round1(question: str, instruction: str, materials: list[dict]) -> str:
    return (
        "You are answering a research question using materials from an earlier search session.\n\n"
        f"Materials:\n{render_materials(materials)}\n\n"
        f"Question: {question}\n{instruction}"
    )


def prompt_round2(
    question: str, instruction: str, materials: list[dict], round1_answer: str
) -> str:
    return (
        "Earlier finding from the previous step:\n"
        f"{round1_answer}\n\n"
        "You are answering a research question using materials from an earlier search session.\n\n"
        f"Materials:\n{render_materials(materials)}\n\n"
        f"Question: {question}\n{instruction}"
    )


def prompt_round2_template(question: str, instruction: str, materials: list[dict]) -> str:
    return (
        "Earlier finding from the previous step:\n"
        "[[ROUND1_ANSWER]]\n\n"
        "You are answering a research question using materials from an earlier search session.\n\n"
        f"Materials:\n{render_materials(materials)}\n\n"
        f"Question: {question}\n{instruction}"
    )


# --------------------------------------------------------------------------- spec


def resolve_material(units: dict[str, dict], unit_id: str, role: str) -> dict:
    unit = units.get(unit_id)
    if unit is None:
        raise SpecError(f"material unit does not exist: {unit_id}")
    return {
        "unit_id": unit_id,
        "artifact_id": unit["artifact_id"],
        "event_index": unit["event_index"],
        "start": unit["start"],
        "end": unit["end"],
        "text": unit["text"],
        "role": role,
    }


def group_primaries(entry: dict, group_id: str) -> list[dict]:
    groups = [group for group in entry["answer_groups"] if group["id"] == group_id]
    if len(groups) != 1:
        raise SpecError(f"expected one group {group_id}, found {len(groups)}")
    primaries = []
    for item in groups[0]["all_of"]:
        primary = item["primary"]
        primaries.append({"primary": primary, "item": item})
    return primaries


def build_spec(source: str | Path, recipe: dict) -> dict:
    case = recipe["case"]
    units = load_units(source, case)
    truths = {entry["target_id"]: entry for entry in load_truth(source, case)}
    targets = load_targets(source)
    target_id = recipe["target_id"]
    if target_id not in truths:
        raise SpecError(f"target not in ground truth: {target_id}")
    entry = truths[target_id]
    target = targets[target_id]
    if target["text"] != entry["target"]["text"]:
        raise SpecError("tasks.jsonl target text differs from ground truth")

    primaries = group_primaries(entry, recipe["group_id"])
    primary_units = {}
    equivalent_units = {}
    for row in primaries:
        for candidate_id in row["primary"].get("candidate_ids") or []:
            primary_units[candidate_id] = row
        for occurrence in row["item"].get("equivalent_occurrences") or []:
            for candidate_id in occurrence.get("candidate_ids") or []:
                equivalent_units[candidate_id] = row

    evidence = {}
    evidence_texts = {}
    for label in ("A", "B"):
        ids = recipe["evidence"][label]
        evidence[label] = [resolve_material(units, unit_id, f"evidence_{label.lower()}") for unit_id in ids]
        for material in evidence[label]:
            if material["unit_id"] not in primary_units:
                raise SpecError(f"evidence {label} unit is not a primary of {recipe['group_id']}: {material['unit_id']}")
        evidence_texts[label] = [material["text"] for material in evidence[label]]

    rounds = []
    for key in ("round1", "round2"):
        spec_round = recipe[key]
        materials = [
            resolve_material(units, item["unit"], item["role"]) for item in spec_round["materials"]
        ]
        ids = [material["unit_id"] for material in materials]
        if len(ids) != len(set(ids)):
            raise SpecError(f"{key} has duplicate material units")
        rounds.append(
            {
                "round": 1 if key == "round1" else 2,
                "question": spec_round["question"],
                "instruction": spec_round["instruction"],
                "materials": materials,
            }
        )

    r1_ids = {material["unit_id"] for material in rounds[0]["materials"]}
    r2_materials = rounds[1]["materials"]
    r2_ids = {material["unit_id"] for material in r2_materials}

    # the split must be real: A is only in round 1, B is only in round 2
    overlap_a = sorted(r1_ids & {material["unit_id"] for material in evidence["A"]})
    overlap_b = sorted(r2_ids & {material["unit_id"] for material in evidence["B"]})
    if not overlap_a or not overlap_b:
        raise SpecError("evidence must be visible in its own round")
    if r2_ids & {material["unit_id"] for material in evidence["A"]}:
        raise SpecError("round 2 raw material contains an evidence-A unit")
    if r1_ids & {material["unit_id"] for material in evidence["B"]}:
        raise SpecError("round 1 raw material contains an evidence-B unit")

    # no A or equivalent text in the raw second-round materials
    equivalents = [material["text"] for material in evidence["A"]]
    for unit_id, row in equivalent_units.items():
        unit = units.get(unit_id)
        if unit is not None:
            equivalents.append(unit["text"])
    raw_r2 = [material["text"] for material in r2_materials]
    check_a = evidence_equivalence(equivalents, raw_r2)
    if not check_a["passed"]:
        raise SpecError(f"round 2 material repeats evidence A: {check_a}")
    equivalent_unit_hits = sorted(set(r2_ids) & set(equivalent_units))
    if equivalent_unit_hits:
        raise SpecError(f"round 2 uses an equivalent-occurrence unit of A: {equivalent_unit_hits}")

    spec = {
        "schema": SCHEMA_SPEC,
        "protocol": {
            "name": "controlled_two_round_genmem",
            "label": "受控多轮验证（GenMem 材料；非原始逐次请求恢复）",
            "generation_model": "Qwen2.5-7B-Instruct (greedy, BF16)",
            "scoring_head": {"model": "Qwen2.5-7B-Instruct", "layer": 19, "head": 15},
            "scoring_query": FIXED_QUERY,
            "return_budget": recipe.get("return_budget", 5),
        },
        "source": {
            "case": case,
            "split": recipe.get("split", "dev"),
            "target_id": target_id,
            "target_number": entry["target_number"],
            "target_text": entry["target"]["text"],
            "target_artifact_id": entry["target"]["artifact_id"],
            "target_event_index": entry["target"]["event_index"],
            "group_id": recipe["group_id"],
            "label_member": f"genmem_batch10_selection_v1/contextual64_v4/{case}/ground_truth.json",
        },
        "evidence": evidence,
        "rounds": rounds,
        "checks": {
            "a_seen_in_round1": overlap_a,
            "b_seen_in_round2": overlap_b,
            "round2_without_evidence_a": check_a,
            "round2_equivalent_unit_hits": equivalent_unit_hits,
            "round1_material_units": len(r1_ids),
            "round2_material_units": len(r2_ids),
            "merged_raw_units": sorted(r1_ids | r2_ids),
        },
    }
    r1_materials = rounds[0]["materials"]
    r2_materials = rounds[1]["materials"]
    spec["rounds"][0]["prompt"] = prompt_round1(
        rounds[0]["question"], rounds[0]["instruction"], r1_materials
    )
    spec["rounds"][1]["prompt_template"] = prompt_round2_template(
        rounds[1]["question"], rounds[1]["instruction"], r2_materials
    )
    spec["spec_sha256"] = sha256_text(canonical({k: v for k, v in spec.items() if k != "spec_sha256"}))
    return spec
