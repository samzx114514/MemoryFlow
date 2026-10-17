# MemoryFlow：从哪里看代码、数据和结果

核查日期：2026-10-17。建议只记两个入口：**本机 Git 仓库**与 **243 的 memoryflow 主目录**。

## 一、本机与服务器各负责什么

| 位置 | 职责 | 日常是否需要进入 |
|---|---|---|
| `F:/CodexProject/MemoryFlow-research` | 私有 Git 仓库的本地副本：研究说明、方法代码、测试、轻量结果 | 是，讨论与查代码从这里开始 |
| 243：`/data2/pkuiti/songzhengxing_intern/memoryflow` | 服务器统一工作入口：方法代码、运行任务、实验产物、轨迹样例 | 是，实际实验从这里开始 |
| 243：`/data2/pkuiti/songzhengxing_intern/SP1.0` | 第三方 SP1 系统、专用 Python 环境、私有 API 配置；只负责产生真实轨迹 | 修改生成系统或配置时进入 |
| 243：`/data2/pkuiti/songzhengxing_intern/codex_files/smallest_experiment` | 老实验的原始运行记录、权重、数据和环境 | 复现老结果时进入，不在这里新增主线任务 |
| `F:/CodexProject/MemoryFlow` | 早期本机资料和上下文 | 历史参考，不是当前 Git 仓库 |
| 245：`/home/qiuzh/work/StackPlanner_tender_audit_backend_20261005` | 师兄的 DCC/CUAD 系统及既有轨迹 | 目前只读；不在这里修改服务 |

243 的 `~/work` 实际指向 `/data2/pkuiti/songzhengxing_intern`。截图里看到的 `work/memoryflow` 就是上面的统一入口，不是另一份项目。

本机 Git 仓库和 243 工作区不是自动同步的同一目录。Git 主要沉淀代码、说明和小结果；服务器保留大数据、模型、环境和原始轨迹。

## 二、243 现在的主目录

```text
memoryflow/
├── src/memoryflow/                  以前的 MemoryFlow 方法实现
├── scripts/                        实验启动与数据处理脚本
│   ├── sp1_20261016/                本轮 SP1 运行脚本及启动记录（保留原版）
│   └── trace_review_v1/             本轮信息流提取程序
├── runs/sp1/                       本轮 SP1 原始运行产物
│   ├── 20261016_health/
│   ├── 20261016_smoke_budget_stop/  第一轮预算不足的短任务
│   ├── 20261016_smoke_complete/     正常完成的短任务
│   └── 20261016_insurance_budget_stop/  保险任务：未完成，不是正式报告
├── reports/flow_review_20261017/    给师兄看的样例与结构化信息流
├── tasks/20261016_flow_review/     本次整理的路径映射、核对记录
└── artifacts/
    ├── legacy/                    指向旧实验根目录，不复制大文件
    ├── raw/flow_review_20261017/    245 单个开发集案例的脱敏导出
    └── third_party/yifeng_20261016/ 艺峰代码解压副本
```

本会话原来散落在 `work/` 根下的六个目录已移动到上述位置，158 个文件逐文件 SHA256 相同，未删除数据。原始运行记录内的旧绝对路径保留不改；新旧对应查 `tasks/20261016_flow_review/path_migration.json`。

根目录的 `model`、`data`、`cache`、历史 ZIP 和用户已有目录没有移动。另一个 `smallest_experiment/remote_bundle` 经本次查看为空目录，但也没有删除。

## 三、LC-Sent-15 的方法代码在哪里

LC-Sent-15 是“每个待溯源句子在 15 个候选来源中选一个”的 LongCite 引用代理任务，不是实际多 Agent 因果信息流测试。

本机统一前缀：`F:/CodexProject/MemoryFlow-research/workspace/`。

243 统一前缀：`/data2/pkuiti/songzhengxing_intern/memoryflow/`。

下面的相对路径适用于这两个前缀：

| 方法 | 含义 | 实现 | 运行入口 |
|---|---|---|---|
| BM25 | 用词面匹配给来源排序 | `src/memoryflow/lc_sent15_bm25.py` | `scripts/run_lc_sent15_bm25_gate.py` |
| Qwen cosine | 冻结 Qwen，平均池化文本表示，再比较余弦相似度 | `src/memoryflow/lc_sent15_fmean.py` | `scripts/run_lc_sent15_qwen_fmean.py` |
| R-SYM | 只学习两段文本的对称关系，不能表达方向 | `src/memoryflow/source_prior_relational.py` 中 `SymmetricRelation`；协议辅助在 `lc_sent15_q1_rsym.py` | `scripts/run_lc_sent15_q1c_rsym_convergence.py`；早期转移入口 `run_lc_sent15_q1_rsym_transfer.py` |
| D-Full-64 / Loss-Head 比较 | 同时保留 Target、Source 各自向量及交互特征的关系头 | `src/memoryflow/lc_sent15_q2.py` 中 `DirectionalFull64` | `scripts/run_lc_sent15_q2_head_loss.py` |
| 固定 Fusion | 在 Train 折外预测选择权重，再组合 D-Full 与 BM25 | `src/memoryflow/lc_sent15_q3.py` | `scripts/run_lc_sent15_q3_oof_fusion.py` |

本次核对的 BM25、F_mean、Q1、Q2、Q3 实现及 Q1C 入口，243 主目录与旧目录版本 SHA256 相同。未全面审计所有历史文件。

**数据构建代码**在本机 `local_data/lc_sent15_v1/build_v1/code/`；方法训练、评分代码在 `workspace/`，不要把两者混淆。

**原始结果、checkpoint 和缓存**通过 243 的以下入口查看：

```text
memoryflow/artifacts/legacy/workspace/results/
  lc_sent15_v1_bm25_gate_v1/
  lc_sent15_v1_qwen_fmean_cosine_v1/
  lc_sent15_v1_q1c_rsym_convergence_v1/
  lc_sent15_v1_q2_head_loss_v1/
  lc_sent15_v1_q3_oof_fusion_v1/
```

本机只看结论时读 `docs/RESULTS.md`、`docs/RESEARCH_BRIEF.md` 和 `evidence/server/`，不用打开原始缓存。旧 c8 与 LC-Sent-15、Ranking checkpoint 与 Edge checkpoint 不可混用，Reserve/Blind 继续封存。

## 四、新产物怎么放

新 SP1 运行只放 `memoryflow/runs/sp1/`；提取代码放 `memoryflow/scripts/trace_review_v1/`；给人阅读的成果放 `memoryflow/reports/`。不得继续向 `~/work` 根目录新增随机后缀实验目录。

本机信息流样例放 `artifacts/raw/flow_review_20261017/`，已被 Git 忽略，避免合同原文、模型输入输出随代码提交。可分享给获授权的组内师兄，但不直接公开发布。

代码和文档提交到 Git，不代表大模型、运行环境和原始轨迹也在 Git；它们用路径、校验和、运行说明关联。
