# GenMem 受控多轮扩测：第一批合格题（2026-11-06）

**状态：** 8 条轨迹各一题，主表 7 题、对照 1 题；补项后的第一批已测完。
本表是新协议（两轮原始候选并集）的第一批；旧的全历史大候选池结果见
`batch10/reports/BATCH10_20261106.md`，不混表。旧 47 题表不变。

## 对首批的修正

| 题 | 修正 | 结果 |
|---|---|---|
| case_03 selected_10 | 第二轮补入 `a0171[144,208)`（member since 2005）与 `a0171[505,610)`（acting leader 总结） | 4 项组齐，完整@5 第 5 |
| case_05 selected_03 | 第二轮补入题目 (a/b)、五组气体、a/b 定义共 9 项 | 11 项组仍超返回预算，10 条内不齐 |
| case_07 selected_07 | 第二轮补入 `a0007[129,193)`（priority management）与 pagefile 段 | 4 项组齐，完整@5 第 4 |
| case_06 selected_04 | 核查：最终轮已有 `a0082`（South Hampshire 定义），最终句“likely South Hampshire”由它直接支持 | 移到对照表 |
| case_10 selected_01 | 撤销“标题相同”合并；`a0194` 与 `a0203` 按两处原文分别保留并放入第一轮 | 4 项组齐，完整@5 第 4 |
| case_02 selected_05 | 清单项都在第一轮；第二跳只展开前 5，只把第 5 项 A 带回 | 仍缺 4 个列表项；留作预算损失 |

## 新口径

- **候选池**：BM25、同一 7B 固定头平铺、MemoryFlow 都只用**两轮原始候选的并集**（同源去重）；
  最后一轮单列，不参与主表；旧的全历史大候选池结果另列。
- 每跳展开 top-5；最终返回 top-10；同源按规范化文本去重，标题相同不合并证据。
- 覆盖沿用原评测：片段按同 artifact 非空白字符覆盖，组内 all_of 全中，组间 OR。
- 主表只收“最终句确实需要上游、且两轮合起来能找齐至少一套证据”的题；最终轮自足的放对照。
- 方法跑丢的题留分母；材料缺失/待核/超预算逐题记原因。

## 主表（7 题，7 条轨迹）

| 方法 | Hit@3 | 完整@5 | 完整@10 | 平均完整名次 | 平均首个证据名次 |
|---|---|---|---|---|---|
| last_round | 7/7 | 0/7 | 0/7 | 11.00 | 1.00 |
| bm25_history | 7/7 | 3/7 | 5/7 | 6.14 | 1.29 |
| head_full_history | 7/7 | 5/7 | 6/7 | 5.57 | 1.00 |
| memoryflow | 7/7 | 5/7 | 5/7 | 5.71 | 1.00 |

**配对（MemoryFlow 对基线，主表 n=7）**

| 基线 | 完整名次 W/T/L | 首个证据 W/T/L |
|---|---|---|
| last_round | 5/2/0 | 0/7/0 |
| bm25_history | 2/3/2 | 1/6/0 |
| head_full_history | 1/4/2 | 0/7/0 |

逐题（MemoryFlow；A/B 为最终合并名次）：

| 轨迹 | 目标 | hop1 结论 | hop2 A | hop1 B | 合并 A/B | 完整名次 | 组 |
|---|---|---|---|---|---|---|---|
| case_01 | selected_02 | 2 | 1 | 1 | 2 / 1 | 2 | 2 项 |
| case_02 | selected_05 | 2 | 2 | 1 | 5 / 1 | — | 6 项，缺 4 个列表项 |
| case_03 | selected_10 | 2 | 1 | 1 | 4 / 1 | 5 | 4 项齐 |
| case_04 | selected_01 | 2 | 2 | 1 | 3 / 1 | 3 | 2 项 |
| case_05 | selected_03 | 1 | 1 | 4 | 4 / 3 | — | 11 项，超 top-10 |
| case_07 | selected_07 | 1 | 1 | 3 | 1 / 3 | 4 | 4 项齐 |
| case_10 | selected_01 | 1 | 1 | 2 | 3 / 1 | 4 | 4 项齐（标题两处分开） |

对照表（最终轮自足，不计入主表）：

| 题 | 最终轮依据 | last_round 完整 | MemoryFlow 完整 |
|---|---|---|---|
| case_06 selected_04 | 最终轮 `a0082` 定义 South Hampshire；最终句只要求“likely South Hampshire” | 否（GT g02 的 `a0060` 在第一轮） | 是（第 1，g02 单项） |

## 哪一步有用、哪一步掉链子

- **第一跳**：8/8 中间结论进前 5（第 1–2）。
- **上游**：8/8 的 A 在第二跳前 5（第 1–2）；B 在第一跳 8/8（第 1–4，case_05 B 第 4）。
- **合并**：8/8 的 A/B 都在最终前 5；MemoryFlow Hit@3 8/8。
- **完整**：5/7。掉的两题不是跳检索：
  - **case_02**：组 6 项（5 列表 + 年份）；5 个列表项都在第一轮，但第二跳只展开 5，只带回第 5 项 A；
    另 4 个列表项没进合并列表 → **上游展开/预算**。head 平铺在 @10 能凑齐（第 10），MF 不能。
  - **case_05**：组 11 项；两轮并集有全部 11 项，但 top-10 装不下 11 项完整组 → **返回预算**，不是检索。
- **方法对比**：同一并集池下，head 平铺在完整@10（6/7）略好于 MemoryFlow（5/7）；
  MemoryFlow 在 @5 与 head 持平（5/7），对 last 明显更好（5/7 对 0/7）。
  MemoryFlow 的损失集中在 hop=5 的展开上（case_02）；把 hop 调到 10 才能与 head 的 @10 对齐。
- **最后轮**：Hit@3 7/7，但完整 0/7；A 不在最终轮，不能作为主方法。
- **旧全历史大候选池**：上一张 batch10 表（head Hit@3 1/8）是旧池口径，不与本表比较。

## 100 目标筛选清单（第一版）

见 [SCREENING_100_20261106.md](SCREENING_100_20261106.md) / `.csv`。计数：

| 状态 | 数量 |
|---|---|
| built-v2（本批 8 题） | 8 |
| built-prev（batch10 三题表） | 3 |
| candidate-full（64 个已标注里的剩余跨事件组） | 10 |
| excluded-single-event（已标注但无跨事件组） | 43 |
| candidate-partial（36 个 partial 里跨事件的补标候选） | 11 |
| excluded-partial（partial 里单事件/待核） | 25 |

64 个已标注目标已全部核对；36 个 partial 只做到“补标候选”，没有当作已完成标注。
下一批优先做 10 个 candidate-full；partial 11 个先补标再构造。

## 复算

```bash
python experiments/multiturn_batch_v1/import_batch10.py \
  --subset artifacts/raw/genmem_batch10_v3/subset/contextual64_v4 \
  --recipe experiments/multiturn_batch_v1/batch10_v2/recipes.json \
  --out experiments/multiturn_batch_v1/batch10_v2
# 243 GPU0，union 平铺，prompt 219–403
artifacts/legacy/.conda_env_cf/bin/python experiments/multiturn_batch_v1/score_cases.py \
  --dir experiments/multiturn_batch_v1/batch10_v2 \
  --root /data2/pkuiti/songzhengxing_intern/memoryflow --physical-gpu 0 --memory-cap-gib 24
python experiments/multiturn_batch_v1/preflight.py --dir experiments/multiturn_batch_v1/batch10_v2
python experiments/multiturn_batch_v1/run_batch.py --dir experiments/multiturn_batch_v1/batch10_v2 --write-lock \
  --out experiments/multiturn_batch_v1/batch10_v2/reports/BATCH10_V2_20261106.json \
  --md experiments/multiturn_batch_v1/batch10_v2/reports/BATCH10_V2_20261106.md
python experiments/multiturn_batch_v1/run_batch.py --dir experiments/multiturn_batch_v1/batch10_v2 \
  --out experiments/multiturn_batch_v1/batch10_v2/reports/BATCH10_V2_20261106.json \
  --md experiments/multiturn_batch_v1/batch10_v2/reports/BATCH10_V2_20261106.md
```

## 边界

- 8 条轨迹来自同一批 GenMem 记录；两轮受控构造，不是原始逐次请求。
- 主表 7 题、对照 1 题；组大于两处的题已补项，超出 top-10 的 case_05 保留为失败。
- 旧 47 题、旧全历史池、pilot B04/F11 表都不并入本表；Reserve/Blind 未触碰。
