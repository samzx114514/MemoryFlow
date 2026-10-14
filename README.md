# MemoryFlow

MemoryFlow studies where a passage in an Agent's memory or final report came from. If a Researcher reads several retrieved documents and writes a summary, we want to identify which source passage supports each summary clause, then ask whether the Reporter used that summary. The present evidence is strongest for **semantic source matching** on LongCite; it does not yet establish actual use or causal information flow in a real Agent run.

This private repository brings together local data preparation and research context with method code, run configurations, and compact results from server 243. It preserves their source identities in `local_data/`, `workspace/`, and `evidence/`. Large inputs and checkpoints remain external. The first version is for reading and discussing the research, then continuing development; it does not assume public release rights.

## Read in this order

1. [研究背景与结论](docs/RESEARCH_BRIEF.md) — the self-contained Chinese explanation.
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

- Local preparation package: `local_data/pyproject.toml`, `local_data/src/memoryflow/`, `local_data/scripts/`, and LC-Sent-15's `local_data/lc_sent15_v1/build_v1/code/`. Its existing light tests can be run from `local_data/` with `python -m pytest tests`; the repository assembly checked this suite without downloading data.
- Server method code: `workspace/src/memoryflow/` and `workspace/scripts/`, with `workspace/configs/`. The experiment index points to the specific run script for each result. Server scripts retain historic external data/model paths; review their arguments and provide your own paths before executing. No GPU experiment was rerun for this repository.
- Small, consented Train/Dev examples are under `local_data/lc_sent15_v1/baseline_core_v1/samples/`; they illustrate records and are not the full dataset. Reserve/Blind records are absent.

### Checked setup and entry commands (PowerShell)

From the repository root, use Python 3.10 or newer. The local preparation package requires `pytest` for its tests; its `pyproject.toml` declares the test dependency. These commands were actually checked during assembly:

```powershell
cd F:\CodexProject\MemoryFlow-research\local_data
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD = '1'
python -m pytest -q tests
cd ..
python workspace\scripts\run_lc_sent15_bm25_gate.py --help
```

The first command ran 28 light tests. The second parsed `--data`, `--out`, and `--staged` without loading model weights or running BM25. To execute the existing CPU BM25 gate, provide the full LC-Sent-15 Train/Dev core via `--data` and a new output directory via `--out`; the data are external as described in [data/README.md](data/README.md). The GPU Q3 entry was also checked at import stage and stopped because this local Python lacks `torch`; its full run additionally needs the original Q0/Q1C/Q2 artifacts and frozen feature caches. No end-to-end training environment was claimed.

The current code layout is intentionally source-preserving. A clean install of the complete GPU pipeline has **not** been verified in this repository because model snapshots, feature caches, data payloads, and the 243 environment are external. See [experiment index](docs/EXPERIMENT_INDEX.md) for the original run contract and [status](docs/STATUS.md) for gaps.

No license is asserted for this repository or its third-party references. Permission for wider publication remains to be confirmed.
