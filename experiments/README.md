# 当前实验入口

当前主线是采集真实 SP1 轨迹、确定信息单元与来源标注，再比较已有基线。这里还不是统一可安装的 MemoryFlow 方法包。

1. [sp1_runtime_v1](sp1_runtime_v1/README.md)：采集运行记录；长任务预算终止问题仍需处理。
2. [trace_review_v1](trace_review_v1/README.md)：提取真实输入输出与可见性；固定展示案例不等于通用 benchmark。
3. [baseline_adapters_v1](baseline_adapters_v1/README.md)：CLM 与艺峰方法已跑通两例，尚未完成统一协议的效果比较。

[dcc_diagnostic_v0](dcc_diagnostic_v0/README.md) 是暂停的离线诊断支线，保留原路径和独立测试，不混入上述主线。旧 LongCite 方法、训练和数据构建已集中到 [legacy](../legacy/README.md)。具体哪些代码继续用、哪些只保留追溯，查 [代码地图](../docs/CODE_MAP.md)。
