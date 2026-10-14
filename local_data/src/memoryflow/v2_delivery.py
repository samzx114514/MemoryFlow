from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any, Iterable


def _debug_rank(seed: int, example_id: str) -> str:
    return hashlib.sha256(f"{seed}:debug:{example_id}".encode("utf-8")).hexdigest()


def select_debug_example_ids(
    examples: list[dict[str, Any]],
    candidate_rows: list[dict[str, Any]],
    splits: dict[str, Any],
    size: int = 30,
    seed: int = 20260727,
) -> list[str]:
    example_by_id = {example["example_id"]: example for example in examples}
    row_by_id = {row["example_id"]: row for row in candidate_rows}
    dev_ids = set(splits["dev"])
    legal = [
        example for example in examples
        if example["example_id"] in dev_ids
        and len(row_by_id[example["example_id"]]["candidate_sets"].get("4", [])) == 4
    ]
    if len(legal) < size:
        raise ValueError(f"only {len(legal)} legal dev K=4 examples")
    legal.sort(key=lambda item: _debug_rank(seed, item["example_id"]))
    selected: list[str] = []

    # First guarantee representation from every dev run that has a legal row.
    for run_id in splits["dev_runs"]:
        choices = [item for item in legal if item["run_id"] == run_id]
        if not choices:
            raise ValueError(f"dev run has no legal K=4 example: {run_id}")
        choices.sort(key=lambda item: (len(item["gold_source_ids"]) == 1, _debug_rank(seed, item["example_id"])))
        selected.append(choices[0]["example_id"])

    multi = [item for item in legal if len(item["gold_source_ids"]) > 1 and item["example_id"] not in selected]
    single = [item for item in legal if len(item["gold_source_ids"]) == 1 and item["example_id"] not in selected]
    reserve_single = 1 if single and not any(len(example_by_id[item]["gold_source_ids"]) == 1 for item in selected) else 0
    for item in multi:
        if len(selected) >= size - reserve_single:
            break
        selected.append(item["example_id"])
    if reserve_single:
        selected.append(single.pop(0)["example_id"])
    remaining = [item for item in legal if item["example_id"] not in selected]
    remaining.sort(key=lambda item: _debug_rank(seed, item["example_id"]))
    selected.extend(item["example_id"] for item in remaining[: size - len(selected)])
    if len(selected) != size or len(selected) != len(set(selected)):
        raise ValueError("debug subset selection did not produce unique requested size")
    return selected


def materialize_debug_rows(
    selected_ids: Iterable[str],
    examples: list[dict[str, Any]],
    candidate_rows: list[dict[str, Any]],
    source_catalog: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    example_by_id = {example["example_id"]: example for example in examples}
    row_by_id = {row["example_id"]: row for row in candidate_rows}
    source_by_id = {source["id"]: source for source in source_catalog}
    output = []
    for example_id in selected_ids:
        example = example_by_id[example_id]
        candidate_ids = row_by_id[example_id]["candidate_sets"]["4"]
        if len(candidate_ids) != 4:
            raise ValueError(f"debug example lacks exact K=4 pool: {example_id}")
        candidates = [{
            "id": source_id,
            "title": source_by_id[source_id]["title"],
            "memory_text": source_by_id[source_id]["memory_text"],
        } for source_id in candidate_ids]
        if not set(example["gold_source_ids"]).issubset(candidate_ids):
            raise ValueError(f"debug pool lost gold: {example_id}")
        output.append({
            "example_id": example_id,
            "run_id": example["run_id"],
            "split": "dev",
            "target": example["target"],
            "candidates": candidates,
            "gold_source_ids": example["gold_source_ids"],
            "candidate_count": 4,
            "label_type": "silver_inline_citation",
        })
    return output


def write_manifest(root: Path) -> Path:
    lines = []
    for path in sorted(file for file in root.rglob("*") if file.is_file() and file.name != "MANIFEST.sha256"):
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            while chunk := handle.read(1024 * 1024):
                digest.update(chunk)
        lines.append(f"{digest.hexdigest()}  {path.relative_to(root).as_posix()}")
    manifest = root / "MANIFEST.sha256"
    manifest.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return manifest


def verify_manifest(root: Path) -> bool:
    manifest = root / "MANIFEST.sha256"
    for line in manifest.read_text(encoding="utf-8").splitlines():
        expected, relative = line.split("  ", 1)
        digest = hashlib.sha256()
        with (root / relative).open("rb") as handle:
            while chunk := handle.read(1024 * 1024):
                digest.update(chunk)
        if digest.hexdigest() != expected:
            return False
    return True

