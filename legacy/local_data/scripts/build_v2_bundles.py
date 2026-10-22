from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path

from memoryflow.v2_delivery import materialize_debug_rows, select_debug_example_ids, write_manifest


FULL_README = """# MemoryFlow Checkpoint A V2

Incremental correction of Checkpoint A processed data. V2 removes candidate-position leakage, enforces exact K candidate counts, adds a conflict-checked global Source catalog, and distinguishes automatic structural checks from executor-read semantic audits.

- Seed: `20260727`.
- Candidate shuffle seed: `SHA256("20260727:<example_id>:<candidate_count>")`.
- `sources.jsonl` URLs are audit-only and excluded from model-visible candidate text.
- Labels are `silver_inline_citation`, not factual citation-support judgments.
- No raw logs, webpages, models, weights, training, GPU, Attention, Anchor, or LoRA outputs are included.
"""

DEBUG_README = """# MemoryFlow Checkpoint B debug input (data-only handoff)

This is a small, self-contained 30-example subset from the unchanged Checkpoint A dev split. Every row has exactly four deterministically shuffled candidate texts and retains every silver gold Source.

It is only a debug data handoff: Checkpoint B modeling has not started. No test examples, raw citation IDs, URLs, raw logs, models, weights, or model outputs are present.
"""


def load_jsonl(path: Path) -> list[dict]:
    with path.open("r", encoding="utf-8") as handle:
        return [json.loads(line) for line in handle]


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")


def ignore_cache(_directory: str, names: list[str]) -> set[str]:
    return {name for name in names if name in {"__pycache__", ".pytest_cache"} or name.endswith((".pyc", ".egg-info"))}


def reset_target(target: Path, remote_root: Path) -> None:
    if target.parent.resolve() != remote_root.resolve() or target.name not in {"checkpoint_a_v2", "checkpoint_b_debug"}:
        raise ValueError(f"unsafe bundle target: {target}")
    if target.exists():
        shutil.rmtree(target)
    target.mkdir(parents=True)


def copy_code(root: Path, target: Path, include_scripts: bool) -> None:
    shutil.copy2(root / "pyproject.toml", target / "pyproject.toml")
    shutil.copytree(root / "src", target / "src", ignore=ignore_cache)
    shutil.copytree(root / "tests", target / "tests", ignore=ignore_cache)
    if include_scripts:
        shutil.copytree(root / "scripts", target / "scripts", ignore=ignore_cache)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", type=Path, required=True)
    parser.add_argument("--expected-v1-manifest-hash", required=True)
    args = parser.parse_args()
    root = args.project_root.resolve()
    remote = root / "remote_bundle"
    v1_manifest = remote / "checkpoint_a/MANIFEST.sha256"
    if sha256(v1_manifest) != args.expected_v1_manifest_hash.upper():
        raise SystemExit("V1 manifest baseline changed; refusing V2 build")
    examples = load_jsonl(root / "data/processed/citation_examples.jsonl")
    candidates = load_jsonl(root / "data/processed/candidate_sets.jsonl")
    sources = load_jsonl(root / "data/processed/sources.jsonl")
    splits = json.loads((root / "data/processed/splits.json").read_text(encoding="utf-8"))

    v2 = remote / "checkpoint_a_v2"
    reset_target(v2, remote)
    copy_code(root, v2, include_scripts=True)
    (v2 / "README_REMOTE.md").write_text(FULL_README, encoding="utf-8")
    data = v2 / "data"
    data.mkdir()
    for name in ("citation_examples.jsonl", "candidate_sets.jsonl", "sources.jsonl", "splits.json"):
        shutil.copy2(root / "data/processed" / name, data / name)
    reports = v2 / "reports"
    reports.mkdir()
    shutil.copy2(root / "data/interim/run_audit.json", reports / "run_audit.json")
    for name in (
        "dataset_report.json", "dataset_report.md", "candidate_position_report.json",
        "automatic_structure_audit_30.jsonl", "semantic_audit_30.jsonl", "semantic_audit_30.md",
        "pytest_output_v2.txt",
    ):
        shutil.copy2(root / "reports" / name, reports / name)
    write_manifest(v2)

    debug = remote / "checkpoint_b_debug"
    reset_target(debug, remote)
    copy_code(root, debug, include_scripts=False)
    (debug / "README_REMOTE.md").write_text(DEBUG_README, encoding="utf-8")
    selected = select_debug_example_ids(examples, candidates, splits, size=30, seed=20260727)
    debug_rows = materialize_debug_rows(selected, examples, candidates, sources)
    write_jsonl(debug / "data/debug_examples.jsonl", debug_rows)
    debug_reports = debug / "reports"
    debug_reports.mkdir()
    single_count = sum(len(row["gold_source_ids"]) == 1 for row in debug_rows)
    debug_report = {
        "seed": 20260727,
        "source_split": "dev",
        "sample_count": len(debug_rows),
        "single_positive_count": single_count,
        "multi_positive_count": len(debug_rows) - single_count,
        "run_count": len({row["run_id"] for row in debug_rows}),
        "run_ids": sorted({row["run_id"] for row in debug_rows}),
        "example_ids": selected,
        "all_candidate_counts_exactly_4": all(len(row["candidates"]) == 4 for row in debug_rows),
    }
    (debug_reports / "debug_subset_report.json").write_text(
        json.dumps(debug_report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    shutil.copy2(root / "reports/candidate_position_report.json", debug_reports / "candidate_position_report.json")
    shutil.copy2(root / "reports/semantic_audit_30.md", debug_reports / "semantic_audit_30.md")
    write_manifest(debug)
    debug_size = sum(path.stat().st_size for path in debug.rglob("*") if path.is_file())
    if debug_size > 5 * 1024 * 1024:
        raise SystemExit(f"debug bundle exceeds 5 MiB: {debug_size}")
    if sha256(v1_manifest) != args.expected_v1_manifest_hash.upper():
        raise SystemExit("V1 manifest changed during V2 build")


if __name__ == "__main__":
    main()
