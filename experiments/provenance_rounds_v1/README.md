# provenance_rounds_v1：基于 GenMem 材料的受控两轮溯源

**状态：** 第一轮执行完成（2026-11-06）。三条样例已跑通：`case_02:selected_03`、
`case_02:selected_09`（case_02 额外目标）、`case_02:selected_06_v2`。报告见
[ROUNDS_20261106](reports/ROUNDS_20261106.md)。最终原文排名（离线复算）见
[FINAL_RANK_20261106](reports/FINAL_RANK_20261106.md)。

## 边界与口径

- 数据：243 上 `artifacts/raw/genmem_batch10_v3/genmem_batch10_selection_v1.zip`
  的 `contextual64_v4`（`source_units.jsonl` + `ground_truth.json`）。只用原开发集
  `case_02`、`case_08`。
- 数据包**没有逐次请求的完整快照**（见包内 `contextual64_v4/README.md`：
  `visibility=unverified`、`actual_use=unknown`）。因此本实验明确标为
  **基于 GenMem 的受控多轮验证**：两轮输入由旧轨迹材料冻结构造，不是原始请求恢复，
  也不是原 47 题主表的一部分。原 47 题结果继续单列。
- 两轮构造规则：第一轮只给证据 A 和同主题候选，得到中间结论；第二轮把第一轮的
  中间结论逐字放进输入，加证据 B（和同检索结果的标题）及同主题候选，得到最终句。
  第二轮**原始材料**必须不含 A 或其等价片段（`build_spec.py` 固定检查：精确包含、
  8-token shingle、最长公共子串 < 40 字符，且不得使用 A 的等价出现单元）。
- 生成：Qwen2.5-7B-Instruct，BF16，greedy，固定 seed；两轮输出逐字冻结。
- 评分：沿用冻结的 7B 固定头（Qwen2.5-7B-Instruct，第 19 层第 15 头，eager，
  contextual64_v4 用的固定 query 和 `\n\n` 候选拼接，目标语句只作为读出目标），
  实现直接复用 `experiments/genmem_quality_v2/predict.py` 的 `build_case`/`Engine`/`EnergyTrap`。
- 连接：直接复用 `experiments/provenance_v2` 的 `from_synthetic` + `ProvenanceQuery`
  （top-k 逐跳、copy/exact/prefix/embedded 传输边、环/深度停止）。两轮之间唯一的
  跨调用传递是“第一轮答案逐字粘贴进第二轮提示”，作为显式 `copy` 边记录。
- 预算：每次返回 `top-k = 5`（与冻结 Hit@5 口径一致）。候选 < 10 时直接报固定预算下
  找齐了哪些原文。
- 证据标签在看分数前固定：A/B 只用 `contextual64_v4/ground_truth.json` 的
  `support_g01` 主证据；标题/URL/同主题片段标 locator/context/distractor，不当作证据。

## 三组比较

| 组 | 输入 | 排序对象 |
|---|---|---|
| 1 最后一轮 | 第二轮实际输入（含中间结论） | 第二轮原始材料（中间结论不算“原文”） |
| 2 平铺 | 两轮原始材料合并 | 同一批原始候选，同一 `top-k` |
| 3 MemoryFlow | 从最终句出发 | 链：最终句 →（copy）中间结论 → 第一轮矩阵 → A；B 在第一跳 |

## 流程

```bash
PY=/data2/pkuiti/songzhengxing_intern/memoryflow/artifacts/legacy/.conda_env_cf/bin/python
ROOT=/data2/pkuiti/songzhengxing_intern/memoryflow
RUN=$ROOT/runs/provenance_rounds_v1/20261106_v1

$PY experiments/provenance_rounds_v1/build_spec.py \
  --source $ROOT/artifacts/raw/genmem_batch10_v3/genmem_batch10_selection_v1.zip \
  --recipe experiments/provenance_rounds_v1/recipes/case_02_selected_03.json \
  --out $RUN/spec_case_02_selected_03.json

$PY experiments/provenance_rounds_v1/generate.py \
  --spec $RUN/spec_case_02_selected_03.json \
  --out $RUN/frozen_case_02_selected_03.json \
  --model /data2/pkuiti/songzhengxing_intern/model/Qwen2.5-7B-Instruct \
  --physical-gpu <空闲卡>

$PY experiments/provenance_rounds_v1/score.py \
  --frozen $RUN/frozen_case_02_selected_03.json \
  --out $RUN/scores_case_02_selected_03.json \
  --root $ROOT --physical-gpu <同一张卡>

$PY experiments/provenance_rounds_v1/analyze.py \
  --frozen $RUN/frozen_case_02_selected_03.json \
  --scores $RUN/scores_case_02_selected_03.json \
  --out $RUN/analysis_case_02_selected_03.json
```

`run_case.sh` 把上面四步串起来并写日志；GPU 选卡前先看
`nvidia-smi --query-gpu=index,memory.free,utilization.gpu --format=csv`，避开当前 SP2 运行。

## 最终原文排名（离线复算）

- 每跳 top-5 与最终 top-5 分开记录；最终列表把直达（hop-1）和经中间结论（hop-1 结论 × hop-2）的路径分数合并，同一原文相加去重，排除中间结论后取全局前 5。
- 三组：G1 最后一轮、G2 两轮平铺、G3 多轮全局。T09 主例：平铺 B 第 8，多轮全局 A 第 1、B 第 2；T06 标为“最终轮自身已有足够证据”的对照（全局 A 第 8，不需要 A）。
- 同义检查：T03 第二轮无第五张断言；T09 无显式 fifth，但 `a0236` 是排序清单（去掉 Caravans 时 Zero Zero 第 5），已标注为可计数影子证据。
- 不同主题样例：`case_08` 两个目标都只有单段主证据，`case_02` 其余目标同主题；本轮不新增。
- 脚本：`final_rank.py`（只读已保存分数）；测试：`tests/test_final_rank.py`。

## 文件

| 文件 | 作用 |
|---|---|
| `core.py` | 读 zip/解压目录、解析单元与 ground truth、冻结 spec、A 排除检查、提示渲染 |
| `build_spec.py` | 生成并校验一条冻结样例（spec + sha256） |
| `generate.py` | 两轮 greedy 生成，冻结中间结论与最终句 |
| `score.py` | 三张固定头矩阵：m1（第一轮）、m2（第二轮）、mflat（平铺） |
| `analyze.py` | 建 provenance_v2 图、逐跳查询、三组名次与是否找齐 |
| `final_rank.py` | 离线最终原文排名：每跳 top-5 + 直达/间接路径合并、去重、全局 top-5 |
| `make_report.py` | 从保存的 spec/frozen/scores/analysis 生成 ROUNDS 报告 |
| `recipes/` | 每条样例的候选集合、角色、问题；候选和标签在看分数前固定 |
| `tests/` | 无模型的结构测试 |

## 尚未做到

- 三条样例的固定头结果只覆盖 dev 案例内的受控构造，不外推到 47 题主表或真实 SP 运行。
- `case_02:selected_09` 不在 8 个冻结开发目标内，单列为“开发案例额外目标”。
- T06 v1 构造有歧义（把标题行算进“第六个”），已弃用；v2 不依赖序号计数。
- 不是原始逐次请求恢复；不把语义支持当作实际使用或因果影响。
