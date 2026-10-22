# 分协议结果

**整理日期：2026-10-14。** 各表只在自己的数据协议内比较。Hit@1 是首名正确比例；MRR 是首个正确候选倒数排名的平均；nDCG@5 衡量前五排序；AUPRC 用于二分类 Edge。表中多种子数据明确标注均值。

## 旧 c8 LongCite 代理协议

固定候选 8，但允许多个正例；Train 854 Targets / 6,832 pairs，Dev 228 / 1,824。与下方严格 15 选 1 **不能直接横比**。旧 Anchor C4 的 Dev nDCG@5 **0.581699**、MRR **0.576958**、Edge AUPRC **0.335071**，见 [C5F 最终报告](../evidence/server/C5F_DEV_FINALIZATION_243.md) 和 [C5F 指标](../evidence/server/c5f_dev_rescore_243_v1/final_dev_selection.json)。R-SYM 的 Ranking MRR **0.849765**、Edge AUPRC **0.550182** 来自不同 checkpoint，见 [M6D.3 对照报告](../evidence/server/m6d3_best_checkpoint_paired_selection_v1/M6D3_REPORT.md)。其三种子配对审计将 R-SYM 与更大的 M6B 评分器判为统计持平，按简单性选 R-SYM；这只支持语义配对，不证明方向。

## LC-Sent-15 v1：同文档严格 15 选 1

Train 854 Targets / 12,810 pairs；Dev 228 / 3,420；Reserve 218 / 3,270（封存）。均匀随机 Hit@1 理论值 **1/15 = 0.0667**。引用标签为 Silver。表内均为 Dev；R-SYM 和 D-Full-64 为三随机种子均值。

| 方法 | Hit@1 | MRR | nDCG@5 | 仓库内来源 |
|---|---:|---:|---:|---|
| BM25 | 0.6842 | 0.7470 | 0.7433 | [BM25 指标](../evidence/server/lc_sent15_v1_bm25_gate_v1/metrics.json) |
| Qwen `F_mean` cosine | 0.451754 | 0.595358 | 0.619916 | [Q0 指标](../evidence/server/lc_sent15_v1_qwen_fmean_cosine_v1/metrics.json) |
| R-SYM，收敛闭环 | 0.754386 | 0.827306 | 0.843610 | [Q1C 指标](../evidence/server/lc_sent15_v1_q1c_rsym_convergence_v1/metrics.json) |
| D-Full-64，listwise CE | 0.780702 | 0.851374 | 0.869965 | [Q2 原始汇总](../evidence/server/lc_sent15_v1_q2_head_loss_v1/metrics_by_run.json) |
| 固定 Fusion，0.65/0.35 | 0.831871 | 0.885701 | 0.897075 | [Q3 指标](../evidence/server/lc_sent15_v1_q3_oof_fusion_v1/metrics.json) |
| 艺峰方法 | 0.872807 | 0.919515 | 0.929711 | [2026-10-22 指标](../experiments/lc_sent15_external_v1/reports/yifeng_metrics.json) |
| CLM | 0.271930 | 0.471214 | 0.511638 | [2026-10-22 指标](../experiments/lc_sent15_external_v1/reports/clm_metrics.json) |

2026-10-22 补测：艺峰 199/228、CLM 62/228，均为固定配置的一次完整 Dev 推理，无新增训练。艺峰用 Qwen2.5-7B-Instruct 固定头 `(19,15)` 回放目标句并排序；其原生模板额外使用原问题。CLM 用 Qwen3-8B 和作者发布头，沿用 Transformers 编码适配器。输入、设置及中文/英文分项见 [补测说明](../experiments/lc_sent15_external_v1/reports/RESULTS_20261022.md)。两行是统一候选上的适配结果，不是各自论文原生任务的复现成绩。旧基线未重跑。

数据身份、抽样和负例限制见 [Data Card](../legacy/local_data/lc_sent15_v1/baseline_core_v1/DATA_CARD.md)。Q1C 沿用 Q1 的三个最佳 epoch 并补完早停；Q2 中 D-Full-64 相对 R-SYM 的 Hit@1 提升的配对区间跨零。Q3 权重只由 Train OOF 选出，Dev 改善的配对区间严格为正。

## Synthetic Summary transfer：smoke test

Track A：137 个唯一单文档生成 Summary Target，正例由生成过程赋予。BM25、Qwen cosine、R-SYM（三种子均值）、D-Full、固定 Fusion 的 Hit@1 分别为 **0.9416、0.5912、0.7129、0.7032、0.8954**；见 [Track A 指标](../evidence/server/memoryflow_summary_transfer_v1/track_a/metrics.json)。BM25 接近饱和，不是自然 Agent 信息流难度。

Track B：10 个多文档 Summary、143 个 clause、4,194 个来源句；[评估状态](../evidence/server/memoryflow_summary_transfer_v1/track_b/citation_evaluation_status.json) 表明没有 Gold/Judge。这里没有准确率可报，方法一致率不能冒充准确率。

## 真实 SP 轨迹

本机旧 SP pilot 的 [可恢复性审计](../legacy/local_data/sp_natural_v1_raw/sp_semantic_edge_recoverability_audit.md) 显示 20 个 Case 中可直接恢复的语义来源边为 0。没有找到完成本研究所需的 SP1 Source→Researcher Summary→Reporter 可评价轨迹和结果表；因此真实轨迹指标为 **未取得**，而不是零分。
