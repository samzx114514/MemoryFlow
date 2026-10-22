# 数据与获取

仓库只放 LC-Sent-15 的协议、构建代码、manifest、数据卡和少量既有 Train/Dev 示例。完整 Train/Dev、Reserve/Blind 和原始 LongCite 不在 Git。示例见 [`samples/`](../legacy/local_data/lc_sent15_v1/baseline_core_v1/samples/)；它们来自原有 baseline core，未重新标注。

官方 LongCite-45k 修订版 `b776b01faf6e132a3d9cc373de1b46cd6630d772` 的 `long.jsonl`：5,726,201,192 bytes，SHA256 `8eb96dad6496d8d28d983982e6f623adc1e44ffa9dce215ffc7d56fd0336623b`。本机历史位置 `F:/CodexProject/MemoryFlow/smallest_experiment/data/lc_sent15_v1/`；构建和身份文件在 [`local_data/lc_sent15_v1/`](../legacy/local_data/lc_sent15_v1/)。使用前按固定修订版获取并核对 checksum。Reserve 不作调参。

真实 SP 的本机旧 pilot 是工作流审计资料，不是可评分的 Source-to-Summary Gold。原始 16 MiB 节点文件保留在原项目，Git 只收审计与 exporter 代码。合作者的 `all_samples.json` 10 查询输入历史 SHA256 为 `0dffd2ca7fcb917d9e2db6f190dc840208715f25f40b2d44d695eae521ff9796`；它不含 Summary 或 citation Gold，未收进 Git。
