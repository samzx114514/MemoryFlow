# 当前状态

## 2026-11-12 补充：实验2改接GenMem96目标，效率批继续

- 用户确认实验2改用旧47题＋新49题，并要求以原轨迹构造。已接入96个不同目标、37条轨迹；旧8条从NAS按原偏移读取并逐事件核对一致，新批读取真实raw_runs，人工中间句未进入新版轨迹。
- 目标和原证据区间已核对。旧标签中4个目标已找到更早材料，4个完整原文支持仍不足；用户确认质量分母92，另外4个保留说明。72个有候选中间调用，不作为已通过的多轮题数。原日志重建完整回放已完成7B/1.5B各350调用，27B接续；统一候选平均243.4个，所有方法共享。见[GenMem接入](../experiments/genmem_merged_v1/README.md)。
- 实验1正式质量表完成，7B采集开关额外耗时三次中位数0.04395秒（同请求59输出token），1.5B的补测安排在效率任务后。
- 实验3继续两组独立设备对。7B第二次完整组原任务未交付，回放又遇到call44生成的非完整JSON工具参数；失败保留，不重新生成该次样本。已修复原样保留非法参数和失败记账，接续7B第三次和1.5B三次；27B串行/完整各三次均完成；1.5B接续中。各组失败均进入完成率。

## 2026-11-12：共同30输入完成，首版单轮质量表已产出

- NBA／CLAUSE／FinAuditing各10个真实调用，来自17个原始任务。三模型90次生成与180张完整输出矩阵全部完成并验证；13个兼容调用直接复用，仅新增计算17个。
- 90份输出的盲审标签已逐条核对并冻结，实际157个陈述，14次无事实输出。标签为AI辅助、代码规划侧语义审阅版，尚无独立人工复核；原文、标签和逐目标结果保留在外部产物目录。
- 同模型单轮两种方法效果接近：27B NBA／CLAUSE F1均为90.09%／74.02%；FinAuditing为MF65.67%、YF64.76%。7B NBA为MF95.28%、YF95.59%，其余同模型表项相同。各模型评价自己的输出，按原始任务平均。
- CLAUSE完整任务预检已完成12调用、12张矩阵、3个最终片段查询。效率后续一次预热报告被4096-token默认上限截断；失败记录保留。新版显式统一8192输出上限，已通过执行端预热（35调用、3目标、392.35秒），A800两组独立设备对4/6与0/2正在接续三次测量。
- [完整18行质量表、分母与测量进度](../experiments/dcc_complete_v1/reports/QUALITY_20261112.md)。师姐提供的DCC归档缺少子Agent完整请求，用户已改用上文GenMem数据。

## 2026-11-11 补充：原生窗口修复与共同输入补齐

- 27B 分析版 30 对调用已完成。7B 在 34K–45K NBA 输入上输出重复感叹号，关闭采集仍复现；9,162-token 开发输入正常。本地两种 Qwen2.5 配置为 32,768、无 RoPE 扩展。已停止该版后续小模型批次并保留现场。
- 用户确认补齐原生长度内的共同 30 输入。已有兼容 13 调用（CLAUSE 6、FinAuditing 7）的三模型生成与完整回放全部完成，共 78 张矩阵，产物清单检查通过。
- 原生窗口预算在生成和在线回放前检查，含输出预留；27B 嵌套 text_config 与 Qwen2.5 平面配置均已验证。服务入口删除强制绕过模型最大长度的环境设置。
- 新共同批次为 `experiment1_native32_30`，先复用上述 13 个，只运行新增 17 个。新的 6 道 NBA 源任务题号已固定并开始采集；分析阶段审阅与标注同步推进。正式质量表仍待完成。
- [修复与当前运行记录](../experiments/dcc_complete_v1/reports/NATIVE_CONTEXT_20261111.md)。

## 最新推进（2026-11-11）DCC 三模型采集与完整优化

- 新入口位于 `experiments/dcc_complete_v1/`，复用 `b6fe3ff` 的森林与查询，DCCv2 为 `1fa314da`。同调用共用完整矩阵、独立变长序列合批和生成／回放重叠均有运行记录。
- 第一批三模型各 30 次生成及回放已完成，保存 180 张矩阵。多数输入处于工具调度阶段，保留为工程预跑，不作为正式质量结果。
- 用户已批准的新分析调用批固定为 NBA／CLAUSE／FinAuditing 各 10 个；27B 已开始采集，随后自动接续 7B、1.5B。待输出完成后审阅标注，再计算 P/R/F1 和覆盖率。
- 正式完整任务效率表尚未产出；实验 2 的 12 条完整轨迹待用户提供。
- [实现与首批证据](../experiments/dcc_complete_v1/reports/ENGINEERING_20261111.md) · [运行入口](../experiments/dcc_complete_v1/README.md)。

## 最新推进（2026-11-09）完整调用回放第一版

- 真实 CLAUSE 9 次调用、NBA 24 次调用共生成 33 张完整矩阵、17,992 个输出行。所有矩阵通过预测行偏移和因果可见性检查。
- CLAUSE T1 与 T2 共用 call07 矩阵，分别读取 [33,41) 和 [42,63) 行。两条查询都按实际命中区间读到了 call05 的对应行。
- NBA 的同一句查询分出工资帽与球队工资原文，工资分支经过 call23、call11、call07、call02 四张矩阵。另有受控三跳分叉测试。
- [实现、命令与逐跳验收](../experiments/provenance_v2/reports/FULL_REPLAY_20261109.md)。

## 最新推进（2026-11-07）：informative30 51 目标整批

- 36 优先 + 15 跨事件全部逐条处理：30 题合格并实测（真实中间消息 12、受控构造 18），最终轮自足对照 3，证据/时序不足 17，诊断 1；覆盖 20 条轨迹。
- 时间顺序检查覆盖正证据和干扰项；case_03:T04 的 ev10 不进 ev8 输入；case_01:T10 的 C0036 作为 ev29 中间消息，上游改用 ev28 的 C0034。
- 30 题：MF Hit@3 30/30、完整@5/@10 25/30、28/30；head 30/30、20/30、28/30；BM25 29/30、15/30、25/30；last 0。配对 MF-last 28/2/0、MF-BM25 21/5/4、MF-head 14/10/6。
- 真实 12 题：MF 8/12、11/12；head 7/12、12/12；BM25 4/12、9/12。
- case_06:T10 的真实 ev8 不承接 A 内容，单列诊断；旧 batch10 17 题不并入。

## 最新推进（2026-11-07）：informative30 真实中间消息首批 2 题

- 36 优先清单已定位；核对 case_01:T10、case_03:T04、case_06:T10 三条真实 agent 消息。
- case_01:T10（父亲身份 → ev29 真实消息 → ev30/31 返回 → ev32 结论）与 case_03:T04（alias → ev8 → ev10/12 → ev14）合格；case_06:T10 的 ev8 未承接 A 的具体内容，只留诊断。
- 真实回放主表 2 题 / 2 轨迹：MF 完整@5/@10 2/2、2/2；head 2/2、2/2（名次 8/7 慢）；BM25 0/2、2/2；last 0。配对 MF-last 2/0/0、MF-BM25 1/1/0、MF-head 2/0/0。
- 人工构造首批 3 题继续单列（MF 2/3、head 3/3）；旧 batch10 17 题直接复用，case_03 s08 诊断。
- 36 清单已核 3 条，剩 33 条；下一批按不同轨迹继续。

## 最新推进（2026-11-07）：informative30_v1 接入，首批 3 题

- 新包 49 case / 300 target / 285 草案；按 (case,id) 连接 tasks/candidates/GT，只取目标事件前材料，原始答案/评分/summary 未进回放。
- 36 个优先目标清单未随包提供；本轮先取 3 个跨轨迹、证据在目标前、GT 组可覆盖的目标。
- 首批 case_03:T02、case_05:T07、case_06:T02，全部为受控中间句（未找到可核实的真实传递消息）；precheck 3/3 PASS。
- 结果：MF 完整@5/@10 2/3、2/3；head 3/3、3/3；BM25 2/3、3/3；last 0。配对 MF-last 2/1/0、MF-BM25 1/0/2、MF-head 0/1/2。
- 旧 batch10 从核过 17 题起算；case_03 selected_08 只留 diagnostic（选举期间口径未确认），不重纳入。旧 100：17 主表、1 diagnostic、3 pending、2 对照、3 排除、43 单事件、6 partial、25 partial 排除。

## 最新推进（2026-11-07）：case_03 criteria 实测，累计 18 题 / 8 轨迹

- case_03 selected_08 拆成“上议院反对党领袖 / 2019 代理任职 / 议员资历”三窗，预检 PASS；MF 失败（A5/B1），head 完整第 6，BM25/last 失败 → 作为方法跑丢题留在分母。
- case_08 selected_09 待核：a0128 只支持 <0.02% 检测比例，缺 SNP 芯片与 known variants 原句；a0001 只支持检测健康风险变异。
- 4 个同事件目标：case_07 selected_01 非答案目标；case_07 selected_08、case_10 selected_04 单段已足够列对照候选；case_10 selected_05 的 12 months 待核。
- 累计 18 题 / 8 轨迹：MF 16/18、16/18；head 16/18、18/18；BM25 13/18、16/18；last 0。配对 MF-last 16/2/0、MF-BM25 7/8/3、MF-head 2/11/5。
- 100 去向：18 主表、3 待核、2 对照、3 排除、43 单事件、6 partial 待补标、25 partial 排除。

## 最新推进（2026-11-07）：三题证据修正，累计 17 题 / 8 轨迹

- case_05 selected_01 补入真正 b 问句 `a0191[96,205)` 与 a/b 定义，4 窗组重冻结重跑：MF/head 完整第 4、BM25 第 5、last 缺 A。
- case_08 selected_02 与 case_09 selected_08 原文没有“生化活性=生物功能”或“灰阶纹理/复用扫描/无额外辐射”的明确断言，改为 pending-evidence，撤出主表。
- 累计 17 题 / 8 轨迹：MF Hit@3 17/17、完整@5/@10 16/17、16/17；head 17/17、16/17、17/17；BM25 17/17、13/17、16/17；last 16/17、0、0。配对 MF-last 16/1/0、MF-BM25 7/7/3、MF-head 2/11/4。
- 100 去向：17 主表、2 pending、2 对照、3 排除、43 单事件、8 partial 待补标、25 partial 排除；共 100。

## 最新推进（2026-11-07）：partial 补标新增 3 题，累计 19 题 / 10 轨迹

- 从 11 个 candidate-partial 中补标并跑通 case_05 selected_01、case_09 selected_08、case_08 selected_02；三题跑前检查 3/3 PASS，MF/head/BM25 全部完整（完整名次 3/3/7、3/3/9、3/3/3）。
- 累计 19 题 / 10 条轨迹：MF Hit@3 19/19、完整@5/@10 17/19、18/19；head 19/19、18/19、19/19；BM25 18/19、14/19、18/19；last 18/19、0、0。配对 MF-last 18/1/0、MF-BM25 8/8/3、MF-head 2/12/5。
- `case_02 selected_05` 留分母（列表项 m1 排 11–14）；case_10 selected_01 日期待核、case_10 selected_07 语义排除、case_05 selected_03 超预算。
- 100 去向：19 主表、2 对照、3 排除、43 单事件、8 个 partial 待补标、25 个 partial 排除；共 100。
- 剩余 8 个 partial 候选和 4 个同事件多证据目标待做。

## 最新推进（2026-11-07）：映射修正后的新增批，累计 16 题 / 7 轨迹

- `batch10_v3` 改为读取 contextual64_v4 逐轨迹 `ground_truth.json`，主证据按原文 ID/起止/文本精确匹配；停用选最长子段和 `fix_group_windows.py`。
- 跑前检查用正式覆盖函数验证：并集能覆盖一套完整组、≤10 窗、最终轮单独不完整。旧错段 11/12 被 BLOCK，修正后 11 题 PASS。
- 11 道新题（含旧 T03/T09）全部完整：MF/head 完整@5 均 11/11，BM25 9/11；新增批全部 Hit@3 11/11（last 10/11）。
- `case_10 selected_07` 排除：B 句“3 months”只修饰瘦素/胰岛素，不是结论的腰围/体重/BMI；A 句也未写三个月。
- 累计 16 题 / 7 轨迹：MF 完整@5/@10 15/16、15/16；head 15/16、16/16；BM25 12/16、15/16；last 0。配对 MF-last 15/1/0、MF-BM25 6/7/3、MF-head 2/10/4。
- `case_02 selected_05` 留分母（列表项 m1 排 11–14，放宽 hop 也进不了前 10）；`case_10 selected_01` 日期待核排除；`case_05` 超预算；`case_06` 与 T06 为对照。
- 100 去向：16 主表、2 对照、2 排除、1 语义排除、43 单事件、11 partial 候选、25 partial 排除；共 100。

## 最新推进（2026-11-07 凌晨）：batch10 并集池第一批 + 100 目标筛选

- 修正首批：case_03/05/07 补齐组内缺项；case_06 核查为最终轮自足（对照）；case_10 撤销“标题相同”合并，`a0194`/`a0203` 分开保留。
- 新口径：BM25、同一 7B 固定头平铺、MemoryFlow 共用两轮原始候选并集（同源去重），final top-10 / hop 5；last_round 单列；旧全历史大池另列。
- 主表 5 题（case_06 对照、case_05 超预算、case_10 日期待核另列）：MF Hit@3 5/5、完整@5/@10 4/5；head 5/5、4/5、5/5；BM25 5/5、3/5、4/5；last 5/5、0、0。配对完整 W/T/L：MF-last 4/1/0、MF-BM25 1/2/2、MF-head 1/2/2。
- case_10 selected_01 的 `Jul 23, 2022` 只是裸元数据，未明确标注为论文发表日期 → 撤出主表，状态 date-unverified；`a0194`/`a0203` 不按同标题合并。
- case_02 用已保存矩阵复算 hop=5/10/100：缺的列表项 m1 分 0.018/0.006/0.0007/0.0002，合并名次 11–14，放宽每跳也进不了前 10 → 上游排序失败，不是预算。
- 100 目标筛选：5 built-v2、1 control、1 excluded-budget、1 excluded-date-unverified、3 built-prev、10 candidate-full、43 单事件、11 candidate-partial、25 partial 排除；64 已标注全核对，36 partial 仅列补标候选。
- 旧 47、旧全历史池、pilot B04/F11 均不并入；Reserve/Blind 未触碰。

## 最新推进（2026-11-06 深夜）：batch10 跨轨迹首批 8 题

- `contextual64_v4` 64 个目标中 20 个至少一组证据跨事件，覆盖 8 条轨迹；首批每条轨迹一题（case_01/02/03/04/05/06/07/10），共 8 目标。
- 四方法（final top-10，hop 5）：MemoryFlow Hit@3 8/8、完整@5/@10 4/8；last Hit@3 8/8、完整 0/8；BM25 Hit@3 6/8、完整@10 2/8；head Hit@3 1/8、完整 0/8。
- 逐跳诊断：hop1 中间结论 8/8 进前 5（第 1–2），hop2 A 8/8（第 1–2），hop1 B 8/8（第 1–3），合并 A/B 8/8 在前 5。未完整 4 题：case_02 是 hop2 只展开前 5（其余列表项未进），case_03/05/07 是构造未含组内其余证据；case_10 同源合并后第 5 名完整。
- 首批无“最终轮自身足够”的题；T06 仍单列。旧 47 题、pilot B04/F11 表不变；Reserve/Blind 未触碰。
- 产物：`experiments/multiturn_batch_v1/batch10/reports/BATCH10_FIRST_20261106.md`、`BATCH10_20261106.{md,json}`；矩阵 GPU0/24 GiB。

## 最新推进（2026-11-06 夜）：pilot-v4 B04/F11 旧材料受控验证

- 数据：243 `genmem63_pilot_v4/deepresearch63_pilot_v4.zip`（同一冰川轨迹，不是独立任务）；B04 目标为 `S20=S0+20k`，F11 为“不是欠定”的修订结论。两轮受控，A/B 与旧替代组保留：B04 g01/g02/g03，F11 g01/g02（g03/g04 旧前态登记但不计分）。
- 四方法（final top-10，hop 5）：B04 MemoryFlow A1/B5（g02@5），head 用 g01@5（A3/B—），BM25 g01@6，last B4/A 不可见；F11 只有 MemoryFlow 完整（A1/B3，旧欠定结论第 2），BM25/head 拿 A 漏 B，last 拿 B 漏 A。
- 宏平均 n=2：Hit@3 last/BM25 0.500、head/MF 1.000；完整@5 last 0、BM25 0、head 0.500、MF 1.000；完整@10 last 0、BM25 0.500、head 0.500、MF 1.000；配对完整 W/T/L：MF-last 2/0/0、MF-BM25 2/0/0、MF-head 1/1/0。
- 边界：同轨迹两题、受控构造、单次前向；不作科学结论，旧 47 题与三题 batch10 表不变。
- 复算：`experiments/multiturn_batch_v1/import_pilot.py`、`score_cases.py`（243 GPU0，24 GiB）、`preflight/lock/run_batch`；报告 `pilot/reports/B04_F11_20261106.md`。

## 最新推进（2026-11-06 晚）：多轮批处理准备，三题开发验收

- 新增 `experiments/multiturn_batch_v1`：统一 case schema（轨迹 ID、目标文本与位置、各轮输入/输出、中间传递位置、原始候选、支持证据组），`real_request` 与 `controlled` 分开统计；T06 单列为“最终轮自身已有足够证据”的对照。
- 四方法：最后一轮、全历史 BM25、同头全历史直接回放、MemoryFlow 多轮追踪；最终返回 top-10，每跳展开 top-5 另记。证据按 `(artifact,start,end)` 归并，`occurrences` 保留各轮位置；覆盖规则复用原评测。
- 三题验收（主表 n=2，T06 不计入）：Hit@3 四方法均 1.0；完整@5 last 0/2、BM25 2/2、head 1/2、MF 2/2；完整@10 last 0/2、其余 2/2；配对完整名次 W/T/L：MF-last 2/0/0、MF-BM25 0/2/0、MF-head 1/1/0。
- T09：head B 第 8，MF A 第 1/B 第 2；BM25 A2/B1。T06 对照的 GT 仍是 ordinal 组（8 项），Complete 只作诊断。
- 预检 3/3 `ok`；`lock.json` 在评分前冻结候选/标签/矩阵哈希；测试 9/9。
- 新数据：`real_request` 导入路径未被数据检验；N 轮 7B 回放器（r1…rN + flat）是下一步；旧 47 题协议单列不动。

## 最新推进（2026-11-06 晚）：GenMem 两轮溯源最终原文排名（离线复算）

- 口径：每跳 top-5 与最终 top-5 分开；路径分 = 直达 hop-1，经中间结论 = hop-1(结论) × hop-2；同一原文相加去重，排除结论后取全局前 5。只读已保存分数，无 GPU。
- 三组最终 top-5：G1 均看不到 A；G2 T03 齐（A2/B1）、T09 缺 B（A1/B8）、T06 齐（A3/B1）；G3 T03 A2/B1、T09 A1/B2、T06 A8/B1。
- T09 主例复核：平铺 B 第 8，多轮全局 A 第 1、B 第 2（与抽查一致）。T06 标为“最终轮自身已有足够证据”的对照：最终句只要专辑 + 年，最终轮题名与 B 直接支持，全局 A 第 8 不算链失败。
- 同义检查：T03 第二轮无第五张断言；T09 无显式 fifth，但 `a0236` 是可计数排序清单（去掉 Caravans 时 Zero Zero 第 5），标为影子证据。
- 不同主题样例：`case_08` 两个目标各只一段主证据，`case_02` 其余目标同主题；无合格样例，本轮不新增。
- 产物：`experiments/provenance_rounds_v1/final_rank.py`、`reports/FINAL_RANK_20261106.md`、`reports/final_ranks_20261106.json`；测试 7/7 通过。

## 最新推进（2026-11-06）：GenMem 受控两轮溯源，3 条样例跑通

- 新增 `experiments/provenance_rounds_v1`：243 v3 包 `contextual64_v4`，只用开发案例 `case_02`/`case_08`；两轮输入冻结，Qwen2.5-7B-Instruct greedy 生成中间结论与最终句，固定头 L19H15 回放，`provenance_v2` 逐跳连接。报告：[ROUNDS_20261106](../experiments/provenance_rounds_v1/reports/ROUNDS_20261106.md)。
- 三条：T03（Secret Symphony + Mike Batt）、T09（Zero Zero 1982 + Epic；case_02 额外目标）、T06 v2（Zero Zero + 1982）。
- top-5 三组：G1 最后一轮都看不到 A；G2 T03 找齐、T09 缺 B（8/17）、T06 找齐；G3 链三条都找齐（结论名次 1/1/3，A 名次 1/1/1，B 名次 2/2/1）。
- 边界：受控多轮验证，不是原始逐次请求恢复；原 47 题单列。T06 v1 构造歧义（标题行算作第六个）已弃用，v1 文件保留。
- 验收：归档 SHA `f465eb1c…`；运行目录 `runs/provenance_rounds_v1/20261106_v1`（T06 v2 在 `_v2`）；GPU0（运行前 1/3/5/7 为 100% 利用，0 号卡 ≥20 GiB 空闲）。

## 最新推进（2026-11-05 晚）：黄金案例 YF/MF 实测排序；DCCv2+27B 未接通

- `simple_zh_ix478` 最终 Writer `20261103T160133-056937cc`：prompt 11848、generated 1664、attention **1664×13511**（首行有效 11848，末行 13511）；上一轮 1664×11848 已修正。
- 已算 T1–T5 的 YF 生成时 L19H15 排序与 MemoryFlow 回放排序；全候选分数、top 表、矩阵在 `outputs/MemoryFlow_执行回传_20261105_03/`。
- 标签初步：T2/T3 由 S6 正文逐字支持；T1/T4 部分支持/日期待核；T5 有 S3 正文候选但数字日期待核；正式指标未填。
- DCCv2+7B：7 native iteration、51.1 s、0 工具、unfinished；DCCv2+27B 仍报 `System message must be at the beginning`，无最终交付。
- 27B 已停止，GPU2 释放；7B 在 GPU1/8100（PID 421790）；GPU0 未占用。

## 最新推进（2026-11-05）：DCCv2/SP2 接入试跑，SP1 回退案例索引

- **DCCv2 + 7B**：`rulearena-nba-comp0-003` 7 次 native iteration、51.1 s、0 次工具调用后 `unfinished`，未接受 FINISH。
- **DCCv2 + 27B**：同任务卡在 `System message must be at the beginning`，无最终交付。
- **SP2 + 7B/27B**：仍无 report ledger/最终报告；27B 的 tool parser/context/system message/max_tokens 多处失败。
- **SP1 回退案例**：`simple_zh_ix478` 完成，9 调用、1 LangSearch、2650 字符、gate true；最终 Writer 调用 `20261103T160133-056937cc`，L19H15，prompt 11848，attention 1664×11848。仅作开发案例，不是首选框架结果。
- **勘误**：`simple_p8gv695r` 与 `simple_zh_ix478` 是同一黄金 query（hash `52bf4c49…`），旧汇总“中产”标签错误。
- **指标**：YF 局部读出、MemoryFlow 回放、Gold 均未完成；hit@3 / 完整@10 为空。正式批次暂不启动。
- 回传：[执行回传 20261105_02](../outputs/MemoryFlow_执行回传_20261105_02/README.md)。

## 最新推进（2026-11-03 第八轮）：SP2 A 阻塞，1.5B 补表与 HTML 完成

- **A（SP2 真实报告对比）阻塞**：本地/242 代码均为 `109f685`，请求提交 `f843873` 不可得，origin SSH 关闭；只有示例配置，无实际 `config.yaml`/`.env`；无可捕获内部状态的本地 7B/vLLM 服务（242:8080 非模型服务）。未选择 query、未生成、未评分；`03_SP2同报告对比.csv` 只有表头。
- **B（N=47 补 1.5B）完成**：标准 predictor `scores_g4small` 补算 Hit@3 **28/47=59.57%**；完整@10 30/47=63.83%；Hit@1 12/47 与旧 Frag@1 一致。六方法主表已出（7B/1.5B/平均/BM25/D-Full/CLM）。
- **C（HTML）完成**：CLAUSE v3 支持最终句→路径、原文片段→已分析范围内的反向后续；selftest 五项全过；静态预览、截图与 90 秒讲解稿已交付。
- **范围**：短例计时支线仍收尾；未重跑 N=47 其他方法，不混 SP2 与旧评测；A 需要模型服务/配置才能继续。
## 最新口径纠正（2026-11-03 第七轮）：短例成本支线收尾

- **两处措辞已纠正**：第六轮 `answer_s` 是“生成结束时刻”（GPU 同步后、tokenizer.decode 之前，未单独保存答案文件），`extra_wait_s` 是“生成结束至来源矩阵写出”；B 的 18.427 GiB 是**当前生命周期整条路线峰值**，不是“先释放生成 cache 后”的峰值。
- **可用数字**：总墙钟中位 A **2.024 s**、B-full **2.589 s**；生成结束至矩阵写出 A **0.009 s**、B **0.600 s**；A/B 矩阵 60×142，非空；B 与第五轮独立整段参考 max 5e-9。详见 `outputs/MemoryFlow_执行回传_20261103_07/`。
- **保留**：第五轮独立配对（0.01513）继续有效，但与本轮计时矩阵差值（0.0206）分开；第五轮全零成本仍作废；N=47、CLAUSE、NBA、HTML、前缀 2.89× 未重跑。
- **状态**：短例“有效读出 + 完整成本”实验**已收尾**；本轮无新增模型实验，不追加跨样本/部署/内核诊断。
## 最新推进（2026-11-03 第六轮）：修复计时读出，有效矩阵成本

- **全零原因**：第五轮在 KV cache 合并前抓 K，单 token K 长度 1，按文档区间 [27,3539) 切片为空，静默求和成全零 60×142。第五轮 A/B 成本结论（2.0607 s / 4.1149 s）**撤回**，文件保留。
- **修复**：改在第19层实际 `eager_attention_forward` 权重上取行，key 轴含完整历史；`readout_checks.slice_doc` 在越界时抛错。A key 3777–3836、B 3836，文档列 3512，A/B 非零 7,651/7,669；B 与第五轮独立整段参考 max 5e-9。测试 2/2。
- **有效成本**：A 中位 **2.024 s**（答案后 **0.010 s** 就绪，峰值 15.074 GiB）；B-full 中位 **2.589 s**（答案后 **0.599 s**，峰值 18.427 GiB）；A/B 60×142 与 3×142 均非空，矩阵各自三次同 hash。
- 第五轮独立 `01_eager_pair` 保留；N=47、CLAUSE、NBA、前缀 2.89× 未重算。
## 最新推进（2026-11-03 第五轮）：同后端配对 + A/B 成本

- **同后端 eager 配对**：冻结 3,777-token prompt / 60-token 输出；生成时读出 vs eager 整段回放：token max **0.01513** / mean **2.23e-5**（最差 token 6）；U00/U01/U02 Spearman **0.9988/0.9983/0.9990**；U00、U01 Top-1 相同，U02 Top-1 不同（极小分数）。U00 两侧 top3 来源已列（第 3 名 66 vs 0）。
- **A/B 成本**：同输入、同 60-token 输出、eager；A 生成时分析中位 **2.0607 s**（答案后 **0.0067 s** 矩阵就绪）；B 生成后回放中位 **4.1149 s**（答案后 **2.0626 s** 就绪）；峰值 15.124/15.328 GiB；A/B 60×142 与 3×142 矩阵逐元素差 **0.0**。
- **口径**：A 捕获适配为仅第19层/头15；B 回放为 teacher-forced 增量 KV-cache；模型加载在外；单短例、单 GPU，不外推部署。
- SDPA token28 仍是后端变化对照，不并入 eager 主表；N=47/CLAUSE 未重算。
## 最新推进（2026-11-03 第四轮）：读出边界验证 + 真实二维矩阵

- **读出正确性**：真实 SDPA 边界（torch 2.11.0+cu128，transformers 4.57.6，is_causal=True，enable_gqa=True，scale 0.0883883）捕获的 Q/K 与 apply_rotary hook 完全一致（0 差）；同一份 Q/K/V 手动 P·V vs 实际 SDPA：行27 0.0017、行28 0.0039、行29 0.0069，全矩阵 max 0.0173。**读出没有错**；0.111 是 SDPA 路径自身在 token 28 的分布异常，不是 hook/readout bug。
- **上游**：eager cache vs eager 整段 token28 仅 0.00226；SDPA 行28 doc mass 0.918（eager 0.034–0.042）；逐层 hidden states 自 layer1 起出现差异（row3804 max 0.574），但 all-token max 异常大，仅作粗定位，不能称 kernel bug。
- **矩阵**：真实导出 60×142 token×来源句矩阵与 3×142 输出单元×来源句矩阵；当前输出 U00/U01(C1)/U02(C2)；旧 C0 与当前 U00 不同，已弃用旧 C0 身份。验证 tokens_all_rows/units_all_rows/unit_restorable 全 true。
- **计时**：新完整口径（文本准备/编码/范围→前向→读出→2D 导出）3 次总墙钟 **0.3158/0.3141/0.3155 s**，中位 **0.3155 s**，峰值 15.378 GiB；旧 0.27646 保留为预编码整段汇总口径。
- **第7页**：call10 规则修正为 [3906,4049)；交付整句实为 [1666,1790)（此前 30 字符只是短语）；call10/11 整句未进入后一步请求，仍标语义改写。
- **影响**：无证据表明 CLAUSE 手动读出实现错误，不重算 CLAUSE 局部矩阵；冻结 N=47 保持 eager 主表身份。
## 最新推进（2026-11-03 第三轮）：完整分析计时 + token 28 定位

- **完整回放分析**：`full_analysis_timing.py` 封装真实入口（输入准备→SDPA 前向+第19层Q/K捕获→因果softmax→来源句聚合→矩阵JSON导出）；预热2次、计时3次：总 **0.2765 / 0.2754 / 0.2767 s**，中位 **0.2765 s**，峰值 **15.378 GiB**；60行×142句，三次矩阵同 hash。阶段中位：准备1.0ms、前向+捕获272.5ms、读出/聚合2.0ms、写盘0.6ms。
- **token 28**：同后端 eager cache vs eager 整段 max **0.00537**（token28 **0.00226**），缓存/位置不是主因；0.111 只在 SDPA 侧，且该行 doc mass 0.914 vs eager 0.034–0.042，top key 位置不同；已定位到 SDPA 读出行异常，kernel/手动读出边界未分开。C1/C2 精确映射，C0 仍缺；C2 Top-1 差异保留。
- **展示**：静态图改为 coder 总结起点，显示两标题 rank1/rank9、top8 限制、直达分支 rank46；第7页后一步只含前一步短语，整句未传递，交付含 call22 结论句。
- **表 B/HTML**：沿用第二轮结论，不重做。
## 最新推进（2026-11-03 第二轮）：坐标修复 + token 级配对 + Hit@3 收尾

- **CLAUSE**：`replay_rich` 改为原文扫描取片段，保存消息内/输入/token 三套区间；同文不同位置保留不同 ID，当前输出前文单独身份、不自环；top8 候选不再重复。重算 call07 T1/T2 与 call05 详细句：T1 1.458 → call05 矩阵（`6. Confidentiality.` rank1/4.026；`6. Disclaimer.` rank9/0.764）；T2 未成两矩阵链；call07 直接合同候选最高 rank46（0.0035）。
- **配对**：同一 CUAD 输入、作者生成 60 token 序列，我们的回放逐 token 对齐：mean abs 1.7e-5，max 0.111（token 28）；子句 Spearman 0.844/0.884/0.901（C0/C1/C2），Top-1 1/1/0。仍不能称等价。计时（3 次同步）：只生成 0.305 s 中位；生成+捕获 1.982 s；回放前向 0.274 s（未含聚合）。
- **Hit@3**：47 身份按 needs_review 排除；D-Full 3 seed：hit@1 48/141=34.04%（16/17/15），hit@3 90/141=63.83%（30/30/30）；其余 34/33/32/10。
- **第 7 页**：NBA 题面→call10 规则→call11 改写→call22 报告→交付，原句/位置/关系已提取。
- **表 B**：两个问句在候选 artifact 内（probe_0 a0001 w778-893；probe_1 a0001 w778-971），但原生成事件/可见上下文仍缺，0/47 完整恢复。
- **HTML v2**：节点=调用、父关系来自森林；selftest 四点击全 ok，截图已存。
## 最新推进（2026-11-03）：CLAUSE 真实两矩阵链 + Hit@3 + 离线查看器

- **A（最高优先）**：旧回放把历史 assistant 分析排除在候选外（call07 msg4 9,947 字符未进入旧 67 候选）；新 `replay_rich.py` 全消息候选（call07 T1 426 候选，msg4 85 片段），真实链 call07 T1 → call05 分析（1.458）→ call05 矩阵 → 合同 “6. Confidentiality.”（4.026）。旧结论“已绑定、分数没选中”被推翻。
- **B**：2 输入/5 子句配对 Spearman 0.752（0.609–0.934），边界 token 全一致、来源覆盖 1.0；差异集中在 CUAD 短/过渡子句；**不能声称等价**。成本仅有资源探针；回放 0.028–0.152s 是单次前向未同步，不作完整耗时。
- **C**：N=47 `EvidenceFragmentHit@3`：固定头 34/47、平均头 33/47、BM25 32/47、D-Full 30/47、CLM 10/47；固定/平均/BM25/CLM 的 Hit@1 与旧表一致，D-Full Hit@1 重算 15/47 vs 旧表 16/47，待核。
- **D**：仅最后调用 top8 全为中间分析、未到原文；逐步展开到合同原文；离线 HTML 已生成（headless 截图通过）。
- **E**：RAG/Agent prompt 摘录、规模小表、NBA 阶段原句已出。
## 最新推进（2026-11-02 深夜）：长输入资源探针 + 表 B 缺口 + CLAUSE 单跳结论

- **资源探针**（A800-80GB，bf16）：7,837/14,285/37,917 tokens；普通生成三条成功（4.76/4.81/7.71 s，峰值 15.7/16.9/21.3 GiB）；作者捕获 7.8k 成功（~8.35 s），14.3k/38.0k OOM（申请 21.44/75.18 GiB，非峰值）；7B/1.5B 回放三条全成功（分析侧峰值 16.6–25.6 / 5.2–13.9 GiB）。38k 探针不属于原 47 条。
- **表 B**：原 GenMem 47 条的原始问题、目标生成时刻、当次可见上下文在存储材料中缺失；只有截断的 “Question:” 片段，可恢复 0/47。未伪造 B；旧 13 条保留为探索性。
- **CLAUSE**：累计尝试 6 个任务、完成 2 个；两条完成轨迹都是直达合同原文/文件转交，没有两张矩阵的真实链。任务 1 的 call05 分析在 call07 请求可见，但矩阵未选中；任务 2 的 coder 写 JSON 时请求不含先前分析。未推荐主/备案例。
## 最新推进（2026-11-02 晚三轮）：表 B 口径修正 + 长输入边界实测 + CLAUSE 首条真实轨迹

- **表 A**：冻结数值不变（固定回放头 61.70/70.21/48.94 等）。
- **表 B 修正**：GenMem 原任务 prompt 不含 target 陈述；上一轮 B 把陈述加进 query，属“给定陈述找依据”的探索性对比（原版 9/13@5、10/13@10；7B 5/13、8/13；1.5B 7/13、9/13），不能作自然生成表 B。
- **长输入边界**：原构造下 7,888 / 14,336 / 37,968 tokens；普通生成 SDPA 三条全成功（4.84/4.76/7.72 s，峰值 15.7/16.9/21.3 GiB）；作者捕获 7.8k 成功（8.35 s），14.3k 与 38.0k 实测 OOM。8k 不是模型上限，上一轮 33 条是 configured_skip。
- **CLAUSE**：文件模式两任务跑通 1 个（193 s，14 调用）；call05 矩阵 → 合同原文（工具 52%），call07 判断直接指向合同 tool msg[3]；**未构成两张不同调用矩阵的真实链**；第二批 2 任务未完成（工具上限）。未推荐主/备案例，未硬造多跳。
## 最新推进（2026-11-02 晚二轮）：方法一 B 首跑 + 方法二定向修复

- **方法一 B**：47 源样本中 14 条在 8k 窗口内，全部生成成功（艺峰原版 + 生成时矩阵）；33 条超窗（最大 31,178 tokens）未生成。有效评测 13 条：完整证据@5/@10/首位 —— 原版 9/13、10/13、2/13；7B 5/13、8/13、3/13；1.5B 7/13、9/13、6/13。生成 161 s（14 条，含重载）；回放分析 6.68 s（7B）/2.49 s（1.5B）。未做重叠，GPU 峰值未采集。
- **方法二修复**：CLI 补 span 候选的 relink（v3 图 42 条候选链接/30 个候选）；删除跨目标矩阵借用；交付句多来源 + preferred 最新；森林同 session 父边、跨 session 记 transfer；片段缺失不默认位置 0；环/汇合区分。测试 7/7（含真实 CLI 跨两矩阵）。
- **真实 v3**：call22 结论查询 → call11/call12 响应后 no_matrix 停止；v3 尚无跨两矩阵的真实链，未把文本匹配说成矩阵恢复。
- **新案例**：CLAUSE 有准备脚本/文档但未下载；FinAuditing 依赖 RAGFlow 服务与 key（缺），未产生任务与案例。
## 最新推进（2026-11-02 晚）：方法二通用原型落地；方法一 B 与新案例未执行

- **方法一 A**：N=47 主表与前缀复用保持原样，未重跑、未改口径。
- **方法一 B（生成时原版对照）**：未执行。需要 47 条源样本的生成输入、艺峰自然生成+捕获、7B/1.5B 回放与重新标注；本轮时间用于方法二原型，未给半成品数字。
- **方法二**：`experiments/provenance_v2/` 通用闭环（ingest / forest / query / cli），5 个机制测试通过；在 `g1_v3_20261031b` 上从 `delivery#s08` 查询得到 `delivery → call10#response → call10 矩阵候选` 两跳，停止于材料输入。
- **新案例（FinAuditing/CLAUSE）**：未运行。适配器在 DCCv2 仓库（CLAUSE 数据准备脚本/文档、FinAuditing 配置），但 `.benchmark-data` 只有 NBA 发布包；缺数据准备与运行时间，未产生候选表。
- 旧结果保留；修正后的配对与案例分数见 `CAUSAL_CORRECTION_20261102.md`。
## 最新推进（2026-11-02 下午）：因果遮蔽修正 + 任务级效率预跑

- 三个手动回放脚本加因果遮蔽；短样例核对最大差 0.00184（未加 mask 0.0797）。
- 配对修正后：均值 Spearman 0.752（0.609–0.934），边界 token 无不一致、来源覆盖 1.0；旧 0.750 仅作修正前记录。
- 案例修正后（绝对份额/候选内份额）：call10 解释句 工具 1.6%（候选内 1.6%）；call10 VIOLATION 行 工具 0.8%、未覆盖 93.6%；call22 结论 工具 5.3%、未覆盖 75.7%。
- 任务级预跑（1 任务 comp0-003，未扩 3 任务、未重复）：S 571.9 s；R7-after 24/24 单元、25.4 s、额外等待 +27.5 s、21.4 GB；R7-online 执行失败（490 s、32 调用）；R1.5-online 执行未完成（175 s、12 调用）、分析 4.04 s、6.3 GB；O 无法在 API 执行模型上捕获，未执行。
- 缺口：3 任务扩展与重复未做；两次 online 无有效答案事件；R7-online 汇总缺失；在线/事后一致性未做。
## 最新推进（2026-11-02 上午）：艺峰原版对照 + Operation A 完整回查

- **艺峰原版**：不能直接进入 N=47 主表——47 个目标是固定目标回放，没有对应的自然生成 + 生成时捕获；现有完整捕获只有 2 份开放样例。主表四行保持原样。
- **同输出配对预实验**（2 输入 / 5 子句）：均值 Spearman 0.750（min 0.609，max 0.935）、Pearson 0.651、Top-1 0.60 / Top-3 0.53 / Top-5 0.64；SP1 样例 0.91–0.94，CUAD 样例 0.61–0.67。只作一致性，不作质量分数；无对应语义标签，不计算准确率。
- **NBA Operation A 回查链**：call10 首次生成“帽下只能用空间 + $7M>$4.588M → VIOLATION”；call11 partial 复制；12–21 文本携带；call22 报告修订；最终交付 A。上游 call06 请求读取规则 200–350 行但无工具结果，call07 为 partial/loop_capped；call10 输入无 Room Teams 特例。
- 回放：call10 解释句 前文 79.7% / 任务 12.1% / 工具 1.5%；call10 VIOLATION 行 任务 89% / 工具 11%；call22 结论 任务 78% / 工具 22%。
- 图：`experiments/source_path_v1/figures/operationA_flow.png`；路径：`out/path_operationA.json`。
## 最新推进（2026-11-01 下午）：yf RAG 与 SP 场景规模对比

- 交付 `experiments/scale_compare_v1/`：Markdown 报告 + 逐任务 CSV + 汇总 JSON；只用已有数据，未跑模型。
- RAG 侧：`longcite45k_200.jsonl` 前 20 条（文件顺序），Qwen2.5-7B tokenizer 计数；单任务 1 次调用（生成一次，引用由注意力规则添加）。
- SP 侧：本机唯一完整报告轨迹 SP1.0 `sp1/20261016_smoke_complete`（1 任务、9 调用）；DCCv2 NBA 运行（1 任务、24 调用）单列补充；SP1 保险未完成（15 调用）仅作量级参考。
- 结果：单次输入 3,696.5 → 9,844.4（中位 4,032.5 → 5,793）；单次输出 301.6 → 342.9（中位 302 → 187）；累计输入 3,696.5 → 88,600（约 24×；DCCv2 267,504）；累计输出 301.6 → 3,086（约 10×）。
- 边界：SP 完整样本只有 1 个，均值不具代表性；242 不可达未核对；RAG 无逐调用日志（调用数按流程记 1），response 为数据集保存答案。
## 最新推进（2026-11-01 上午）：长序列回放修通，两条判断矩阵齐备

- 手动捕获（SDPA + 第 19 层 post-RoPE q/k 拦截）解决 call22 的 eager OOM（21,166 tokens）；入口 `replay_manual.py`。
- call10 验证：与 eager 版本行和 0.9802 一致、top 候选全为前文、类别主次一致（前文 0.797 vs 0.792）。
- call10：前文 0.7972 / 任务事实 0.1215 / 工具返回 0.0152（按行平均）；前向 0.331 s。
- call22（Operation B）：任务事实 0.1045 / 前文 0.0580 / 工具返回 0.0415；候选内份额约 51% / 28% / 20%；前向 0.379 s。
- E1 探针：两条判断串行前向 0.710 s（仅选定判断链，非完整任务成本）。
- 下一步：E2（真实再执行 + 在线分析器，独立 GPU）；G7 mask 语义与 P/D 小例。
## 最新推进（2026-11-01 凌晨）：正式调用回放 call10 有效矩阵

- 可复用入口 `replay_call10.py`（REPLAY_CALL/REPLAY_TARGET 参数），对 call10 的**原始消息**做分析侧 chat-template 序列化（prompt 9,444 tokens），保留真实响应前文 1,305 tokens，目标 46 tokens；行位置为 full-sequence 索引 10,748–10,793。
- 有效性：layer 19/head 15 捕获 shape (28 heads, 82 candidates)，finite，行和 0.9802，逐候选和与行和一致；候选切片解码与原文一致；短正对照形状选择仍需修。
- 结果：call10 目标句的固定头关联 80.8% 落在**模型自己的前文**、17.7% 任务事实、仅 1.4% 工具返回（真实分数：0.229/0.218/0.093/0.084…）。这是关联观察，不是因果证明；结合规则文件 0 次 Bird 命中，表述为“当前检索尚未定位到支持该解释的具体原文，依据待核查”。
- 旧 0 分探针已标无效并从路径估计中移除；call22 回放因 prompt 21,166 tokens、eager attention OOM（25.6 GiB），下一步改分块/目标行捕获。
- E1 只有 1/2 覆盖（3.161 s），不作分析成本；E2 未启动；G7 未动。
## 最新推进（2026-11-01 凌晨）：新版运行的两条判断链（G2 首接）

- 在新版首条完整运行（`3c98481`，571.9 s、24 调用、答案 True/A/B vs gold True/B/B）上固定两条判断：G2-1 关键规则解释首次出现在 **call10（perception）**，G2-2 “Operation B complies”首次出现在 **call22（reporter）**；调用身份：7 central / 1 memory_recaller / 7 perception / 9 reporter，delegate→子调用映射未记录。
- **关键结论**：任务提供的规则文件（98,208 字符）中 Bird/Non-Bird/Early Bird 出现 **0 次**，“cap room”短语 0 次；call10 可见输入只有 grep 命中与“无匹配”。报告采用的“under-cap 必须用 cap room、Non-Bird 只适用于超帽队”**在给定材料中找不到依据**（artifact metadata 也自述用了 standard framework）。不作“幻觉”定性。
- 路径：`out/path_v3.json`（24 calls / 86 units / 81 edges / 9 gaps），查询 `delivery#s08` / `s15` 可展开生成调用与可见工具返回；artifact 版本链 v1→v2 已记录。
- 回放探针：两条判断各跑 7B 固定头（prompt 1061/589 tokens、21/6 候选、0.634/0.195 s），但候选质量全 0.0——与 G7 同类的区间/位置映射问题，**不作为有效来源关联**。
- E1 因回放无效暂缓；E2 未启动（需真实再执行＋在线分析器）；G7 待 mask 语义核对。
## 最新推进（2026-10-31 深夜）：新版 DCCv2 接入与第一条完整运行

- **接入**：确认远端 DCCv2 头 `3c984815…`，新 worktree 检出（旧 `0914afc3` 现场保留，未叠旧补丁）；安装官方 `rulearena-nba-v1` Release（216 任务）；任务映射核对：旧 `comp_0#004` 对应新 **`rulearena-nba-comp0-003`**（document 11/11 行逐字一致，gold True/B/B），单任务清单放入 bundle/public。
- **记录层**：`dcc_trace.TraceChatOpenAI` 记录完整公开请求/响应/工具调用；`DCC_MODEL_USE` 选择 transport；inline 任务追加交付机制说明（只补机制）。
- **Run 1**（g1_v3_20261031）：9 调用、162 s，未完成——模型调 `sp_finish` 但引用不存在的 artifact（无 write_file），原生拒绝“requires required artifact type 'report' and a matching final_artifact_ref”。
- **Run 2**（g1_v3_20261031b）：**completed**，24 调用、8 轮、571.9 s，FINISH 接受，最终交付 `spart_a9627af0556afc2e`（report_revision v2，SHA256 `819cf38e…`）。
- **正确性**：Accuracy-only 评测 **0.0**（1/216）；交付结论 “True / A / B” 对官方 “True / B / B”——违规判断与球队对、**操作字母错**。只从保存交付评分，未重跑。
- **待做**：G2 在该 run 上出 1—2 条来源链；G3 E0/E1/E2；G7 mask 语义与 P/D 对齐。
## 最新推进（2026-10-31 夜）：G2 伪环修正、G3 口径统一、G7 真实探针

- **G2**：修掉“最终报告句因同文早现又回到早期调用”的伪环——更早的同文出现记入 `input_occurrences` 并映射到原文 chunk，`report_span_0` 出边为空；直达 0.3563 与经摘要 0.6437 两条路径保留。森林命名改为“恢复出的链”（14/3/2/1 不是原生会话数），缺口=缺 task/attempt/session/delegate 标识。
- **G3**：字段口径从记录代码确认（`ts`=完成时刻，`elapsed`=耗时）；v6 无答案事件 → `answer_ready=null`、`trace_end`、`extra_wait=null`，来源提前量 **−246.5 s**；只覆盖 7 句、合计 9.25 s；s5/s6 前缀因产生于更晚被置空并标注。CPU 组件 E1/E2 的 answer/source 事件已分离，测试通过。
- **G7**：布局已接真实 7B 单次前向。正确性未通过：单分支 P vs D 最大绝对差 0.215、sum 0.946 vs 0.892、top-1 不一致；两分支 0.300/0.179；改 b 影响 a 0.067。可见性检查通过。首个嫌疑=candidate 区间与打包位置的映射（prompt 最后 token 在 D 是 block 首键、在 P 是分支起点）。计时 D 1.20 s / P 单 0.95 s / P 双 1.06 s，正确性未过前不作收益结论。
- **G1**：仍等新版 DCCv2。
- 产物：`experiments/source_path_v1/G_ROUND3_20261031.md`、`branch_packing_v1/pack_runner.py`、`task_timing_v1/analysis_queue.py`；服务器 `g3_queue_v6.json`、`g7_pack_probe.json`。
## 最新推进（2026-10-31 晚）：G2 连接修复、G3 队列、G4 统一口径

- **G2**：`query.py` 现在沿 estimate 边展开且按边防环——一条命令从 `report_span_0` 展开到摘要（0.6437）→ call4 → 13 个上游片段；`compare_views.py` 更正为“最后调用可见摘要+原文 2 个单元”。森林改按角色前缀+工具集 hash+先后顺序：v6 为 Central 14 链 / coder 3 / perception 2 / memory_recaller 1，0 分支；缺口=无原生 session/delegate 标识。三视图已按真实结构重画（B 用 CUAD 有效矩阵，C 补生成/可见/直达箭头）。
- **G3**：日志驱动队列测试完成：7 个理由句分析约 10 s；answer_ready 1793278637.9、sources_ready 1793278386.5，extra_wait **−251.4 s**（来源先于答案就绪），max backlog 6；标注为日志驱动，非在线。
- **G4**：标准 predictor 统一口径重跑：1.5B @5 0.5532/@10 0.6383/Frag@1 0.2553，46.54 s、11.87 GB（11.05 GiB）；7B @5 0.6170/@10 0.7021/Frag@1 0.4894，105.43 s、35.24 GB（32.82 GiB）。同流程 1.5B 快 2.27×、省 2.97× 显存，质量低 6.4/6.4/23.4 个百分点。开发集 11 个（比冻结协议多 3 个 case_02 超限目标 selected_07/08/09，full coverage，与 47 评测目标无 case 重叠）；选头 (16,2) 不变。
- **G7**：未实现，下一轮。
- 产物：`experiments/source_path_v1/G_ROUND2_20261031.md`、`out/method2_views.{svg,png}`；服务器 `/data1/songzhengxing_intern_dccv2/{g3_queue_v6.json,predict_small.py,metrics_g4small/}`。
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

## 多记录 packing（2026-11-05）

- 层一合并：**完成并确认收益**，5 目标句 3.90×，显存基本不变。
- 层二打包：**完成但 7B 上不划算**；等长时略逊于普通 batch，偏斜时 batch 与打包都远慢于顺序回放。要在 varlen/稀疏内核下才可能翻盘。
- 正确性：同形状重复性 0.0；逐候选第一名一致；打包残差 0.021–0.492（短记录单键，top-key 一致）。含 11.8k Writer 的打包 2 条 OOM，属 eager 显存成本。
- 多轮 YF：开发案例锁定 `simple_zh_ix478`（Writer `20261103T160133-056937cc` / Researcher `20261103T160040-61aced06`），覆盖仅 L19/H15、仅 T2/T3、仅 S6/S7；`003` 为单跳不适用。
