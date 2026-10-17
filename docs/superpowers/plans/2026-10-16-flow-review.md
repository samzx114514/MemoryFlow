# 信息流样例与目录整理 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. 本会话未提供这些技能，按用户授权内联执行，不创建子代理。

**Goal:** 核实保险运行结果，收拢本会话创建的 243 文件，交付可供师兄讨论的真实信息流样例和目录地图。

**Architecture:** 243 统一使用现有 memoryflow 根目录；只移动本会话创建的六个目录，校验文件内容不变。245 只读导出一个已知 dev 案例。离线提取实际调用、可见文本和显式引用，不推断 Gold。

**Tech Stack:** Python 标准库、SSH/SCP、JSON、Markdown；无模型调用或 GPU。

## Global Constraints

- 不重跑保险任务，不改变实验方法、候选集或标签。
- 原始日志不入 Git；本地存入已忽略的 `artifacts/raw/flow_review_20261017`。
- 实际输入可见不等于语义支持；显式引用不等于因果归因。
- 移动前确认运行结束，移动后逐文件 SHA256 相同；保存路径映射，不留散落的旧目录链接。
- 245 不修改任何服务、代码和原始文件。

### Task 1: 目录整理

- [x] `experiments/trace_review_v1/organize.py`：六个目录迁移完成，158 个文件内容校验一致。
- [x] 后续 SP1 runner 输出改为 `memoryflow/runs/sp1/`，不改变既有运行记录；新版未执行，预算异常限制见运行器 README。

### Task 2: 离线提取

- [x] `extract.py`：三组轨迹提取完成，输出 `flow.json`、可读样例和来源清单。
- [x] `test_extract.py`：7 项测试通过；覆盖文本可见性、缺失输出和节点/边完整性。
- [x] 两个完整案例提供可核对摘录，保险任务保持部分轨迹。两例 Reporter 同时看到原文与 Summary，不能解释为单一路径；语义边待人工确认。

### Task 3: 交付与索引

- [x] 输出 243 和本机可读的样例包，给出准确的失败边界和提取局限。
- [x] `docs/WORKSPACE_MAP.md`：解释服务器、本地 Git、方法实现与历史结果的关系。
- [x] 更新 STATUS 与实验索引；轻量代码/文档单独提交，日志、合同原文、模型输入输出和凭据不入 Git。

2026-10-17 收尾核查：7 项单元测试通过；服务器重新提取三例与已交付 JSON 完全一致；158 个迁移文件重新核对一致；保险运行仍为 BUDGET_STOP，没有存活的本轮运行器进程。
