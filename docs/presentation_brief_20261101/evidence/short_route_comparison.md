# 同一生成服务下的效率短对照：S / S+O / S+R（2026-10-29）

## 结论先说

- **配对完成了**：同一作者插件服务（Qwen3.8-27B FP8、TP=1、同一卡、同一 SDK 客户端、同一冻结材料 3,162 prompt tokens、128 输出上限），
  S（无捕获）与 S+O（捕获 + 作者来源计算）各 3 次交替，**输出完全相同**（hash `4175d731…`）。
- **捕获的额外成本**：生成 3.687 → **4.062 s**（+0.375 s，+10.2%），来源后处理 **0.033 s**，完整链路 **4.097 s**（+0.41 s，+11.1%）。
- **事后回放路线**：S 的 3.687 s + R 的 **1.014 s** = **4.701 s**（串行）。
- 两条路线在**这个短条件、这组模型**下：捕获路线 4.10 s，回放路线 4.70 s；模型不同（Qwen3.8-27B 生成 vs Qwen2.5-7B 回放），
  只能称“实际部署路线对照”，不能当作同骨干算法比较。

## 环境与身份

| 项 | 值 |
|---|---|
| 服务 | `/data2/xyf/conda_envs/xuyf/vllm_hook_env`，vLLM 0.18.0，torch 2.10.0+cu128，Python 3.12.13 |
| 模型 | `/data/Qwen3.8-27B-FP8`，`--served-model-name /data/Qwen3.8-27B`，TP=1，单卡 A800-80GB |
| 启动 | `VLLM_PLUGINS=vllm_hook_piecewise`、`VLLM_HOOK_PIECEWISE=1`、`VLLM_HOOK_USE_SAFETENSORS=1`、`VLLM_HOOK_WORKER=qk_piecewise`、`TORCHDYNAMO_DISABLE=0`、`VLLM_USE_AOT_COMPILE=0`、PIECEWISE、`--max-model-len 10240`、`--kv-cache-dtype auto` |
| 客户端 | 作者 SDK 客户端副本（只改 DATA_PATH/冻结材料/计时打印，不改捕获算法） |
| 冻结材料 | `/data1/.../yf_server/p0/frozen.json`：source 6000 字符、prompt **3,162 tokens**、chat template 关闭 thinking、SHA256 固定 |
| 预热 | 首次请求 73.4 s（编译/首 token），**不参与正式统计** |

## 结果表（TP=1，同一服务，3 次正式样本）

| 设置 | 内容 | 正式样本 | 稳态中位 | 范围 | 输出 |
|---|---|---:|---:|---|---|
| S | 只生成，无捕获 | 2（另有 1 次 73.379 s 编译预热，剔除） | **3.687 s** | 3.676–3.697 | `4175d731edd9…` |
| S+O | 生成 + Q/K 捕获 + 来源计算 | 3 | **4.097 s**（生成 4.062 + 后处理 0.033） | 4.094–4.132 | `4175d731edd9…`（与 S 的完整 SHA256 相同） |
| S+R | S 的文本交给 Qwen2.5-7B 回放 | 1 | **4.701 s**（3.687 + 1.014） | — | 回放输入 = S 的输出 |

捕获证据：每次 S+O 都读到单头 artifact（`Q=(128,256)`、`K=(3289,256)`、`TP=1`、`tp_rank=0`、`local_q_head=20`、`local_kv_head=3`、
layer 51.self_attn.attn），并输出引用分数；S 的请求没有产生任何该 run 的捕获文件。

## R 的明细

| 项 | 值 |
|---|---|
| 回放模型 | Qwen2.5-7B-Instruct，bf16，固定头 (19,15)，单卡 |
| 目标/候选 | 5 个回答片段 / 104 个来源句（与生成侧同一冻结原文） |
| prompt tokens | 3,352 |
| prefill | 0.775 s |
| 目标块 | 0.238 s |
| 回放合计 | **1.014 s** |
| 模型加载 | 9.179 s（另列） |
| 峰值显存 | 16.75 GB |

## 三条回答

1. **捕获是否真的发生**：是。S+O 每次都有 Q/K 文件与头/行数元数据，并产出引用分数；S 没有对应文件。
2. **相同条件下捕获增加多少**：生成 +0.375 s（+10.2%），后处理 +0.033 s，完整链路 +0.41 s（+11.1%）；两侧输出一致。
3. **两条路线差多少**：S+O 4.10 s vs S+R 4.70 s（不同模型、同一冻结材料）；串行总时差 0.60 s，但**不能**据此说哪条路线更优——
   模型骨干不同，且这是单条短样例。

## 与上一版的关系

- 上一版 P0 报告里 G0/G1（无插件）8.9 s 与 G2（插件 TP=4）2.0 s 的 4.5 倍差异，**本轮不用于本表**；该差异仍未定位，
  且测量时 GPU 被其他用户占用、TP=4 服务随后初始化失败，原数字单列为附录。
- 本轮改用**同一插件服务**内的 S vs S+O 对比，消除了“插件服务 vs 普通服务”的混淆；TP=1 是当前稳定资源下的选择，
  TP=4 的旧数字（G0 8.9 / G2 2.0）保留在上一份报告，不混表。

## 边界

- 单条短样例（2k 级输入、128 输出、并发 1），六长度条件与并发 4 未跑。
- R 与生成模型不同骨干；同骨干回放适配仍是待办。
- 后处理时间只包含作者客户端的 attention 重建、片段聚合与引用选择；Q/K 写盘与读取已计入端到端（客户端等待 artifact）。
- 两模型未同时驻留：S 阶段 1 卡（27B FP8），R 阶段 1 卡（7B），峰值显存分别记录，不相加。

## 产物

- 服务器：`/data1/songzhengxing_intern_dccv2/yf_server/p0/{s_nocap_tp1.json, so_cap_*.log, r_from_s.json, frozen.json}`；
  服务日志 `g2_tp1.log`
- 客户端副本：`/data1/.../yf_driver/client_frozen.py`（冻结材料 + 捕获）
- 驱动：`experiments/flow_efficiency_v1/{yf_p0_bench.py,yf_replay_bench.py}`
- 轻量结果：`experiments/flow_efficiency_v1/reports/yf_sor_20261029.json`
