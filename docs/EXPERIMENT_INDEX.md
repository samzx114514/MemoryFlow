# 实验索引

## G2 递归/森林修正、G3 队列、G7 布局（2026-10-31 晚）

**状态：G2 的查询/最后输入/森林分类修正完成；G3 CPU 队列原型完成；G7 CPU 布局检查完成；真实 D/P 性能与 G1 未完成。** 入口 [G2 后续](../experiments/source_path_v1/G2_FOLLOWUP_20261031.md)、[G3 队列](../experiments/task_timing_v1/reports/G3_QUEUE_20261031.md)、[G7 布局](../experiments/branch_packing_v1/reports/PACKING_LAYOUT_20261031.md)。

- G2：`query.py` 跨 estimate 追溯；`compare_views.py` 最后输入为摘要+原文 2 units；森林 20 roots（central 14/coder 3/perception 2/memory 1），0 branches 仅是当前恢复结果。
- G3：44 calls、分析 0.25 s/call 假设下 E0 896.653 s / E1 907.653 s / E2 896.903 s；E2 是日志回放，不是在线流水线。
- G7：共享前缀+分支 target 的 4-D mask/position 布局，6 项 CPU 测试通过；未做真实 7B D/P 性能。
- G4：质量/时间/显存已有；11 个开发目标 ID、单位、计时重复次数见 [G4 说明](../experiments/source_path_v1/G4_NOTES_20261031.md)；原 8 目标冻结清单未保存，候选反推不作事实。
## G2 来源链/森林/图 + G4 小模型（2026-10-31 初版）

**状态：G2 本轮范围完成；G4 质量/时间/显存完成；G1 阻塞；G3/G7 未实现。** 入口 [G 轮记录](../experiments/source_path_v1/G_ROUND_20261031.md)。

- G2：v2 查询、森林（v6 20 roots/0 分支）、三视图、方法二对照（最后调用 vs 全链）。
- G4：1.5B @5 0.5532/@10 0.6383/Frag@1 0.3191，39.92 s/11.87 GiB；7B 0.6170/0.7021/0.4894，105.43 s/35.24 GiB。
- G1 等新版 DCCv2；G3 队列、G7 packing 下一步。
## 来源路径身份修复（2026-10-30 第三轮）

**状态：四项修复完成；v6 回放退化待修；DCCv2 未再运行。** 入口 [修复前后对照](../experiments/source_path_v1/SOURCE_PATH_V2_20261030.md)。

- 摘要父单元+句单元、生成/可见分离、端点齐全、工具结果 full_ref。
- v6 生成归属 call31（写文件 call38）；回放矩阵退化（单候选占满）。
- DCCv2：v10 call40 finish=length；Central 提示未见简短输出约束，待讨论。
## 可查来源路径原型 + DCCv2 参数修复（2026-10-30 第二轮）

**状态：原型可用（CUAD + v6 两种输入）；DCCv2 参数修复生效但 v10 仍未 FINISH（输出 8192 截断）。** 入口 [来源路径](../experiments/source_path_v1/SOURCE_PATH_20261030.md)、[DCCv2 v10](../experiments/dcc_nba_v1/reports/DCCv2_参数修复与v10_20261030.md)。

- 原型：`source_path_v1/{build.py,query.py}`，`out/path_cuad.json` / `out/path_v6.json`；记录/估计/缺口分列。
- 计分：CUAD max vs sum 排序不变；只有条款原文有两条路径。
- DCCv2：重试 8192、等待 180/90、`thinking: disabled`；v10 未 FINISH、无答案（8192 截断）。
- 服务器 `runs/dccv2/20261030_nba_v10_params/`。本机无 git。
## 官方前提恢复与收尾失败定位（2026-10-30）

**状态：前提已修复并验证；三次运行均未 FINISH，失败在模型响应层（空响应/截断/超时）。** 入口 [前提修复与收尾诊断](../experiments/dcc_nba_v1/reports/DCCv2_前提修复与收尾诊断_20261030.md)。

- 前提：官方 Assume 段（RuleArena blob `06cbfa74d0…`）已拼入 `prepare_task`；v6 首调 0/6 金额，v8/v9 6/6。
- 未 FINISH：v6 产物已注册但 FINISH 动作 0 次；v7 `SPCentralEmptyResponse`（2048 被推理耗尽）；v8 8192 截断；v9 `SPCentralModelTimeout`。
- 修改：perception 40→80、outline 30→60、coder 100→130（工具预算）；`thinking: disabled` 实测有效。
- 待决定：Central 超时放宽 / 收尾提示 / 换非思考模型或短输出兜底。
- 服务器 `runs/dccv2/20261030_nba_v{7,8,9}_*/`。本机无 git。
## DCCv2 聚焦诊断与修复（2026-10-29 第六轮）

**状态：4 项修好、1 项输入缺口证实、1 项待查（Central 收尾）；v6 一次运行未 FINISH。** 入口 [诊断与修复](../experiments/dcc_nba_v1/reports/DCCv2_适配诊断与修复_20261029.md)。

- 修好：空响应、grep 文件路径、记录完整、子任务工具上限 15→20（sp-coder max_turns 100→130）。
- 输入缺口：规则文件无 2024-25 工资帽金额（只有交易例外金额）；模型观察正确。
- v6：44 调用、896.9 s、未 FINISH；产物 violation=false（官方 True/B/B）。
- 效率记录修正：S 正式 2 次、S/S+O 完整哈希相同；CUAD 排名措辞修正。
- 服务器 `runs/dccv2/20261029_nba_v6_toolbudget/`。本机无 git。
## S/S+O/S+R 配对、CUAD 展示稿、SP1 尝试（2026-10-29 第五轮）

**状态：效率配对完成；CUAD 展示材料完成；SP1 NBA 未完成（thinking 预算耗尽）。** 入口 [S/S+O/S+R](../experiments/flow_efficiency_v1/reports/YF_SOR_20261029.md)、[CUAD 展示稿](../experiments/dcc_flow_v1/reports/CUAD_CHAIN_SHOWCASE_20261029.md)、[SP1 尝试](../experiments/dcc_nba_v1/reports/SP1_NBA_ATTEMPT_20261029.md)。

- **效率**：S 3.687 s、S+O 4.097 s（+11.1%，输出相同）、R 1.014 s、S+R 4.701 s（TP=1，同一服务）。
- **CUAD**：0.7569 / 0.6437 / 0.4872，直达 0.3563；三框 + 图 + 口径说明。
- **SP1**：24k-token 注入可行，模型推理耗尽 8192 输出预算后超时；需关 thinking。
- 服务器 `runs/sp1/nba_6tlu479r/`、`/data1/songzhengxing_intern_dccv2/yf_server/p0/`。本机无 git。
## 短条件对照修正、CUAD 案例补算（2026-10-29 第四轮）

**状态：P0 部分完成（捕获证据已核实、捕获增量未能严格同条件）、P1 用 CUAD 两跳补位、P2 收尾。** 入口 [P0 短条件](../experiments/flow_efficiency_v1/reports/YF_P0_SHORT_20261029.md)、[CUAD 补算](../experiments/dcc_flow_v1/reports/CUAD_CHAIN_RECOMPUTE_20261029.md)。

- **P0**：原先“有捕获 1.84 s”实为无捕获；客户端捕获路径有效（生成 2.286 + 后处理 0.017 s，Q/K 证据齐全）。G0 8.89 / G1 8.95 / G2 无捕获 2.05 s；R 0.915 s；G0/G2 差异未定位（输出不同 + GPU 被占），不作 hook 归因。
- **P1**：CUAD 两跳 0.7595→0.7569、0.4889→0.4872，顺序不变；NBA 完整案例仍缺（SP1 需另做规则注入）。
- **P2**：质量新表为有效表（61.70/70.21/48.94）。
- 服务器 `runs/dcc_flow_v1/20261029_v3_trapfix/`、`/data1/songzhengxing_intern_dccv2/yf_server/p0/`。本机无 git。
## 质量补算、yf 实测、子任务上限追补（2026-10-29 第三轮）

**状态：B 完成、C 短样例+四设置完成（六条件未跑）、A 仍未 FINISH。** 入口 [质量补算](../experiments/genmem_quality_v2/reports/TRAP_FIX_RECOMPUTE_20261029.md)、[yf 效率](../experiments/flow_efficiency_v1/reports/YF_EFFICIENCY_20261029.md)、[A 追补](../experiments/dcc_nba_v1/reports/DCCv2_诊断与修复_20261029.md)。

- **B**：N=47 固定头 @5 **0.6170**、@10 **0.7021**（不变）、Frag@1 0.4894；Top-1 变化 0、Top-5 变化 10；原结论不变。
- **C**：G0 8.79 / G1 8.95 / G2 无捕获 1.92 / G2 有捕获 1.84 s（同输出）；后处理 0.017 s；R 1.44 s；G2 vs G0 输出不同，不作 hook 归因。
- **A**：skill + grep 两处最小修复后，v5 仍被“重复调用 + 工具硬上限”中止；无完整案例。
- 服务器 `runs/genmem_quality_v2/20261029_v1_trapfix/`、`/data1/songzhengxing_intern_dccv2/yf_server/`。本机无 git。
## DCCv2 执行端诊断、回放端修正、yf 交付包可行性（2026-10-29 第二轮）

**状态：A 完成（修复+单次运行，仍未 FINISH）、B 完成（计分修复+链 v2）、C 仅可行性。** 入口 [诊断与修复](../experiments/dcc_nba_v1/reports/DCCv2_诊断与修复_20261029.md)、[链 v2](../experiments/dcc_nba_v1/reports/NBA_CHAIN_20261029_v2.md)、[计分修复](../experiments/genmem_quality_v2/reports/TRAP_FIX_20261029.md)、[C 可行性](../experiments/flow_efficiency_v1/reports/C_YF_DELIVERY_FEASIBILITY_20261029.md)。

- **A**：Central 空响应 = 4096 输出预算被隐藏推理耗尽（length + 空正文 + 无 tool call）；修复后 11 次调用 0 次 length；新堵点 = 子 agent `loop_capped`（2 次），停在 3 轮。
- **B**：计分半开区间修复（旧式误差 0.736 → 修复后 3e-7；3 目标指标不变）；链 v2 归属修正后 4 条边全 replay_only（验证未进入最终判断）；缺口 2 个。
- **C**：包与环境/模型/插件身份核对通过；根分区满，需把缓存与 TMPDIR 移到 `/data1`；未启动服务，同骨干对照仍需适配。
- 服务器 `runs/dccv2/20261029_nba_v3_fix/`、`runs/dccv2/20261029_nba_v1/source_chain_v2/`、`runs/flow_efficiency_v1/20261029_trap_fix/`。本机无 git。
## DCCv2 NBA 两例、来源链、整批前缀复用（2026-10-29）

**状态：A/B 完成（两例均未 FINISH，记录与产物保留）、C1 完成、C2 缺口说明。** 入口 [结果说明](../experiments/dcc_nba_v1/reports/DCCv2_NBA_结果说明.md)、[来源链](../experiments/dcc_nba_v1/reports/NBA_CHAIN_20261029.md)、[效率](../experiments/flow_efficiency_v1/reports/EFFICIENCY_20261029.md)、[C2](../experiments/flow_efficiency_v1/reports/C2_YF_PIECEWISE_20261029.md)。

- **DCCv2**：commit `0914afc3…`，独立 clone + `venv312`（Python 3.12.16）；`--check-config` 通过；NBA 插件（prepare/inputs/skills/parse/score）与调用记录包装就位。两例 Central 未 FINISH：#003 `protocol_error` 333 s、#004 `infrastructure_error` 576.7 s、#003 重试（pro）476.7 s。
- **判断对比**：#003 False vs 官方 True/A/A；#004 True/A/Team B vs 官方 True/B/B。98 次调用、1,660,994 tokens。
- **来源链**：#004 最终判断 top 来源 `rule_93/68/16`；验证段落 top `rule_53/130/136/109`；缺 2024-25 金额；`check_3` 缺口。
- **效率**：88 目标/36 组/64.26% 复用；B 406.1 s vs D 140.7 s（2.89×），分数完全一致，峰值相同。
- 服务器 `runs/dccv2/20261029_nba_v1|v2/`、`runs/flow_efficiency_v1/20261029_batch_reuse*/`。本机无 git。
## 多轨迹基线、SP1 简查、CLM 方案（2026-10-28 收尾）

**状态：三项完成（无新训练、无新增付费调用）。** 入口 [多方法主表](../experiments/genmem_baselines_v2/reports/MULTI_METHOD_20261028.md)、[SP1 简查](../experiments/sp1_runtime_v1/reports/SP1_REVIEW_20261028.md)、[CLM 方案](../experiments/baseline_adapters_v1/reports/CLM_ADAPT_PLAN_20261028.md)。

- **多轨迹基线**：55 个目标（评测 47 / 开发 8）、36,584 对，补齐随机、F_mean、R-SYM（3 seed）、D-Full（3 seed）、CLM。固定头 @5/@10 0.5957/0.7021（宏平均 0.5376/0.6753），D-Full 0.5319/0.6809，BM25 0.5532/0.6170，平均头 0.5745/0.6170，R-SYM 0.4468/0.5816，F_mean 0.2766/0.4043，CLM 0.1277/0.1915，随机 0.0108/0.0215。修正“宏平均=目标平均”的错误。
- **SP1.0**：DeerFlow 系、HEAD c81444fe…；记录器 v3 SHA 88f6d212…；单一 BASIC_MODEL=deepseek-v4-flash-0731；日志缺工具定义与 token IDs、摘要未落盘；uv 不在本账号 PATH → 无法重启与做停止传播测试；NBA 需题目注入与提示/工作流适配。
- **CLM**：官方头迁移结果保留；适配方案（冻结 backbone、只训投影头、组内等价不互为负例、同预算比较）已写成，不训练。
- 服务器
uns/genmem_baselines_v2/20261028_v1/。本机无 git。

## GenMem 正式评价与 NBA 首例（2026-10-28 晚）

**状态：两项完成。** 入口 [GenMem 评价](../experiments/genmem_quality_v2/reports/QUALITY_CONTEXTUAL64_20261028.md)、[NBA 案例](../experiments/nba_case_v1/reports/NBA_CASE_20261028.md)。

- **GenMem**：采用用户确认的 contextual64_v4 规范证据，复用冻结窗口预测（无 GPU）。分母 55（v4 64 ∩ 可运行 88 = 56，排除 case_10 T01），评测集 47、开发集 8、83 组、160 片段。固定头 @5 0.5957 / @10 0.7021 / FragHit@1 0.4894；平均头 0.5745 / 0.6170 / 0.3404；BM25 0.5532 / 0.6170 / 0.5745；随机头 @5 0.0638–0.5532。前文变体对所有方法都不更好。
- **NBA comp_0#003**：三次真实调用（21,700 / 22,052 / 961 tokens），模型判 False，官方 True。错误起点 check_2 把 2020 年合同长度当服役年数（4 年，套 <7 年档），最终判断以 0.8047 质量沿用；薪资帽/空间/例外从未核查。路径：
ule_12 间接 0.3474、act_7 直达 0.0869；直接回溯与多跳前四名一致。
- **CUAD 修正**：研究者矩阵答案片段分数 0.5045 → 0.7595（机器结果），未重跑。
- 服务器
uns/genmem_quality_v2/20261028_v1/metrics_contextual64/、
uns/nba_case_v1/20261028_v1*/。本机无 git。

## 规划侧复核后的最小补充（2026-10-28 晚）

**状态：三项补充完成，均为 CPU/标签层面，未重跑 GPU。** 见 [候选接入表](../experiments/dcc_candidates_v1/reports/ACCESS_20261028.md)、[NBA 规则映射](../experiments/dcc_candidates_v1/reports/NBA_RULE_MAP_20261028.md)、[v2 预测说明](../experiments/genmem_quality_v2/reports/PREDICT_20261028.md)、[Flow case（完整上下文回放）](../experiments/dcc_flow_v1/reports/FLOW_CASE_20261028.md)。

- **标签版本**：评测侧入口改为 ZIP 内的 `ground_truth_v2`（v2：64 完整/36 部分；88 条可容纳子集 56 完整/32 部分、84 组覆盖 56 个目标），v1 与两版身份、SHA256 都记在 `labels/labels_version.json`；模型输入与 `scores_full.jsonl` 未变，未重跑 GPU。覆盖率 88/100，12 条“本协议不可评分”（11 条不含前文也超限）；Known evidence 分母 88、CompleteGroup 分母 56。
- **CUAD Flow**：回放改为**该次调用完整请求文本**（call 4 = 5,041 tokens，call 7 = 1,203 tokens），候选 = 请求里逐字出现的记录片段（保留重复出现与角色），目标 = 记录输出单元，输出前文缺失如实记录；路径枚举间接与直达并取最大值：答案片段间接 **0.4889**、直达 **0.3563**、最大值 0.4889（间接）；摘要对结论 0.6437。旧通用模板版（0.7103 / 0.3583 vs 0.2897）保留在 `runs/dcc_flow_v1/20261028_v1/`。
- **NBA comp_0#003 规则映射**：五条规则各自到 `reference_rules.txt` 的字符区间、引文、必要事实字段与可支持条件已建表；三处歧义待确认（Years of Service 定义、出生日期、是否使用例外）。规则名与答案不进模型输入。
- 服务器 `runs/genmem_quality_v2/20261028_v1/`、`runs/dcc_flow_v1/20261028_v2/`；本机无 git，未提交未推送。
## 四候选接入检查、来源质量 v2 预测、DCC Flow（2026-10-28）

**状态：任务零完成；任务一“预测完成，待标签评价”；任务二单 case 完成。** 入口 [候选接入表](../experiments/dcc_candidates_v1/reports/ACCESS_20261028.md)、[v2 预测说明](../experiments/genmem_quality_v2/reports/PREDICT_20261028.md)、[Flow case](../experiments/dcc_flow_v1/reports/FLOW_CASE_20261028.md)。

- **候选接入**：RuleArena NBA 两个 level-1 样例完整 0-shot 输入 21,952 / 22,095 tokens（在 32,768 内），`relevant_rules` 是规则名而非字符区间；CLAUSE `ANIXABIO…` 两端逐字命中可用，`ADAMSGOLF…`/`ABILITYINC…` 的 contradicted 端缺失不可用；FinRule-Bench 401、FinAuditing gated。
- **来源质量 v2**：候选载荷与上一版逐字节相同，新增“含目标前文”变体（读行 `P+C-1 … P+C+n-2`）。88 目标 × 2 变体 = 176 行、12 条件、36 前缀组、164 前向、170.6 秒、峰值 32.8 GiB。行对齐、缓存回退、错位负对照、重复运行 0.0 全过；76 个有前文目标两变体分数全部不同。参考草稿 100 条全 pending、gold=false（55 完整/44 部分/1 未解决），**不发布质量成绩**。
- **DCC Flow**：trace `00923364ccde0fd5`，13 片段/8 调用/1 摘要/1 结论；摘要对结论的注意力质量 0.7103；直接溯源与多跳都把答案片段排第 1，但次席不同（直接 `3670:4931` 0.1266 vs 多跳 0.0244）。决策调用输出未留存，语义矩阵缺失已记录。
- 代码：`experiments/{genmem_quality_v2,dcc_flow_v1,dcc_candidates_v1}/`；测试 12 项 CPU 通过；原文只在工作目录与服务器。

## 前缀复用验证（2026-10-27 晚）


**状态：COMPLETED / 待协调侧审查。** 入口 [README](../experiments/prefix_reuse_v1/README.md)、[报告](../experiments/prefix_reuse_v1/reports/REPORT.md)。3 个前缀组 × 8 目标，比较 A（逐 token 回放）/ B（目标块并行）/ C（普通 batch）/ D（共享前缀 + 串行分支）。

- **时间**（整组 8 目标，中位数）：A 8.98 / 28.01 / 38.69 秒，B 8.24 / 24.83 / 38.57，C 6.14 / 23.66 / 36.45，**D 1.11 / 3.69 / 5.11**；B→D **6.7–7.6×**，A→D 7.6–8.1×，**A→B ≈ 0**。D 显存与 B 相同（17–25 GiB），C 需 35–44 GiB 且长前缀组微批压到 2–3。
- **一致性**：B 与 D 直接对齐后逐位相同（24 个目标、10,984 个候选，最大绝对差 0.0，Top-1/Top-5/完整排序均 24/24）；D 相对 A 的 Top-1 24/24 相同、Top-5 集合 20/24 相同（按组 6/8、6/8、8/8）；BF16 最大绝对差 3.3e-3–1.56e-2，FP32 对照 2.4e-7–2.0e-6（每组 1 个目标）；13/72 个 Top-5 变化全落在近并列（分差 1.4e-5–2.2e-3，大于同分容差 1e-6），归因 bf16 噪声。
- **容差如实记录**：v1（≤1e-3）与主实验前另立的 v2（≤3e-3）**都未通过**，原因是 bf16 噪声随前缀长度放大；决策口径改为 Top-1/Top-K 重合 + FP32 对照，未事后放宽阈值。
- **机制**：读出偏移错一位会改分数（0.043–0.102）；兄弟分支隔离 0.0；前缀 KV 哈希在 8 分支前后不变；单 token 正确。规模曲线：B 每目标 +2.9 秒，D 约 +0.1 秒。
- **建议**：在**同一 tokenized 前缀组内**用 D；当前是串行分支 + KV 复用（`crop` 复位），不是分支 packing；后续评测统一精度与计算方式再比较分数；加速只覆盖已测三组 × 8 目标，不推算整批。
- 服务器运行 `runs/prefix_reuse_v1/20261027_v1/`；测试 21 项通过。

## 诊断修订、条件 G 与 GenMem batch10 预检（2026-10-27）

**状态：COMPLETED_SMALL_SCALE / 待协调侧审查。** 补查与修订见 [补充说明](../experiments/anchor_replay_diagnostic_v1/reports/REVIEW_ADDENDUM_20261027.md) 与 [G 摘要](../experiments/anchor_replay_diagnostic_v1/reports/g_summary_20261027.json)；新批次见 [预检报告](../experiments/genmem_batch10_v1/reports/PREFLIGHT_20261027.md)。

- **修订**：旧报告六处超出证据的表述已更正（整体路径差值不等于单因素贡献；可见性干预只报指标；补 D-last 的 Recall@5 优势；删 position IDs 错误推论；删“packing 无收益／只剩 Anchor 池化”；定义矛盾的实验 F 不执行）。主指标与原始运行未改。
- **机制补查**：S2 直接注入 token IDs（布局/位置/mask 不变）；S1 Anchor 全部 29 个隐藏状态逐位不变，共享 Target Anchor 从第 2 层起变化；P1/P2 attention 逐元素 allclose 全部通过（≤3.87e-6），隐藏表示未通过（≤1.42e-3）；默认 causal 与显式 4D causal 逐位相同，故 E 的差异归到 mask 内容。
- **条件 G**：只放开“目标正文读全部来源正文”。旧读出下首位命中 11/32 vs A 的 12/32（MRR −0.037、Recall@5 −0.026）；固定头读出下 10/32 vs B 的 8/32（MRR +0.054）但 Recall@5 −0.052。结论：这条通路单独打开不足以修复旧结构。
- **新批次预检**：附件 `ea0ca24c…` 一致，10 轨迹／100 目标／73,824 对；prompt 1,183–37,968 tokens，纳入解释上下文后 12 条超 32,768（不含该上下文时 11 条；case_01／02／04），78 条超旧 8,192 限制；41 个不同 tokenized 前缀、15 个可复用组、74/100 目标可共享；已导出标签隔离输入与给 yx 的待标注表（100 行，标注留空）。下一步只建议“共享前缀 + 分支隔离”的 packing 原型，未执行。
- 运行：`runs/anchor_replay_diagnostic_v1/20261027_v1/`、`runs/genmem_batch10_v1/20261027_v1/`（服务器）。测试 18 + 14 项通过。

## Anchor、mask、packing 与固定头回放诊断（2026-10-26）

**状态：COMPLETED_SMALL_SCALE_DIAGNOSTIC / 待协调侧审查。** 入口 [README](../experiments/anchor_replay_diagnostic_v1/README.md)、[回传](../experiments/anchor_replay_diagnostic_v1/reports/REPORT.md)。旧 c8 Dev 短样本 32 条、机制案例 3 个，回答"旧 Anchor 弱在哪、固定头 (19,15) 起什么作用、来源可见性有没有用"。

- 机制：Source 隔离成立（屏蔽位置注意力恰为 0；同长度替换 S2 后 S1 的 Anchor 隐藏表示逐位不变，共享 Target Anchor 则变化最大 62.85）；批内打包与独立前向在 raw 分数上等价（3.1e-7），隐藏表示的 1.4e-3 漂移由批形状数值对照证明是 batching 舍入；条件 A 的 raw 分数与旧 C4 存档逐例逐候选完全一致（32/32，差 0.0）。
- 指标（32 条，旧 c8 多正例）：A 旧 Anchor/last8 0.375 Hit@1、B 同前向固定 (19,15) 0.250、C 回放/last8 0.8125、D 回放/固定头 **0.9063**、E 回放+来源隔离 0.8125；D-last 0.8125、D-mean 0.750。
- 最明显配对变化是 C−A（Hit@1 +0.4375，16 好/2 坏/14 平）：路径差异远大于选头；固定头在旧 Anchor 路径上是负效应（B−A −0.125），只在回放路径上小幅正效应（D−C +0.094，3/0/29）；来源隔离 E−D 为 −0.094。建议的下一步是单条件实验 F（把 Anchor 机制搬到回放路径），本轮未执行。
- 服务器 `memoryflow/runs/anchor_replay_diagnostic_v1/20261026_v2/`（`20261026_v1` 输出逐字节相同、缺分阶段代码身份，已标记取代）。

## GenMem63 Pilot v4 首轮方法比较（2026-10-26）

**状态：COMPLETED_REFERENCE_PILOT / 待协调侧审查。** 入口 [README](../experiments/genmem63_pilot_v1/README.md)、[回传汇总](../experiments/genmem63_pilot_v1/reports/SUMMARY_20261026.md)、[指标表](../experiments/genmem63_pilot_v1/reports/comparison_20261026.md)。在 10 个跨消息目标、3,468 个前序候选上跑完 Random、BM25、Qwen F_mean cosine、R-SYM、D-Full-64、CLM、艺峰回放；每方法 10/10 目标，MLP 两个头各 3 seed。参考集是“已列出的相关来源窗口”（40 组、56 窗口），不是完整 Gold，参考集以外窗口不作负例。艺峰 KnownHit@1 0.80 / MRR 0.90 / 组完成@5 0.325，BM25 0.70 / 0.808 / 0.275，其余四种 0.10–0.30；随机参考 0.0163。逐例对照与输入留在服务器 `memoryflow/runs/genmem63_pilot_v1/20261026_v4_run2/`，不入 Git。

## LC-Sent-15 两条外部基线（2026-10-22）

**状态：COMPLETED_LC_SENT15_DEV / VERIFIED_228_EACH。** [入口](../experiments/lc_sent15_external_v1/README.md)、[结果](../experiments/lc_sent15_external_v1/reports/RESULTS_20261022.md)。艺峰固定头回放 Hit@1 0.872807，CLM 0.271930。各 228 targets / 3,420 scores，完整输入、无训练、无 Reserve/Blind。旧基线不重跑。服务器 `memoryflow/runs/lc_sent15_external_v1/20261022_v1/`，完成结果分别在 `yifeng/` 与 `clm_fulltext/`；`clm/` 是保留的长度检查停止记录。

## 代码整理（2026-10-22）

当前开发入口与冻结复用代码见 [CODE_MAP](CODE_MAP.md)。Git 中旧 `workspace/`、`local_data/` 改为 `legacy/workspace/`、`legacy/local_data/`；服务器目录和历史证据内的路径不变。本次不运行模型、不改实验协议、不产生新方法分数。

## CLM / 艺峰完整模型小样例（2026-10-18）

**状态：COMPLETED_UNLABELLED_SMOKE_NOT_ACCURACY。** [结果说明](../experiments/baseline_adapters_v1/reports/MODEL_SMOKE_20261018.md)。两例 CLM 来源排序、两例固定 (19,15) 艺峰原生生成与引用完成。CLM 使用 Transformers 末 token 后端，未验证与 vLLM 数值等价。20 项测试通过；报告记录模型与产物哈希、输入长度及 GPU 开销。服务器：`memoryflow/runs/baseline_adapters_v1/models_20261018_v1/`。无语义 Gold，不与旧 LC-Sent-15 指标混报。

## CLM / 艺峰基线接入 v1（2026-10-17）

**状态：ADAPTERS_AND_UPSTREAM_COMPONENTS_READY / NO_MODEL_BENCHMARK。** [代码与方法边界](../experiments/baseline_adapters_v1/README.md)、[243 组件报告](../experiments/baseline_adapters_v1/reports/component_report.json)、[真实输入准备报告](../experiments/baseline_adapters_v1/reports/preparation_report.json)。

两份未标注真实轨迹输入；9 项作者组件检查通过。CLM 参考头与作者实现固定版本，艺峰保持自然生成归因协议。没有 LC-Sent-15 新分数、没有语义 Gold、没有 GPU/付费调用。服务器产物在 `memoryflow/runs/baseline_adapters_v1/`。保险任务暂停。

## 真实轨迹展示与目录整理（2026-10-17）

**状态：短链路完成；保险任务预算停止；离线提取完成；没有语义 Gold。** 代码：[trace_review_v1](../experiments/trace_review_v1/README.md)。统一入口：[WORKSPACE_MAP](WORKSPACE_MAP.md)。

243 输出：`memoryflow/reports/flow_review_20261017/`，包含 SP1 完整短例、保险未完成例、245 的单个 CUAD dev 例；每例含 `flow.json` 与可读说明，分享包以根 `README.md` 为入口。输入仍在 `memoryflow/runs/sp1/`；245 原始路径保持只读。外部原文不提交 Git。本轮只做日志提取与可见性核查，不重新评分旧方法、不访问 Reserve/Blind。

## DCC Stage 1：离线校准（2026-10-15）

**状态：OFFLINE / HUMAN_REVIEW_PENDING / NO_MODEL_RUNS。** T1 内部条款引用存在性、T2 条件与替代依据义务各 4 版；每版 4 个对象。8 例仅用于协议校准，不进入正式效果评测。公开题面、Gold 和辅助索引分别见 [data/](../experiments/dcc_diagnostic_v0/data/)；固定配置见 [stage1.json](../experiments/dcc_diagnostic_v0/config/stage1.json)。

代码入口为 [stage1.py](../experiments/dcc_diagnostic_v0/stage1.py) 的 `validate`、`render-preview`、`report`，求值和渲染见 [core.py](../experiments/dcc_diagnostic_v0/core.py)。结果是离线校验 8/8、32 个对象、20 份 `DRY_RUN_NOT_SENT` 预览、18/18 单元测试；没有模型指标。证据见 [validation.json](../experiments/dcc_diagnostic_v0/reports/validation.json)、[逐例评审包](../experiments/dcc_diagnostic_v0/reports/REVIEW_PACKET.md)和 [交付清单](../experiments/dcc_diagnostic_v0/reports/delivery_manifest.json)。无外部大产物；未被后续版本替代。
