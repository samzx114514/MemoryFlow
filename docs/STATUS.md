# 当前状态

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
