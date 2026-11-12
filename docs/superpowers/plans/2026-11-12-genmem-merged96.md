# GenMem 47＋49 原日志多轮评测 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把已确认的旧47题和新49题合成去重清单，按原日志的真实中间输出重建多轮查询，复用现有MemoryFlow及DFAMS、BM25、CLM。

**Architecture:** 先冻结96个历史目标与原标签的对应关系，按sample_id和原文区间去重。中间输出只取原日志；先核对证据和链路，再运行方法。完整回放与森林复用dcc_complete_v1/provenance_v2，不创建另一套溯源引擎。

**Tech Stack:** Python标准库、现有Qwen回放服务、既有基线与固定权重。

## Global Constraints

- 用户2026-11-12明确改为旧47题＋新49题，实验2改用GenMem；实验1/3的DCC批次继续，不改已有结果。
- 不补写中间句，不移除最后一轮已有的原文，不按方法分数挑目标。
- 先按真实材料与中间分析核对链路。存在中间调用不等于已经证明证据依赖；缺少完整请求的可见性单列。
- 严格以47＋49=96个目标为初始清单；重复项只计一次。旧开发题不混入旧47。
- 同方法共享候选、标签与返回预算。P/R/F1、原文覆盖率沿用执行定稿，旧Hit@3/完整证据@5/@10补充保留。
- 原日志、完整标签和大矩阵不进入Git；新版本不覆盖两批旧产物。

### Task 1: 原日志接入与96目标清单

**Files:** `experiments/genmem_merged_v1/intake.py`, `test_intake.py`。
**Interfaces:** 输入旧v3 ZIP、旧评测coverage IDs、新包、新49冻结cases、NAS原始JSONL；输出独立目录的targets.json、traces/*.json、intake.json。

- [x] 从旧55题清单中按已冻结开发划分取47题；新批只取原49题。
- [x] 用NAS byte_offset/byte_length核对旧轨迹，用包内真实raw_runs读取新轨迹；输出仅白名单字段，移除答案/经验总结等评测字段。
- [x] 把两套标注映射到日志内原文区间，逐一检查目标与证据文本、时序；保留旧标签身份和哈希。
- [x] 输出重复项、原文缺口、生成内容标签和候选中间调用；候选中间调用仍需语义核对。
- [x] 验证错区间会报错，未来证据会报错，生成消息不会自动算原始材料，重复目标只计一次。

### Task 2: 原日志链路和完整回放

**Files:** 复用 `experiments/dcc_complete_v1/pipeline.py`、`forest_bridge.py` 和 `experiments/provenance_v2/full_query.py`；只补GenMem日志适配。

- [x] 核对真实中间分析承接的具体事实、被修正的旧结论与干扰项；保存人工可读逐跳原文。
- [x] 完整输出一次建表、目标阶段取行；按实际记录建立转交。日志未保存完整请求时记录重建依据，不虚构看不见原文的条件。
- [x] 先测三模型长度与候选覆盖；超长/缺失保留在清单中，不静默截断。
- [x] 小规模验收同调用两目标复用和真实跨调用展开，再按冻结清单批量运行。

### Task 3: 沿用基线并交付

- [x] 同一候选和目标运行DFAMS三个seed、BM25、CLM官方Qwen3-8B投影头；MemoryFlow 27B/7B/1.5B。
- [x] GPU作业避开正在测量的实验3设备，先并行完成CPU材料和标注。
- [ ] 报原文P/R/F1与覆盖率，以及链长/直接原文可见性的诊断、2–3个原文案例；旧指标单列。
- [x] 每个有实质结果的阶段更新状态、索引和小证据，提交并核对远端分支。

实际结果：用户确认92条作质量分母、4条保留说明；三模型各350调用，六方法完整运行，已交根材料结果和三个逐跳案例。全体语义链长Gold仍未冻结，实际展开步数与消息间隔均不作为真实链长。
