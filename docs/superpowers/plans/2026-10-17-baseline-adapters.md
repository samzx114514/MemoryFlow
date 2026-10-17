# CLM 与艺峰方法接入 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. 本会话没有这些子技能，按用户已授权的“开始复现与适配”在当前会话直接执行，不创建子代理。

**Goal:** 接通两条作者原始实现与 MemoryFlow 数据接口，取得真实的组件测试结果；不把工程跑通称为完整论文复现。

**Architecture:** 作者源码保存在 243 的 `memoryflow/artifacts/third_party/`，不改写；自有适配层保存在 Git 的 `experiments/baseline_adapters_v1/` 与 243 的 `scripts/baseline_adapters_v1/`。固定目标来源排序使用 CLM；艺峰方法保留自然生成回答后归因的原生任务，原始 SP1 输出不是它生成的回答。

**Tech Stack:** Python 标准库；243 既有 PyTorch/NumPy 环境；作者 CLM 与 citation_common/generate_attention 实现。

## Global Constraints

- 保险任务暂停；不运行 SP1，不修改 SP2，不读 Reserve/Blind。
- 固定 CLM 代码 commit `d5f9ef0fd9bde185df0ceaad4f4ecc6cfe8c34f6`，参考权重必须匹配 Qwen3-8B last-token pooling，不能替换成旧 Qwen2.5 均值表示。
- 旧方法的 Gold、候选顺序和 tie rule 不变。本轮不产生 LC-Sent-15 新指标。
- 模型计算只在 243。先运行 CPU 组件测试；不抢占已有 GPU，不进行付费 API 调用，不下载 Qwen3-8B 或其他 GB 级依赖。
- 小型 CLM 官方投影头允许下载到 243，先查 revision/大小/校验值，下载上限 100 MB，且只加载张量 checkpoint。
- 艺峰 head selection 缺失时，不冒用任意 head 为论文选中 head；不把 teacher-forced replay 默认为作者协议。
- 真实轨迹无语义 Gold；适配输出只标未评分，不能按文本可见性造正例。
- 原文、第三方受限源码、权重不入 Git；输出目录必须新建，不覆盖旧结果。

### Task 1: 固定方法契约及无模型适配层

**Files:** `experiments/baseline_adapters_v1/adapters.py`、`test_adapters.py`、`prepare.py`。

**Interfaces:** 统一记录包含 `id, query, language, target, sources[{id,text}], gold=null, candidate_policy`。`clm_request(record)` 返回 `(state, questions)`；每个 source ID 原样作为 choice key，Target 是 state，来源原文是 action candidate。`yifeng_input(record)` 返回 `(native_record, source_map)`；只用原始 query 和来源拼接上下文，不把既有 Target 泄露给自然生成器。

- [x] 先写并运行测试：相同来源文本不同 ID 不合并；重复 ID 拒绝；空文本拒绝；Oracle/Gold 字段不进入模型输入；艺峰 native 输入不包含 Target；源偏移逐字可回查。
- [x] 实现最小函数。CLM 调用公式固定为 `engine.answer(state, questions, model='clm-latest')`，不用会丢失 ID 的字符串排名返回；按分数降序、source ID 升序排序。
- [x] `prepare.py` 只读取两份完整例，按全部已检索来源建立候选清单，保留总结原文，不宣称候选全集就是实际输入集合。输出为 `memoryflow/runs/baseline_adapters_v1/inputs_20261017/`。
- [x] 本机和 243 运行 `python -m unittest discover -s experiments/baseline_adapters_v1 -p test_adapters.py -v`：12 项通过（243 使用服务器脚本目录）。

### Task 2: 243 上调用作者组件

**Files:** `experiments/baseline_adapters_v1/component_smoke.py`、`README.md`、`reports/component_report.json`。

**Interfaces:** `component_smoke.py --clm-root <固定clone> --yifeng-root <解压代码> --head <已校验checkpoint> --output <新目录>`。CLM 使用固定种子 20261017 的模拟 encoder 向量，验证作者投影头与 Engine 分数一致；这些向量不是语言模型结果。艺峰使用固定 attention 矩阵验证原生聚合、熵阈值、拒答与引用 ID 输出。CPU 环境来自旧 `.conda_env_cf`，不修改它。

- [x] 作者 schema 及 citations 数值例已纳入组件测试。
- [x] 固定官方投影头 revision/校验值，调用作者真实 HeadPair 和 Engine；75,557,149 字节，经过本机中转到 243。
- [x] 9 项检查通过；输出版本、输入/代码/权重 SHA256、seed、运行时间和 `COMPONENT_ONLY_NOT_MODEL_EVALUATION` 标记。结果在 `components_20261017_v3/`。
- [x] 上传适配代码到 243，执行测试与两例数据转换；只下载不含原文的报告到 Git。

### Task 3: 状态与下一步

**Files:** `docs/STATUS.md`、`docs/EXPERIMENT_INDEX.md`、243 `tasks/20261017_baselines/STATUS.md`。

- [x] README 区分已完成组件、待执行模型推理、待取得的 head selection 和大模型依赖。
- [x] 明确 CLM 原生参考头约 76 MB，Qwen3-8B 未下载；艺峰 Qwen2.5-7B 已有但 BGE-M3/固定 head ranking 尚缺。
- [x] 不自动开启 200 样本 probe、长上下文或 GPT-4o Judge；已向用户询问下一轮资源安排。
- [x] 轻量代码与报告已推送用户指定 GitHub 的 main；远端 commit `a5abb1f` 与本地一致。原文与模型产物保持忽略。
