# 关键研究决策

- 停止继续扩大共享 Anchor 模型：7B 校准未使 Attention 读出成为可靠语义来源边。
- 使用冻结 Qwen 全文表示和关系评分器：把文本编码与 Target–Source 关系判断分开。
- 旧 c8 的 M6D.3 在统计持平时选较简单的 R-SYM；保留 Ranking/Edge 分 checkpoint 的事实。
- 重构严格单正例、同文档 15 候选的 LC-Sent-15；Reserve 保持封存。
- LC-Sent-15 的 Q3 融合权重只在 Train OOF 冻结，然后评估 Dev；不把融合当独立创新。
- 不再优化合成 Summary 的 Track A/B 作为主要结果；转向可审计的自然 SP 轨迹。
- 用户会重新考虑研究方向；旧计划不自动构成下一步授权。
