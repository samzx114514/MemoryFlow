见 [EXPERIMENT_INDEX.md](EXPERIMENT_INDEX.md)。

## CLM / 艺峰基线接入 v1（2026-10-17）

**状态：ADAPTERS_AND_UPSTREAM_COMPONENTS_READY / NO_MODEL_BENCHMARK。** [代码与方法边界](../experiments/baseline_adapters_v1/README.md)、[243 组件报告](../experiments/baseline_adapters_v1/reports/component_report.json)、[真实输入准备报告](../experiments/baseline_adapters_v1/reports/preparation_report.json)。

两份未标注真实轨迹输入；9 项作者组件检查通过。CLM 参考头与作者实现固定版本，艺峰保持自然生成归因协议。没有 LC-Sent-15 新分数、没有语义 Gold、没有 GPU/付费调用。服务器产物在 `memoryflow/runs/baseline_adapters_v1/`。保险任务暂停。

## 真实轨迹展示与目录整理（2026-10-17）

**状态：短链路完成；保险任务预算停止；离线提取完成；没有语义 Gold。** 代码：[trace_review_v1](../experiments/trace_review_v1/README.md)。统一入口：[WORKSPACE_MAP](WORKSPACE_MAP.md)。

243 输出：`memoryflow/reports/flow_review_20261017/`，包含 SP1 完整短例、保险未完成例、245 的单个 CUAD dev 例；每例含 `flow.json` 与可读说明，分享包以根 `README.md` 为入口。输入仍在 `memoryflow/runs/sp1/`；245 原始路径保持只读。外部原文不提交 Git。本轮只做日志提取与可见性核查，不重新评分旧方法、不访问 Reserve/Blind。

## DCC Stage 1：离线校准（2026-10-15）

**状态：OFFLINE / HUMAN_REVIEW_PENDING / NO_MODEL_RUNS。** T1 内部条款引用存在性、T2 条件与替代依据义务各 4 版；每版 4 个对象。8 例仅用于协议校准，不进入正式效果评测。公开题面、Gold 和辅助索引分别见 [data/](../experiments/dcc_diagnostic_v0/data/)；固定配置见 [stage1.json](../experiments/dcc_diagnostic_v0/config/stage1.json)。

代码入口为 [stage1.py](../experiments/dcc_diagnostic_v0/stage1.py) 的 `validate`、`render-preview`、`report`，求值和渲染见 [core.py](../experiments/dcc_diagnostic_v0/core.py)。结果是离线校验 8/8、32 个对象、20 份 `DRY_RUN_NOT_SENT` 预览、18/18 单元测试；没有模型指标。证据见 [validation.json](../experiments/dcc_diagnostic_v0/reports/validation.json)、[逐例评审包](../experiments/dcc_diagnostic_v0/reports/REVIEW_PACKET.md)和 [交付清单](../experiments/dcc_diagnostic_v0/reports/delivery_manifest.json)。无外部大产物；未被后续版本替代。
