# LC-Sent-15 对比审计报告

## 决策

`MEMORYFLOW_YIFENG_METHOD_COMPARISON_PROTOCOL_AMBIGUITY`

未运行 Dev。补充材料只支持自然生成回答后按生成 clause 做 attention citation attribution；未定义在不改写既有 Target 的前提下对 LC-Sent-15 固定 Target-Source 对打分。归档还缺少固定 `head_ranking.json`，已知 Qwen 7B 缓存无权重 snapshot。重新 probe、手工指定 head、设计 teacher forcing 或重新生成 Target 都超出授权。

## 未生成结果

未生成 `dev_scores.jsonl`、`metrics.json`、bootstrap CI、集合指标或 GPU 峰值。没有本次 Dev 分母、点估计或可与冻结基线并列的艺峰方法结果。

## 冻结基线（仅待比较参考）

| Method | Hit@1 | MRR | nDCG@5 |
|---|---:|---:|---:|
| BM25 | 0.6842 | 0.7470 | 0.7433 |
| Qwen cosine | 0.451754 | 0.595358 | 0.619916 |
| R-SYM | 0.754386 | 0.827306 | 0.843610 |
| D-Full-64 | 0.780702 | 0.851374 | 0.869965 |
| D-Full-64 + BM25 | 0.831871 | 0.885701 | 0.897075 |

## 下一最小任务

索取官方固定 `head_ranking.json`（含模型 revision、probe split 与选择记录），以及对给定 Target 的官方 teacher-forced replay/direct Target→Source scoring 定义。收到后只重新做方法契约复核。