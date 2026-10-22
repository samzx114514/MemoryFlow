# LC-Sent-15 external baselines Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add CLM and Yifeng scores for the frozen 228-target Dev set without rerunning old baselines.

**Architecture:** A small runner in `experiments/lc_sent15_external_v1/evaluate.py` loads the checksum-bound Dev inputs, strips labels before inference, reuses the existing CLM runner, and teacher-forces the fixed target through Yifeng's selected head. Evaluation joins predictions to labels only after scoring.

**Tech Stack:** Existing Python, pytest, PyTorch, Transformers, official CLM Engine/head and Yifeng aggregation utilities on 243.

## Global Constraints

- Dev only: 228 targets, 15 unchanged candidates each, one Silver positive; no Reserve/Blind.
- No training, downloads, paid APIs, new head selection, threshold tuning or old baseline reruns.
- Yifeng head `(19,15)`; user approved fixed-target replay on 2026-10-22. Display name: 艺峰方法.
- Replay attention predicting target token j comes from its preceding position, matching upstream greedy decoding. Aggregate over all target tokens, then sum candidate token attention using the upstream function. No citation abstention threshold for forced ranking.
- Preserve candidate order; ties sort by source ID ascending. CLM consumes target and candidates; Yifeng also consumes the original query via its native prompt. Disclose this input difference.
- Both methods retain full input, limit 8,192 tokens. CLM's first preflight found 5 inputs above the smoke runner's 2,048 limit (maximum 6,385, backbone context 40,960); expose an optional length argument with the original smoke default unchanged. The first blocked CLM output stays preserved; rerun writes `clm_fulltext`.
- GPU selected from current free memory; 40 GiB minimum free and 32 GiB allocator cap. Small outputs only; disk has about 5.2 GB free.
- Inline execution is already authorized. The named execution sub-skills are not installed; use local tests and checkpointed runs directly.

## Task 1: Protocol and tests

Files: create `experiments/lc_sent15_external_v1/evaluate.py` and `test_evaluate.py`.

Interfaces: `prepare_records(rows, catalog)` returns label-free records and separate Gold; `evaluate(gold, predictions)` returns overall/zh/en metrics and target ranks; `replay_attention(...)` returns selected-head rows aligned to forced target tokens.

- [x] Run tests before implementation with plugin autoload disabled:

```powershell
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD='1'
F:/app/Anaconda3/python.exe -m pytest experiments/lc_sent15_external_v1/test_evaluate.py -q
```

Tests assert candidate preservation, no label fields in model records, rank-8 MRR `1/8`, rank-2 nDCG `1/log2(3)`, rejection of missing/duplicate/nonfinite predictions, and shifted positions `[9,10,11]` for prompt length 10 and target length 3. The server's tiny-model test replays the author's generated IDs and requires exact attention equality.

- [x] Implement the runner with a `prepare` action and separate `clm`/`yifeng` actions. Use the checked-in test cases as the executable contract; existing CLM runner only gains the explicit length argument described above.
- [x] Pass local metric tests and the server's upstream-replay equivalence test before model runs. Commit runner and tests with the final compact evidence.

## Task 2: Run and publish the two rows

- [x] Prepare fixed Dev records and Gold once; verify both input SHAs and all candidate invariants.
- [x] Run `evaluate.py clm --root ROOT --inputs RUN/inputs --output RUN/clm` and the equivalent `yifeng` command with safe GPU visibility and offline mode. ROOT is `/data2/pkuiti/songzhengxing_intern/memoryflow`; RUN is its `runs/lc_sent15_external_v1/20261022_v1` child. Completed CLM rerun is in `clm_fulltext`.
- [x] Require 228 unique predictions, 3,420 finite scores and matching input hashes for each completed report. Recompute metrics independently from saved predictions.
- [x] Save compact score/report evidence under this experiment's `reports/`; update `docs/RESULTS.md`, `docs/STATUS.md`, `docs/EXPERIMENT_INDEX.md`. Explain Hit@1 and report the random baseline 1/15. Keep old metric values unchanged.
- [x] Verify staged changes exclude raw text, model weights and credentials; commit, push and verify the remote commit.
