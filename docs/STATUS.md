# 当前状态

## 最新推进（2026-10-31 晚）：G2 递归与森林修正、G3 队列、G7 布局

- **G2（本轮完成项）**：`query.py` 现在跨 `estimate` 追溯，防环改为 branch-local；`report_span_0` 可查到 `summary_final`（0.6437）→ 13 个上游片段（含 0.7569），并保留直达原文 0.3563。`compare_views.py` 的最后调用输入从 1 个更正为 2 个：摘要 + 原文。
- **G2 森林**：旧 44 calls 全 central 是角色分类 bug（全篇搜索 `CentralAgent`）；改为首行角色声明后为 20 roots：central 14、coder 3、perception 2、memory_recaller 1。`branches=0` 只是当前前缀/顺序规则下的结果，不能证明真实无分支；delegate→子 Agent 映射仍 unresolved。
- **G3（CPU 原型）**：新增日志驱动 `task_timing_v1/analysis_queue.py`，E0/E1/E2 与排队/积压/答案可用时间记录；v6 44 calls、分析耗时假设 0.25 s/call 时 E0 896.653 s、E1 907.653 s、E2 896.903 s。E2 是回放，不是在线流水线。
- **G7（CPU 局部检查）**：新增 `branch_packing_v1/layout.py`，共享前缀 + 分支 target 的 4-D mask/position/target-row 布局；6 项 CPU 测试通过。**尚未跑真实 7B 的 D/P 前向、分数对齐或性能。**
- **G4**：质量/时间/显存已完成，但开发集 11 目标 ID、显存单位、计时重复次数已补入 [G4 说明](../experiments/source_path_v1/G4_NOTES_20261031.md)：已恢复 11 个 ID；原冻结 8 目标清单未保存，候选反推不作事实；`11868368384 bytes = 11.87 GB / 11.05 GiB`；39.92 s 仅为一次运行记录，不能写成三次稳态中位。
- **G1**：仍等新版 DCCv2；未重构旧分支。
- 详细记录：[G2 后续](../experiments/source_path_v1/G2_FOLLOWUP_20261031.md)、[G3 队列](../experiments/task_timing_v1/reports/G3_QUEUE_20261031.md)、[G7 布局](../experiments/branch_packing_v1/reports/PACKING_LAYOUT_20261031.md)。

## 上一轮（2026-10-31）：G2 初版、G4 小模型对照

- **G2（完成本轮范围）**：`source_path_v1` v2 查询 + 消息级会话森林（v6：20 roots、0 分支，子 Agent 各自成树，delegate→子 Agent 未记录标 unresolved）+ 三视图 `out/method2_views.{svg,png}`（A 森林/B 单次调用+局部矩阵/C CUAD 跨步，实线记录、虚线回放、gap 标注）。方法二对照：只查最后调用只见 1 个单元（条款原文），沿传递可追到摘要产生调用与 13 个上游片段（0.7569 第 1）。
- **G4（质量+同工作负载计时完成）**：Qwen2.5-1.5B（28 层/12 头），开发集 11 目标选头 (16,2)；同 47 目标空前文：@5 **0.5532**、@10 **0.6383**、Frag@1 0.3191，39.92 s、11.87 GiB；7B 同协议 105.43 s、35.24 GiB、0.6170/0.7021/0.4894。取舍：1.5B 快 2.64×、省 2.96× 显存，但质量低 6.4/6.4/17.0 个百分点，不建议直接替换。
- **G1**：服务器上仍无师兄新版本，阻塞；未重复改旧分支、未再跑整题。
- **G3/G7（上一轮状态，后续见上）**：本轮初版未实现；G3 需分析队列与事件回放（E0/E1/E2）；G7 需共享前缀+分支隔离掩码与位置编码，先做 6.1 五项局部检查。
- 产物：`experiments/source_path_v1/G_ROUND_20261031.md`、`out/{forest_v6.json,method2_views.svg,method2_views.png}`；服务器 `/data1/songzhengxing_intern_dccv2/{g4_scan.json,g4_eval47_empty.json}`、`runs/genmem_quality_v2/20261029_v1_trapfix/scores_g4same.jsonl`。
## 最新推进（2026-10-30 第三轮）：来源路径身份修复

- **修复四项**：①摘要保留整段父单元 + 三句带区间的子单元，整段分数只挂父单元；②生成归属与输入可见分开，同文输入出现记入 input_occurrences（修掉自环）；③8 个调用节点全部入图，缺请求的显式标 recorded:false；④工具结果保留预览 + full_ref。v6 逐句匹配生成调用：Operation A 句归 call31，写文件为 call38。
- **查询**：CUAD 报告片段→call7（生成）+ chunk（可见）+ 摘要 0.6437/原文 0.3563；摘要句→父单元与生成调用，句级分数缺口明确；v6 理由句→call31 + 回放矩阵（58 候选/55 目标 tokens）。
- **v6 回放退化**：全部质量落在第一个候选（0.3598），其余 0，暂不能作为有效关联，需检查候选区间与注意力位置的映射后重跑。
- **DCCv2 只读核对**：最后一次请求为 v10 call40（finish=length, 8192）；`sp/prompt/` 只有任务记忆长度约束，未见“每轮简短输出”的显式要求；候选约束待讨论，本轮未运行。
- 产物：`experiments/source_path_v1/SOURCE_PATH_V2_20261030.md`、`out/path_cuad.json`、`out/path_v6.json`。
## 最新推进（2026-10-30 第二轮）：可查来源路径原型 + DCCv2 参数修复

- **来源路径原型（主交付）**：统一 schema + 查询入口已形成。`experiments/source_path_v1/{build.py,query.py}` 读取 CUAD 旧记录与 v6 DCCv2 attempt，输出 `out/path_cuad.json`、`out/path_v6.json`；查询示例：CUAD 报告片段 → 条款原文（0.7569）→ 摘要（0.6437）→ 直达（0.3563），v6 产物 → `write_file` 调用 → 8 段工具返回。记录确认/回放估计/追不到三类分开标注；缺口记录：v6 无 FINISH 记录、规则原文只有工具返回文本（文件级 hash 缺失）、v6 的“哪段证据支撑哪句”未回放。
- **计分对照**：CUAD 上 max 与 sum 排序不变（条款原文 0.4872→0.8435 仍第 1），只有它同时有两条真实路径；暂时没有第二个多路径来源来检验排序翻转，不作优劣结论。
- **DCCv2 参数修复**：重试上限 2048→8192、Central 等待 90→180/60→90、思考开关换为实测有效的 `thinking: {"type": "disabled"}`。v10 一次运行：41 次调用、557 s、0 次 FINISH、`answer=null`；直接原因 = 最后一次 Central 调用 `finish=length`（8192）截断，与 v8 同型；v7 的空响应已不再出现。判断不能评对错。
- 产物：`experiments/source_path_v1/SOURCE_PATH_20261030.md`、`experiments/dcc_nba_v1/reports/DCCv2_参数修复与v10_20261030.md`；服务器 `runs/dccv2/20261030_nba_v10_params/`。SP1 停止，PPT 不动。
## 最新推进（2026-10-30）：官方前提恢复、收尾失败定位

- **更正**：上一轮“原 benchmark 缺金额”的结论撤回。RuleArena 官方 `nba/auto_test.py`（blob `06cbfa74d0…`）在 Assume 段提供 2023-24/2024-25 工资帽、奢侈税、两个 apron 与“球队工资不含到期合同”等前提；漏在**我们的适配**（`nba_plugin.prepare_task` 没拼 Assume 段）。已恢复原文前提（六个金额 + 例外类型说明），规则仍走文件；本地检查通过，v8/v9 首调请求六个金额全部可见（v6 为 0/6）。
- **未 FINISH 的直接原因**：不是产物注册/FINISH 过滤——v6 的产物已注册为 `generated_file` artifact，但 trace 里 **FINISH 动作 0 次**，Central 从未发出。修前提后失败移到模型响应层：v7 请求上限 **2048** + `chat_template_kwargs.thinking` 无效（reasoning=2048，正文空 → `SPCentralEmptyResponse`）；v8 用实测有效的 `thinking: {"type":"disabled"}` + 8192，Central 长分析在 8192 处 `finish=length` 截断；v9 把 perception 预算抬到 12 次工具后子任务能交付 partial，但下一次 Central 调用 `stalled 90+60 s`（`SPCentralModelTimeout`）。三次均未 FINISH、无最终交付、无判断。
- **已记录的有界修改**：`sp-coder.max_turns 100→130`（工具 15→20）、`sp-perception 40→80`（工具 6→12）、`sp-outline 30→60`；`DCC_MODEL_EXTRA_BODY` 改为 `thinking: {"type":"disabled"}`；`--max-tokens 8192` 在 v8 起进入请求（v7 仍 2048）。yaml diff 62 行，`nba_plugin.py` SHA256 `0244926a…`。
- **待师兄决定**：①Central 单次超时 90→180 s / 重试 60→90 s；②是否允许改 Central 收尾提示（8192 内先结论后理由）；③是否换非思考模型或加“最终答案”短输出兜底。任务单要求暂不连续重试。
- 产物：`experiments/dcc_nba_v1/reports/DCCv2_前提修复与收尾诊断_20261030.md`；服务器 `runs/dccv2/20261030_nba_v{7,8,9}_*/`。SP1 停止，PPT 不动。
## 最新推进（2026-10-29 第六轮）：DCCv2 聚焦诊断、有界修复、一次运行

- **已修好**：①空响应（v5/v6 共 85 次调用，`length`+空正文 0 次）；②grep 文件路径（v5 子任务直接 grep 规则文件成功）；③记录完整（v5/v6 的 state/result/trace 全在）；④子任务工具上限：定位到 `LoopDetectionMiddleware` 的 run-total 硬上限公式 `hard = max(2, min(20, (max_turns-6)//6))`，v5 为 15（coder 15 次调用全部有进展却被强制停），本轮把 `sp-coder.max_turns` 100→130，上限升到 20（常量封顶）。
- **已证实的输入缺口**：`reference_rules.txt`（461 行/98,208 字符）**没有任何 2024-25 工资帽/税线/中产金额**，只有交易例外金额（$250,000 / $5M / $6.5M / $7.5M）；官方答案所需的金额条件不在可见材料里，模型的“文件里没有金额”观察正确。
- **仍待查**：v6 修复后一次运行（`comp_0#004`，896.9 s、13 轮、44 次调用）**未 FINISH**；coder 已写出 `recovery-verdict.json`（violation=false，官方 True/B/B，判断错），Central 收到“3 个缺口”后继续委派、最终没有选中交付。疑点集中在 Central 的收尾/FINISH 条件对“负证据（文件里没有某事实）”的处理，属工作流语义，本轮未改。
- **记录整理**：S 正式样本 2 次（另 1 次 73.379 s 编译预热剔除），S 与 S+O 完整 SHA256 相同（`4175d731edd9…c5d3dd0a`）；CUAD 排名改为“研究者矩阵原文第 1；报告者矩阵摘要第 1、原文第 2”。
- 产物：`experiments/dcc_nba_v1/reports/DCCv2_适配诊断与修复_20261029.md`、`experiments/dcc_nba_v1/local_patches.diff`（58 行）；服务器 `runs/dccv2/20261029_nba_v6_toolbudget/`。SP1 不再重试；旧 CUAD 不替代本次正式案例。
## 最新推进（2026-10-29 第五轮）：S/S+O/S+R 配对、CUAD 展示稿、SP1 尝试

- **效率配对（完成）**：同一作者插件服务（Qwen3.8-27B FP8、TP=1、同一卡、同一 SDK 客户端、冻结材料 3,162 prompt tokens、128 输出），S（无捕获）与 S+O（捕获+来源计算）各 3 次交替，**输出完全相同**（`4175d731…`）。稳态：S **3.687 s**（3.676–3.697），S+O **4.097 s**（生成 4.062 + 后处理 0.033，4.094–4.132）→ 捕获增量 **+0.41 s（+11.1%）**；捕获证据齐（`Q=(128,256)`、`K=(3289,256)`、TP=1、tp_rank=0、layer 51）。S+R：3.687 + **R 1.014 s**（prefill 0.775 + 块 0.238，加载 9.18 s 另列）= **4.701 s**。两路线模型不同，标为实际部署路线对照。
- **CUAD 展示稿（完成）**：`CUAD_CHAIN_SHOWCASE_20261029.md` 给出原任务与判断、三个文本框（合同原文/研究者摘要/报告片段，带调用编号）、记录 vs 回放的图、来源表（**0.7569 / 0.6437 / 0.4872**，直达 0.3563）、以及展示口径（乘积是原型路径计分，不是依赖概率；单摘要单结论，不能证明多跳优于直达）。
- **SP1 NBA（尝试一次，未完成）**：规则整体注入可行（查询 99,296 字符、prompt 24,074 tokens 在上下文内）；但 8,192 输出 token 全被推理占用（`LengthFinishReasonError`，reasoning_tokens=8192），随后 3 次 APITimeout，5 次调用后 `BUDGET_STOP`，无 final_report。最小修复=在 SP1 模型调用处关闭 thinking（与 DCCv2 同型修复），本轮按任务单未改该系统配置。
- 产物：`experiments/flow_efficiency_v1/reports/YF_SOR_20261029.md`、`experiments/dcc_flow_v1/reports/CUAD_CHAIN_SHOWCASE_20261029.md`、`experiments/dcc_nba_v1/reports/SP1_NBA_ATTEMPT_20261029.md`；服务器 `runs/sp1/nba_6tlu479r/`、`/data1/songzhengxing_intern_dccv2/yf_server/p0/`。本机无 git。
## 最新推进（2026-10-29 第四轮）：短条件对照修正、CUAD 案例补算

- **P0 短条件对照（部分完成，关键口径已修正）**：捕获请求必须走顶层 `vllm_xargs`（SDK 的 `extra_body` 在 HTTP 层才变成它）；上一版“G2 有捕获 1.84 s”的两条请求**没有产生任何 Q/K 文件**，实为无捕获，已在报告中更正。作者客户端捕获路径验证通过（`Q=(128,256)`、`K=(2196,256)`、layer 51、tp_rank 3，引用分数正常）：一次完整捕获 **生成 2.286 s + 后处理 0.017 s = 2.303 s**。冻结材料（source 6000 字符、2102 prompt tokens、128 输出）下：G0 **8.89 s**、G1 **8.95 s**（输出与 G0 相同）、G2 无捕获 **2.05 s**；R 回放 **0.915 s**（prefill 0.764 + 块 0.150，加载 7.16 s 另列）。**G0/G2 的 4.5 倍差异未定位**：两组输出不同（`87f3e1e3…` vs `4fa1a955…`），测量时 GPU 被其他用户占满、TP=4 服务随后初始化失败；两条配置分别报，不作 hook 归因。捕获增量未能拿到严格同条件值（+0.2~0.3 s 量级，prompt 路径不同）。环境更正：torch 实际 **2.10.0+cu128**。
- **P1 备用主例（CUAD 两跳）**：用修复后 `predict.py` 重算：答案片段 0.7595→**0.7569**（仍第 1），回报质量 0.6437 不变，间接 0.4889→**0.4872**，顺序与结论不变；展示数字改用新值。NBA #004 仍无完整 FINISH 案例（A 的 v5 被重复调用/工具硬上限中止），SP1 备用路线本轮未启动（其 agent 无文件工具，97 KB 规则需另注入，已列为缺口）。
- **P2 质量收尾**：质量补算表为当前有效表（固定头 @5 61.70% / @10 70.21% / Frag@1 48.94%），BM25 首项更高、随机头扫描、CLM 零训练迁移的说明保留；B/D 2.89× 与作者工具测量分别对应“计算复用”与“生成时捕获/事后回放”，不混表。
- 产物：`experiments/flow_efficiency_v1/reports/YF_P0_SHORT_20261029.md`、`experiments/dcc_flow_v1/reports/CUAD_CHAIN_RECOMPUTE_20261029.md`；服务器 `runs/dcc_flow_v1/20261029_v3_trapfix/`、`/data1/songzhengxing_intern_dccv2/yf_server/p0/`。本机无 git。
## 最新推进（2026-10-29 第三轮）：质量补算、yf 实测、子任务上限追补

- **B 质量补算（完成）**：用修复后的 `predict.py` 重算 88 个可运行目标的注意力条件，新运行 `runs/genmem_quality_v2/20261029_v1_trapfix/`。评测集 N=47：固定头 **@5 0.6170（+1 目标）/ @10 0.7021（不变）/ FragHit@1 0.4894（不变）**；平均头 0.5745/0.6170/0.3404；随机头 `L21H5` @10 0.7660→0.7447、`L25H1` 0.2128→0.1915、`L20H12` @5 0.0638→0.0851；BM25/CLM/cosine/R-SYM/D-Full 不变。55 目标上 Top-1 变化 0、Top-5 变化 10、CompleteGroup@5 变化 1。**原结论不变，旧表可被新表替换。**
- **C yf 交付包（短样例与四设置实测完成）**：包 SHA `c11ab00f…` 校验通过；FP8 Qwen3.8-27B + TP=4 + PIECEWISE 启动成功，Q/K 捕获与引用输出正常。同一 2102-token 输入、128 输出、预热后中位：**G0 8.79 s / G1 8.95 s（+1.8%，输出相同）/ G2 无捕获 1.92 s / G2 有捕获 1.84 s（输出相同，捕获≈0）**；G2 后处理 0.017 s；客户端完整链路 2.30 s。G2 比 G0 快 4.8× 但**输出不同**（`4fa1a955…` vs `87f3e1e3…`），是插件实现路径差异，不能归因于 hook。MemoryFlow 回放 R：prefill 1.29 s + 块 0.16 s = **1.44 s**（加载 6.7 s 另列），`G0+R` ≈ 10.2 s。同骨干对照仍未做（需 Qwen3.8 回放适配）。
- **A 子任务上限（追补，仍未 FINISH）**：定位到 coder 反复把文件路径传给 `grep` 触发循环检测；修复 skill 文案 + 让 `grep` 工具接受文件路径（diff 45 行）。v4（仅 skill）16 次调用仍未 FINISH；v5（skill+grep）29 次调用后触发“重复调用检测 / 工具调用硬上限”被强制停止，仍未 FINISH、无完整案例。剩余方向：检查 read_file/grep 截断并只调整该子任务的工具调用预算，待规划侧决定。
- 产物：`experiments/genmem_quality_v2/reports/TRAP_FIX_RECOMPUTE_20261029.md`、`experiments/flow_efficiency_v1/reports/YF_EFFICIENCY_20261029.md`、`experiments/dcc_nba_v1/reports/DCCv2_诊断与修复_20261029.md`（含追补）；服务器新目录 `runs/genmem_quality_v2/20261029_v1_trapfix/`、`/data1/songzhengxing_intern_dccv2/yf_server/`。本机无 git。
## 最新推进（2026-10-29 第二轮）：DCCv2 执行端诊断、回放端修正、yf 交付包可行性

- **执行端（A）**：定位到 `#003/#004` 未 FINISH 的直接原因——**Central 输出的隐藏推理把 4096 token 预算耗尽**，返回 `finish_reason=length`、空正文、无 tool call；SP2 判为 `SPCentralEmptyResponse(requires_more_tokens)`，重试受 CLI `max_tokens` 限制无法扩大，最终以“未验证草稿”收尾。**不是超时**（25–27 s « 90 s）、**不是工具参数截断**（截断调用无 tool call）。最小修复：`--max-tokens 8192` + 关闭 thinking（本地补丁 `DCC_MODEL_EXTRA_BODY`，diff 26 行）。修复后单次真实运行（#004）：**11 次调用 0 次 length**，空响应消失；但子 agent 两次 `loop_capped` 让 Central 停在第 3 轮，仍未 FINISH——新的堵点是子 agent 循环上限，按任务单只交诊断，不扩改。
- **回放端（B）**：① 计分边界修复——`EnergyTrap` 的含端点前缀和相减实际求和 `[left+1, right+1)`，合成测试最大误差 0.736，零补前缀后与直接切片差 3e-7；3 目标实测 Top-1/Top-5、CompleteGroup@5、FragHit@1 均不变（分数最大绝对差 0.0054）。② `source_chain_v2.py` 改为按“产生该文本的调用”归属（响应正文/工具参数），按 attempt 过滤调用与产物，唯一编号；重跑 #004 得到 6 个单元、4 条边**全部 replay_only**——验证报告在最终判断之后产生、没有进入最终判断，真实传递是反方向（验证读取产物）。`check_3` 等 2 个单元仍为缺口（已在响应/工具参数/请求三处检索）。③ 共享前缀小组（8 目标）用修复后计分复核 B/D：max abs diff 0.0、Top-1/Top-5 8/8。
- **C 可行性（yf 交付包）**：包 SHA `c11ab00f…`、35 个文件校验通过；243 上作者环境（vLLM 0.18.0 / torch 2.10.0 / Python 3.12.13）与**交付包插件逐字节一致**，`/data/Qwen3.8-27B`（52 GB）与 FP8（29 GB）都在，8×A800 可 TP=4；**根分区 0 字节空闲**，必须把编译缓存/TMPDIR 移到 `/data1`。本轮未启动服务，给出迁移步骤、测量口径与同骨干缺口。
- 产物：`experiments/dcc_nba_v1/reports/{DCCv2_诊断与修复_20261029.md, NBA_CHAIN_20261029_v2.md}`、`experiments/genmem_quality_v2/reports/TRAP_FIX_20261029.md`、`experiments/flow_efficiency_v1/reports/C_YF_DELIVERY_FEASIBILITY_20261029.md`；服务器 `runs/dccv2/20261029_nba_v3_fix/`、`runs/dccv2/20261029_nba_v1/source_chain_v2/`、`runs/flow_efficiency_v1/20261029_trap_fix/`。本机无 git。
## 最新推进（2026-10-29）：DCCv2 接 NBA 两例、来源链、整批前缀复用

- **DCCv2 可用性**：按 `0914afc3…` 拉取 `StackPlanner2.0` DCCv2，Python 3.12 独立环境（`venv312`）装好，`--check-config` 通过、原生工具齐全、NBA 插件注册成功、逐次调用记录（`calls.jsonl`：消息+工具定义+返回+finish reason+usage）落盘。**但原生 SP2 Central 在两例上都没走到 FINISH**：`comp_0#003` 两次 Central 超时→恢复→未验证草稿（`protocol_error`，333 s），`comp_0#004` 走到 verification 后 `SPCentralEmptyResponse`（`infrastructure_error`，576.7 s）；`#003` 用 `deepseek-v4-pro` 重试一次仍未 FINISH（476.7 s）。故障定位在服务端模型对 SP2 Central 长请求的超时/空响应，不在插件或文件注入。
- **两例判断**：`#003` 产物 `violation=false`（官方 True/A/A，判断错）；`#004` 产物 `true/A/Team B`（官方 True/B/B，判断✓、球队✓、操作✗）。两例合计 98 次模型调用、1,660,994 tokens。只做展示，不作总体准确率。
- **来源链（#004）**：最终判断的回放来源集中在 5% 涨薪（`rule_93` 0.118）、Over-38（`rule_68` 0.063）、10 年以上顶薪（`rule_16` 0.058）；验证段落在第二土豪线/中产/空间条款；验证报告自己确认**规则文件没有 2024-25 的工资帽/税线金额**，而结论依赖一个文件给不出的不等式——错误可定位到“缺金额”，不是“缺条款”。`check_3` 在调用记录中找不到同文本，标为缺口。
- **整批前缀复用**：88 目标、36 前缀组、可复用 64.26% 前缀 token；**B 中位 406.1 s vs D 中位 140.7 s（2.89×）**，三遍逐候选分数完全相同（Top-1/Top-5 88/88，最大差 0.0），峰值 32.82 GiB 两者相同；每目标 B 中位 3.26 s / D 中位 0.94 s（额外一遍，GPU 共享）。之前三组的 6.7–7.6× 原样保留，整批单列。
- **C2（yf PIECEWISE）**：243 无 vLLM、无作者 hook 实现，本轮不做运行；已给出 PPT 数字转述、复现条件表与需向师兄索取的最小材料清单。
- 代码/产物：`experiments/dcc_nba_v1/`、`experiments/flow_efficiency_v1/`；服务器 `runs/dccv2/20261029_nba_v1|v2/`、`runs/flow_efficiency_v1/20261029_batch_reuse{,_pertarget2}/`。本机无 git，未提交未推送。
## 最新推进（2026-10-28 收尾）：多轨迹基线、SP1 简查、CLM 方案

- **GenMem 多轨迹基线（八方法，原窗口候选 + contextual64_v4 证据）**：补齐随机（2,000 次同种子模拟）、Qwen F_mean cosine、R-SYM（3 seed）、D-Full-64（3 seed）、CLM（官方头迁移），与既有固定头/平均头/8 随机头/BM25 同表。评测集 N=47：**固定头 @5 0.5957 / @10 0.7021 / FragHit@1 0.4894**；D-Full 0.5319 / 0.6809；BM25 0.5532 / 0.6170；平均头 0.5745 / 0.6170；R-SYM 0.4468 / 0.5816；F_mean 0.2766 / 0.4043；CLM 0.1277 / 0.1915；随机 0.0108 / 0.0215。**轨迹宏平均**（按 case 等权）固定头 **0.5376 / 0.6753**、BM25 0.5302 / 0.5823，与目标平均不同；先前“宏平均等于目标平均”的写法已在报告中更正。全部方法在 55 个目标上完成（36,584 对），无长度缺口；8 个 v4 目标超限、T01 单列。CLM 低分对应“官方头直接迁移（零额外训练）”，R-SYM/D-Full 是 LC-Sent-15 跨任务迁移，均不当作上限。详见 [MULTI_METHOD](../experiments/genmem_baselines_v2/reports/MULTI_METHOD_20261028.md)。
- **SP1.0 简查**：根 /data2/pkuiti/songzhengxing_intern/SP1.0（DeerFlow 系，git HEAD c81444fe…），采集入口 memoryflow/scripts/sp1_20261016/sp1_bounded_run_v3.py（SHA 88f6d212…）；依赖由 uv 管理，.venv 为空且本账号 PATH 无 uv → **当前入口无法直接重启**。配置只有 BASIC_MODEL（实际 deepseek-v4-flash-0731），各角色同一模型。日志已保存 messages、输出、finish_reason、检索返回、graph 状态与 researcher traces；**缺工具定义、缺 token IDs、运行摘要未落盘**。跑 NBA 需新增题目注入与提示/工作流适配。预算停止在历史保险运行里最终生效但已打满检索预算；本轮无法做不联网的传播测试（环境缺 uv），已给出测试方案。详见 [SP1_REVIEW](../experiments/sp1_runtime_v1/reports/SP1_REVIEW_20261028.md)。
- **CLM 适配方案（不训练）**：保留“官方头直接迁移”结果，另设“来源任务适配 CLM”；冻结 Qwen3-8B、只训投影头并从官方头初始化，损失适配为 listwise/BCE、组内等价来源不互为负例；47 个评测目标不进训练，8 个开发目标太少，正式结论需新的独立留出；给出同预算比较协议与资源估计。详见 [CLM_ADAPT_PLAN](../experiments/baseline_adapters_v1/reports/CLM_ADAPT_PLAN_20261028.md)。
- 代码/产物：experiments/genmem_baselines_v2/、
uns/genmem_baselines_v2/20261028_v1/。本机无 git，未提交未推送；原文只在服务器。

## 最新推进（2026-10-28 晚）：GenMem 正式质量评价 + NBA 首例

- **GenMem 正式评价（原窗口候选 + contextual64_v4 证据）**：按用户决定采用 `contextual64_v4/ground_truth.json` 的 `self_contained_evidence` 作为规范答案，预测复用 `scores_full.jsonl`，未重跑 GPU。分母：v4 64 个目标 → 与 88 个可运行目标交集 56 → 排除 case_10 T01（`needs_review`、`insufficient_for_full_target_claim`）→ **55 个**（评测集 47 + 开发集 8），覆盖 83 个完整 OR 组、160 个证据片段；8 个 v4 目标因长度超限未跑。主指标（评测集 N=47，无前文）：**固定头 @5 0.5957 / @10 0.7021 / FragHit@1 0.4894**；最后 8 层平均 0.5745 / 0.6170 / 0.3404；**BM25 0.5532 / 0.6170 / 0.5745**；8 个随机头 @5 分布 0.0638–0.5532（均值 0.2473）。含前文变体对所有方法都不更好（固定头 0.5745 / 0.6596 / 0.3404）。开发集 N=8 单列（固定头 0.375 / 0.500 / 0.125），不据此调头。结论：固定头在完整组找齐上优于词面检索（@10 +8.5pt），但 FragHit@1 更低；前文在当前协议下不是收益来源；固定头总体优于平均头与多数随机头，但**不是跨轨迹全面占优**（case_04 落后）。详见 [QUALITY_CONTEXTUAL64](../experiments/genmem_quality_v2/reports/QUALITY_CONTEXTUAL64_20261028.md)。
- **NBA 首例（三阶段受控执行）**：`comp_0#003`，三次真实调用（输入 21,700 / 22,052 / 961 tokens，贪心，`max_new_tokens=700`，生成 sdpa、回放 eager 固定头）。模型给出 **False（合规）**，官方答案是 **True（操作 A 违规）**——答案错了也保留。中间链的错误起点是 `check_2`：把“2020 年签了 4 年”当成“服役 4 年”，据此套用 <7 年档 `rule_12`（25%），最终判断以 0.8047 的质量沿用该判断；中间核查**从未覆盖薪资帽/空间/例外**这一路，最终判断里“符合 Team Salary cap / Apron”没有对应原文。Flow：`rule_12` 间接 0.3474、`fact_7` 直达 0.0869、`fact_5` 间接 0.0819；直接回溯与多跳的前四名一致，多跳如实记录了错误链、没有纠正规则。规则原文是模型输入，规则名清单/映射表与官方答案只在评价侧。详见 [NBA_CASE](../experiments/nba_case_v1/reports/NBA_CASE_20261028.md)。
- **CUAD 报告修正**：研究者矩阵里答案片段的分数从 0.5045 更正为机器结果的 **0.7595**（0.4889 = 0.7595 × 0.6437），没有重跑 CUAD。
- 代码：`experiments/{genmem_quality_v2,nba_case_v1}/`；服务器 `runs/genmem_quality_v2/20261028_v1/metrics_contextual64/`、`runs/nba_case_v1/20261028_v1/`、`runs/nba_case_v1/20261028_v1_flow/`。本机无 git，未提交未推送；原文只在服务器。

## 最新推进（2026-10-28）：四候选接入检查、来源质量 v2 预测、DCC Flow case

- **任务零（DCC 候选接入）**：RuleArena NBA 两个 level-1 样例的完整 0-shot 输入实测 **21,952 / 22,095 tokens**（模板+全文规则+实例，在 32,768 内），`relevant_rules` 是规则**名**、不是规则原文的字符区间（5 个名字在 `reference_rules.txt` 里逐字出现 0 个）。CLAUSE 抽查两例：`ANIXABIO…` 三条扰动的两端在修改后合同中**逐字命中**（可用）；`ADAMSGOLF…` 与 `ABILITYINC…` 的 `contradicted_text` 连折叠空白后也找不到（不可用，保留原标签不修）。FinRule-Bench 公开入口返回 **401**，未读到任何字段；FinAuditing 的 `en-finmr` 为 **gated**。表见 [ACCESS_20261028](../experiments/dcc_candidates_v1/reports/ACCESS_20261028.md)。
- **任务一（来源质量 v2）**：新包 `f99e1494…` 的候选载荷与上一版**逐字节相同**（tasks/review_targets/dataset 三者一致），只新增参考草稿与 `evolution`。已冻结“含目标前文”变体（读行 `P+C-1 … P+C+n-2`，前文不并入目标行）并跑完 **88 个可容纳目标 × 2 变体**：176 行、12 个条件（固定头、最后 8 层平均、8 个随机头、两版 BM25）、36 个前缀组、164 次前向、**170.6 秒**、峰值 **32.8 GiB**。行对齐全过（块长度、首末行、缓存回退、错位负对照、重复运行差 0.0、与冻结短跑一致）；76 个有前文目标的两个变体分数全部不同。参考草稿 100 条全 `pending`/`gold=false`（55 条完整、44 条部分、1 条未解决，95 个 OR 组覆盖 55 个目标），**本轮不发布质量成绩**，状态“预测完成，待标签评价”。详见 [PREDICT_20261028](../experiments/genmem_quality_v2/reports/PREDICT_20261028.md)。
- **任务二（DCC Flow）**：CUAD dev trace `00923364ccde0fd5`，13 片段 / 8 调用 / 1 摘要 / 1 结论。call 4 输入里 13 个片段全部可见；call 7 输入里可见“摘要 + 1 个片段”。局部矩阵：摘要→片段最高是答案片段 0.5045；结论对 reporter 输入的质量 **0.7103 落在摘要**、0.2897 落在答案片段。直接溯源与多跳都把答案片段排第 1，但次席不同（直接是 `3670:4931` 0.1266，多跳把它压到第 8 0.0244）。逐跳原文核对成立；决策调用 1/6/8 的输出未留存，无法构造语义矩阵。详见 [FLOW_CASE_20261028](../experiments/dcc_flow_v1/reports/FLOW_CASE_20261028.md)。
- **补充（同日，按规划侧复核）**：①评测标签入口从 `ground_truth_v1` 改到 **v2**（v1 55 完整/44 部分/1 未解决；**v2 64 完整/36 部分**；88 条可容纳子集里 v2 是 56 完整/32 部分、84 组覆盖 56 个目标）。仅换评测标签，未触碰冻结输入与预测、未重跑 GPU；覆盖率 88/100，12 条标“本协议不可评分”（11 条不含前文也超限），Known evidence 分母 88、CompleteGroup 分母 56。②CUAD Flow 改为**完整调用上下文回放**（call 4 请求 5,041 tokens、call 7 请求 1,203 tokens），并枚举“间接/直达”两条路径取最大值：答案片段间接 **0.4889** > 直达 **0.3563**，路径最大值仍为间接；摘要对结论的质量 0.6437（旧通用模板版是 0.7103），旧数值归档在 `runs/dcc_flow_v1/20261028_v1/`。③**NBA `comp_0#003` 规则映射表**：五条规则各定位到一个原文区间（如 5% 递增 [32842,33428)、4 赛季 [85769,86988)、薪资帽 [10874,11029)、10 年以上顶薪 [4627,4917)、Over-38 [21817,22187)），并记录 Years of Service 定义、出生日期、是否用例外三处歧义。
- 代码：`experiments/{genmem_quality_v2,dcc_flow_v1,dcc_candidates_v1}/`；服务器运行 `runs/genmem_quality_v2/20261028_v1/`、`runs/dcc_flow_v1/20261028_v1/`、`runs/dcc_flow_v1/20261028_v2/`。CPU 测试：quality v2 12 项通过。本机无 git，未提交也未推送；原文数据只在工作目录与服务器。
## 最新推进（2026-10-27 晚）：前缀复用验证完成

- 三个前缀组（4,770 / 11,712 / 16,173 tokens，每组 8 个目标）比较 A（逐 token 回放）/ B（目标块并行）/ C（普通 batch）/ D（共享前缀 + 串行分支）。代码 `experiments/prefix_reuse_v1/`，结果 `runs/prefix_reuse_v1/20261027_v1/`。
- **时间（整组 8 目标，3 次中位数）**：A 8.98 / 28.01 / 38.69 秒，B 8.24 / 24.83 / 38.57，C 6.14 / 23.66 / 36.45，**D 1.11 / 3.69 / 5.11**。B→D **6.7–7.6×**，A→D 7.6–8.1×，**A→B 只有 −8.2%/−11.3%/−0.3%**（目标只有 8–57 token，前缀才是瓶颈）。D 峰值显存与 B 相同（17–25 GiB）；C 因为每个目标保留一份前缀副本，峰值 35–44 GiB，且长前缀组必须把微批压到 2–3。
- **一致性**：D 与 B 按目标 ID/候选 ID 直接对齐后**逐位相同**（24 个目标、10,984 个候选，最大绝对差 0.0）；D 相对 A 的 **Top-1 在 24/24 个目标上相同、Top-5 集合在 20/24 个目标上相同**（按组 6/8、6/8、8/8）；BF16 下最大绝对差 3.3e-3–1.56e-2（C 最大），**FP32 全条件对照 2.4e-7–2.0e-6（每组仅 1 个目标）**。13/72 个“目标×条件”改变 Top-5 集合，全部发生在第 5/6 名分差（1.4e-5–2.2e-3）小于该次差值的近并列处；这些分差都大于冻结的同分容差 1e-6，所以是 bf16 噪声导致的名次变化，不是同分规则问题。
- **容差如实记录**：`plan.json` 在任何 GPU 运行前冻结 v1（≤1e-3），机制小样 1.8e-3 已超；据此在主实验前另立 v2（≤3e-3）。**主实验 v1/v2 都未通过**（最大 1.56e-2），原因是 bf16 噪声随前缀长度放大、机制小样低估。决策口径因此改为 Top-1/Top-5/Top-10 重合率 + FP32 对照，没有事后放宽阈值。
- **机制检查**：读出偏移错一位会改变分数（0.043–0.102）；换兄弟分支后本目标分数变化 0.0；前缀 KV 在 8 个分支前后哈希不变；单 token 目标走 1 行正确。规模曲线（中等组）：B 每加一个目标约 +2.9 秒，D 约 +0.1 秒，8 目标时 23.69 对 3.54 秒。
- **实现要点**：只读第 19 层注意力时必须用 forward hook 截取该层；`output_attentions=True` 会保留 28 层，在 11k–16k 前缀下要 22–31 GiB，既慢又易 OOM。选卡要避开被他人占满的设备（本轮物理卡 3），否则计时无效。
- 结论与限制：建议在**同一 tokenized 前缀组内**采用 D；它现在是串行分支 + KV 复用（`crop` 复位、不复制），不是分支 packing；bf16 下分数差异 3e-3–1.6e-2，来自 dtype 与 kernel 分块，后续评测应统一精度与计算方式再比较分数。加速结论只覆盖已测的三个共享前缀组（每组 8 个目标），不推算整批。详见 [REPORT](../experiments/prefix_reuse_v1/reports/REPORT.md)。本机无 git，未提交也未推送。

## 最新推进（2026-10-27）：诊断修订、条件 G 与新批次预检

- **解释修订**：按交接要求新增 [REVIEW_ADDENDUM_20261027](../experiments/anchor_replay_diagnostic_v1/reports/REVIEW_ADDENDUM_20261027.md)，并在旧报告顶部加指针。更正六处超出证据的表述：整体路径差值不拆成单因素贡献；来源可见性干预只报指标下降、不解释语义机制；补上 D-last 的 Recall@5 优势（0.9167 > 0.9089）；删除“position IDs 重置会破坏读出偏移”的错误推论；删除“packing 已在用所以无收益／只剩 Anchor 池化”的说法；定义矛盾的实验 F 不再执行。历史指标与原始运行未改动。
- **五项机制补查（原 3 案例）**：S2 改为直接注入 token IDs（不再是 decode→re-tokenize），长度／Anchor 位置／position IDs／chunk 归属／mask 全部不变；S1 Anchor 在**全部 29 个隐藏状态**上逐位不变（max abs 0.0），共享 Target Anchor 从第 2 层起变化（最大 77.3）。逐元素 allclose：P1/P2 attention **全部通过**（≤3.87e-6，无元素越界），隐藏表示**未通过**（≤1.42e-3）——分数吻合、隐藏表示等价未通过。默认 causal 与显式 4D causal **逐位相同**，因此 E 的差异可归到 mask 内容；E 每次删 15,630–34,690 条跨来源边，目标行仍完整 causal。
- **条件 G（旧路径只放开“目标正文读全部来源正文”）**：CPU 先断言新 mask 只在「目标正文行 × 来源正文列」上多出边、删除边为 0、AT 行与来源行不变；旧 A 复现与存档逐候选差 0.0。结果：**G 在旧读出下不改善**（首位命中 11/32 vs A 的 12/32；MRR −0.037、Recall@5 −0.026，3 好／4 坏／25 平）；换固定头读出时 Hit@1／MRR 小幅回升（10/32 vs B 的 8/32，MRR +0.0544）但 Recall@5 降 0.052。本子集不支持“这条通路就是旧结构缺的那一环”。耗时 17.7 s、峰值 31.1 GiB。
- **新批次（GenMem batch10 v1）CPU 预检**：附件 SHA `ea0ca24c…9904` 一致；10 轨迹／100 目标／73,824 对；真实 tokenizer 实测 prompt 1,183–37,968 tokens（均值 17,092），纳入解释上下文后 **12 条超 32,768**（不含该上下文时 11 条，本轮前缀复用实验用的就是不含口径）（case_01／02／04），78 条超旧 runner 的 8,192；按实际 tokenized 前缀判定 **41 个不同前缀、15 个可复用组、74/100 目标可共享前缀**；已导出标签隔离的模型输入、标签／导航分文件、给 yx 的待标注表（100 行，标注留空）。适配器 14 项测试通过。详见 [预检报告](../experiments/genmem_batch10_v1/reports/PREFLIGHT_20261027.md)。
- 代码：`experiments/anchor_replay_diagnostic_v1/{g_intervention.py,test_g_mask.py}`、`experiments/genmem_batch10_v1/{prepare.py,preflight.py,test_batch10.py}`；服务器运行 `runs/anchor_replay_diagnostic_v1/20261027_v1/`、`runs/genmem_batch10_v1/20261027_v1/`。本机无 git，未提交也未推送；原文数据留在服务器。

## 最新推进（2026-10-26）：Anchor / mask / packing 与固定头回放诊断完成

- 用旧 c8 Dev 里 32 条 1–128 token 的短样本、3 个机制案例、一次冻结的 Anchor（C5F config C epoch 04），在 FP32 eager、无训练、无选头、未访问 Blind 的条件下跑完五个条件。代码进 `experiments/anchor_replay_diagnostic_v1/`，结果在服务器 `memoryflow/runs/anchor_replay_diagnostic_v1/20261026_v2/`。
- 机制层结论：**Source 隔离成立**（被屏蔽位置的注意力恰为 0；把 S2 换成同长度序列后，S1 的 Anchor 隐藏表示逐位不变，而共享 Target Anchor 变化最大 62.85，说明共享点在 Target Anchor 而不是 Source 之间）。**打包本身不是问题**：正确保留 pair 关系的批内打包与独立前向在 raw attention 上等价（3.1e-7），隐藏表示的 1.4e-3 漂移被"同 batch 两份相同副本差 0、但对单条前向同样漂移 1.4e-3"这一对照解释为 batching 舍入。条件 A 的 raw 分数与旧 C4 存档逐例逐候选完全一致（32/32，差 0.0），说明比较基准就是旧实现。
- 指标（32 条、旧 c8 多正例协议）：旧 Anchor/last8 **A 0.375**，同前向换固定 (19,15) 的 **B 0.250**，普通 causal 回放/last8 **C 0.8125**，回放/固定头 **D 0.9063**，回放+来源隔离 **E 0.8125**；辅助读出 D-last 0.8125、D-mean 0.750（Hit@1）。
- 证据排序：**整体路径 ≫ 选头**（C−A +0.4375，16 好/2 坏；B−A 反而是 −0.125；D−C 仅 +0.094 且 3 好/0 坏/29 平）。**来源之间互相可见有用**：把它们隔开（E）掉 0.094。D-mean 掉 0.156 说明来源 token 上应求和而非取平均。32 条不足以支撑任何显著性声明，也不与旧完整 Dev、LC-Sent-15、GenMem 的数字横比。
- 下一步只建议一个补充实验（未执行）：把 Anchor 机制搬到回放路径上（同模板、同预测位置、同 (19,15)，只加 Anchor 槽与 AT 读出），用来把"模板/位置"与"Anchor 本身"分开。轻量回传见 [REPORT](../experiments/anchor_replay_diagnostic_v1/reports/REPORT.md)。

## 最新推进（2026-10-26）：GenMem63 Pilot v4 首轮方法比较完成

- 在 10 个跨消息目标、3,468 个前序候选上跑完 7 个已有方法：Random、BM25、Qwen F_mean cosine、R-SYM、D-Full-64、CLM、艺峰固定 `(19,15)` 回放。每方法 10/10 目标；R-SYM 与 D-Full 各 3 个冻结 seed 先算指标再平均。无训练、无付费 API、未访问 LC Reserve/Blind。
- 参考集是“当前已列出的相关来源窗口”（43 个解释组里的 40 组、56 个窗口），不是完整 Gold；参考集以外的窗口不作负例，也不报 accuracy。KnownHit@1：艺峰 0.80、BM25 0.70、R-SYM/D-Full 0.30、cosine 0.20、CLM 0.10，随机参考 0.0163；组完整度最高只有艺峰 32.5%@5。
- 主要失败是有结构的：需要两个条件同时成立的组（B04 全部）没有任何方法在前 10 内凑齐；被修订的旧系数/旧结论反而排得很前（F11 中艺峰把被推翻的“欠定”陈述排第 3），Known 指标不扣这种分。44 个高分未标注窗口列入待复核清单，本轮不改参考集。
- 艺峰 prefill 改为 2,048 token 分窗（上游单发在 32 GiB 预算下对 9,967 token 上下文 OOM）；已在 A07 上与单发版本做等价检查，Known 指标一致、分数相关 0.99976。`metrics.py --verify` 与本机跨机复算均通过（最大差 1.4e-14）。
- 代码与轻量汇总见 [实验目录](../experiments/genmem63_pilot_v1/README.md)，回传汇总见 [SUMMARY](../experiments/genmem63_pilot_v1/reports/SUMMARY_20261026.md)；含轨迹原文的逐例对照留在服务器 `memoryflow/runs/genmem63_pilot_v1/20261026_v4_run2/`。本次未 push，交回协调侧审查后再决定补标或扩展。

## 最新推进（2026-10-22）：LC-Sent-15 补测完成

- 同一 Dev 228 条、每条 15 个候选：艺峰方法 Hit@1 **87.28%（199/228）**，CLM **27.19%（62/228）**。旧 BM25、MLP、Fusion 指标直接复用，未重跑。完整对照见 [RESULTS](RESULTS.md)。
- 艺峰固定 `(19,15)` 回放目标句，CLM 使用作者已有头、不额外训练；两者均不截断、不删样本、不读 Reserve/Blind。艺峰比固定 Fusion 高约 4.09 个百分点是点估计，未做本轮显著性检验。
- 两条运行均完成，保存分数独立复算通过；GPU 推理在 243 完成，无付费调用。代码、设置、分语言指标见 [补测目录](../experiments/lc_sent15_external_v1/README.md)及 [结果说明](../experiments/lc_sent15_external_v1/reports/RESULTS_20261022.md)。后续真实 SP1 数据建设仍由 yx 推进，不把这次代理任务分数当成真实 Agent 信息流效果。

## 最新推进（2026-10-22）：按代码用途收拢仓库

- 当前主线是 SP1 真实轨迹、细粒度标注和已有方法比较，不是继续 Anchor 调参或来源事实核查。SP2 暂不接入；保险和 DCC 扩展均不在本轮执行范围。
- 原 `workspace/`、`local_data/` 整体移至 `legacy/`，128 个跟踪文件内容保持不变。R-SYM、D-Full、BM25 等仍可复用，旧审计和训练保留追溯。当前三个开发入口及缺口见 [代码地图](CODE_MAP.md)。服务器目录、历史报告和科学指标未修改。
- CLM 加载作者已有投影头与 Qwen3-8B，本项目没有额外训练。艺峰固定头在自身生成文本上归因，与 CLM / MLP 的既有目标排序仍未统一协议。
- Python 轨迹已有 Gemini 初标（37 个目标单元、17 个相关来源片段），尚需修订粒度、可见性与执行状态判断；不是正式 Gold 或完整候选库。任务已交由 yx 继续数据处理，本次整理以代码盘点为中心。
- 旧状态和研究快照保留在下方；其“没有轨迹”“缺权重”等描述不再作为当前结论。
- 本次验证：77 项轻量测试通过（轨迹 7、适配 12、权重校验 4、DCC 离线 18、旧数据准备 28、BM25 5、池化工具 3）；129 个 Python 文件语法检查通过，16 份当前入口文档的本地链接无断链。128 个移动文件与原 Git blob 一致。使用本机已有 Python/pytest；torch 测试和 GPU 推理未重跑，也未安装大依赖。

## 最新推进（2026-10-18）：两条方法完整模型小样例已跑通

- Qwen3-8B 的 14 个文件完成校验。CLM 官方头与 Engine 配合 Transformers 末 token 编码，输出两例的 10/13 个来源分数；未另装 vLLM，数值等价性尚未验证。
- 用户固定艺峰论文头 (19,15)，不再等待选头确认或重新 probe。两例原生生成与引用完成，矩阵分别为 2×233、3×142，输出 45/58 tokens，均正常结束。
- 20 项测试通过，9 个回传输出文件哈希一致。GPU 7 顺序运行后退出，未修改其他用户任务，无付费调用。
- 首轮结果不支持宣称效果可靠：CLM 首位来源需要语义核查，艺峰 CUAD 输出 no_answer，与原 SP1 的 found 不同，并给非事实过渡语添加了引用。
- 详见 [本轮结果](../experiments/baseline_adapters_v1/reports/MODEL_SMOKE_20261018.md)。下一步先固定原子目标和小规模人工来源核查，不调这两例的头、阈值或提示词。下方关于权重和选头未到位的条目均为历史状态。

## 最新推进（2026-10-17）：两条对比方法接入

- 后续授权：用户允许将 Qwen3-8B 下载至 243，GPU 编号随后提供；艺峰固定 head_ranking.json 由用户向师兄索取。本轮只准备权重，不启动 GPU 推理、不重新选头。下载固定 revision `b968826d9c46dd6066d109eabc6255188de91218`，预计 16,397,459,696 字节；是否完成以服务器模型目录内的 `acquisition_report.json` 为准，不能仅凭下载进程判断。

- 用户决定暂停保险任务，不再排查或重跑；当前推进 CLM 与艺峰方法复现和适配。
- Git remote 已改为用户指定仓库的 HTTPS 地址，沿用本机已有认证；历史未推送内容及本轮基线接入提交 `a5abb1f` 已同步 main 并核对远端一致。未关闭 SSH 安全校验、未改动私钥。
- 两条方法已建立独立于历史实验的 [适配目录](../experiments/baseline_adapters_v1/README.md)。CLM 固定作者 commit 和官方参考头；艺峰复用补充材料原代码。两份真实轨迹输入已转换，来源数为 10/13，无语义 Gold。
- 243 的 9 项作者组件检查通过：CLM 发布头 + 模拟向量、艺峰注意力聚合/引用 CLI/小型随机模型解码。**这是组件运行，不是完整论文复现或真实模型效果。** 原始轨迹与权重不入 Git。
- 下一步依赖：CLM 的 Qwen3-8B 权重与可用 GPU；艺峰 Qwen2.5-7B 对应的固定 head ranking，或安排 BGE-M3 + 独立选头数据重新 probe。当次 243 磁盘约剩 47 GB、GPU 均有占用，未下载 GB 级资源、未启动 GPU 任务或付费 API。

以下保留历次状态；与上面冲突的旧“下一步”不再执行。

**整理日期：2026-10-14。** `completed` 表示有仓库内报告或指标；`pending` 表示仍需执行；`blocked` 表示有明确外部依赖；`unverified` 表示未找到最终产物。旧文件中的“正在运行”只作为历史记录。

| 事项 | 状态 | 依据或最后已知状态 |
|---|---|---|
| Anchor + Attention 与 packed 原型、旧 c8 校准 | completed | [C5F 报告](../evidence/server/C5F_DEV_FINALIZATION_243.md)。仅为代理任务。 |
| 冻结 Qwen 表示、M6B/M6D R-SYM 机制核查 | completed | [M6D.3 报告](../evidence/server/m6d3_best_checkpoint_paired_selection_v1/M6D3_REPORT.md)；Ranking/Edge checkpoint 分开。 |
| LC-Sent-15 数据构建、Train/Dev 基线和 Q1C/Q2/Q3 | completed | [本机构建报告](../legacy/local_data/lc_sent15_v1/baseline_core_v1/BUILD_REPORT.md)及 [指标表](RESULTS.md)；Reserve 仍封存。 |
| Synthetic Summary Track A/B | completed | [运行摘要](../evidence/server/memoryflow_summary_transfer_v1/run_summary.json)；完成的是 smoke test，Track B 无 Gold。 |
| 旧 SP pilot 日志可恢复性 | completed | [本机审计](../legacy/local_data/sp_natural_v1_raw/sp_semantic_edge_recoverability_audit.md)：无可直接恢复的语义 Gold 边。 |
| SP1 完整真实轨迹与 Source-to-Summary 评测 | unverified | 在本轮指定资料与 243 实验结果中未找到最终轨迹/指标；[2026-08-31 汇报底稿](../evidence/local/MemoryFlow_假期结束工作汇报准备底稿.md)最后称单 Query schema gate 尚未完成。 |
| 艺峰方法的 200 样本 Head probing | blocked | [243 readiness](../evidence/server/yifeng_qwen25_head_probe_v1/readiness_report.md) 标记 `NEEDS_INPUTS`，未见 `head_ranking.json` 或最终 200 样本报告。 |
| 艺峰方法与 LC-Sent-15 的同协议比较 | blocked | [243 对比报告](../evidence/server/yifeng_method_lcsent15_comparison_v1/comparison_report.md) 标记协议歧义，未运行 Dev。 |
| Q4A 内部层表示恢复 | unverified | 交接文件曾记录恢复进行中；本轮未将其视为完成，也未为此展开排查。 |
| GitHub 仓库同步 | completed | 用户提供 `samzx114514/MemoryFlow`；本地 `main` 已首次推送到 `origin/main`。后续变更按 README 约定提交和推送。 |
| 仓库及第三方材料公开权限 | unverified | 已有远端，但本轮未核实仓库可见性或取得第三方材料的公开授权；继续按私有研究资料处理。 |

## DCC Stage 1（2026-10-15）

| 事项 | 状态 | 依据 |
|---|---|---|
| DCC 诊断校准的 Schema、8 案例、确定性 Gold 核验、A/B/C 输入预览与离线测试 | completed — OFFLINE / NO_MODEL_RUNS | [阶段报告](../experiments/dcc_diagnostic_v0/reports/STAGE1_REPORT.md)；8 案例、32 对象、20 份未发送预览、18 项测试通过。|
| DCC 独立科学审查及后续模型选择、费用授权 | pending — HUMAN_REVIEW_PENDING | [逐例评审包](../experiments/dcc_diagnostic_v0/reports/REVIEW_PACKET.md)；程序通过不代表人工批准。阶段二及完整 Pilot 尚未授权。|

## 真实轨迹与目录收拢（2026-10-17，补充以上历史状态）

- SP1 专用环境 `langgraph-prebuilt` 已由 0.5.1 对齐项目 lock 的 0.1.8；离线初始化和真实短链路通过。第二次短任务正常结束，9 次模型请求、1 次检索、1 个 Summary、1 份最终报告；字数约束未严格遵守，不代表报告质量已通过。
- 用户提供的保险公司复杂 Query 已运行，但约 287 秒后预算停止：15 次实际模型请求、40 次搜索请求、38 份成功搜索返回；没有完成的 Researcher Summary 或最终报告。累计输入预算异常被旧异步调用链误处理，随后再次委派，最终触及搜索预算；不得称为记忆丢失的科学证据。
- 离线提取了完整短任务（10 个去重网页片段）、保险部分轨迹（379 个片段）、245 的单个 CUAD dev 案例（13 个合同 chunk）。语义支持 Gold 和准确率仍未建立；Reporter 同时可见 Summary 与原文，须考虑直接 Source→Reporter 路径。
- 243 新增的六个散落目录已迁入现有 `memoryflow/`，158 个文件 SHA256 核对一致。位置、方法代码和结果入口见 [目录地图](WORKSPACE_MAP.md)。
- 提取代码及测试见 [trace_review_v1](../experiments/trace_review_v1/README.md)；组内原文样例只存服务器 `memoryflow/reports/flow_review_20261017/` 和本机已忽略的 `artifacts/raw/flow_review_20261017/review/`，不入 Git。
- 下一步先请师兄确认标注粒度与双路径可见性的处理；复杂保险任务先修复预算终止/异常传播并合理拆分研究任务，不直接增加预算重跑。本轮未新增模型调用或修改 SP2。
