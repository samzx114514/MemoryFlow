# multiturn_batch_v1：多轮目标的统一入口与四方法批处理

**状态（2026-11-06）：** 三题开发验收跑通；另用 genmem63 pilot-v4 的 B04/F11
做了两道不同主题的旧材料受控验证。新数据（约 40–60 个目标、≥8 条轨迹）尚未到。
本目录只读已有的冻结输入与矩阵，不重跑模型（pilot 的 7B 矩阵在 243 上另算）。

B04/F11 结果见 [B04_F11_20261106](pilot/reports/B04_F11_20261106.md)：
B04 上 MemoryFlow A1/B5、head 用替代组 g01 完整；F11 上只有 MemoryFlow 完整
（A1/B3，旧欠定结论第 2）。两题同一轨迹，不是独立任务。

## 做什么

把多轮目标统一成一种 case（轨迹、目标位置、各轮输入/输出、中间传递、原始候选、
支持证据组），在**锁定候选与标签之后**跑四种方法：

| 方法 | 输入 | 最终返回 |
|---|---|---|
| `last_round` | 最后一轮实际可见材料，固定头回放 | top-10 |
| `bm25_history` | 全历史原始候选，BM25 | top-10 |
| `head_full_history` | 全历史原始候选，同头直接回放 | top-10 |
| `memoryflow` | 从最终句沿中间结论逐跳，乘积路径分，同一原文合并 | top-10（每跳 5） |

指标沿用原评测的覆盖规则：Hit@3、完整证据@5/@10、逐题名次、配对胜平负。
同一证据按 `(artifact, start, end)` 归并，`occurrences` 保留它在各轮的实际位置。
`T06` 是“最终轮自身已有足够证据”的对照，主表宏平均不含它。

## 快速开始

```bash
PY=python   # 本机 CPU 即可；新数据的矩阵需要服务器 7B 回放

$PY experiments/multiturn_batch_v1/import_dev.py \
  --manifest artifacts/raw/genmem_batch10_v3/report_manifest.json \
  --subset artifacts/raw/genmem_batch10_v3/subset \
  --out experiments/multiturn_batch_v1

$PY experiments/multiturn_batch_v1/preflight.py --dir experiments/multiturn_batch_v1

$PY experiments/multiturn_batch_v1/run_batch.py \
  --dir experiments/multiturn_batch_v1 --write-lock \
  --out experiments/multiturn_batch_v1/reports/BATCH_20261106.json \
  --md experiments/multiturn_batch_v1/reports/BATCH_20261106.md

$PY experiments/multiturn_batch_v1/run_batch.py \
  --dir experiments/multiturn_batch_v1 \
  --out experiments/multiturn_batch_v1/reports/BATCH_20261106.json \
  --md experiments/multiturn_batch_v1/reports/BATCH_20261106.md
```

## 文件

| 文件 | 作用 |
|---|---|
| `TEMPLATE.md` | case / 矩阵 schema、缺失登记、锁定流程 |
| `cases.py` | case 校验、canonical 证据身份、覆盖规则 |
| `import_dev.py` | 把 provenance_rounds_v1 的三题导入为统一 case + matrices |
| `import_pilot.py` | 把 genmem63 pilot-v4 的目标按 recipe 导入为统一 case（全候选 + 两轮材料） |
| `score_cases.py` | 在 243 上用固定头 7B 为统一 case 生成 r1/r2/flat 矩阵（GPU） |
| `preflight.py` | 阻断问题、缺失登记、矩阵一致性检查 |
| `methods.py` | 四种方法的排序；链式逐跳与路径合并 |
| `metrics.py` | Hit@3、完整@5/@10、名次、配对胜平负 |
| `run_batch.py` | 锁定、批量跑方法、写 JSON + Markdown |
| `cases/`、`matrices/`、`manifest.json` | 三题开发验收的冻结输入 |
| `pilot/` | genmem63 pilot-v4 的 B04/F11：case、矩阵、锁、报告 |
| `lock.json`、`preflight.json` | 评分前的候选/标签/矩阵哈希锁与预检结果 |
| `reports/BATCH_20261106.{md,json}` | 三题批处理输出 |
| `reports/ACCEPTANCE_20261106.md` | 接入验收、复算说明、缺失登记规则 |

## 边界

- 三题是 dev 案例内的受控构造，不是 47 题主表；宏平均 n=2，只作验收，不作科学结论。
- 真实请求（`record_type=real_request`）的导入器尚未被数据检验；schema 已支持。
- 新数据的 7B 矩阵需要先由回放侧生成，接口见 `TEMPLATE.md` 第 6 节。
- T06 的 GT 组仍是原 ordinal 组（8 项），与受控最终句不完全同构；它只作对照，不进主表。
