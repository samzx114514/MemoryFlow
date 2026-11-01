# G 轮续做：G2 连接修复、G3 日志驱动队列、G4 统一口径（2026-10-31 晚）

## 1. 本轮做了什么、结果

| 项 | 判定 | 关键结果 |
|---|---|---|
| G2 查询 | 修复 | 一条命令从 `report_span_0` 自动展开：报告 → call7（生成）→ 摘要（0.6437）→ call4（生成）→ 13 个上游片段；最后调用实际可见 **2 个单元**（摘要 + 原文），已按 planner 更正 |
| G2 森林 | 修复+补缺口 | 角色前缀识别修正；v6 = Central 14 条链、coder 3、perception 2、memory_recaller 1；0 个分支；session key = Agent+工具集 hash；缺原生 session/delegate 标识 |
| G3 队列 | 新增（日志驱动） | 7 个理由句分析共约 10 秒；`answer_ready − sources_ready = −251.4 s`（来源在答案前就绪），max backlog 6；**日志驱动，非在线** |
| G4 口径 | 补做+更正 | 用标准 predictor 重跑 1.5B：@5 0.5532 / @10 0.6383 / Frag@1 0.2553；46.54 s、11.87 GB（11.05 GiB）；7B 同流程 105.43 s、35.24 GB（32.82 GiB） |
| G7 | 未实现 | 下一轮 |

## 2. G2 细节

- 查询：`query.py` 现在沿 `estimate` 边继续展开，且按边而不是按节点防环，两条合法路径都保留；分支局部访问集合避免全局吞路径。
- 对照：`compare_views.py` 统计 call7 的 `history` 输入（摘要 + 原文，2 个单元）；跨步追查再给出摘要的产生调用与 13 个上游片段。此前“只看见 1 个单元”的结论已撤回。
- 森林：`agent_of` 改为系统提示前缀匹配（CentralAgent / memory_recaller / perception / coder），session key 加入请求工具集 hash，父调用必须更早且同 session key；结果：`{"central":14,"coder":3,"perception":2,"memory_recaller":1}`，branches=0。缺采集字段：原生 session_id、delegate 调用与子 Agent 会话的映射、每调用的输出 artifact 引用。
- 图：A 面板改为真实角色链数量；B 面板改用 CUAD 有效矩阵（13 候选，0.7569 首位）并注明 v6 退化只作诊断；C 面板补上“摘要→call7 可见”“call7→报告 生成”，0.3563 指向报告内容、0.6437 指向摘要，0.7569 写为整段分数并标句级 gap。

## 3. G3 日志驱动队列

- 固定范围：`recovery-verdict.json` 的 7 个理由句；每句候选来自其生成调用可见的工具返回（最多 120 行）。
- 单 worker FIFO；分析时长用固定头内核实测（1.0–1.9 s/句，共约 10 s）；时间轴用调用完成时刻（`ts+elapsed`）模拟。
- 结果：`answer_ready=1793278637.899`、`sources_ready=1793278386.498`、`extra_wait=−251.4 s`、`max_backlog=6`。含义：该任务的选定分析在答案产生前约 4 分钟已完成，队列无额外等待；**不是在线流水线**。
- 产物：`/data1/songzhengxing_intern_dccv2/g3_queue_v6.json`、`g3_queue.py`。

## 4. G4 统一口径

标准 predictor（`predict_small.py`，同 predictor 同协议，仅换模型与读写头）：

| 模型 | 头 | @5 | @10 | Frag@1 | 时间（88 forwards，empty+context） | 峰值显存 |
|---|---|---|---|---|---|---|
| Qwen2.5-7B | (19,15) 固定 | 0.6170 (29/47) | 0.7021 (33/47) | 0.4894 (23/47) | 105.43 s | 35.24 GB / 32.82 GiB |
| Qwen2.5-1.5B | (16,2) 开发集选 | 0.5532 (26/47) | 0.6383 (30/47) | 0.2553 (12/47) | 46.54 s | 11.87 GB / 11.05 GiB |

- 同流程同工作量：1.5B **快 2.27×**、显存 **省 2.97×**；@5/@10 各低 6.4 个百分点，Frag@1 低 23.4 个百分点。
- 较早的 39.92 s 来自自建脚本（47 forwards、单变体），与标准流程不可比，按本表为准。
- 开发集口径：扫描用了 11 个 dev 目标（case_02/08），比冻结协议多 3 个：`genmem_874c34ceb20bf193:selected_07/08/09`（均 case_02、标注 full coverage、在 55 目标协议中属于 not_runnable 的超限目标）；三者与 47 个评测目标 case 无重叠，不构成评测泄漏。选头在 11 个上重复一次仍为 (16,2)，按要求不据评测结果重选。
- 计时元数据：单次运行、无预热重复（模型加载不计入）；47 目标、23 个共享前缀组、88 forwards（empty+context 两个变体）；独占 GPU（7B 在 GPU1、1.5B 在 GPU2）；不能写成三次稳态中位。

## 5. 下一轮

- G7：共享前缀 + 分支隔离的 P 入口与 5 项局部检查，再做 88 目标 D/P 对照。
- G2：补原生 session/delegate 字段的采集清单；等新版 DCCv2 后接正式案例。
- G3：在线 E0/E1/E2 等可运行任务；日志驱动结果保持其身份。
