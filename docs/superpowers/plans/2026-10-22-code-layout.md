# Code layout implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Separate the current trace/baseline work from historical experiments without changing scientific behavior.

**Architecture:** Keep current `experiments/` entry points intact. Move the coupled `workspace/` and `local_data/` trees together under `legacy/`; identify reusable model code there without copying it into another package. Keep the self-contained DCC branch in place and label it paused.

**Tech Stack:** Python, PowerShell, Git, Markdown.

## Global constraints

- No GPU/model/API run, dataset scan, Reserve/Blind access, or server filesystem change.
- Preserve every moved file byte-for-byte, including historical metadata and reports.
- Do not merge the two distinct historical `memoryflow` Python packages.
- Update current documentation links, not historical evidence payloads or absolute server paths.
- No deletions or duplicate compatibility trees. User authorized reorganization and push.
- Execute inline: the optional execution skills named above are unavailable; no subagents are needed.

## Task 1: Establish the baseline

- [x] Read repository rules, research brief, status and experiment index; verify clean checkout and remote.
- [x] Inspect entry points, relative imports and external-path assumptions.
- [x] Run pre-move local-data tests (28), BM25/pooling tests (8), DCC tests (18). Trace/adapter standard-library checks previously pass (7/16); repeat after moving.

## Task 2: Relocate frozen trees

Files: move all tracked contents of `workspace/` to `legacy/workspace/`, and `local_data/` to `legacy/local_data/`. Create `legacy/README.md` and `docs/CODE_MAP.md`.

- [x] Verify resolved source/destination paths are below the checkout and destinations do not exist, then use PowerShell `Move-Item -LiteralPath` for both directories.
- [x] Compare each destination's Git blob hash with the original index entry; require 128/128 identical files.
- [x] Keep `workspace` and `local_data` as siblings so the synthetic transfer runner's existing parent-relative paths remain valid inside the frozen tree.
- [x] Update README, current documentation links, data index and workspace map with the new Git paths. Leave all server paths unchanged.

## Task 3: Make the current scope readable

Files: `README.md`, `AGENTS.md`, `experiments/README.md`, `docs/CODE_MAP.md`, `docs/STATUS.md`, `docs/EXPERIMENT_INDEX.md`, `docs/RESEARCH_BRIEF.md`, `docs/WORKSPACE_MAP.md`, `docs/RESULTS.md`, `data/README.md`.

- [x] Classify active, reusable/frozen, one-off, and paused code; name actual interfaces and missing integration.
- [x] Record no extra CLM training, the fixed Yifeng head, and the differing target contracts.
- [x] Add a rule against copying run-specific variants into new code directories or overwriting old outputs.

## Task 4: Validate and publish

From the checkout root (Python 3.10+, pytest for the local-data suite):

```powershell
python -m unittest discover -s experiments/trace_review_v1 -p test_extract.py
python -m unittest discover -s experiments/baseline_adapters_v1 -p test_adapters.py
python -m unittest discover -s experiments/baseline_adapters_v1 -p test_acquire_qwen3.py
python -m unittest discover -s experiments/dcc_diagnostic_v0/tests -p 'test_*.py'
python -m pytest -q legacy/local_data/tests -c legacy/local_data/pyproject.toml
$env:PYTHONPATH = (Resolve-Path legacy/workspace/src).Path
python -m unittest discover -s legacy/workspace/tests -p test_lc_sent15_bm25.py
python -m unittest discover -s legacy/workspace/tests -p test_lc_sent15_fmean.py
```

- [x] Require the same 77 lightweight checks to pass after the move; report unavailable torch tests separately, without installing GPU dependencies.
- [x] Validate Python syntax, current documentation links, exact renames, and staged-file exclusion/secret checks; inspect only filenames or counts for sensitive matches.
- Publish reviewed changes with a normal commit/push (no force); completion is recorded by matching remote main and local HEAD, not asserted in advance in this plan.
