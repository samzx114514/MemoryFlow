# Native baseline smoke runs Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Run the two existing unlabelled cases through CLM and author-native citation generation on 243.

**Architecture:** Preserve all existing inputs and upstream source. A small runner supplies Transformers last-token embeddings to the official CLM Engine, or calls the author's generation and citation functions with fixed head (19,15). This is a backend adaptation, not a verified numerical reproduction of vLLM.

**Tech Stack:** Existing torch 2.11.0, transformers 4.57.6, numpy; no package installation.

## Global Constraints

- User explicitly chose paper head (19,15), zero based; do not probe or choose the raw-score winner (14,0).
- Raw score file SHA256: 89dbd7cdc665e87ddfc71c69c6f613fcc78d5a9be15a2f3b3bfe00fcc4c11e84. 784 heads, 44 scores each; paper head ranks fifth by sum.
- Only two prepared cases, no Reserve/Blind, no paid API, no server 245 writes.
- Batch one, one shared GPU, sequential models, 32 GiB allocator cap, no other-process changes.
- CLM max input 2048; Yifeng max input 8192 and greedy output cap 600. No input truncation. Record if output reaches cap.
- Original text/results stay in ignored artifacts or 243 memoryflow/runs; Git receives code and content-free reports.
- Required execution skills are not installed; execute inline with tests and checkpoints, as user requested.

## Task 1: Runner and regression checks

Files: create experiments/baseline_adapters_v1/run_local_models.py and test_local_models.py.
Interfaces: last_token_vector(hidden) returns normalized last-token float32 vector for one unpadded sequence; overlap_ids(start,end,mapping) returns all overlapping original source IDs. Runner modes clm and yifeng accept --root and a new --output directory.

- [x] Write tests for last-token (not mean) pooling, zero-vector rejection, source overlaps, and no-overlap result; first run failed with missing runner module.
- [x] Implement runner without changing author files. CLM uses AutoModel + author Engine; Yifeng calls generate_attention.run and add_citations.run, saving generation length/stop reason and source mapping.
- [x] Run on 243: `PY=/data2/pkuiti/songzhengxing_intern/memoryflow/artifacts/legacy/.conda_env_cf/bin/python; $PY -m unittest discover -s /data2/pkuiti/songzhengxing_intern/memoryflow/scripts/baseline_adapters_v1 -p 'test_*.py' -v`. All 20 checks passed.

## Task 2: Bounded full-model runs

- [x] Check current free GPU memory; require at least 40 GiB before each model. GPU 7 passed both checks.
- [x] Run `CUDA_VISIBLE_DEVICES=7 HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 OMP_NUM_THREADS=2 $PY $MF/scripts/baseline_adapters_v1/run_local_models.py clm --root $MF --output $MF/runs/baseline_adapters_v1/models_20261018_v1/clm`.
- [x] Run the same command with mode/output suffix `yifeng`, only after CLM exits.
- [x] Check finite scores, exact candidate IDs, nonempty generation, matrix dimensions, fixed citation head, source offsets and output cap. Report metrics as interface results, not accuracy.
- [x] Copy small reports and a local ignored review bundle. Update STATUS and EXPERIMENT_INDEX. Git commit/push is tracked by the task's final delivery message, not assumed by this checklist.

Acceptance: two CLM rankings, two generated answers with attention matrices and citations, stable source mapping, run metadata including input/code/model identity, token counts, memory and runtime; failures remain visible and are not relabelled successes.
