# 通用跨调用溯源原型（provenance_v2）

## 完整调用回放入口

`python -m provenance_v2.full replay` 冻结每次调用的全部输出行和来源列，`build` 建森林和片段转交链接，`query` 用调用 ID 与输出区间查询。以 `experiments` 为模块搜索目录。历史的 `cli.py` 仍可读取目标级矩阵。完整命令和实测案例见 [第一版验收](reports/FULL_REPLAY_20261109.md)。


目标：把“执行记录 → 上下文森林 → 局部矩阵 → 跨调用连接 → 逐跳查询”做成不依赖具体任务文本的代码流程。

## 结构

```
ingest.py   从 calls.jsonl/predictions.jsonl（或合成 fixture）读入 calls/units/candidates/matrices
            传输链接：assistant 精确/复制/前缀；tool 内容里包含前序输出（embedded）；
            交付句到产生它的调用（copy）
forest.py   上下文森林：每个调用的父节点=其请求中最后一条 assistant 消息的生产者调用；
            同一父节点的多个子调用即分支；多生产者时记录 ambiguous；会话未知时标注
query.py    固定逐跳展开：矩阵 top-k → 传输链接 → 上游调用的矩阵 → 继续；
            防止环、深度上限、缺矩阵/缺上游时停止并记录原因
cli.py      build（运行目录 + 回放 JSON → 图） / query（目标单元 → 路径 JSON）
tests/      5 个机制测试：复制链、直达+间接、分支可见性、环/深度、trace 读入
```

## 使用

```bash
python experiments/provenance_v2/cli.py build \
  --run runs/g1_v3_20261031b \
  --matrices replay_call10.json replay_violation.json replay_conclusion.json \
  --out out/graph.json

python experiments/provenance_v2/cli.py query \
  --graph out/graph.json --unit "delivery#s08" --depth 5 --top-k 5 \
  --out out/query.json
```

图与查询均为 JSON：每跳包含单元、调用、矩阵、候选（原文、消息位置、分数、排名、传输链接）与停止原因；链接区分 `generation`（矩阵）/`copy|exact|prefix|embedded`（记录/位置，跨调用）。

## 本轮验证

- 合成测试 5/5 通过（`python -m unittest discover -s experiments/provenance_v2/tests`）。
- 真实 trace：`runs/g1_v3_20261031b`（24 调用）构建成功；从交付句 `delivery#s08` 查询得到
  `delivery#s08 → call10#response → call10 矩阵 top 候选` 的两跳路径，停止在工具/任务材料（无更早模型输出）。

## 适配边界

- 矩阵 JSON 需带 `call`、`target`、`candidates[].text/score/where`；`where=message[N]` 用于把候选绑定到真实消息位置（绑定失败则跳过并计数）。
- 森林父边只认“请求里最后一条 assistant 消息”的内容匹配；多生产者标 ambiguous，不合并。
- 文本匹配目前是精确/包含，不做模糊语义；同一内容多处出现保留位置，不强行合并。
- 尚未接入 artifact 版本链、FinAuditing/CLAUSE 专用读取器；这些是下一步，不在本轮冒称完成。
