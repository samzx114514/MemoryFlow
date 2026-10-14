# MemoryFlow 假期结束工作汇报准备底稿

> 整理日期：2026-08-31  
> 用途：组会/阶段汇报的事实底座，不等同于最终 PPT 或论文表述。  
> 原则：区分“已经验证的结果”“合理解释”“尚待实验的设想”，不把 LongCite 代理任务或合成数据结果表述为真实多 Agent 信息流成果。

## 一、最核心的阶段结论

这一阶段最重要的成果，不只是把某个指标从低做高，而是逐步澄清了 MemoryFlow 真正要解决的问题以及旧方案失败的原因：

1. 我们验证了“统一 Chunk Anchor + structured mask + packed forward”在工程上可运行，并具有明确的推理效率优势。
2. 实验否定了一个过强假设：仅训练一个共享 Anchor，并直接读取 Anchor-to-Anchor Attention，不能自动得到可靠的语义来源边或真实信息流边。
3. 冻结 Qwen 全文表示后，轻量关系评分器能够显著改善 Chunk 间语义来源恢复；R-SYM 成为经过机制核查的 LongCite 强基线。
4. 更干净的 LC-Sent-15 协议进一步证明，非线性关系建模和词法—语义互补确实有效，但单纯继续刷 LongCite 已不足以支撑项目的核心创新。
5. 合成 Summary transfer 证明了模型链路可以迁移，但也暴露出 BM25 几乎饱和、无 Gold 等问题，因此不能作为真实 Agent provenance 的主证据。
6. 当前主线已经合理转向真实 SP1.0 轨迹：先获得可审计的 Source → Researcher Summary → Reporter 链路，再判断已有方法能否恢复真实执行中的信息流。

一句话概括：

> 我们从一个有吸引力但假设过强的 Anchor-Attention 方案出发，通过数据、指标、优化、表示、关系建模和迁移实验逐层排除错误解释，已经获得可信的 Chunk 语义来源恢复基线；下一步要把“语义匹配”推进到带有真实运行证据、方向和因果验证的多 Agent Memory Flow。

## 二、项目为什么值得做

MemoryFlow 的起点不是再实现一个多 Agent 系统，而是回答一个现有日志很难回答的问题：

> 最终答案或下游 Memory 的每个 Chunk，究竟实际使用了哪些上游 Memory Chunk？

普通日志通常只能保留 Agent/Step 级通信，例如 `Researcher → Writer → Reporter`，但不能定位 Writer 的某一句结论究竟来自 Researcher 的哪段 Observation。这个缺口直接影响三类应用：

- 引用生成与核查：某个结论应该引用哪段证据，已有引用是否得到真实支撑；
- 错误归因：最终输出出错时，错误最早来自哪个 Agent、步骤和 Memory Chunk；
- Memory 管理：上下文变长后，哪些内容真正被后续使用，哪些只是被看见。

项目需要严格区分三层关系：

1. **Semantic Support**：Source 在语义上能否支持 Target；
2. **Observed Use**：本次运行中 Target Agent 是否实际读取或引用 Source；
3. **Causal Influence**：删除或替换 Source 后，Target 是否发生相应变化。

LongCite 主要提供第一层的代理监督；真实 SP 轨迹和后续反事实实验才可能覆盖第二、第三层。

## 三、阶段推进与路线转折

| 阶段 | 当时的问题 | 完成的工作 | 得到的判断 | 为什么进入下一步 |
|---|---|---|---|---|
| 1. 问题与方法契约 | Anchor 到底是什么，Attention 如何读出边 | 固定 Chunk、Anchor、mask、packed 与评测定义；审计实现 | Anchor 是程序插入的共享软向量，不是模型生成的新 token；当前训练不是 SFT | 先消除方法描述和实现之间的歧义 |
| 2. LongCite 代理实验 | Anchor 是否含有来源恢复信号 | 建立 Ranking、Edge、随机基线和候选规模评测 | Anchor 优于 Frozen EOS/普通 Attention，但明显弱于 BM25，且候选规模增大时退化 | 需要区分“有信号”和“可靠边” |
| 3. 7B 扩模与优化校准 | 是否只是 1.5B 容量不足 | 完成 7B 对照、学习率/漂移审计、C5D/C5E/C5F 校准 | 7B 提升了原生 mean-pool 表示，却没有改善 Anchor；扩模不是当前解法 | 瓶颈更可能在 Anchor 压缩、监督和 Attention 读出 |
| 4. 冻结表示与关系评分 | Qwen 是否已有足够语义信息 | 缓存 `F_mean`，比较 Linear/MLP、对称/非对称评分器 | R-SYM 大幅超过旧 Anchor，说明 Qwen 表示本身可用 | 必须核查是否存在泄漏、位置捷径或 Source 先验 |
| 5. 机制和鲁棒性闭环 | 高分是否可信 | Source-only、Target 置乱、label/pair permutation、OOF、困难子集、三种子与 bootstrap | R-SYM 确实依赖 Target–Source 配对；但仍是对称语义匹配器 | 需要更干净数据和真实 Agent 场景验证 |
| 6. LC-Sent-15 | 原 LongCite 协议是否过度依赖既有数据构造 | 从官方固定版本重建非 Blind、同文档 15 候选协议，完成 BM25/Qwen/Head/Loss/Fusion | 非线性关系建模有效，D-Full 与融合更强；但 LongCite 仍是引用代理任务 | 继续刷代理任务的边际价值下降 |
| 7. Summary transfer | LongCite 方法是否能迁移到报告生成链路 | 完成合成 Track A/B | Track A 词面重合过强；Track B 无 Gold；只能做 smoke test | 必须获得系统自然生成的真实轨迹 |
| 8. SP1.0 真实轨迹 | 如何得到真实 Source → Summary → Reporter 数据 | 完成 SP1 仓库部署预检和 trace 可恢复性审计 | 输入身份已固定；环境/配置和结构化 exporter 尚未完成 | 下一步先做单 Query Schema Gate，而非直接跑十个 Query |

## 四、最重要的量化证据

### 4.1 旧 Anchor：证明“有信号”，也证明“不够可靠”

校准后的 7B Anchor 最佳 Dev checkpoint C4：

| 指标 | 数值 |
|---|---:|
| nDCG@5 | 0.581699 |
| MRR | 0.576958 |
| AUPRC | 0.335071 |

需要同时报告的解释：

- 训练 Anchor 相比 Frozen EOS 和普通 Token Attention 有改善；
- packed 推理相对 sequential pairwise 可达约 6.40×–8.25×，相对 batched pairwise 约 2.02×–3.28×；
- 但 packed 与 pairwise 的排序并不等价；
- Edge F1 接近 predict-all-positive，且当前数据不支持原生 no-source 判断；
- 候选数从 8 增长到 16/32 时性能明显下降，暴露 softmax 竞争和 Target 表示漂移。

因此旧 Anchor 的合理定位是：白盒结构和效率基线，而不是已经成功的信息流恢复器。

### 4.2 R-SYM：把问题从 Attention 读出转成可核查的关系学习

LongCite Dev 的代表性结果：

| 方法 | Ranking MRR | Edge AUPRC | 说明 |
|---|---:|---:|---|
| 旧 Anchor C4 | 0.576958 | 0.335071 | 校准后的共享 Anchor + Attention |
| Qwen `F_mean` cosine | 约 0.5956 | 约 0.3639 | 无关系头 |
| R-SYM | 0.849765 | 0.550182 | Ranking 与 Edge 来自分别训练的 checkpoint |
| 完整 MLP（M6B） | 0.864547 | 0.533784 | 同样为任务分别选择的最佳 checkpoint |

关键机制证据：

- Source-only 明显较弱；
- Target 置乱后，R-SYM Ranking MRR 从约 0.850 降至约 0.490，Edge AUPRC 从约 0.550 降至约 0.332；
- permutation、位置和候选指纹控制未发现能够解释主结果的捷径；
- 在 source-controlled OOF、BM25-hard、prior-challenging、role-switching 子集上仍保持关系信号；
- R-SYM 与完整 MLP 的主要指标差异置信区间均跨 0，因此按“统计持平时优先简单方法”冻结约 91.8 万参数的 R-SYM，而不是约 183.5 万参数的完整 MLP。

这一阶段真正证明的是可信的 Target–Source 语义匹配，不是方向或真实执行 provenance。

### 4.3 LC-Sent-15：更干净的任务与方法竞争

LC-Sent-15-v1 使用官方固定 revision 的 LongCite-45k 原始数据，在非 Blind 条件下构造同文档 15 候选、严格单正例协议。Dev 有 228 个 Target、3,420 个 pair。

| 方法 | Hit@1 | MRR | nDCG@5 |
|---|---:|---:|---:|
| BM25 | 0.6842 | 0.7470 | 0.7433 |
| Qwen `F_mean` cosine | 0.451754 | 0.595358 | 0.619916 |
| R-SYM（收敛闭环） | 0.754386 | 0.827306 | 0.843610 |
| D-Full-64 + listwise CE | 0.780702 | 0.851374 | 0.869965 |
| 固定 OOF Fusion | 0.831871 | 0.885701 | 0.897075 |

这里得到四个值得汇报的判断：

1. 原始 Qwen cosine 很弱，说明强表示不等于强关系判断；
2. Linear-Full 仍弱，非线性交互确有必要；
3. D-Full-64 比 R-SYM 点估计更高，但增益不显著且 Train–Dev gap 更大，因此不能轻率宣布方向性胜利；
4. 词法和语义信号互补，Train OOF 冻结的融合显著优于各组件，但融合本身不是论文创新点。

### 4.4 Synthetic Summary transfer：有迁移信号，但不能充当主证据

Track A 共 137 个唯一文档生成 Summary Target：

| 方法 | Hit@1 |
|---|---:|
| BM25 | 0.9416 |
| 固定 Fusion | 0.8954 |
| R-SYM | 0.7129 |
| D-Full | 0.7032 |
| Qwen cosine | 0.5912 |

BM25 几乎饱和，说明该任务主要奖励直接词面重合。Track B 生成了 10 个多文档 Summary、143 个 Clause 和 4,194 个 Source sentence，但没有 Gold；方法一致率只能用来发现分歧，不能当准确率。

正确结论是：已有管线能够迁移并产出分数，但合成任务不足以验证真实 Agent 信息流。

## 五、这一阶段为什么会多次“转向”

这些转向不是缺少主线，而是由证据触发的假设淘汰：

1. **从 raw Attention 转向训练 Anchor**：冻结模型的天然 Attention 信号不足。
2. **从 1.5B 转向受控 7B**：检验容量是否是瓶颈，而不是默认扩大模型。
3. **从继续扩模转向优化审计**：7B 原生表示更强但 Anchor 更差，且首步更新远大于初始向量。
4. **从 Anchor 调参转向冻结表示关系头**：校准改善有限，说明瓶颈不是单一学习率。
5. **从高分转向机制核查**：小数据上的大幅提升必须排除泄漏、Source 先验和候选位置。
6. **从 LongCite 转向 Summary transfer**：语义引用代理任务无法覆盖 Agent 角色、实际可见性和执行方向。
7. **从合成 Track 转向 SP1.0**：合成 Summary 的标签过于乐观或根本缺失，不能支撑真实 provenance 结论。

这条路线体现了一种比较成熟的研究推进方式：每个阶段只回答一个明确问题，证据不足时降低主张，发现任务不再区分方法时及时换到更接近核心命题的数据。

## 六、除模型指标外，已经积累的能力与产物

### 6.1 数据与评测契约

- 明确区分 Ranking、pairwise Edge 和 none-of-the-above；
- 固定随机基线、分母、tie rule、seed-first 非线性指标聚合和 target-group bootstrap；
- 识别 LongCite citation label 只能称为 Silver；
- 证明原 SP 日志的 workflow/containment edge 不能自动提升为 semantic Gold；
- 重建 LC-Sent-15 的官方 revision、文档隔离、候选协议、checksum 和单/多正例边界。

### 6.2 实验完整性与可复现性

- 每轮记录代码/数据/config/checkpoint SHA、seed、GPU、runtime 和输出路径；
- Dev 负责选择，Reserve/Blind 保持封存；
- checkpoint、optimizer/RNG、预测和 bootstrap 产物采用新目录与原子写入；
- 对 checkpoint binding、seed 聚合、score lineage 和 tie-aware AUROC 做了多轮纠错；
- 建立 dynamic GPU 选择和显式安全余量，不干扰其他进程。

### 6.3 可迁移工程体系

- 完成 10025 → 243 的 create-only、hash-equal-skip、conflict-blocking 迁移；
- 建立 core/resume 两类 portable handoff；
- 第三方仓库、模型、环境、缓存、Blind 和密钥均不进入科学包；
- 将本地协调、SSH 执行和本地数据处理职责拆开，执行者不自行改变研究规则。

这些工作不应在汇报中占据过多页数，但可以作为“研究结果为什么可信、为何能够继续复现”的重要支撑。

## 七、失败和阻塞带来的真实价值

建议在汇报中选择三到四个代表性例子，而不是罗列所有报错：

1. **7B 扩模没有提升 Anchor**：排除了“只要模型更大就能解决”的直觉解释。
2. **M6D bootstrap 多次被一致性门拒绝**：发现 AUROC tie、logit 先平均和 seed-first 聚合等问题，避免错误 CI 进入方法选择。
3. **M6B final score 未绑定 best checkpoint**：重新 rescore 后才得到可信的 R-SYM/M6B 统计比较，说明 checkpoint lineage 比单个高分更重要。
4. **Q4A double final norm 与 CUDA retention**：证明内部层表示实验必须先验证框架输出语义和内存生命周期；该支线因此被限制为辅助探索。
5. **M8 mixed Blind catalog 被主动暂停**：当 Dev 来源无法与 Blind 安全分离时选择不读取，而不是为了完成实验破坏封存协议。
6. **Synthetic Track A/B 的局限被主动承认**：BM25 饱和或无 Gold 时停止优化，防止把容易任务包装成主结果。

可以把这一部分概括为：本阶段不仅产出了分数，还建立了一套能够拒绝错误结果的实验系统。

## 八、当前准确状态

目前不应说“SP1 已部署完成”。准确状态是：

- SP1.0 已在 243 上固定到 `PKU-SIS/Stack-Planner@zb_demo_v11`，commit 为 `c81444fe94fa1cbc300b98231387fa38baff6dea`；
- `all_samples.json` 已固定，SHA256 为 `0dffd2ca7fcb917d9e2db6f190dc840208715f25f40b2d44d695eae521ff9796`；
- 仓库默认日志不足以稳定恢复完整 Source → Summary → Reporter 结构；
- `uv`、repo-local 环境、模型配置和选定搜索后端配置尚未完成；
- 因此真实 Query 尚未运行，当前没有真实 SP1 Source-to-Summary 分数。

暂停在这里是合理的：先复盘、冻结汇报叙事和下一阶段成功标准，能够避免配置完成后再次无边界扩展实验。

## 九、假期后建议的主线

### P0：完成一个真实 Query 的 Schema Gate

目标不是先得到好分数，而是确认数据是否足以定义 benchmark。

成功标准：

- 输入仅为 `all_samples.json` 中一个固定 Query；
- 系统自然产生检索 Source、Researcher observation/Memory Summary 和 Reporter output；
- Source 具有稳定 ID、URL/标题和完整可见文本；
- 每次 Researcher 调用能恢复实际可见的 Source 集；
- Summary 与 Reporter 都具有 run/call/parent identity；
- trace 可解析、引用完整，不包含任何密钥；
- 若字段不足，只增加最小 create-only exporter，再重复该 Query。

### P1：冻结 Schema，运行剩余九个 Query

成功标准：十个 Query 使用同一 commit、配置、trace schema 和执行规则；运行失败、重试和空结果也作为正式事件保存，不人工补写。

### P2：构造真实 Source-to-Summary benchmark

第一版应优先快速给出点估计和分母：

- Random；
- BM25；
- Qwen cosine；
- 冻结 R-SYM；
- 冻结 D-Full；
- 固定 Fusion。

标签规则必须保守：显式 Source ID 优先；单 Source Researcher call 可用唯一输入构成 provenance-by-construction 正例；无法确定唯一来源的多 Source call 单独报告，不强行制造 Gold。

### P3：先看错误，再决定是否改方法

重点区分：

- 词面改写导致 BM25 失败；
- Summary 融合多个 Source；
- Source 被读取但未使用；
- Source 主题相似但不支持具体结论；
- 运行可见性、时间和 Agent 角色决定方向。

只有错误分析表明现有 scorer 缺少方向或运行结构时，才进入角色感知有向模型，而不是预先扩大网络。

### P4：再进入 Summary-to-Reporter 与反事实验证

- 定义 Reporter 句/段落对应的输入 Summary；
- 允许多来源与 no-source；
- 用删除、替换、角色交换、时间逆转区分 Semantic Support、Observed Use 和 Causal Influence；
- 最后才讨论层级 Anchor、结构化 mask 和少量 packed forward 如何统一准确率、忠实性和效率。

## 十、建议的假期结束汇报结构

建议控制在 8–10 页，主线比实验清单更重要。

1. **问题与动机**：为什么 Agent/Step 日志不等于 Chunk 级 Memory Flow。
2. **最初方案**：统一 Anchor、structured mask、packed forward，以及最初的三个关键假设。
3. **旧方法验证结果**：有信号、有速度，但边识别、候选稳定性和 pairwise 等价性不足。
4. **为什么不能只扩模**：7B 原生表示提升而 Anchor 未提升，展示优化与结构瓶颈。
5. **关系建模转折**：冻结 Qwen + R-SYM，展示主要指标和机制核查。
6. **更干净的 LC-Sent-15**：BM25、Qwen、R-SYM、D-Full、Fusion 的方法竞争。
7. **为什么还不能宣布完成 MemoryFlow**：LongCite、对称评分器、合成 Summary 的边界。
8. **真实 SP 路线**：Source → Summary → Reporter benchmark 和单 Query Schema Gate。
9. **下一阶段计划与成功标准**：先分数和错误，再方法；最后方向与因果。
10. **讨论/需要支持**：SP 服务配置、稳定运行资源、Gold 定义和少量高质量反事实标注。

建议只放三张核心结果图：

- 旧 Anchor → R-SYM → LC-Sent-15 方法的性能演进；
- “语义支持—实际使用—因果影响”三层关系示意；
- 项目路线图：LongCite proxy → Synthetic smoke → Real SP trace → Counterfactual faithfulness。

## 十一、三分钟口头汇报骨架

> 这段时间我们围绕 MemoryFlow 做的核心工作，是验证能否从多 Agent 运行中恢复 Chunk 级的信息来源。最初方案是在每个 Chunk 后放统一 Anchor，通过 structured Attention 和一次 packed forward 读出 Target 对 Source 的关系。实验表明，这个方案在工程上可运行，也有明显效率优势，但只训练共享 Anchor 并直接读取 Attention，无法得到可靠的信息流边：性能随候选数增加明显下降，边检测接近全预测为正，而且 7B 扩模并没有解决问题。
>
> 为了判断瓶颈究竟在 Qwen 表示还是关系读出，我们冻结 Qwen 的全文平均表示，训练轻量关系评分器。R-SYM 在 LongCite Dev 上将 Ranking MRR 从旧 Anchor 的约 0.577 提高到约 0.850，Edge AUPRC 从约 0.335 提高到约 0.550。Source-only、Target 置乱、OOF 和困难子集实验说明，它学到的主要是 Target–Source 语义匹配，而不是明显泄漏或候选位置捷径。
>
> 随后我们从官方数据重建了更干净的 LC-Sent-15 协议。R-SYM、方向感知 D-Full 和固定词法—语义融合分别达到约 0.754、0.781 和 0.832 Hit@1，说明非线性关系建模和词法—语义互补是有效的。但这些仍然是引用代理任务，不能证明真实多 Agent 运行中的方向和实际使用关系。合成 Summary 实验也被 BM25 近乎饱和，进一步说明不能把合成结果当主证据。
>
> 所以现在的主线已经转向稳定 SP1.0 真实轨迹。下一步不是继续调 LongCite，而是先跑一个 Query，冻结 Source、Researcher Summary 和 Reporter 的结构化 trace；Schema 足够后再跑十个 Query，比较 BM25、Qwen、R-SYM、D-Full 和 Fusion 的真实 Source-to-Summary 分数。拿到分数和典型错误后，再决定是否引入 Agent、时间、可见性和反事实信息，真正把语义匹配推进成有方向、可验证的 Memory Flow。

## 十二、可能被追问的问题

### 1. 现在最好的模型到底是什么？

在旧 LongCite 协议上，R-SYM 是机制证据最完整、参数更少的冻结主基线；在 LC-Sent-15 Dev 上，固定 OOF Fusion 点估计最高，D-Full-64 是最强单一神经 scorer。但它们都尚未在真实 SP provenance 上得到准确率结论。

### 2. 为什么不继续把 LongCite 做到更高？

因为当前核心不再是证明“文本对可以匹配”，而是证明真实运行中的 Source → Target 方向、实际可见性和因果影响。继续刷代理任务可能提高数字，却不再解决项目最关键的科学缺口。

### 3. Anchor 方法是不是失败了？

不能简单说失败。它验证了统一节点、structured mask 和 packed 效率，也帮助定位了 Attention 读出、Anchor 压缩和候选竞争问题。但它尚未成为可靠边恢复器，后续更适合承担结构路由或效率模块，而不是直接把 Attention 当边。

### 4. R-SYM 有创新吗？

作为句对模型结构，创新性有限；它的价值是成为经过机制核查的强语义基线。最终创新应来自 Chunk-level Agent provenance 问题、结构与方向建模、真实 trace 数据、反事实忠实性和 packed 效率的组合。

### 5. 为什么 SP1 还没有分数？

因为仓库环境和外部服务配置尚未完成，而且默认日志不能稳定恢复完整链路。直接运行十个 Query 会产生难以作为 benchmark 的不可审计输出，因此先做单 Query Schema Gate 是必要的数据质量门。

### 6. 下一阶段最可能遇到什么问题？

多 Source Researcher call 可能没有唯一 Gold；Summary 可能融合、压缩或舍弃 Source；Reporter 可能再次改写。需要分开报告显式 provenance、单 Source construction labels 和未标注多 Source 子集，不能用相似度或工作流关系补造 Gold。

## 十三、汇报措辞边界

推荐表述：

- “恢复 Chunk 间语义来源/支持关系”；
- “真实多 Agent 信息流仍待 SP trace 与反事实验证”；
- “R-SYM 是冻结 Qwen 表示上的轻量关系基线”；
- “Track A/B 是合成 smoke test”；
- “当前尚未获得 SP1 Source-to-Summary 分数”。

避免表述：

- “已经恢复真实多 Agent 信息流”；
- “Attention 就是信息流”；
- “R-SYM 证明了方向性”；
- “方法一致率就是准确率”；
- “LongCite Silver label 是真实 Gold”；
- “SP1 已部署完成”或“十个 Query 已跑完”。

## 十四、主要证据产物索引

- `F:/CodexProject/MemoryFlow/AGENTS.md`：长期研究、安全和汇报规则。
- `F:/CodexProject/MemoryFlow/CURRENT_HANDOFF.md`：截至 2026-08-29 的当前决策状态和完整关键数字。
- `F:/CodexProject/MemoryFlow/PROJECT_CONTEXT.md`：项目目标、方法契约、历史结果与决策记录。
- `F:/CodexProject/MemoryFlow/outputs/ICLR 9 月 Memory Flow_调研补全版.md`：原始问题故事、方法设想、风险与第一轮成功标准。
- `F:/CodexProject/MemoryFlow/outputs/2026-08-13_MemoryFlow周报_方法探索与方向复盘.md`：旧 Anchor、R-SYM、机制核查和创新边界的阶段复盘。
- `F:/CodexProject/MemoryFlow/smallest_experiment/reports/dataset_report.md`：早期 citation-source 数据结构与候选位置审计。
- `F:/CodexProject/MemoryFlow/docs/superpowers/plans/2026-08-05-sp-semantic-edge-recoverability-audit.md`：为什么 workflow/containment edge 不能当 semantic Gold。
- `F:/CodexProject/MemoryFlow/docs/superpowers/plans/2026-08-14-lc-sent15-v1.md`：官方数据、非 Blind 和可复现 LC-Sent-15 构建契约。
- `F:/HuaweiMoveData/Users/25779/Desktop/本地codex回复_243工作.txt`：SP1.0 部署预检、输入 SHA、配置状态和 trace 缺口。

## 十五、下一步汇报制作建议

在真正制作 PPT 前，还需要用户确定三个外部约束：

1. 汇报时长和页数；
2. 听众主要是导师/师兄，还是包含不熟悉项目的同学；
3. 更强调“做了什么工作”，还是更强调“论文故事和下一步决策”。

确定后可从本底稿直接裁剪成：

- 8–10 页组会 PPT；
- 一页书面阶段总结；
- 3 分钟或 8 分钟口头讲稿；
- 面向论文推进的实验路线图。
