# Qwen3-8B 下载 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. 本会话无这些子技能，按用户明确授权内联执行。

**Goal:** 将固定版本 Qwen3-8B 下载并核验到 243，等待用户指定 GPU；不启动推理。

**Architecture:** 官方 API 提供 revision 与文件身份；243 从可达发布源取回相同文件，并逐文件对官方哈希。HF 镜像大文件超时后改用 Qwen 的 ModelScope 发布，LFS 文件哈希须完全相同，固定每文件 commit；小文件保留 HF 固定 revision。小脚本、清单与结果进 Git，权重只在服务器。

**Tech Stack:** 已有 huggingface_hub 0.36.2、Python 标准库、SSH。

## Global Constraints

- 用户已批准约 16 GB 下载，GPU 编号随后提供；不得启动 GPU/模型推理。
- 艺峰 head_ranking.json 由用户向师兄索取，不重跑 probe。
- 模型固定 `Qwen/Qwen3-8B@b968826d9c46dd6066d109eabc6255188de91218`。
- 唯一目标目录 `/data2/pkuiti/songzhengxing_intern/memoryflow/artifacts/models/Qwen3-8B`，不复制到本机。
- 镜像不接收用户凭据；`token=False`，禁用隐式 token 和 Xet 额外缓存。
- 不修改环境依赖，不删除用户文件；下载前保留至少 5 GiB 余量。

### Task 1: 固定清单与下载

**Files:** `experiments/baseline_adapters_v1/qwen3_snapshot.json`、`acquire_qwen3.py`。

**Interface:** `acquire_qwen3.py --destination /data2/pkuiti/songzhengxing_intern/memoryflow/artifacts/models/Qwen3-8B` 使用邻接清单，下载后写 `acquisition_report.json`。

- [x] 官方 API 核实 14 个所需文件的大小及 LFS SHA256 / Git blob ID，固定 revision。
- [x] 启动限 2 并行的后台下载，不获取第二套完整副本。HF 镜像线路慢，已停止本任务原进程，保留约 20 MB 断点，切换到校验值一致的 ModelScope 发布。后台进程为 1423448；进程号只用于本次记录，后续必须先核对命令再操作。
- [ ] 按下式流式核验权重 SHA256；小文件核验 Git blob：`sha1(b'blob '+str(size).encode()+b'\0'+content)`。缺失或不符不得标记完成。

### Task 2: 验收与交接

- [ ] 核对 index 引用的 5 个权重 shard 全部在清单内；config 是 qwen3、hidden_size 4096。
- [ ] 报告保存实际大小、每文件 SHA256、官方身份匹配结果、剩余磁盘、revision、下载源与 `gpu_used=false`。
- [ ] 更新当前状态并推送轻量文件；模型仍不入 Git。GPU 未获指定之前只停留在已准备好阶段。

下载日志：`/data2/pkuiti/songzhengxing_intern/memoryflow/tasks/20261017_baselines/qwen3_download.log`。完成判据是目标目录生成 `acquisition_report.json`，不能将后台启动当成下载完成。4 项离线文件校验测试通过。
