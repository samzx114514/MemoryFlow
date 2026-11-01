# G1：新版 DCCv2 正式接入与第一条完整运行（2026-10-31）

## 1. 版本与接入

- 远端分支头确认：`3c98481507b8c1725cf70b64c609c8e31ce229e5`（DCCv2，2026-10-31 21:50 北京时间）。
- 新检出：`/data1/songzhengxing_intern_dccv2/sp2_dccv2_3c984815`（git worktree，旧 `0914afc3` 现场保留；未叠加旧补丁）。
- 数据：官方 Release `rulearena-nba-v1`（195,463 字节，216 条任务），安装到 `.benchmark-data/rulearena-nba-v1/bundle`。
- 本地新增记录层（只加采集，不改规划/工具/完成判定）：
  - `dcc_harness/evaluation/dcc_trace.py`：`TraceChatOpenAI(BenchmarkChatOpenAI)`，记录每次模型调用的完整公开请求（messages + tool schemas）、可见响应、工具调用与 usage 到 `calls.jsonl`。
  - `benchmark_runner.effective_app` 支持 `DCC_MODEL_USE` 环境变量选择该 transport（1 行）。
  - `preprocessing/native.py` 的 inline 任务追加交付机制说明（见 §3），官方场景、Assume、金额与输出格式未改。

## 2. 任务映射（旧 comp_0#004 → 新编号）

新 Release 的任务编号与旧任务清单不一致：旧 `comp_0#004`（Team A $176M / Team B $136M / 23rd pick 2016…）对应新 **`rulearena-nba-comp0-003`**。核对方式：新 `document` 与旧 prompt 11/11 行一致、归一化后逐字相等。新 gold：`answer=true, illegal_operation=B, problematic_team=B`（与旧认识一致）。单任务清单写入 `bundle/public/g1_tasks_004.jsonl`（路径相对 bundle 才能解析规则/上下文文件）。

## 3. 两次运行与直接原因

**Run 1**（`runs/g1_v3_20261031`）：9 次调用、162.1 s、4 轮，`status=unfinished`。
- 直接原因（事实）：模型调用 `sp_finish`，参数 `final_artifact_ref=spart_27f1af2ce77821e0, required_artifact_type="report"`，但**没有任何 write_file 调用**、该 artifact 不存在；原生 FINISH 拒绝：`FINISH requires required artifact type 'report' and a matching final_artifact_ref`。模型自己编了引用。

**适配修复**（记录在案）：inline 任务 `prepare_task` 末尾追加交付机制说明——"用原生 write_file 把完整答案写入 `answer.md`，再用该 artifact 的准确 id 与 `required_artifact_type="report"` 调 FINISH"。只补交付机制，不动题目、Assume、金额、输出格式。

**Run 2**（`runs/g1_v3_20261031b`）：24 次调用、8 轮、**571.9 s，status=completed**，原生 FINISH 接受。
- 最终交付 artifact：`spart_a9627af0556afc2e`（`report_revision` v2）；delivery SHA256 `819cf38e…`；`delivery` 为一份完整分析报告。
- 记录齐全：`calls.jsonl`（24 条完整请求/响应）、`attempts/0000/{state.json,trace.jsonl,result.json}`、`native-state-g1-v3b/`、`manifest.json`。

## 4. 执行 / 交付 / 正确性分开报告

| 项 | 结果 |
|---|---|
| 执行 | ✅ completed（原生 FINISH 接受，8 轮、571.9 s） |
| 交付 | ✅ 有最终交付：报告 artifact（`report_revision` v2）+ 文本 delivery，SHA256 已记录 |
| 正确性 | ❌ **accuracy = 0.0**（官方 Accuracy-only，`rule_metrics=not_requested`） |

交付结论原文：“**Answer: True. Illegal Operation: A. Problematic Team: B.**”；官方 gold 为 `True / B / B`。违规判断与球队正确，**违规操作字母错（A vs B）**。评测只从已保存交付读取，未重跑任务；`evaluated_samples=1 / available 216`，`complete_dataset=false`。

## 5. 下一步

- **G2**：在这条 run 上选 1—2 条判断（优先交付里的操作判断与中间摘要），用 7B 固定头回放，产出可查询路径与路径表；同一 attempt，保留实际请求与目标前文。
- **G3**：E0 = 本轮 run（571.9 s、24 调用）；E1 用保存记录串行分析；E2 在线重叠用独立 GPU，同一分析协议。
- **G7**：按任务单先查 mask 语义（Qwen2 eager 加性 mask），再对齐 D/P 的 token、行、位置与候选区间。

## 6. 产物

- 运行：`/data1/songzhengxing_intern_dccv2/runs/g1_v3_20261031b/`（calls/predictions/attempts/manifest）
- 评测：`/data1/songzhengxing_intern_dccv2/eval/g1_v3_20261031b_accuracy2/{scores.jsonl,report.json}`
- 单任务与选项：`bundle/public/g1_tasks_004.jsonl`、`/data1/songzhengxing_intern_dccv2/nba_accuracy_only.json`
- 补丁：`dcc_trace.py`、`benchmark_runner.py`（DCC_MODEL_USE）、`native.py`（DELIVERY_NOTE）
