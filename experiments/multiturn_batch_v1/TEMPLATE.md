# 多轮目标统一入口（schema v1）

一条记录 = 一个轨迹里的一个最终目标句。文件是 UTF-8 JSON；一个目标一个文件，
文件名建议 `<case_slug>.json`。目标必须来自**同一条轨迹**；开发/评测按轨迹隔离，
不能把同一轨迹的目标拆到两边。

## 1. 顶层字段

| 字段 | 必填 | 说明 |
|---|---|---|
| `schema` | 是 | 固定 `memoryflow.multiturn_case.v1` |
| `case_id` | 是 | 目标唯一 ID（原 GenMem 用 `genmem_<trajectory>:selected_XX`） |
| `trajectory_id` | 是 | 轨迹 ID；同一轨迹的目标共享该值 |
| `trajectory_case` | 是 | 原案例名（如 `case_02`） |
| `split` | 是 | `dev` / `eval`；按轨迹分配，不在目标级混用 |
| `record_type` | 是 | `real_request`（真实请求/响应记录）或 `controlled`（受控构造） |
| `control` | 否 | 目前只用 `final_round_sufficient`，表示最终轮自身证据已足够，单列对照 |
| `target` | 是 | 最终句及其位置，见下 |
| `rounds` | 是 | 至少两轮；每轮输入、输出、中间传递位置 |
| `candidates` | 是 | 原始候选，按 (artifact, start, end) 归并，带各轮出现位置 |
| `evidence_groups` | 是 | 支持证据组；或标记缺失，见第 5 节 |
| `labels` | 否 | 开发验收用的 A/B 标签；新数据在锁定前补 |
| `provenance` | 是 | 数据来源、哈希、是否原始快照 |

## 2. target

```json
"target": {
  "text": "最终被评分的句子",
  "sha256": "…",
  "origin": "recorded_target | controlled_output",
  "artifact_id": "…", "start": 0, "end": 0,
  "original_target": {
    "text": "原轨迹里的目标句",
    "artifact_id": "…", "start": 0, "end": 0,
    "event_index": 35, "group_id": "…:support_g01"
  }
}
```

- `real_request` + `recorded_target`：`artifact_id/start/end` 必填，指向目标在轨迹里的真实位置。
- `controlled` + `controlled_output`：位置可以为 `null`，但 `original_target` 必须保留原目标句和位置，便于溯源。

## 3. rounds

```json
{
  "round": 1,
  "question": "第一轮问题",
  "inputs": [
    {"unit_id": "…", "artifact_id": "…", "start": 0, "end": 82, "text": "…",
     "role": "evidence_a | evidence_b | context | distractor | locator",
     "position": {"slot": "material", "index": 2}}
  ],
  "output": {"text": "第一轮输出", "sha256": "…", "origin": "model_output | recorded_assistant"},
  "transmission": [
    {"from_round": 1, "unit_id": "round1_output", "text": "…", "sha256": "…",
     "position": {"slot": "earlier_finding", "index": 0}}
  ]
}
```

- `transmission` 只记录**真正进入下一轮输入**的中间文本及其位置；第二轮起链方法需要它，
  缺位时登记 `missing_inputs` 并让链方法停止，不伪造传递。
- 真实请求的 `position` 用原消息序号/角色；受控构造用 `slot=material/earlier_finding` 加序号。
- 同一 unit 的文本必须与 `inputs[].text` 一致；`sha256` 用于锁定。

## 4. candidates 与证据身份

候选按 **原始材料身份和区间** 归并：`canonical_id = "{artifact_id}#{start}-{end}"`。
同一原文在多轮重复出现只保留一个候选，`occurrences` 记录它在各轮的实际位置：

```json
{
  "canonical_id": "genmem_xxx:a0305#0-82",
  "artifact_id": "genmem_xxx:a0305", "start": 0, "end": 82, "text": "…",
  "occurrences": [
    {"round": 1, "unit_id": "…:a0305:u0-82", "role": "evidence_a",
     "position": {"slot": "material", "index": 2}},
    {"round": 2, "unit_id": "…:a0305:u0-82", "role": "context",
     "position": {"slot": "material", "index": 7}}
  ]
}
```

评分返回的是 `canonical_id`；覆盖检查用 `(artifact_id, start, end)` 的区间，
不按 unit id 或文本重复计数。

## 5. evidence_groups

```json
{
  "group_id": "…:support_g01",
  "coverage": "full | partial",
  "items": [
    {
      "primary": {"artifact_id": "…", "start": 0, "end": 82, "text": "…"},
      "alternatives": [
        {"artifact_id": "…", "start": 0, "end": 82, "text": "…"},
        {"artifact_id": "…", "start": 259, "end": 341, "text": "…"}
      ]
    }
  ]
}
```

- 组间 OR；组内每个 item 的任一 alternative 被覆盖，组才算完整。
- 覆盖沿用冻结规则：同一 artifact 上，选中窗口对片段的**非空白字符**全覆盖；
  触碰边界不算覆盖。
- `coverage=full` 才进入 Complete@5/@10 的分母；`partial` 只做诊断。

## 6. 矩阵输入（方法侧）

评分矩阵不由本入口负责，单独放在 `matrices/<case_slug>.json`：

```json
{
  "schema": "memoryflow.multiturn_matrices.v1",
  "case_id": "…",
  "final_round": "r2",
  "hop_budget": 5,
  "final_budget": 10,
  "matrices": {
    "r1": {"target": "第一轮输出", "candidates": [{"canonical_id": "…", "text": "…", "score": 0.0}]},
    "r2": {"target": "最终句", "candidates": [
      {"canonical_id": "transmission:r1", "text": "第一轮输出", "score": 0.0},
      {"canonical_id": "…", "text": "…", "score": 0.0}
    ]},
    "flat": {"target": "最终句", "candidates": [{"canonical_id": "…", "text": "…", "score": 0.0}]}
  },
  "source": {"scores_path": "…", "scores_sha256": "…"}
}
```

- `rN` 矩阵 = 第 N 轮输出对第 N 轮可见材料；`transmission:r{N-1}` 是中间传递候选，
  MemoryFlow 沿它展开到上一轮矩阵。
- `flat` 矩阵 = 最终句对全部历史原始候选（同头直接回放）。
- 所有方法共用 `final_budget`（默认 10）；`hop_budget`（默认 5）另记。
- 候选 id 必须能在 case 的 `candidates` 里找到（`transmission:*` 除外）。

## 7. 缺失登记

导入先跑 `validate_case`（阻断）和 `missing_registry`（登记），规则：

| 情况 | 处理 | 记录 |
|---|---|---|
| 目标句空 / 位置缺（real 模式） | 拒绝导入 | `E_TARGET` |
| 轮次 < 2 或输入/输出空 | 拒绝导入 | `E_ROUND` |
| 中间传递文本与上一轮输出不符 | 拒绝导入 | `E_TRANSMISSION` |
| 中间传递缺位 | 允许导入、链方法停止 | `missing_inputs: roundN:transmission` |
| `evidence_groups` 空 | 允许导入、不评分 | `missing_labels: evidence_groups` |
| 某组 `coverage=partial` | 允许、组不进分母 | `partial_group` |
| 候选池空 | 拒绝评分 | `missing_inputs: candidates` |
| 受控构造 | 允许，单独统计 | `warnings: controlled construction` |

阻断问题写进 `preflight.json` 并停止；非阻断问题进入 manifest 的 `registry`，
在报告里单列，不能悄悄当成完整样本。

## 8. 预检、锁定与评分

```bash
# 1) 导入（开发验收用 import_dev.py；新数据走同一 schema 的导入器）
python experiments/multiturn_batch_v1/import_dev.py \
  --manifest artifacts/raw/genmem_batch10_v3/report_manifest.json \
  --subset artifacts/raw/genmem_batch10_v3/subset \
  --out experiments/multiturn_batch_v1

# 2) 预检并锁定：先固定纳入条件、候选、标签、矩阵哈希，再看分数
python experiments/multiturn_batch_v1/preflight.py --dir experiments/multiturn_batch_v1
python experiments/multiturn_batch_v1/run_batch.py \
  --dir experiments/multiturn_batch_v1 --write-lock \
  --out experiments/multiturn_batch_v1/reports/BATCH_20261106.json \
  --md experiments/multiturn_batch_v1/reports/BATCH_20261106.md

# 3) 评分
python experiments/multiturn_batch_v1/run_batch.py \
  --dir experiments/multiturn_batch_v1 \
  --out experiments/multiturn_batch_v1/reports/BATCH_20261106.json \
  --md experiments/multiturn_batch_v1/reports/BATCH_20261106.md
```

`run_batch.py` 无 `lock.json` 会拒绝评分；lock 含 case/matrix/candidate/label/evidence
哈希，任何一项变化都会中止。新数据到后先只跑 `preflight.py` 和 `--write-lock`，
确认小批一致，再启动评分。
