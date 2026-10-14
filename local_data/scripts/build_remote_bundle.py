from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path


README = """# MemoryFlow Checkpoint A-Local remote bundle

This bundle contains only the compact citation-source recovery dataset, deterministic preprocessing code, tests, and audit reports.

Scope boundaries:

- FactStruct is the primary dataset; SP appears only in structural audit totals.
- Labels are `silver_inline_citation` mappings, not citation-truth judgments.
- No model, GPU, Attention, Anchor, LoRA, training, full log, full webpage, or raw event is included.
- Candidate files contain Source IDs only; Source visible text is stored with citation examples.
- Seed: `20260727`; split unit: run; two complete runs are dev; remaining valid runs are test; no train split.

Run tests from this directory with:

```text
python -m pytest -q
```
"""


def ignore_cache(_directory: str, names: list[str]) -> set[str]:
    return {
        name for name in names
        if name in {"__pycache__", ".pytest_cache"}
        or name.endswith((".pyc", ".egg-info"))
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", type=Path, required=True)
    parser.add_argument("--target", type=Path, required=True)
    args = parser.parse_args()
    root = args.project_root.resolve()
    target = args.target.resolve()
    expected_parent = (root / "remote_bundle").resolve()
    if target.parent != expected_parent or target.name != "checkpoint_a":
        raise SystemExit(f"refusing unexpected bundle target: {target}")
    if target.exists():
        shutil.rmtree(target)
    target.mkdir(parents=True)
    (target / "README_REMOTE.md").write_text(README, encoding="utf-8")
    shutil.copy2(root / "pyproject.toml", target / "pyproject.toml")
    for directory in ("src", "scripts", "tests"):
        shutil.copytree(root / directory, target / directory, ignore=ignore_cache)
    data_target = target / "data"
    data_target.mkdir()
    for name in ("citation_examples.jsonl", "candidate_sets.jsonl", "splits.json"):
        shutil.copy2(root / "data/processed" / name, data_target / name)
    reports_target = target / "reports"
    reports_target.mkdir()
    shutil.copy2(root / "data/interim/run_audit.json", reports_target / "run_audit.json")
    for name in ("dataset_report.json", "dataset_report.md", "manual_audit_30.jsonl", "pytest_output.txt"):
        shutil.copy2(root / "reports" / name, reports_target / name)

    forbidden_keys = {"raw_content", "cleaned_source_content", "url", "URL", "final_report", "raw_log_provenance"}
    with (data_target / "citation_examples.jsonl").open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            item = json.loads(line)
            stack = [item]
            while stack:
                value = stack.pop()
                if isinstance(value, dict):
                    bad = forbidden_keys.intersection(value)
                    if bad:
                        raise SystemExit(f"forbidden remote keys at line {line_number}: {sorted(bad)}")
                    stack.extend(value.values())
                elif isinstance(value, list):
                    stack.extend(value)
    manifest_lines = []
    for path in sorted(file for file in target.rglob("*") if file.is_file() and file.name != "MANIFEST.sha256"):
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            while chunk := handle.read(1024 * 1024):
                digest.update(chunk)
        manifest_lines.append(f"{digest.hexdigest()}  {path.relative_to(target).as_posix()}")
    (target / "MANIFEST.sha256").write_text("\n".join(manifest_lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
