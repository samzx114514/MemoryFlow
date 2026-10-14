# 艺峰补充方法契约审计

## 结论

正式名称：**Attention-based citation attribution**。本次不运行 LC-Sent-15 Dev：补充代码仅对自然 greedy QA generation 产生的 response clause 做归因；没有对给定 Target 句子进行 teacher-forced replay 或直接 Source 评分的入口。把 LC-Sent-15 Target 改写为 question、prompt 或生成目标都会改变评测协议。

## 固定身份

- ZIP：`/data2/pkuiti/songzhengxing_intern/AAAI27_supplementary_material.zip`
- ZIP SHA256：`f44074df6a22596c9a78b2ab3f815ce9c2486f2225db6377c9aaad9e8a48487e`
- 提取目录：`third_party_readonly/AAAI27_supplementary_material`（只读）
- 主模型：`Qwen/Qwen2.5-7B-Instruct`
- Probe embedding model：`BAAI/bge-m3`
- 服务器仅有 Qwen 7B ref 标记；无该 ref 对应 snapshot/权重。

## 推理和 Head

使用 `AutoTokenizer(..., use_fast=True)`；有 chat template 时调用 `apply_chat_template(..., add_generation_prompt=True, enable_thinking=False)`，否则使用固定 book/question/answer prompt。模型以 argmax 自然生成（默认最多 600 token）并捕获一个 head 的生成 token 到 document token attention。

推理必须从 `--head-ranking` 读取第一名，或由用户传入 `--layer`、`--head`。归档中没有 `head_ranking.json`、固定 layer/head 或等价产物。probe 脚本会在附带 LongCite-45k 200 条数据上（seed 42，100 中文+100 英文）重新选择所有 head，默认 semantic threshold 0.70、margin 0.05；本 checkpoint 不得重跑此选择。

## 公式和原生输出

每个 generated clause 先平均其各生成步骤的 selected-head attention，在 document token 范围归一化；再对每个 source sentence token span 求和并二次行归一化，形成 clause × source matrix。

`peak=max(row)`；`H=-sum(p log p)/log(number_of_sources)`；`confidence=peak-H`。若 `confidence > tau`，预测所有 `row_i > beta*peak` 的 source，否则 abstain。固定默认 `tau=-0.70`、`beta=0.50`。原生输出为连续矩阵、每个生成 clause 的多引用集合及 abstention，而非一个外部给定 Target 的固定-15候选 ranking。

## LC-Sent-15 兼容性

不兼容，且不得自行适配。LC-Sent-15 要求固定 Target、15 个固定候选 Source 及其既有 ID/文本/顺序/标签；补充方法要求自然生成回答再定义 clause token 范围。不存在方法保持的 Target→Source 映射。