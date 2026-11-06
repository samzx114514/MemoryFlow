# GenMem 受控多轮扩测：累计主表（2026-11-07）

**状态：** 第一批合格题主表 5 题（5 条轨迹）、最终轮自足对照 1 题、超预算 1 题、日期待核 1 题。
本轮先交这些核验与累计表；10 个 candidate-full、11 个 partial 补标候选、4 个同事件多证据题
已列入下一批清单。旧 47 题表分开，Reserve/Blind 未触碰。

## 两项指定核验

**case_10 selected_01（日期）**：`a0205:u0-12` 只有 `Jul 23, 2022`，是搜索结果的裸元数据行，
同事件没有“Published/Publication date”标注；标题 `a0194`、期刊 `a0192`、日期片段各自可见，
但**不能确认该日期就是这篇论文的发表日期**。按任务要求撤出主表，状态 `excluded-date-unverified`。
同源合并也已撤销：`a0194` 与 `a0203` 是两处原文，不能再因标题相同合并。

**case_02 selected_05（放宽每跳）**：用已保存矩阵复算 hop=5/10/100。缺的 4 个列表项在
m1 里只有 0.018/0.006/0.0007/0.0002，合并后名次 **11–14**；即使把每跳扩到 100，也进不了最终前 10。
所以这条不是“第一跳没找到中间结论”，也不是“hop 太小”，而是**上游 m1 排序把列表项压得太低**。
保留为失败样例。

## 累计主表（5 题，5 条轨迹）

| 方法 | Hit@3 | 完整@5 | 完整@10 | 平均完整名次 | 平均首个证据名次 |
|---|---|---|---|---|---|
| last_round | 5/5 | 0/5 | 0/5 | 11.00 | 1.00 |
| bm25_history | 5/5 | 3/5 | 4/5 | 5.00 | 1.40 |
| head_full_history | 5/5 | 4/5 | 5/5 | 4.80 | 1.00 |
| memoryflow | 5/5 | 4/5 | 4/5 | 5.00 | 1.00 |

**配对（MemoryFlow 对基线，n=5）**

| 基线 | 完整名次 W/T/L | 首个证据 W/T/L |
|---|---|---|
| last_round | 4/1/0 | 0/5/0 |
| bm25_history | 1/2/2 | 1/4/0 |
| head_full_history | 1/2/2 | 0/5/0 |

逐题：

| 轨迹 | 目标 | hop1 结论 | hop2 A | hop1 B | 合并 A/B | 完整名次 | 说明 |
|---|---|---|---|---|---|---|---|
| case_01 | selected_02 | 2 | 1 | 1 | 2 / 1 | 2 | 2 项组 |
| case_02 | selected_05 | 2 | 2 | 1 | 7 / 1 | — | 6 项组；列表项 m1 排 11–14，hop 100 也进不了前 10 |
| case_03 | selected_10 | 2 | 1 | 1 | 4 / 1 | 5 | 4 项齐 |
| case_04 | selected_01 | 2 | 2 | 1 | 3 / 1 | 3 | 2 项组 |
| case_07 | selected_07 | 1 | 1 | 3 | 1 / 3 | 4 | 4 项齐 |

对照与排除：

| 题 | 状态 | 依据 |
|---|---|---|
| case_06 selected_04 | control-final-sufficient | 最终轮 `a0082` 定义 South Hampshire，最终句只需该定义；last_round 的 0 完整是 GT g02 的 `a0060` 在第一轮，不代表语义不足 |
| case_05 selected_03 | excluded-budget | 11 项组，top-10 装不下，任何方法在预算内都凑不齐 |
| case_10 selected_01 | excluded-date-unverified | 日期未明确标注为论文发表日期 |

## 哪一步有用、哪一步掉链子

- hop1 中间结论：5/5 进前 5（1–2 名）。
- hop2 A：5/5 进前 5（1–2 名）；hop1 B：5/5（1–3 名）；合并 A/B：5/5 都在前 5。
- 完整：4/5。case_02 是上游排序失败，不是传输/预算；case_05 是组超过 top-10；case_10 是标签未确认。
- 同一并集池下，head 平铺 @10 5/5，MemoryFlow 4/5；@5 两者都 4/5；last 0/5。
  MemoryFlow 没有在这批超过同池平铺；它的价值在跨跳可解释，不在完整率。

## 100 目标去向（第一版）

| 状态 | 数量 |
|---|---|
| built-v2（主表 5） | 5 |
| control-final-sufficient | 1 |
| excluded-budget | 1 |
| excluded-date-unverified | 1 |
| built-prev（batch10 三题表） | 3 |
| candidate-full（待跑） | 10 |
| excluded-single-event | 43 |
| candidate-partial（待补标） | 11 |
| excluded-partial | 25 |

68 个此前筛掉的目标里，**16 个**有两处以上证据：10 个 candidate-full（跨事件）、4 个同事件
多证据（case_07 selected_01/08、case_10 selected_04/05），另有 2 个旧三题表目标。
下一批先跑 10 个 candidate-full；4 个同事件多证据按“两段各自必要”单独构造；
11 个 partial 先补标；剩余 47 个单段/partial 排除已逐条记原因（见 CSV）。

旧三题表复核：T06 仍作最终轮对照；T03/T09 的目标 ID 在 100 清单里，按本轮并集池复算后
才能并入累计表，本轮未完成，列为下一批，不重复计入。

## 产物

- 100 目标逐条清单：[SCREENING_100_20261106.csv](SCREENING_100_20261106.csv)
- 四方法明细：[BATCH10_V2_20261106.md](BATCH10_V2_20261106.md)
- 首批修正报告：[FIRST_QUALIFIED_20261106.md](FIRST_QUALIFIED_20261106.md)
- 矩阵：243 GPU0，union 平铺 prompt 219–403 tokens；已保存，可复算。

## 边界

- 5 条轨迹来自同一批 GenMem 记录；两轮受控构造，不是原始逐次请求。
- case_02、case_05、case_10 留作失败/排除，不粉饰。
- 旧 47 题、旧全历史池、pilot B04/F11 都不并入本表。
