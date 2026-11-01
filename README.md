# MemoryFlow

## 2026-11-01：PPT 生成资料包

供其他模型生成参考稿的[完整资料包](docs/presentation_brief_20261101/README.md)，包含生成提示词、22 个主讲单元与 5 个备选单元、核准数据与图表、案例摘录、待补清单和历史参考。可先读[单文件简报](docs/presentation_brief_20261101/START_HERE_ONE_FILE.md)。当前汇报口径以该包为准；下文的旧研究介绍保留历史身份。

MemoryFlow studies how fine-grained information is passed, rewritten and combined across Agent calls. Sources and generated claims may themselves be wrong; tracing their relationships is separate from fact-checking them. The present quantitative evidence is strongest for **semantic source matching** on LongCite, not actual use or causal influence in a real Agent run.

This private repository brings together method code, run configurations and compact results from server 243. Current work lives in `experiments/`; historical implementations are preserved under `legacy/`, with reports in `evidence/`. Large inputs and checkpoints remain external. It does not assume public release rights.

## Current development

Start with the [代码地图 / code map](docs/CODE_MAP.md): it distinguishes active work, reusable frozen baselines, one-off scripts and paused experiments. [Current experiment entry points](experiments/README.md) cover SP1 logging, trace extraction, and CLM/Yifeng adapters. R-SYM, D-Full and BM25 remain reusable in `legacy/workspace/`; they were not deleted or retrained.

The immediate task is a small, reviewed real-trajectory dataset, then a fair comparison on the same target units and candidate sources. The existing two-case model smoke test is not that benchmark. SP1 is the current trajectory provider; SP2 integration is deferred. See [status](docs/STATUS.md) for verified progress and gaps.

## Read in this order

1. [研究背景与结论](docs/RESEARCH_BRIEF.md) — the self-contained Chinese explanation; [讨论简报](docs/DISCUSSION_BRIEF.md) can be read on its own.
2. [分协议结果](docs/RESULTS.md) — numbers, denominators and source files.
3. [当前状态](docs/STATUS.md) and [待讨论问题](docs/OPEN_QUESTIONS.md).
4. [实验索引](docs/EXPERIMENT_INDEX.md) — code, configurations, reports, and external artifacts.
5. [数据](data/README.md), [大产物](artifacts/README.md), and [第三方材料](references/README.md).

## Representative results

| Protocol | Method | Main result | Interpretation |
|---|---|---:|---|
| Historical c8, Dev | Anchor + Attention C4 | MRR 0.576958 | Packed white-box feasibility; distinct from c15. |
| LC-Sent-15, Dev (228 Targets) | BM25 | Hit@1 0.6842 | Strong lexical baseline. |
| LC-Sent-15, Dev | R-SYM | Hit@1 0.754386, three-seed mean | Frozen Qwen features plus symmetric relation scorer. |
| LC-Sent-15, Dev | D-Full-64 | Hit@1 0.780702, three-seed mean | Role-aware scorer; stronger point estimate, larger Train–Dev gap. |
| LC-Sent-15, Dev | Fixed fusion | Hit@1 0.831871 | Train-OOF-frozen 0.65 D-Full / 0.35 BM25; strongest Dev system. |
| Synthetic Summary Track A | BM25 | Hit@1 0.9416 | Optimistic smoke test with lexical overlap. |

The 15-way uniform random Hit@1 is 1/15 ≈ 0.0667. See [RESULTS](docs/RESULTS.md) before comparing methods: the older Anchor protocol has different candidates and labels.

## Code and verified entry points

- Historical preparation package: `legacy/local_data/pyproject.toml`, `legacy/local_data/src/memoryflow/`, `legacy/local_data/scripts/`, and LC-Sent-15's `legacy/local_data/lc_sent15_v1/build_v1/code/`. These are old data pipelines, not the new SP1 benchmark builder.
- Frozen method code: `legacy/workspace/src/memoryflow/` and `legacy/workspace/scripts/`, with `legacy/workspace/configs/`. Server scripts retain historic external data/model paths; review their arguments and provide your own paths before executing. No GPU experiment was rerun for this reorganization.
- Small, consented Train/Dev examples are under `legacy/local_data/lc_sent15_v1/baseline_core_v1/samples/`; they illustrate records and are not the full dataset. Reserve/Blind records are absent.

### Checked setup and entry commands (PowerShell)

From the repository root, use Python 3.10 or newer. The preparation package requires `pytest` for its tests; its `pyproject.toml` declares the test dependency. The paths below reflect the 2026-10-22 move:

```powershell
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD = '1'
python -m pytest -q legacy/local_data/tests -c legacy/local_data/pyproject.toml
python legacy/workspace/scripts/run_lc_sent15_bm25_gate.py --help
```

The first command ran 28 light tests. The second parsed `--data`, `--out`, and `--staged` without loading model weights or running BM25. To execute the existing CPU BM25 gate, provide the full LC-Sent-15 Train/Dev core via `--data` and a new output directory via `--out`; the data are external as described in [data/README.md](data/README.md). The GPU Q3 entry was also checked at import stage and stopped because this local Python lacks `torch`; its full run additionally needs the original Q0/Q1C/Q2 artifacts and frozen feature caches. No end-to-end training environment was claimed.

The code layout is source-preserving; the old root `workspace/` and `local_data/` paths are now under `legacy/`. Server directories have not moved. A clean install of the complete GPU pipeline has **not** been verified because model snapshots, feature caches, data payloads, and the 243 environment are external. See [experiment index](docs/EXPERIMENT_INDEX.md) for the original run contract and [status](docs/STATUS.md) for gaps.

## Keeping the research record current

For each later development change, commit the code and configuration with the relevant light report or metric file. Update `docs/EXPERIMENT_INDEX.md` to connect its entry, inputs, split, output and external large artifacts. Update `docs/RESULTS.md` only when checked results change, and `docs/STATUS.md` when a task completes, blocks or becomes unverified. State the evidence limit and keep prior versions; do not replace old reports or commit raw data, checkpoints or secrets. Push reviewed commits to `origin/main` (or use a feature branch and PR for work that needs review). This is a recording convention, not a promise to run experiments or publish restricted data.

No license is asserted for this repository or its third-party references. Permission for wider publication remains to be confirmed.
