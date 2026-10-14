# 外部模型与运行产物

主要实验的原始根目录在 243：`/data2/pkuiti/songzhengxing_intern/codex_files/smallest_experiment/workspace/results/`，合成 transfer 位于同项目的 `results/memoryflow_summary_transfer_v1/`。仓库的 [`evidence/server/`](../evidence/server/) 保留精简报告、指标、冻结配置和 manifest；完整逐样本预测、原始日志、特征缓存、checkpoint 和模型权重仍在原位置。服务器不可访问时，仓库内的结果表和报告足以阅读主要结论。

Qwen2.5-7B-Instruct 快照及 Q0 的 FP32 `F_mean` 缓存需按对应 run manifest 的 revision/checksum 和路径准备；不得用另一个快照默默替代。旧 c8、LC-Sent-15 的候选构造与 checkpoint 身份不同。没有引入 Git LFS。
