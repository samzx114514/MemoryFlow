# MemoryFlow 完整多轮溯源第一版验收

2026-11-09

## 已实现

入口是 `python -m provenance_v2.full`。`replay` 为选定运行实例的每次调用保存一份矩阵和一份位置表，`build` 从原始请求和响应生成森林，`query` 从调用 ID 和输出字符区间查询。查询只读已有矩阵。重复出现的目标可用字符区间或第几次出现来指定。

- 森林保存原始请求和响应。上下文父边、调度关系、工具调用与返回的配对、逐片段内容转交分开存。用 action ID 和工具调用 ID 确认记录里能对齐的关系。文本匹配保存生产者输出区间和接收者输入区间，同文多处时保留歧义。
- 回放沿用 Qwen2.5-7B-Instruct 的第 19 层、第 15 个头（从 0 起）。输入含记录中的消息和工具定义。完整输出一次分词，工具调用参数按 Qwen 模板序列化。矩阵每行对应一个预测位置，候选列保留原始文本和坐标。同调用的前文列随预测位置保持因果可见性。
- 查询按目标跨度选择矩阵行，局部分数为这些行对候选片段的注意力质量之和。沿转交边只追被命中的上游区间，输出每条路径的调用、范围、局部名次、分数和原文终点。

原日志保存的是结构化工具调用和回复文字。这里以 7B 模板重放这些记录，原始生成模型的字节级工具输出未保存。系统提示和工具定义参与回放上下文，来源列延续 rich 回放的非 system 候选范围。文本转交和注意力分数分别记录，路径是可核对的溯源候选。重复原文和框架任务提示也可能进入候选，已在真实样例中看到这类干扰。

## 真实矩阵覆盖

| 轨迹 | 选中的记录 | 整次调用矩阵 | 输出行 |
|---|---|---:|---:|
| CLAUSE `cuad_ambiguity_04dc45f69b796b86` | 已完成实例，call00–call08 | 9 | 5,732 |
| NBA `rulearena-nba-comp0-003` | 已完成实例，call00–call23 | 24 | 12,260 |

CLAUSE 的日志文件还混有另一实例和独立记录。按已完成任务的 user ID 确定本次范围，保留原日志下标。33 份矩阵均核对了文件校验和、矩阵形状和预测行偏移。所有尚未可见的输出前文列在对应行上均为零。12 个机制测试通过，其中包含三次局部评分、两条间接分支和一条直达原文的独立受控验收。

## 同一矩阵查询两句

`call07.npy` 有 1,052 行、679 列。查询前后 SHA-256 均为 `04e3bc4529969b0b64137a62c3384339e7598373047719d02c263d18a9173d5a`。区间使用从 0 开始的半开范围。

| 目标 | call07 字符区间 | call07 矩阵行 | 命中的 call05 输出区间 | call05 矩阵行 | 找到的合同原文 |
|---|---|---|---|---|---|
| T1，两个 Section 6 | [156,198) | [33,41) | [107,280) | [21,63) | `6. Confidentiality.` |
| T2，修改权与编辑控制冲突 | [200,278) | [42,63) | [696,1130) | [151,241) | `(e) WebMD retains absolute editorial control…` |

T1 选取的路径局部分数为 1.5103、4.5884。T2 对应路径为 1.9218、20.1392。两句直接复用 call07 和 call05 的完整矩阵。报告列的是可人工核对的分支，查询产物还保留同次查询的其他路径。

## 真实长链与分支

从 NBA 的 `call23` 工具调用总结查询「Team B has only $4,588,000 in cap room」。目标字符区间为 [130,168)，矩阵行 [30,47)。首跳命中 `call11` 的 [3984,4102)，其矩阵行 [1074,1129)。从这段起同时找到工资帽和球队工资两条分支。

| 分支 | 按查询顺序读取矩阵 | 局部分数 | 原文终点 |
|---|---|---|---|
| 工资帽 | call23 → call11 | 0.8359 → 2.3491 | call11 的 message 2，工资帽 140,588,000 美元 |
| 球队工资 | call23 → call11 → call07 → call02 | 0.8359 → 4.9285 → 3.9670 → 6.1052 | call02 的 message 2，球队工资 136,000,000 美元 |

球队工资分支依次查了四个不同调用的矩阵。每条转交边的生产者区间与下一跳实际取行的区间逐项相等。该样例走的均是记录中的调用和工具历史。

## 实际运行入口

在 243 的部署目录下运行。将输出路径指到新的目录可从头复算。原路径再次执行会校验已有矩阵并复用。

```bash
cd /data2/pkuiti/songzhengxing_intern/memoryflow/artifacts/runs/full_replay_20261109
root=/data2/pkuiti/songzhengxing_intern/memoryflow
py="$root/artifacts/legacy/.conda_env_cf/bin/python"
model=/data2/pkuiti/songzhengxing_intern/model/Qwen2.5-7B-Instruct
clause_run=/data1/songzhengxing_intern_dccv2/clause_run/runs/clause_2
nba_run=/data1/songzhengxing_intern_dccv2/runs/g1_v3_20261031b
"$py" -B -m provenance_v2.full replay --run "$clause_run" --out clause --model-dir "$model" --gpu 0
"$py" -B -m provenance_v2.full replay --run "$nba_run" --out nba --model-dir "$model" --gpu 0
"$py" -B -m provenance_v2.full build --run "$clause_run" --matrix-dir clause --out clause/forest_v1.json
"$py" -B -m provenance_v2.full query --forest clause/forest_v1.json --matrix-dir clause --call call07 --text 'duplicate Section 6 numbering (structural)' --out clause/t1_v1.json
"$py" -B -m provenance_v2.full query --forest clause/forest_v1.json --matrix-dir clause --call call07 --span 200 278 --out clause/t2_v1.json
"$py" -B -m provenance_v2.full build --run "$nba_run" --matrix-dir nba --out nba/forest_v1.json
"$py" -B -m provenance_v2.full query --forest nba/forest_v1.json --matrix-dir nba --call call23 --span 130 168 --out nba/team_b_v1.json
```

上面的回放、建图和查询命令均在 243 实跑。三条查询还在本地用同批矩阵复算，统一换行后 JSON 的 SHA-256 与服务器相同。实测模型为 bfloat16，Transformers 4.57.6，PyTorch 2.11.0+cu128，A800 GPU0。

## 复核产物

- [逐跳验收数据](<C:/Users/25779/Documents/Codex/2026-11-05/memoryflow-2026-11-05-memoryflow-ppt/work/memoryflow-full-replay/artifacts/runs/acceptance_20261109.json>)
- [CLAUSE T1 查询](<C:/Users/25779/Documents/Codex/2026-11-05/memoryflow-2026-11-05-memoryflow-ppt/work/memoryflow-full-replay/artifacts/runs/clause/t1_v1.json>) · [CLAUSE T2 查询](<C:/Users/25779/Documents/Codex/2026-11-05/memoryflow-2026-11-05-memoryflow-ppt/work/memoryflow-full-replay/artifacts/runs/clause/t2_v1.json>)
- [NBA 完整查询](<C:/Users/25779/Documents/Codex/2026-11-05/memoryflow-2026-11-05-memoryflow-ppt/work/memoryflow-full-replay/artifacts/runs/nba/team_b_v1.json>) · [NBA 森林](<C:/Users/25779/Documents/Codex/2026-11-05/memoryflow-2026-11-05-memoryflow-ppt/work/memoryflow-full-replay/artifacts/runs/nba/forest_v1.json>)
- [CLAUSE 矩阵清单](<C:/Users/25779/Documents/Codex/2026-11-05/memoryflow-2026-11-05-memoryflow-ppt/work/memoryflow-full-replay/artifacts/runs/clause/manifest.json>) · [NBA 矩阵清单](<C:/Users/25779/Documents/Codex/2026-11-05/memoryflow-2026-11-05-memoryflow-ppt/work/memoryflow-full-replay/artifacts/runs/nba/manifest.json>)
