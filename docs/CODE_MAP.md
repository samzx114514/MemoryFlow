# MemoryFlow 代码地图

2026-10-22。本次按“当前继续开发、冻结复用、历史追溯”整理，不以某条路线分数高低决定删代码。128 个历史文件仅移动位置，算法和实验结果不变。

## 现在从哪里开始

```text
experiments/                   当前工作入口，另保留一个明确暂停的 DCC 分支
  sp1_runtime_v1/              采集真实模型、工具调用
  trace_review_v1/             日志 → 来源、调用、Summary、报告及可见性
  baseline_adapters_v1/        CLM、艺峰方法的输入适配与推理
  lc_sent15_external_v1/       旧 15 选 1 Dev 补测入口、CLM/艺峰分数及复算
  dcc_diagnostic_v0/           暂停：离线诊断校准，不是当前报告测试集
legacy/
  workspace/                  冻结方法实现、旧训练与审计脚本
  local_data/                 旧数据准备、LongCite 构建与测试
evidence/                     已有实验的轻量证据，不是开发目录
docs/                         科研结论、状态、代码与服务器位置索引
data/、artifacts/、references/ 外部数据、权重、第三方材料的说明
```

Git 保存代码和小结果；原始轨迹、模型、缓存和完整数据留在服务器或忽略目录。本次没有移动 243 的目录，服务器位置仍查 [WORKSPACE_MAP](WORKSPACE_MAP.md)。

## 当前还值得继续开发的代码

| 入口 | 实际作用 | 目前缺什么 |
|---|---|---|
| [SP1 runner](../experiments/sp1_runtime_v1/runner.py) | 记录模型输入输出、HTTP/搜索返回及工作流事件 | 长任务预算异常传播尚未修复；它是采集包装，不是 SP1 系统本身 |
| [trace extract](../experiments/trace_review_v1/extract.py) | `sp1`、`dcc` 读取运行记录，`add_visibility` 核查文本包含关系，`write_case` 导出图和说明 | 主入口仍固定三个展示案例；不能当作通用标注器或语义 Gold 生成器 |
| [baseline adapters](../experiments/baseline_adapters_v1/adapters.py) | 保留候选 ID、构造 CLM 请求及艺峰生成输入 | 需要统一目标单元、候选范围和多来源评价协议 |
| [local model runner](../experiments/baseline_adapters_v1/run_local_models.py) | 加载本地权重，运行 CLM 排序或艺峰生成归因 | 两例 smoke 已完成；新真实轨迹多来源评价仍待标注 |
| [LC-Sent-15 补测](../experiments/lc_sent15_external_v1/evaluate.py) | 在固定 Dev 上补跑 CLM 与艺峰回放；复用旧基线数字 | 已完成各 228 条；不是新的真实 Agent benchmark |
| [来源路径/森林](../experiments/source_path_v1/query.py) | 递归查询 v2 来源路径；`build_forest.py` 从 calls 恢复主/子会话树 | 原生日志缺 session/委派 id；0 branches 不是“无分支”的证明 |
| [任务级分析队列](../experiments/task_timing_v1/analysis_queue.py) | E0/E1/E2 日志回放，记录分析等待/积压/答案可用时间 | 分析耗时是显式输入假设；不是在线流水线 |
| [分支 packing 布局](../experiments/branch_packing_v1/layout.py) | 共享前缀 + 分支 target 的 4-D mask/position/target-row 检查 | 尚未接入 7B 前向或 D/P 性能对照 |

CLM 使用作者发布的投影头和 Qwen3-8B，本项目未额外训练；现有编码后端与作者 vLLM 后端的数值等价性未测。艺峰方法固定 Qwen2.5-7B 的 `(19,15)` 头，解释其自己生成的文本，不能读取原 SP API 模型的注意力。MLP 是以前在 LongCite 上训练的评分器，还需接到新的细粒度数据上。

LC-Sent-15 代理任务的统一候选补测已完成；真实 SP1 的统一 benchmark、在线信息流矩阵维护器和多方法比较仍待粒度与人工核查数据确定。艺峰目标回放的具体设置见 [补测说明](../experiments/lc_sent15_external_v1/README.md)。

## 冻结复用：不要重新抄一份 MLP

以下文件都在 `legacy/workspace/`。目录名表示它们属于历史实验，不代表这些方法不能继续使用。

| 要复用什么 | 原始实现 | 依赖与使用边界 |
|---|---|---|
| R-SYM | [source_prior_relational.py](../legacy/workspace/src/memoryflow/source_prior_relational.py) 的 `SymmetricRelation` / `symmetric_features` | torch；配原训练 checkpoint 与特征规范，不重新选头或训练 |
| D-Full-64 | [lc_sent15_q2.py](../legacy/workspace/src/memoryflow/lc_sent15_q2.py) 的 `DirectionalFull64` | 依赖 `directional_scorer.pair_features` 和 R-SYM 模块，暂不拆散 |
| BM25 | [lc_sent15_bm25.py](../legacy/workspace/src/memoryflow/lc_sent15_bm25.py) 的 `GroupBM25` | 固定分词与同分规则；新数据需要独立输入适配 |
| Qwen 表示 | [lc_sent15_fmean.py](../legacy/workspace/src/memoryflow/lc_sent15_fmean.py)、[提取入口](../legacy/workspace/scripts/run_lc_sent15_qwen_fmean.py) | 主模型、池化和数值精度必须与评分头一致 |
| 固定 Fusion | [lc_sent15_q3.py](../legacy/workspace/src/memoryflow/lc_sent15_q3.py) | 历史 0.65/0.35 权重；不在小测试集上重新调参 |
| LC-Sent-15 数据构建 | [构建代码](../legacy/local_data/lc_sent15_v1/build_v1/code/) | 仅复现旧代理任务需要；不是 SP1 真实轨迹构建器 |

两个历史树里都有 `memoryflow` 包，部分解析工具名称也相同。它们服务不同实验，不能同时放进 `PYTHONPATH` 或按名字直接合并。以后抽取共用模块时，需要先做行为等价测试；本次保留原依赖，不增加一套兼容包装。

## 不再作为主线开发的部分

- `legacy/workspace/` 的 Anchor、C5、B 系列、Q4A、旧 M6/M7 审计及容量搜索：用于解释历史结论和复现，不继续自动扩展路线。
- `run_memoryflow_summary_transfer_v1.py` 和 `legacy/local_data/sp_natural_v1_raw/`：合成 smoke / 旧日志分析，不能替代新的真实轨迹数据。
- [dcc_diagnostic_v0](../experiments/dcc_diagnostic_v0/README.md)：8 个离线校准案例与确定性检查，保留为暂停支线；不因整理仓库而重启模型实验。
- `trace_review_v1/organize.py`：一次性目录迁移，不能重跑；`fetch_dcc.py` 是固定 245 案例读取器，Python 报告主线不需要它。
- `acquire_head.py`、`acquire_qwen3.py`：权重准备工具，权重已就位时不要重复下载。`run_smoke_243.sh` 是历史运行记录，不是任意新任务的一键命令。

这些文件尚有追溯用途，本次没有认定某个文件可安全永久删除。减少的是日常开发入口的混杂，不是伪造磁盘空间节省。

## 验证和维护

从仓库根目录执行；下列测试不调用模型、API 或 GPU：

```powershell
python -m unittest discover -s experiments/trace_review_v1 -p test_extract.py
python -m unittest discover -s experiments/baseline_adapters_v1 -p test_adapters.py
python -m unittest discover -s experiments/baseline_adapters_v1 -p test_acquire_qwen3.py
python -m unittest discover -s experiments/dcc_diagnostic_v0/tests -p 'test_*.py'
python -m unittest discover -s experiments/source_path_v1/tests -p 'test_*.py'
python -m unittest discover -s experiments/task_timing_v1/tests -p 'test_*.py'
python -m unittest discover -s experiments/branch_packing_v1/tests -p 'test_*.py'
python -m pytest -q legacy/local_data/tests -c legacy/local_data/pyproject.toml
$env:PYTHONPATH = (Resolve-Path legacy/workspace/src).Path
python -m unittest discover -s legacy/workspace/tests -p test_lc_sent15_bm25.py
python -m unittest discover -s legacy/workspace/tests -p test_lc_sent15_fmean.py
```

本机需要 Python 3.10+，local-data 测试另需 pytest。torch 相关测试与完整 GPU 推理仍使用服务器已有环境；本次不为目录整理安装大依赖。验证结果见 [当前状态](STATUS.md)。

同一功能优先修改已有实现并加测试；仅当科学协议变化时建新版本。单次运行只产生配置、结果和日志，不复制一整套代码。历史结果不覆盖，原始数据不进 Git。
