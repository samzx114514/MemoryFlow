# 多轮批处理接入验收（三题开发集，2026-11-06）

**状态：** 统一入口、预检、锁定、四方法评分已在三题上跑通；新数据（约 40–60 个目标、
≥8 条轨迹）尚未到，本轮不新增样例、不重跑模型。三题只作开发验收，宏平均 n=2，
不作科学结论。

## 1. 交付物

| 交付 | 位置 |
|---|---|
| 统一 schema、缺失登记、锁定流程 | `TEMPLATE.md` |
| 三题冻结输入 | `cases/*.json`、`matrices/*.json`、`manifest.json` |
| 预检结果 | `preflight.json` |
| 评分前锁定 | `lock.json` |
| 四方法批处理输出 | `reports/BATCH_20261106.md`、`reports/BATCH_20261106.json` |
| 代码 | `cases.py`、`import_dev.py`、`preflight.py`、`methods.py`、`metrics.py`、`run_batch.py` |
| 测试 | `tests/test_batch.py`（9/9 通过） |

## 2. 导入验收

| 题 | case_id | 轨迹 | split | 类型 | 对照 | 轮数 | 候选 | 证据组 |
|---|---|---|---|---|---|---|---|---|
| T03 | `genmem_874c34ceb20bf193:selected_03` | `genmem_874c34ceb20bf193` | dev | controlled | — | 2 | 16 | 3 |
| T09 | `genmem_874c34ceb20bf193:selected_09` | `genmem_874c34ceb20bf193` | dev | controlled | — | 2 | 17 | 2 |
| T06 | `genmem_874c34ceb20bf193:selected_06` | `genmem_874c34ceb20bf193` | dev | controlled | `final_round_sufficient` | 2 | 19 | 1 |

- 合计：3 题，controlled 3 / real_request 0，dev 3 / eval 0，对照 1。预检 3 题全部 `ok`，无阻断。
- 三题都来自同一条轨迹（case_02），所以 dev 隔离没有跨轨迹混用；新数据按 `trajectory_id` 分配 split，
  预检会拒绝同一轨迹跨 dev/eval 的批次。
- 重复证据已合并：T03 有 8 个候选在两轮重复出现（如 `a0296#126-258`
  在两轮各有一次，`occurrences` 记录 round 1/2 与材料序号）；评分只按一个 canonical 身份计数。
- 中间传递：T03/T09/T06 的第二轮都有 `transmission:r1`，文本与第一轮输出逐字一致；
  矩阵 `r1`/`r2`/`flat` 齐全，`flat` 覆盖全部候选。

## 3. 四方法验收表

最终返回预算 top-10；每跳展开 top-5（另记）。完整表见
[`BATCH_20261106.md`](BATCH_20261106.md)。

**主表（T03 + T09，n=2；T06 对照不计入）**

| 方法 | Hit@3 | 完整@5 | 完整@10 | 平均完整名次 | 平均首个证据名次 |
|---|---|---|---|---|---|
| last_round | 1.000 (2/2) | 0.000 (0/2) | 0.000 (0/2) | 11.00 | 1.00 |
| bm25_history | 1.000 (2/2) | 1.000 (2/2) | 1.000 (2/2) | 2.00 | 1.00 |
| head_full_history | 1.000 (2/2) | 0.500 (1/2) | 1.000 (2/2) | 5.00 | 1.00 |
| memoryflow | 1.000 (2/2) | 1.000 (2/2) | 1.000 (2/2) | 2.00 | 1.00 |

**配对胜平负（MemoryFlow 对基线，主表 n=2）**

| 基线 | 完整名次 W/T/L | 首个证据名次 W/T/L |
|---|---|---|
| last_round | 2/0/0 | 0/2/0 |
| bm25_history | 0/2/0 | 0/2/0 |
| head_full_history | 1/1/0 | 0/2/0 |

**逐题关键名次**

| 题 | 方法 | A | B | 完整名次 |
|---|---|---|---|---|
| T03 | last_round | — | 1 | — |
| T03 | bm25 / head / memoryflow | 2 / 2 / 2 | 1 / 1 / 1 | 2 / 2 / 2 |
| T09 | last_round | — | 1 | — |
| T09 | bm25_history | 2 | 1 | 2 |
| T09 | head_full_history | 1 | 8 | 8 |
| T09 | memoryflow | 1 | 2 | 2 |

T09 仍是主例：全历史直接回放把 B 排到第 8，多轮链把 A、B 拉到第 1/2；
全历史 BM25 也把两条都排到前 2。T03 上四种方法里只有 last_round 缺 A。

**T06 对照**

T06 的最终句只要求“专辑 + 发行年”，最终轮 top-5 已含 B（`a0284:137-154`）和专辑题名
（`a0279`、`a0282`），所以“最终轮自身已有足够证据”成立。它的 GT 组仍是原 ordinal 组
（6 个列表项 + `a0282` + `a0284`，共 8 项），与受控最终句不完全同构，因此它的
Complete@5/@10 全是 0，只作诊断，不进主表宏平均。

## 4. 怎么复算

```bash
PY=python

# 1) 导入三题（只读 provenance_rounds_v1 的 spec/frozen/scores；不重跑模型）
$PY experiments/multiturn_batch_v1/import_dev.py \
  --manifest artifacts/raw/genmem_batch10_v3/report_manifest.json \
  --subset artifacts/raw/genmem_batch10_v3/subset \
  --out experiments/multiturn_batch_v1

# 2) 预检：阻断问题、缺失登记、矩阵一致性
$PY experiments/multiturn_batch_v1/preflight.py --dir experiments/multiturn_batch_v1

# 3) 锁定候选/标签/矩阵哈希（先于看方法分数）
$PY experiments/multiturn_batch_v1/run_batch.py \
  --dir experiments/multiturn_batch_v1 --write-lock \
  --out experiments/multiturn_batch_v1/reports/BATCH_20261106.json \
  --md experiments/multiturn_batch_v1/reports/BATCH_20261106.md

# 4) 评分（无 lock 会拒绝；lock 不匹配会中止）
$PY experiments/multiturn_batch_v1/run_batch.py \
  --dir experiments/multiturn_batch_v1 \
  --out experiments/multiturn_batch_v1/reports/BATCH_20261106.json \
  --md experiments/multiturn_batch_v1/reports/BATCH_20261106.md
```

分数来源：`matrices/*.json` 由 `experiments/provenance_rounds_v1` 已保存的
`m1`/`m2`/`mflat` 矩阵映射而来（`source.scores_sha256` 可核）；BM25 是 CPU 的
`legacy/workspace/src/memoryflow/lc_sent15_bm25.py`，没有 GPU。覆盖规则：
同一 artifact 上选中窗口对片段的非空白字符全覆盖才算覆盖；组内所有 item 都有
alternative 被覆盖才算组完整；组间 OR。

## 5. 缺输入、缺标签的登记

| 情况 | 处理 | 登记字段 |
|---|---|---|
| 目标句空 / real 模式缺位置 | 拒绝导入 | `E_TARGET` |
| 轮次 < 2、输入/输出空 | 拒绝导入 | `E_ROUND` |
| 中间传递文本与上一轮输出不符 | 拒绝导入 | `E_TRANSMISSION` |
| 中间传递缺位 | 允许导入、链方法停止 | `missing_inputs: roundN:transmission` |
| `evidence_groups` 空 | 允许导入、不评分 | `missing_labels: evidence_groups` |
| 组 `coverage=partial` | 允许、不进完整度分母 | `partial_group` |
| 候选池空 | 拒绝评分 | `missing_inputs: candidates` |
| 受控构造 | 允许、单独统计 | `warnings: controlled construction` |

预检把每题标为 `ok` / `incomplete` / `blocked`；`blocked` 直接退出，`incomplete`
进入 `preflight.json` 和 manifest 的 `registry`，在报告里单列，不默认为完整样本。

## 6. 新数据到达后的流程

1. 先取一小批（建议 1–2 条轨迹、5–10 个目标）按 `TEMPLATE.md` 导入；目标位置、
   各轮输入/输出、中间传递、候选、证据组逐项核对。
2. 跑 `preflight.py`；把 `blocked`/`incomplete` 处理完，锁定 `manifest`。
3. 先 `--write-lock`，确认候选身份、A/B（如有）、证据组和矩阵哈希都固定；
   此时仍未看方法分数。
4. 再跑 `run_batch.py` 出正式表。旧 47 题协议继续单列，不并入本表。
5. split 按轨迹分配：同一 `trajectory_id` 不能同时出现在 dev 和 eval。

## 7. 边界与未做

- 三题是 dev 案例内的受控构造；n=2 的主表宏平均只作验收，不作方法优劣结论。
- `real_request` 路径（目标位置来自真实记录、轮次来自真实请求）尚未被数据检验；
  schema 与校验已支持，导入器需要在真实数据上补。
- 新数据的 7B 矩阵（r1…rN + flat）需要回放侧先生成；本轮的矩阵是复用已保存分数。
  矩阵接口见 `TEMPLATE.md` 第 6 节；下一步是把 `provenance_rounds_v1/score.py` 的
  两轮逻辑扩成 N 轮并接进来。
- T09 的 `a0236` 仍是可计数影子证据（去掉 Caravans 时 Zero Zero 第 5），不是 GT 的 A；
  T06 的 GT 组与受控最终句不完全同构；这两点都保留在报告里。
- 多轮链每跳 5，最终返回 8–9 条（去重后）；其余方法 10 条。若要求严格同长，
  把 hop 调到 10，表里另记。
