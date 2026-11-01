# CUAD 两跳案例：一条结论怎么从合同原文走到报告（可读版）

数据：`artifacts/raw/flow_review_20261017/review/03_dcc_complete/flow.json`（CUAD dev "preferential rights"）；
计分为修复后重跑结果 `runs/dcc_flow_v1/20261029_v3_trapfix/flow_case.json`（固定头 (19,15)，Qwen2.5-7B 回放）。

## 1. 原任务问什么，最终报告给了什么

原任务（CUAD dev，合同偏好权条款）要求：在合同里找出与“优先权（preemptive / right of first refusal 等）”相关的条款原文。
DCC 系统先由研究者检索合同片段、写摘要，再由报告者产出最终引用片段。最终报告给出的是一句逐字条款：

> **2.1 Party A shall have a preemptive right to carry out mobile game services with Party B on a nationwide basis.**

中文解释：合同第 2.1 条约定，甲方对与乙方开展移动游戏服务拥有“优先权”。研究者摘要同时说明：合同里没有出现
“right of first refusal / first offer / first negotiation”这些字面术语，2.1 条的“preemptive right”是功能上最接近的表述，
建议由律师复核。该案例只做条款定位，不做“是否应当视为 ROFR”的法律判断。

## 2. 三个文本框（原文摘录 + 调用编号）

**A. 相关合同原文**（chunk `2593:3850`，研究员调用 4 的输入里可见）

> Article 2 Rights and Obligations of Party A
>
> **2.1 Party A shall have a preemptive right to carry out mobile game services with Party B on a nationwide basis.**
>
> 2.2 Party A shall have the right to know and review the business license, relevant qualification certificate, copyright ownership, business permits, bank account and such other information provided by Party B.

**B. 研究者摘要**（`summary_final`，由调用 4 `call_01a11cbb-2578-70a3-ad9b-7b5e496fa145` 产出，5,041 prompt tokens）

> The contract contains a clause in Article 2 (Rights and Obligations of Party A), Section 2.1: **'Party A shall have a preemptive right to carry out mobile game services with Party B on a nationwide basis.'** This is a preemptive right (functionally analogous to a right of first offer/negotiation) granting Party A priority to carry out mobile game services with Party B. No explicit 'right of first refusal', 'right of first offer', or 'right of first negotiation' terminology appears in the contract, but the 'preemptive right' clause in 2.1 is the closest match to the ROFR/ROFO/ROFN category and should be reviewed by a lawyer.

**C. 最终报告**（`report_span_0`，由调用 7 `call_01a11cbb-cc9d-7133-9771-0a5475b7b417` 产出，1,203 prompt tokens）

> **2.1 Party A shall have a preemptive right to carry out mobile game services with Party B on a nationwide basis.**

三处加粗内容是同一句条款的不同粒度：合同原文是完整句子；摘要把它写进分析；报告只回填这一句。

## 3. 关系图（记录里可核对 vs 回放估计）

```
13 个合同片段（source_chunk，共 13 个）──实际请求可见（记录：text_visible_in_input）──▶ 研究员调用 4
                                                                                  │ 产出
                                                                                  ▼
                                                                          摘要 summary_final
                                                                                  │
合同片段 2593:3850（含 2.1 条）──实际请求可见（记录）──────────────────┐          │ 实际请求可见（记录）
                                                                        ▼          ▼
                                                              报告者调用 7（1,203 tokens）
                                                                        │ 产出
                                                                        ▼
                                                          报告片段 report_span_0（2.1 条原文）

回放估计（虚线含义）：调用 4 的请求里，13 个片段对“摘要”的来源分数：2593:3850 **0.7569** 第一；
调用 7 的请求里，“摘要”对“报告片段”的来源分数 **0.6437**，同请求里 2593:3850 直达分数 **0.3563**。
```

- 实线（记录）：13 个片段出现在调用 4 的请求里（29 条 `text_visible_in_input` 边）；摘要与 2593:3850 都出现在调用 7 的请求里；
  2593:3850 到报告片段还有一条 `explicit_chunk_reference_and_verified_offset`（`result.json#/spans/0`）。
- 数值（回放）：固定头 (19,15) 在**该次实际请求**上重放得到的来源分数，不是原模型的依赖权重，也不是因果责任比例。

## 4. 来源表（修复后新值）

| 统计 | 数值 | 含义 |
|---|---:|---|
| 原文 2593:3850 对摘要的来源分数 | **0.7569** | 13 个片段里排第 1（第 2 名 0.1692） |
| 摘要对报告片段的来源分数 | **0.6437** | 报告者请求里“摘要”这一项的分数 |
| 乘积（原型路径计分） | **0.4872** | 0.7569 × 0.6437 |
| 直达分数（报告者请求里 2593:3850 本身） | **0.3563** | 条款原文也在报告者输入里 |
| 离线直达参考（不区分调用的通用模板） | 0.7131 | 仅作参考，不参与链路选择 |

- 排名：研究员矩阵里 `2593:3850` 第 1（0.7569）；报告者矩阵里“摘要”第 1（0.6437）、“原文 2593:3850”第 2（0.3563）。
- 乘积 0.4872 **是当前原型的路径计分规则**（把两跳的局部关联相乘），不是“真实依赖概率”；
  两条路径都保留：间接 0.4872 与直达 0.3563，本案例间接更大。

## 5. 展示口径与限制

- 这个例子说明：**跨调用的内容记录 + 局部矩阵**可以连成一条可查的链——13 个片段如何进入摘要、摘要与原文如何进入报告，都能回到具体调用与请求。
- 它**没有**检验“多条款、多条件判断”，也**不能**证明“多跳一定优于直接溯源”：这里只有一份摘要、一个结论，
  所有根来源的间接分数都乘同一个 0.6437。
- 原文同时出现在摘要与报告者输入中时，实际生成采用了哪一路，现有记录与回放分数**尚不能唯一确定**；
  报告里的“间接/直达”是两条候选路径的分数，不是已证实的实际依赖。
- 本页数字用于汇报素材，不修改 PPT；术语按“来源关联分数”表述，不写成“内容质量”或“回报片段质量”。
