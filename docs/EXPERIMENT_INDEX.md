# 实验索引

## informative30 51 目标整批：30 合格（2026-11-07）

**状态：** 36 优先 + 15 跨事件全处理；30 合格（真实 12、受控 18）、对照 3、不足 17、诊断 1；覆盖 20 条轨迹。入口：
[51 汇总](../experiments/multiturn_batch_v1/informative30_batch/reports/SUMMARY_51_20261107.md)。

- 时间顺序检查覆盖正证据和干扰项；case_03:T04 ev10 不进 ev8；case_01:T10 用 ev28 C0034 而非 C0036。
- 30 题：MF 25/30、28/30；head 20/30、28/30；BM25 15/30、25/30；last 0。配对 MF-BM25 21/5/4、MF-head 14/10/6、MF-last 28/2/0。
- 真实 12 题：MF 8/12、11/12；head 7/12、12/12；BM25 4/12、9/12。
- case_06:T10 诊断；旧 batch10 17 题单列。

## informative30 真实中间消息首批：2 题 / 2 轨迹（2026-11-07）

**状态：** 36 优先清单已定位；3 条真实消息核对，2 条合格、1 条诊断。入口：
[真实批报告](../experiments/multiturn_batch_v1/informative30_real/reports/REAL_FIRST_20261107.md)。

- case_01:T10（ev29 父亲身份 → ev30/31 → ev32 结论）与 case_03:T04（ev4 alias → ev8 → ev10/12 → ev14）合格。
- case_06:T10 的 ev8 未承接 A 内容，只作诊断。
- MF 完整 2/2、2/2；head 2/2、2/2（名次 8/7）；BM25 0/2、2/2；last 0；配对 MF-BM25 1/1/0、MF-head 2/0/0。
- 人工构造首批 3 题单列；旧 batch10 17 题复用。

## informative30_v1 接入：首批 3 题（2026-11-07）

**状态：** 新包接入并跑完首批 3 题（3 轨迹，受控中间句）。入口：
[首批报告](../experiments/multiturn_batch_v1/informative30/reports/FIRST_20261107.md)。

- 49 case / 300 target / 285 草案；按 (case,id) 连接，只取目标前材料；36 优先清单未随包提供。
- case_03:T02 / case_05:T07 / case_06:T02；precheck 3/3 PASS；全为 controlled。
- MF 完整 2/3、2/3；head 3/3、3/3；BM25 2/3、3/3；last 0；配对 MF-BM25 1/0/2、MF-head 0/1/2。
- 旧 batch10 从 17 题起算；case_03 s08 只留 diagnostic；旧 100 去向已更新。

## case_03 criteria 实测：累计 18 题 / 8 轨迹（2026-11-07）

**状态：** case_03 selected_08 新增实测（方法跑丢）；case_08 selected_09 待核。入口：
[本批报告](../experiments/multiturn_batch_v1/batch10_v4/reports/TURN14_20261107.md)。

- case_03 三窗：上议院反对党领袖 / 2019 代理任职 / 议员资历；MF 失败，head 完整第 6，BM25/last 失败。
- case_08 selected_09：a0128 只支持检测比例；缺 SNP 芯片与 known variants 原句。
- 累计 18 题：MF 16/18、16/18；head 16/18、18/18；BM25 13/18、16/18；last 0；配对 MF-last 16/2/0、MF-BM25 7/8/3、MF-head 2/11/5。
- 100 去向：18 主表、3 待核、2 对照、3 排除、43 单事件、6 partial 待补标、25 partial 排除。

## 三题证据修正：累计 17 题 / 8 轨迹（2026-11-07）

**状态：** case_05 修正后重跑；case_08/09 待核撤出。入口：
[修正报告](../experiments/multiturn_batch_v1/batch10_v4/reports/FIX_20261107.md)。

- case_05 selected_01 补 b 问句 `a0191[96,205)` 与定义；4 窗组，MF/head 完整第 4、BM25 第 5。
- case_08 selected_02、case_09 selected_08 原文断言不足，pending-evidence。
- 累计 17 题：MF 16/17、16/17；head 16/17、17/17；BM25 13/17、16/17；last 0；配对 MF-last 16/1/0、MF-BM25 7/7/3、MF-head 2/11/4。
- 100 去向：17 主表、2 pending、2 对照、3 排除、43 单事件、8 partial 待补标、25 partial 排除。

## partial 补标新增 3 题：累计 19 题 / 10 轨迹（2026-11-07）

**状态：** case_05 selected_01、case_09 selected_08、case_08 selected_02 补标并跑通；
累计主表 19 题、10 条轨迹。入口：
[partial 报告](../experiments/multiturn_batch_v1/batch10_v4/reports/PARTIAL_20261107.md)、
[批明细](../experiments/multiturn_batch_v1/batch10_v4/reports/BATCH10_V4_20261107.md)。

- 三题 precheck 3/3 PASS，MF/head/BM25 全完整；MF 完整名次 3/3/7。
- 累计：MF 17/19、18/19；head 18/19、19/19；BM25 14/19、18/19；last 0；配对 MF-last 18/1/0、MF-BM25 8/8/3、MF-head 2/12/5。
- 100 去向：19 主表、2 对照、3 排除、43 单事件、8 partial 待补标、25 partial 排除。

## 映射修正后的新增批：累计 16 题 / 7 轨迹（2026-11-07）

**状态：11 道新题全部跑完并完整；累计主表 16 题。** 入口：
[新增批报告](../experiments/multiturn_batch_v1/batch10_v3/reports/EXPANDED_20261107.md)、
[批明细](../experiments/multiturn_batch_v1/batch10_v3/reports/BATCH10_V3_20261107.md)、
[跑前检查](../experiments/multiturn_batch_v1/batch10_v3/precheck.json)。

- 改为 contextual64_v4 逐轨迹 GT；主证据按 ID/起止/文本精确匹配，停用最长子段和事后改标注。
- 跑前检查：并集覆盖完整组、≤10 窗、最终轮单独不完整；旧错段 11/12 BLOCK，修正后 11/11 PASS。
- 新增 11 题全部完整：MF/head 完整@5 11/11，BM25 9/11；旧 T03/T09 复核并入。
- `case_10 selected_07` 语义排除（B 句 3 个月只修饰瘦素/胰岛素）。
- 累计 16 题：MF 15/16、15/16；head 15/16、16/16；BM25 12/16、15/16；last 0。配对 MF-last 15/1/0、MF-BM25 6/7/3、MF-head 2/10/4。
- 100 去向：16 主表、2 对照、2 排除、1 语义排除、43 单事件、11 partial 候选、25 partial 排除。

## batch10 并集池第一批与 100 目标筛选（2026-11-07 凌晨）

**状态：第一批主表 7 题 + 对照 1 题；5/7 完整；100 目标筛选第一版。** 入口：
[修正首批报告](../experiments/multiturn_batch_v1/batch10_v2/reports/FIRST_QUALIFIED_20261106.md)、
[100 目标筛选](../experiments/multiturn_batch_v1/batch10_v2/reports/SCREENING_100_20261106.md)、
[四方法输出](../experiments/multiturn_batch_v1/batch10_v2/reports/BATCH10_V2_20261106.md)。

- 新口径：两轮原始候选并集（同源去重）；BM25 / 7B 固定头平铺 / MemoryFlow 共用；final 10、hop 5；last 单列。
- 主表 5 题（case_06 对照、case_05 超预算、case_10 日期待核另列）：MF 完整@5/@10 4/5，head 4/5、5/5，BM25 3/5、4/5，last 0；配对 MF-last 4/1/0、MF-BM25 1/2/2、MF-head 1/2/2。
- case_02 hop=5/10/100：缺列表项名次 11–14，放宽每跳也进不了前 10 → 上游排序失败；case_10 日期未明确标注为发表日期，撤出主表。
- 筛选：5 built-v2、1 control、1 excluded-budget、1 excluded-date-unverified、3 built-prev、10 candidate-full、43 单事件、11 partial 候选、25 partial 排除；36 partial 未完成补标。
- 旧 47、旧全历史池、pilot B04/F11 不并入。

## batch10 跨轨迹首批 8 题（2026-11-06 深夜）

**状态：首批完成；4 完整 / 4 部分；跨 8 条轨迹。** 入口：
[首批报告](../experiments/multiturn_batch_v1/batch10/reports/BATCH10_FIRST_20261106.md)、
[四方法输出](../experiments/multiturn_batch_v1/batch10/reports/BATCH10_20261106.md)。

- 64 个 contextual64_v4 目标中 20 个多事件、覆盖 8 条轨迹；首批每条轨迹一题（case_01/02/03/04/05/06/07/10）。
- MemoryFlow Hit@3 8/8、完整@5/@10 4/8；last Hit@3 8/8、完整 0；BM25 Hit@3 6/8、完整@10 2/8；head Hit@3 1/8、完整 0。
- 逐跳：hop1 中间结论 8/8（1–2 名），hop2 A 8/8（1–2），hop1 B 8/8（1–3），合并 A/B 8/8 在前 5。
- 未完整：case_02 hop2 预算（列表项），case_03/05/07 构造未含组内其余证据；case_10 同源合并后完整。
- 旧 47、pilot B04/F11 不变；首批无最终轮自足对照，T06 单列。

## pilot-v4 B04/F11 旧材料受控验证（2026-11-06 夜）

**状态：两题跑通；同一轨迹，不作独立/科学结论。** 入口：
[B04/F11 报告](../experiments/multiturn_batch_v1/pilot/reports/B04_F11_20261106.md)、
[四方法输出](../experiments/multiturn_batch_v1/pilot/reports/BATCH_PILOT_20261106.md)。

- B04（公式 + T=20）：MemoryFlow A1/B5（g02@5）；head 用 g01@5（A3/B—）；BM25 g01@6；last B4/A 不可见。
- F11（新增条件 + 修订结论）：只有 MemoryFlow 完整（A1/B3，旧欠定第 2）；BM25/head 拿 A 漏 B，last 拿 B 漏 A。
- 宏平均 n=2：Hit@3 last/BM25 0.500、head/MF 1.000；完整@5 last0/BM25 0/head0.5/MF1；完整@10 last0/BM25 0.5/head0.5/MF1。
- 配对完整 W/T/L：MF-last 2/0/0、MF-BM25 2/0/0、MF-head 1/1/0。
- 旧 47 题与 batch10 三题表不变；矩阵 GPU0/24 GiB，单次前向。

## 多轮批处理准备（2026-11-06 晚）

**状态：统一入口 + 四方法 + 三题开发验收；新数据未到。** 入口：
[验收报告](../experiments/multiturn_batch_v1/reports/ACCEPTANCE_20261106.md)、
[批处理输出](../experiments/multiturn_batch_v1/reports/BATCH_20261106.md)、
[模板](../experiments/multiturn_batch_v1/TEMPLATE.md)。

- 统一 case：轨迹、目标位置、各轮输入/输出、中间传递、候选、证据组；受控/真实请求分开。
- 四方法：last_round、bm25_history、head_full_history、memoryflow；final top-10，hop 5 另记。
- 三题主表 n=2：Hit@3 均 1.0；完整@5 last 0/2、BM25 2/2、head 1/2、MF 2/2；完整@10 last 0/2、其余 2/2。
- 配对完整名次 W/T/L：MF-last 2/0/0、MF-BM25 0/2/0、MF-head 1/1/0。
- T06 为“最终轮自身已有足够证据”对照；预检 3/3、锁文件、测试 9/9。

## GenMem 两轮溯源最终原文排名（2026-11-06 晚）

**状态：离线复算完成；只读已保存分数。** 入口：
[最终排名报告](../experiments/provenance_rounds_v1/reports/FINAL_RANK_20261106.md)、
[排名 JSON](../experiments/provenance_rounds_v1/reports/final_ranks_20261106.json)、
[说明](../experiments/provenance_rounds_v1/README.md)。

- 规则：直达 = hop-1；经中间结论 = hop-1(结论) × hop-2；同一原文 sum 去重，排除结论，全局 top-5。
- G1 均看不到 A；G2 T03 齐（A2/B1）、T09 缺 B（A1/B8）、T06 齐（A3/B1）；G3 T03 A2/B1、T09 A1/B2、T06 A8/B1。
- T09 主例：平铺 B 第 8，多轮全局 A 第 1、B 第 2。T06 为“最终轮自身已有足够证据”对照。
- 同义检查：T03 无第五张断言；T09 的 `a0236` 是可计数清单，标为影子证据；无不同主题合格样例。

## GenMem 受控两轮溯源（2026-11-06）

**状态：3 条样例跑通；不并入 47 题主表。** 入口：
[报告](../experiments/provenance_rounds_v1/reports/ROUNDS_20261106.md)、
[说明](../experiments/provenance_rounds_v1/README.md)。

- 数据：243 `artifacts/raw/genmem_batch10_v3/genmem_batch10_selection_v1.zip` 的 `contextual64_v4`；只用 `case_02`/`case_08`。
- 构造：两轮输入冻结；Qwen2.5-7B-Instruct greedy；7B 固定头 (19,15)；`provenance_v2` 逐跳；top-5。
- 样例：T03（Secret Symphony + Mike Batt）、T09（Zero Zero 1982 + Epic，额外目标）、T06 v2（Zero Zero + 1982）。
- 三组：G1 均看不到 A；G2 T03 找齐、T09 缺 B（8/17）、T06 找齐；G3 三条找齐（结论名次 1/1/3，A 名次 1/1/1，B 名次 2/2/1）。
- 边界：受控多轮，不是原始快照；T06 v1 构造歧义已弃用（v1 文件保留）。

## 黄金案例 YF/MF 实测排序（2026-11-05 晚）

**状态：案例排序已算；DCCv2+27B 未接通；正式指标未填。** 入口：
[执行回传 20261105_03](../outputs/MemoryFlow_执行回传_20261105_03/README.md)、
[实际配对排序](../outputs/MemoryFlow_执行回传_20261105_03/03_实际配对排序.md)、
[标签包](../outputs/MemoryFlow_执行回传_20261105_03/04_标签审阅包.md)。

- `simple_zh_ix478` Writer `20261103T160133-056937cc`：11848 prompt / 1664 generated / 1664×13511 attention。
- T1–T5 的 YF L19H15 与 MemoryFlow 回放全候选分数、top 表、矩阵已出。
- T2/T3 正文支持；T1/T4 部分；T5 候选待核；无正式 Hit@3/完整@10。
- DCCv2 7B unfinished（7 iteration/51.1 s/0 tool）；27B system message 400，未交付。

## DCCv2/SP2 接入试跑与 SP1 回退案例（2026-11-05）

**状态：首选框架未完成；SP1 回退案例索引已建，指标缺失。** 入口：
[执行回传 20261105_02](../outputs/MemoryFlow_执行回传_20261105_02/README.md)、
[执行结论](../outputs/MemoryFlow_执行回传_20261105_02/00_执行结论.md)、
[YF 模型表](../outputs/MemoryFlow_执行回传_20261105_02/01_YF模型支持表.md)、
[试跑清单](../outputs/MemoryFlow_执行回传_20261105_02/02_试跑清单与推荐组合.md)。

- DCCv2+7B：`rulearena-nba-comp0-003` 7 iteration、51.1 s、0 tool、unfinished。
- DCCv2+27B：严格 Qwen 模板 system message 400，无交付。
- SP2+7B/27B：无 report ledger/最终报告。
- SP1 `simple_zh_ix478`：完成；9 调用、1 搜索、2650 字符、gate true；最终 Writer `20261103T160133-056937cc` L19H15。
- 勘误：`simple_p8gv695r` 与 `simple_zh_ix478` 同一 query `52bf4c49…`，非“中产”。
- 指标：YF/MemoryFlow/Gold 未完成；正式批次暂不启动。

## SP2 阻塞、1.5B 补表与信息流 HTML（2026-11-03 第八轮）

**状态：A 待配置；B/C 完成。** 入口：
[执行回传八](../outputs/MemoryFlow_执行回传_20261103_08/00_执行结论.md)、
[缺失配置](../outputs/MemoryFlow_执行回传_20261103_08/01_缺失配置清单.md)、
[N=47 六方法](../outputs/MemoryFlow_执行回传_20261103_08/04_N47六方法主表.md)、
[HTML](../outputs/MemoryFlow_执行回传_20261103_08/05_信息流HTML.md)。

- A：指定提交不可得、无实际配置/可观测模型；实验待定。
- B：1.5B Hit@3 28/47、完整@10 30/47；六方法主表。
- C：CLAUSE v3、前向/反向、selftest 五项通过。
## 口径纠正与短例成本收尾（2026-11-03 第七轮）

**状态：报告口径已纠正，短例支线收尾；无新增实验。** 入口：
[口径纠正与收口](../outputs/MemoryFlow_执行回传_20261103_07/00_口径纠正与收口.md)、
[PPT 可用成本表](../outputs/MemoryFlow_执行回传_20261103_07/01_PPT可用成本表.md)。

- 第六轮 `answer_s` = 生成结束（decode 前、无独立答案文件）；`extra_wait_s` = 生成结束→矩阵写出。
- B 的 18.427 GiB 是当前生命周期整条路线峰值，不是释放生成 cache 后的峰值。
- 可用：A 2.024 s / B 2.589 s 总墙钟；间隔 0.009 s / 0.600 s；A/B 矩阵 60×142、非空。
- 第六轮原始数据保留；第五轮全零成本作废、独立配对保留。
## 有效矩阵与成本修复（2026-11-03 第六轮）

**状态：读出修复、A/B 有效矩阵成本完成。** 入口：
[执行回传六](../outputs/MemoryFlow_执行回传_20261103_06/00_修复结论.md)、
[有效矩阵核对](../outputs/MemoryFlow_执行回传_20261103_06/01_有效矩阵核对.md)、
[完整成本](../outputs/MemoryFlow_执行回传_20261103_06/02_完整成本.md)。

- 旧全零：缓存前 K 轴长 1 + 空切片；旧成本撤回。
- 修复后 A 2.024 s / 额外 0.010 s；B-full 2.589 s / 额外 0.599 s；矩阵非零，峰值 15.074/18.427 GiB。
- 第五轮独立配对保留；不混 SDPA 0.3155 s。
## 同后端配对与 A/B 成本（2026-11-03 第五轮）

**状态：eager 配对与两条路线成本完成。** 入口：
[执行回传五](../outputs/MemoryFlow_执行回传_20261103_05/00_执行结论.md)、
[同后端配对](../outputs/MemoryFlow_执行回传_20261103_05/01_同后端配对.md)、
[答案与来源计时](../outputs/MemoryFlow_执行回传_20261103_05/02_答案与来源就绪计时.md)。

- eager 生成时读出 vs 整段回放：token max 0.01513；U00/U01/U02 Spearman 0.9988/0.9983/0.9990。
- A 2.0607 s（额外等待 0.0067 s）；B 4.1149 s（额外等待 2.0626 s）；矩阵 60×142、逐元素差 0。
- SDPA 诊断单列；不混用后端成本。
## 读出边界与二维矩阵（2026-11-03 第四轮）

**状态：读出实现验证通过；二维矩阵与完整分析计时完成。** 入口：
[执行回传四](../outputs/MemoryFlow_执行回传_20261103_04/00_执行结论.md)、
[读出边界诊断](../outputs/MemoryFlow_执行回传_20261103_04/01_读出边界诊断.md)、
[输出单元与矩阵](../outputs/MemoryFlow_执行回传_20261103_04/02_输出单元与矩阵.md)、
[分析计时](../outputs/MemoryFlow_执行回传_20261103_04/03_分析计时.md)。

- 真实 SDPA 参数：q/k/v 形状、is_causal、GQA、scale；hook Q/K 与算子输入 0 差；manual P·V vs 实际输出行28 0.0039。
- token 28：SDPA doc mass 0.918 vs eager 0.034/0.042；上游 layer1 起差异（粗定位）。
- 矩阵 60×142 / 3×142；计时中位 0.3155 s（含文本准备/编码/2D 导出）。
- 第7页坐标修正：call10 [3906,4049)，交付整句 [1666,1790)。
## 完整分析计时与配对差异（2026-11-03 第三轮）

**状态：完整分析成本已实测；token 28 残留在 SDPA 读出层。** 入口：
[执行回传三](../outputs/MemoryFlow_执行回传_20261103_03/00_执行结论.md)、
[完整分析计时](../outputs/MemoryFlow_执行回传_20261103_03/01_完整分析计时.md)、
[配对差异定位](../outputs/MemoryFlow_执行回传_20261103_03/02_配对差异定位.md)。

- 完整分析中位 0.2765 s（3 次，峰值 15.378 GiB，矩阵 60×142 三次同 hash）。
- 同后端 eager cache/full max 0.00537；token28 0.00226；SDPA 侧 0.111 行异常，原因边界未分开。
- 静态图 v2 与第7页来源表已出。
## 坐标修复与 token 级配对（2026-11-03 第二轮）

**状态：CLAUSE 两矩阵链保留、token 级新测量完成、Hit@3 收尾。** 入口：
[执行回传二](../outputs/MemoryFlow_执行回传_20261103_02/00_执行结论.md)、
[配对与成本](../outputs/MemoryFlow_执行回传_20261103_02/02_单轮配对与成本.md)、
[Hit@3](../outputs/MemoryFlow_执行回传_20261103_02/03_固定评测辅助指标.md)。

- 片段坐标三套区间；同文位置独立；top8 无重复；T1/T2 重算。
- token 级：60 tokens，max 0.111（token 28），子句 0.844–0.901，尚不能等价。
- D-Full 3 seed：@1 48/141，Hit@3 90/141；47 身份固定。
- HTML v2 + selftest；第 7 页四阶段原句；表 B 两问句来源。
## CLAUSE 两矩阵链与辅助指标（2026-11-03）

**状态：真实两矩阵链达成；Hit@3 完成；配对仍不等价。** 入口：
[执行回传](../outputs/MemoryFlow_执行回传_20261103/00_执行结论.md)、
[真实案例](../experiments/cases_finauditing_clause/CASE_RICH_20261103.md)、
[Hit@3](../experiments/genmem_quality_v2/reports/hit3_20261103.json)。

- 候选修复：rich 候选全消息（assistant/tool/user），call07 msg4 参与评分。
- 真实链：call07 T1 → call05 分析 → 合同原文；“最后一步”top8 未到原文，逐步展开到达。
- 配对 0.752；Hit@3 固定头 34/47；离线 HTML `outputs/.../demo/clause_flow.html`。
## 资源探针与 CLAUSE 单跳（2026-11-02 深夜）

**状态：资源探针完成；表 B 有数据缺口；CLAUSE 单跳。** 入口：
[资源探针](../experiments/method1_v2/B_RESOURCE_PROBE_20261102.md)、
[表 B 缺口](../experiments/method1_v2/B_GAP_20261102.md)、
[CLAUSE 记录](../experiments/cases_finauditing_clause/CLAUSE_CASE_20261102.md)。

- 原版捕获：7.8k 成功，14.3k/38.0k OOM；普通生成 38k 成功；回放三条成功。
- 表 B：0/47 原轨迹问题可恢复，未伪造。
- CLAUSE：6 尝试/2 完成，均单跳；无跨两矩阵链。
## 表 B 修正与 CLAUSE 首跑（2026-11-02 晚三轮）

**状态：B 口径修正 + 边界实测完成；CLAUSE 1 个任务完成、无跨两矩阵链。** 入口：
[B 修正](../experiments/method1_v2/B_CORRECTION_20261102.md)、
[B 边界](../experiments/method1_v2/B_BOUNDARY_20261102.md)、
[CLAUSE 记录](../experiments/cases_finauditing_clause/CLAUSE_CASE_20261102.md)。

- 8k：configured_skip，不是模型上限；普通生成 37.9k 成功；作者捕获 14.3k 起 OOM。
- CLAUSE：task1 completed；call05/call07 矩阵直达合同原文；无两矩阵链。
## 方法一 B 首跑与方法二修复（2026-11-02 晚二轮）

**状态：B 为 14/47 窗口内子集（有效 13）；方法二修复测试 7/7；新案例未运行。** 入口：
[方法一 B](../experiments/method1_v2/B_GENERATION_20261102.md)、
[方法二修复](../experiments/provenance_v2/reports/FIXES_20261102.md)、
[新案例状态](../experiments/cases_finauditing_clause/STATUS_20261102.md)。

- B：14 生成、33 超窗、13 有效；原版 9/10、7B 5/8、1.5B 7/9（@5/@10）。
- 方法二：relink/精确矩阵/多来源交付/session 森林；CLI 测试跨两矩阵。
- 缺口：33 超窗、无重叠计时、无 GPU 峰值；CLAUSE 下载与 FinAuditing 服务未做。
## 方法二通用原型（2026-11-02 晚）

**状态：闭环代码 + 测试完成；真实数据只做 v3 演示；方法一 B 与新案例未执行。** 入口：
[provenance_v2](../experiments/provenance_v2/README.md)、[方法一状态](../experiments/method1_v2/STATUS_20261102.md)、
[新案例状态](../experiments/cases_finauditing_clause/STATUS_20261102.md)。

- 通用闭环：ingest/forest/query/cli；测试 5/5；合成覆盖复制、改写（矩阵）、分支、直达/间接、环/深度。
- 真实演示：`g1_v3_20261031b` 24 调用建图，`delivery#s08` 两跳查询。
- 缺口：47 生成时原版对照、FinAuditing/CLAUSE 数据与 2+2 案例未做。
## 因果修正与任务级效率预跑（2026-11-02 下午）

**状态：修正完成；任务级仅单任务预跑，online 执行失败。** 入口：
[因果修正](../experiments/source_path_v1/CAUSAL_CORRECTION_20261102.md)、
[效率预跑](../experiments/flow_efficiency_v1/TASK_EFF_PILOT_20261102.md)。

- 因果遮蔽：短样例 max diff 0.00184；配对 0.752；案例绝对份额重算。
- 效率：S 571.9 s；R7-after +27.5 s；R7-online 失败；R1.5-online 未完成；O 不适用。
- 产物：pair_check_causal、replay_*_causal、eff_after_7b、eff_online_15b。
## 艺峰原版对照与 Operation A 回查（2026-11-02 上午）

**状态：原版不进入 N=47；配对一致性完成（2/5）；NBA 回查链完成。** 入口：
[艺峰配对](../experiments/baseline_adapters_v1/reports/YIFENG_PAIR_20261102.md)、
[Operation A 回查](../experiments/source_path_v1/G2_OPERATIONA_20261102.md)。

- 原版：无 47 目标的自然生成+生成时捕获，不能补做；配对 2 输入/5 子句，Spearman 均值 0.750。
- NBA：call10 首现 → call11 复制 → 12–21 携带 → call22 报告 → 交付 A；上游 call06 读取 200–350 无结果。
- 产物：`path_operationA.json`、`operationA_flow.png`、pair CSV/JSON。
## yf RAG 与 SP 场景规模对比（2026-11-01 下午）

**状态：对比完成；SP 完整样本 n=1，仅作量级说明。** 入口 [规模对比报告](../experiments/scale_compare_v1/SCALE_COMPARE_20261101.md)。

- 数据：RAG `longcite45k_200.jsonl` 前 20；SP1.0 smoke 完整 1 任务 9 调用；DCCv2 NBA 补充 1 任务 24 调用。
- 结果：单次输入 3,697→9,844；单次输出 302→343；累计输入 3,697→88,600（24×）；累计输出 302→3,086（10×）。
- CSV：`scale_compare_v1/scale_compare_tasks.csv`；汇总 JSON 同目录。
## 长序列回放修复（2026-11-01 上午）

**状态：call22 OOM 解除；两条判断矩阵可用；E2/G7 待续。** 入口 [手动回放记录](../experiments/source_path_v1/G2_MANUAL_REPLAY_20261101.md)。

- 手动捕获：SDPA + layer19 拦截 q/k，只算目标行；call10 与 eager 对照通过。
- call10 前向 0.331 s（P=9,444）；call22 前向 0.379 s（P=21,166）。
- 类别（按行平均）：call10 前文 0.797/任务 0.121/工具 0.015；call22 任务 0.105/前文 0.058/工具 0.041。
- `path_v3.json` 的 `replays` 字段记录参数与归一化。
## 正式调用回放 call10（2026-11-01 凌晨）

**状态：call10 有效矩阵完成；call22 OOM 待修；E1/E2/G7 待续。** 入口 [call10 回放记录](../experiments/source_path_v1/G2_CALL10_REPLAY_20261101.md)。

- 序列化：原始消息 + 分析侧 Qwen2.5 模板，prompt 9,444 tokens；前文 1,305；目标 46。
- 捕获：layer 19/head 15，shape (28, 82)，行和 0.9802，finite。
- 类别质量：前文 0.7924 / 任务事实 0.1736 / 工具返回 0.0142。
- call22：21,166 tokens，eager attention OOM；需内存可控捕获。
## 新版运行的两条判断链（2026-11-01 凌晨）

**状态：G2 路径与“关键解释无原文依据”结论完成；回放映射退化、E1/E2/G7 待续。** 入口 [G2 v3 记录](../experiments/source_path_v1/G2_V3_20261101.md)。

- 两条判断：call10（cap-room 规则解释）、call22（Operation B complies）；perception/reporter 身份按首行判定。
- 规则文件 0 次 Bird/Non-Bird；“under-cap 必须用 cap room”无原文支撑。
- 路径 `out/path_v3.json`；回放 0 分退化，不作有效关联。
- 运行 `runs/g1_v3_20261031b/`，评测 `eval/g1_v3_20261031b_accuracy2/`。
## 新版 DCCv2 接入与第一条完整运行（2026-10-31 深夜）

**状态：接入完成；第一条任务执行+交付完成、答案错误（accuracy 0.0）；G2/G3/G7 下一步。** 入口 [G1 v3 记录](../experiments/source_path_v1/G1_V3_20261031.md)。

- 版本 `3c984815…`，worktree `/data1/.../sp2_dccv2_3c984815`；数据 `rulearena-nba-v1`（216 任务）。
- 映射：旧 comp_0#004 → 新 `rulearena-nba-comp0-003`（逐字一致，gold True/B/B）。
- Run1 未完成（FINISH 引用不存在的 report artifact）；补交付机制后 Run2 completed（571.9 s，24 调用，artifact `spart_a9627af0…`）。
- 评测：accuracy 0.0；交付 “True / A / B” vs gold “True / B / B”。
- 记录：`runs/g1_v3_20261031b/`、`eval/g1_v3_20261031b_accuracy2/`。
## G2 伪环修正 + G3 口径 + G7 探针（2026-10-31 夜）

**状态：G2/G3 修正完成；G7 已接 7B 但正确性未通过；G1 等待。** 入口 [第三次回传记录](../experiments/source_path_v1/G_ROUND3_20261031.md)。

- G2：同文早现映射到 chunk，report 无出边；两条合法路径保留。
- G3：ts=完成时刻；answer=null、trace_end、extra_wait=null；7 句 9.25 s；前缀可用性已检查。
- G7：P vs D 单分支差 0.215、top1 不一致；可见性通过；下一步先定位区间/位置映射。
- 服务器 `g3_queue_v6.json`、`g7_pack_probe.json`。
## G2 修复 + G3 队列 + G4 口径（2026-10-31 晚）

**状态：G2 连接修复完成；G3 日志驱动队列完成；G4 统一步骤完成；G7 未实现。** 入口 [续做记录](../experiments/source_path_v1/G_ROUND2_20261031.md)。

- G2：单命令展开完整链；最后调用可见 2 单元；森林 Central 14/coder 3/perception 2/memory 1，0 分支；三视图重画。
- G3：7 句分析约 10 s，extra_wait −251.4 s，backlog 6（日志驱动）。
- G4：1.5B 0.5532/0.6383/0.2553，46.54 s、11.87 GB；7B 0.6170/0.7021/0.4894，105.43 s、35.24 GB。
- 下一步：G7 packing；G1 等新版 DCCv2。
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

## 多记录 packing 接 7B 回放（2026-11-05）

**状态：层一合并已实现并验证有收益；层二打包已实现，7B dense eager 下不划算（有条件）。** 代码：[branch_packing_v2](../experiments/branch_packing_v2/record_layout.py)、[pack_replay.py](../experiments/branch_packing_v2/pack_replay.py)、[诊断](../experiments/branch_packing_v2/diagnose_short.py)；布局单测 7 项通过。

层一（同一记录多目标句一次完整回放）：Writer 记录 5 个目标句 14.523 s → 3.728 s（3.90×），峰值显存 20.44 → 21.05 GiB。层二（跨记录打包，块对角掩码 + 逐记录 position_ids）：2/4 条、等长/偏斜共四组，D 中位 1.17–2.35 s、B 1.26–5.10 s、P 6.00–14.69 s；峰值显存 P 28.0–47.5 GiB 均高于 D 的 16.7 GiB。

旧 G7 两处根因：4-D 布尔掩码被 HF 当 0/1 加到分数上（等于没屏蔽），候选区间被 `min(end, len(prompt)-1)` 截断（该 token 是 D 键空间的 block 首键）。回传：[MemoryFlow_执行回传_20261105_06](../outputs/MemoryFlow_执行回传_20261105_06/README.md)。
