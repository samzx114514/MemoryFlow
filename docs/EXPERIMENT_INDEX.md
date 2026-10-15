见 [EXPERIMENT_INDEX.md](EXPERIMENT_INDEX.md)。

## DCC Stage 1：离线校准（2026-10-15）

**状态：OFFLINE / HUMAN_REVIEW_PENDING / NO_MODEL_RUNS。** T1 内部条款引用存在性、T2 条件与替代依据义务各 4 版；每版 4 个对象。8 例仅用于协议校准，不进入正式效果评测。公开题面、Gold 和辅助索引分别见 [data/](../experiments/dcc_diagnostic_v0/data/)；固定配置见 [stage1.json](../experiments/dcc_diagnostic_v0/config/stage1.json)。

代码入口为 [stage1.py](../experiments/dcc_diagnostic_v0/stage1.py) 的 `validate`、`render-preview`、`report`，求值和渲染见 [core.py](../experiments/dcc_diagnostic_v0/core.py)。结果是离线校验 8/8、32 个对象、20 份 `DRY_RUN_NOT_SENT` 预览、18/18 单元测试；没有模型指标。证据见 [validation.json](../experiments/dcc_diagnostic_v0/reports/validation.json)、[逐例评审包](../experiments/dcc_diagnostic_v0/reports/REVIEW_PACKET.md)和 [交付清单](../experiments/dcc_diagnostic_v0/reports/delivery_manifest.json)。无外部大产物；未被后续版本替代。
