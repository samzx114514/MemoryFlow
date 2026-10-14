"""Integrity gates shared by C3C training and one-shot Blind evaluation."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Mapping, Sequence


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def verify_frozen_directory(path: Path) -> dict[str, str]:
    frozen = json.loads((path / "FROZEN.json").read_text())
    observed = {name: file_sha256(path / name) for name in frozen["files"]}
    expected = {name: item["sha256"] for name, item in frozen["files"].items()}
    if observed != expected:
        raise ValueError(f"frozen hash mismatch in {path}")
    return observed


def require_checkpoint_before_blind(metadata: Mapping, checkpoint: Path) -> None:
    if metadata.get("status") != "FROZEN_BEFORE_BLIND":
        raise ValueError("checkpoint is not frozen before Blind access")
    if metadata.get("checkpoint_sha256") != file_sha256(checkpoint):
        raise ValueError("checkpoint hash mismatch")
    if metadata.get("blind_used_for_selection") is not False:
        raise ValueError("Blind selection guard missing")


def validate_complete_method_rows(rows: Sequence[Mapping], examples: Sequence[Mapping], methods: Sequence[str]) -> None:
    expected = {(row["example_id"], method) for row in examples for method in methods}
    observed = {(row["example_id"], row["method"]) for row in rows}
    if observed != expected or len(rows) != len(expected):
        raise ValueError("method/example coverage mismatch")
    candidates = {row["example_id"]: set(row["candidate_source_ids"]) for row in examples}
    for row in rows:
        ranking = list(row["ranking"])
        if len(ranking) != 8 or len(set(ranking)) != 8 or set(ranking) != candidates[row["example_id"]]:
            raise ValueError("incomplete or duplicate ranking")
