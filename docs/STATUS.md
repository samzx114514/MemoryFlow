# 当前状态

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
| LC-Sent-15 数据构建、Train/Dev 基线和 Q1C/Q2/Q3 | completed | [本机构建报告](../local_data/lc_sent15_v1/baseline_core_v1/BUILD_REPORT.md)及 [指标表](RESULTS.md)；Reserve 仍封存。 |
| Synthetic Summary Track A/B | completed | [运行摘要](../evidence/server/memoryflow_summary_transfer_v1/run_summary.json)；完成的是 smoke test，Track B 无 Gold。 |
| 旧 SP pilot 日志可恢复性 | completed | [本机审计](../local_data/sp_natural_v1_raw/sp_semantic_edge_recoverability_audit.md)：无可直接恢复的语义 Gold 边。 |
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
