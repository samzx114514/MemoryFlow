# Multi-round Query Development Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在已有7B完整矩阵上隔离中间候选筛选的影响，确认能补回多少多段证据及CPU开销。

**Architecture:** 不改FullQuery.walk或forest_bridge.query默认行为。新建开发查询器，复用原矩阵加载、局部质量归约与来源连接，把重复片段组成有向无环图，按剩余深度缓存每个节点的根分数和路径计数。数学规则仍为逐跳相乘、同一原文的所有路径分数相加；只输出代表路径，完整连接保留在查询图里。

**Tech Stack:** Python、NumPy、已有provenance_v2与GenMem固定标签。

## Global Constraints

- CPU小验证，不运行GPU、不重生成、不重建1050张矩阵。
- 原92题版本、标签、候选、返回上限、实验一/三、PPT保持不动。
- 全部配置深度16。原作者筛选、缓存作者筛选、Top5、Top10均回传。
- 最终返回预算2/5/10；实际返回数及固定预算Precision一并记录。
- 缓存不归一化局部权重、不平均多条转交、不重选模型头。
- 相同调用＋相同文本区间只归约一次；同一节点的不同剩余深度单独汇总。
- 路径数量报告全部路径的整数计数，展示路径只保留每个原文的最高分实例；不可把代表路径数当全部路径数。
- 固定3条开发轨迹：必含musique_1252_run_2；另取按sample_id排序首个含≥3支持项的轨迹，以及首个同时含1项与≥3项的不同轨迹。只依据标注结构选择，不读方法结果。
- 同轨迹所有目标归同侧；剩余轨迹本轮不运行新版。此前原版成绩已知，不称为全新盲测。Reserve/Blind不访问。
- 查询预算：最多2000独立片段、20000深度状态、500000根分数缓存项、30秒墙钟。触及限制标记未完成，禁止把部分结果当完整结果。

### Task 1: 缓存与合并查询器

**Files:** 新建`experiments/provenance_v2/compact_query.py`与`tests/test_compact_query.py`。

**Interfaces:** `CompactQuery(..., top_k, depth, candidate_selector=None).walk(call_id, span, root_key=None, limits=None)`返回聚合根分数、每根代表路径、完整节点连接、原路径总数、缓存与预算记录。

- [ ] 先写共享上游分叉、歧义转交、同调用前文及深度截断测试，与旧FullQuery逐条枚举比较。
- [ ] 实现局部分数缓存和按`(调用, 区间, 剩余深度)`的汇总，保留每条转交的原权重。
- [ ] 用`abs(error)<1e-10`核对原文分数、精确核对路径数和返回排序；测试触及预算必须未完成。
- [ ] 运行：`python -m unittest provenance_v2.tests.test_compact_query`（PYTHONPATH含experiments）；预计全部通过。

### Task 2: 固定开发集与显式配置

**Files:** 新建`experiments/flow_query_dev_v1/config.json`、`run.py`、`README.md`。

**Interfaces:** `run.py freeze --common ... --output ...`只读原cases固定轨迹划分及哈希；`run.py run --common ... --replay ... --protocol ... --output ... --model ...`只运行固定开发目标。

- [ ] 冻结上述3轨迹及所有对应目标，运行其中有完整原文标签的目标；不足题保留状态。
- [ ] 固定4配置及三次CPU计时，轮换执行顺序，每次新建引擎；同一深度16。
- [ ] 原版未缓存输出与原v1排名按目标核对；缓存作者版与旧枚举的原文分数及路径计数核对。
- [ ] 归并到既有原文身份后按原规则排序；调用已有`genmem_merged_v1.metrics.evaluate`计算同预算2/5/10指标。
- [ ] 每目标保存完整查询图、代表路径、时间、独立节点、状态数、路径数、缓存命中及未完成原因。

### Task 3: CPU运行、回传和归档

**Files:** 新回传`MemoryFlow_执行回传_20261112_02`；仓库开发报告、小证据、STATUS和EXPERIMENT_INDEX。

- [ ] 在243 CPU运行固定开发集，不扫92题选参数；不启动模型服务。
- [ ] 给原版/新版找齐率、P/R/F1、返回数和成本；分1段/2段/≥3段，保留逐题胜平负及未改善例。
- [ ] 沿教练案例定位任期中间句和原文进入/丢失的位置；宽度和深度均从配置记录读取。
- [ ] 提交代码、配置与小证据，push并核对远端提交；完整原日志、标签与大图保留外部目录。

执行方式：按用户已授权范围在本会话直接执行，不另开执行选择或审批。
