# SP Semantic Edge Recoverability Audit (C5C-Local)

本报告只审计 manifest 中的 20 个 pilot Case。未修改 `sp_nodes.jsonl`，未运行模型/GPU，未使用文本相似度创建任何边。

## 结论

- 恢复等级：A=0，B=14，C=6。
- 建议：**C**：当前日志只适合工作流分析，不适合语义溯源 Gold。
- 审计自动创建的语义边：0。

## 现有边类型统计

| evidence_type | parent step_type | child step_type | edge class | count |
|---|---|---|---|---:|
| explicit | other | report_paragraph | containment | 445 |
| explicit | other | retrieval_observation | workflow | 22 |
| inferred | other | outline | workflow | 20 |
| inferred | other | retrieval_observation | workflow | 1 |
| inferred | query | other | unclassified | 21 |
| inferred | query | other | workflow | 65 |

分类合计：
- Workflow Edge：108
- Containment Edge：445
- Semantic Provenance Edge：0（仅统计已有 Observation/Outline→Report parent link）
- Unclassified：21

## 引用和定位统计

- report_paragraph_total: 445
- report_paragraph_with_parseable_citation_numbers: 97
- citation_occurrence_total: 418
- citation_occurrences_locatable_to_observation: 0
- citation_occurrences_unlocatable: 418
- manual_review_target_paragraph_total: 445

## Pilot Case 恢复等级

A 只允许存在显式 Semantic Provenance parent edge；B 表示可观察到引用编号或标题结构，但仍需规则/少量人工确认；C 表示没有足够日志证据，只能做语义标注。

| case_id | 等级 | report paragraphs | citation paragraphs | explicit semantic edges | exact outline/report headings | manual-review targets |
|---|---|---:|---:|---:|---:|---:|
| 73f905f2-4a90-47b7-ae98-6d7da87b50d1 | B | 42 | 1 | 0 | 0 | 1 |
| a765ea7b-fe46-462d-b1f1-5a532e0dc244 | B | 45 | 6 | 0 | 0 | 6 |
| d4a0a481-9a6a-44eb-9fba-6de7c5f9f282 | B | 40 | 6 | 0 | 0 | 6 |
| f2533580-b8b9-469f-91fe-e6b244682c08 | C | 50 | 0 | 0 | 0 | 0 |
| 5739a8b6-46c7-41db-afef-c9c3b32683ca | B | 77 | 1 | 0 | 0 | 1 |
| 71a6a240-3a7a-4ea3-bc44-13f376162c9f | B | 9 | 2 | 0 | 0 | 2 |
| 52511e6f-d025-4fde-a96a-83c5929c201e | B | 10 | 9 | 0 | 0 | 9 |
| 959b4490-f22d-404c-b7ea-16cde0e0ddcb | C | 6 | 0 | 0 | 0 | 0 |
| 4e439738-234d-49a5-be68-53c55fb859c0 | C | 8 | 0 | 0 | 0 | 0 |
| 73d9ee5e-cada-4551-95b6-e0719dcebe2c | C | 15 | 0 | 0 | 0 | 0 |
| 5f453386-3ad1-422d-ba8f-a8d604949e90 | B | 10 | 8 | 0 | 0 | 8 |
| 74a71f74-6726-4cf8-97b9-1e28dcffebdf | B | 10 | 7 | 0 | 0 | 7 |
| 3bf81df5-78aa-44f8-bcd3-5d890f4d8024 | B | 12 | 9 | 0 | 0 | 9 |
| 0b395360-883d-4632-9b03-bc781b7e84cb | C | 12 | 0 | 0 | 0 | 0 |
| 87a1fd85-04df-4b65-8b98-34ab2bafeb04 | B | 18 | 8 | 0 | 0 | 8 |
| 4313d8d6-e817-4fca-9e72-227e46dfc969 | B | 36 | 16 | 0 | 0 | 16 |
| eebf776a-800c-4d13-8ece-dd6b957e4759 | B | 14 | 9 | 0 | 0 | 9 |
| 44864557-6514-4346-8565-c5dd822a1402 | B | 11 | 8 | 0 | 7 | 8 |
| 8ecb606d-d48c-499a-ab9a-cb8cbb583dbb | B | 10 | 7 | 0 | 0 | 7 |
| 595aca02-7ae7-4adc-a2db-6e3baba29d26 | C | 10 | 0 | 0 | 0 | 0 |

## 五个真实例子

### 2 个可通过显式 ID 自动恢复
- 实际没有等级 A Case；不填充伪造例子。

### 2 个部分可恢复
- `73f905f2-4a90-47b7-ae98-6d7da87b50d1`：Only citation/heading signals are observable; they are not treated as semantic Gold edges. Query：In ecology, how do birds achieve precise location and direction navigation during migration? What cues and disturbances influence this process?
- `a765ea7b-fe46-462d-b1f1-5a532e0dc244`：Only citation/heading signals are observable; they are not treated as semantic Gold edges. Query：While the market features diverse quantitative strategies like multi-factor and high-frequency trading, it lacks a single, standardized benchmark for assessing their performance across multiple dimensions such as returns, risk, and adaptability to market conditions. Could we develop a general yet rigorous evaluation framework to enable accurate comparison and analysis of various advanced quant strategies?

### 1 个不可恢复
- `f2533580-b8b9-469f-91fe-e6b244682c08`：No explicit Observation/Outline→Report provenance ID or edge is present in pilot nodes. Query：Summarize recent research progress in reinforcement learning focused on enabling agents to explore efficiently and proactively under conditions of sparse rewards and constraints, respectively. Additionally, analyze and discuss the potential implications and insights this research provides for trajectory planning problems.

### 额外真实例子（用于达到 5 条；因 A 级为空，不伪造 A 级）

- `d4a0a481-9a6a-44eb-9fba-6de7c5f9f282`（B）：Only citation/heading signals are observable; they are not treated as semantic Gold edges. Query：How to conduct comprehensive and accurate situational awareness of space targets in the cislunar space, and support the effectiveness of short-term cislunar space tracking and monitoring tasks?
- `5739a8b6-46c7-41db-afef-c9c3b32683ca`（B）：Only citation/heading signals are observable; they are not treated as semantic Gold edges. Query：Create comprehensive, in-depth study notes for the Diamond Sutra (Vajracchedikā Prajñāpāramitā Sūtra). These notes should offer deep analysis and interpretation from various perspectives, exploring its teachings and relevance in contexts such as daily life, the workplace/career, business practices, marriage, parenting, emotional well-being, and interpersonal dynamics.

## 证据边界

Observation 中的 URL、标题、检索序号或引用标记只作为可见性诊断；Report 中的 `[1]`、`【1】` 或标题相同也不自动映射到 Observation。只有日志中显式 ID/依赖字段才能升级为 Semantic Provenance Edge。

## 输入与完整性

- Pilot Case：20；Pilot 节点：597。
- sp_nodes SHA-256：`619ae5574b2b62e2bae413af4975d6aea550b67818e50fb635d66cd8d43d1794`
- manifest SHA-256：`5d3cf3e296fd473768d6ef1b35caf021e11ee34b46f0671111996db612a41a00`
- 所有 pilot parent_id 均可解析；输入节点未修改；审计未使用模型/GPU/文本相似度。
