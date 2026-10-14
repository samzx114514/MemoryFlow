# MemoryFlow 周报：LongCite 方法探索、问题复盘与后续方向

> 时间：截至 2026 年 8 月 13 日  
> 本周重点：完成 LongCite 上旧 Anchor 方法的校准与复盘，验证“冻结 Qwen 文本向量 + 轻量关系评分器”路线，分析其有效性、局限和创新空间，并结合 HDT 重新思考 MemoryFlow 的方法设计。  
> 说明：本文将已经完成并核查的实验结果与尚未实验验证的研究设想严格分开。LongCite 结果只能说明引用来源恢复代理任务上的表现，不能直接表述为多 Agent Memory Flow 已经实现。

## 一、本周工作概览

MemoryFlow 最初希望解决的问题是：在一次多 Agent 协作过程中，最终生成的某个 Memory Chunk 或报告段落，究竟使用了哪些上游 Memory Chunk？与只记录“Agent A 给 Agent B 发过消息”相比，我们希望把研究粒度进一步细化到 Chunk 层面，恢复一张有方向的 Source Chunk → Target Chunk 信息流图。

此前我们提出了“统一 Anchor + 结构化 Attention + packed 单次前向”的方法设想：在每个 Chunk 末尾放置 Anchor，让 Anchor 汇聚该 Chunk 的信息，再从 Target Anchor 指向 Source Anchor 的 Attention 中估计依赖关系。这个设想兼顾了结构建模和计算效率，但它是否真的能恢复语义来源，必须通过实验而不是直觉判断。

本周主要完成和厘清了以下工作：

1. 完成 7B Anchor 方法的优化校准和 Dev 选择，旧方法的最佳 Dev 结果为 MRR 约 0.577、AUPRC 约 0.335。
2. 验证 Qwen 原生文本表示，发现最后一层全文平均表示 `F_mean` 明显优于 `<|im_end|>` 位置的上下文表示，直接使用 `F_mean` 余弦匹配也略优于旧 Anchor。
3. 在冻结 Qwen 的前提下，训练轻量文本关系评分器。当前选定的 R-SYM 使用两个文本向量的逐维乘积、绝对差和余弦相似度，Dev MRR 达到约 0.850，AUPRC 达到约 0.550。
4. 完成泄漏、Source-only、Target 置乱、候选位置、困难子集和多随机种子等核查。现有证据支持 R-SYM 学到了真实的 Target–Source 语义匹配，而不只是 Source 热度或候选位置捷径。
5. 比较了约 183.5 万参数的完整 MLP 与约 91.8 万参数的 R-SYM。二者在主要指标上统计持平，因此按照“效果相近时选择更简单方法”的规则，暂时冻结 R-SYM 为 LongCite 阶段的首选方法。
6. 进一步确认：R-SYM 虽然效果好，但结构本身并不新，而且它是对称评分器，只能证明语义来源匹配，不能证明有方向的真实信息流。
7. 调研 HDT 后发现，HDT 的 Anchor+Attention 与我们的旧方法表面相似，但任务、训练方式和 Anchor 的作用存在本质区别。HDT 的经验更适合用于改进“Anchor 如何形成结构化 Chunk 表示”，不能作为“Attention 权重天然等于信息流”的依据。

本周最重要的结论不是简单地“旧方法不行、新方法更好”，而是明确了三个层次：

- 旧 Anchor 方法验证了结构化 packed 方案可以运行，也有一定关系信号和效率优势，但当前表示学习与 Attention 读出不足以支撑可靠边恢复。
- R-SYM 证明了在冻结 Qwen 的条件下，轻量模型可以较好地恢复 Chunk 之间的语义支持关系。
- 真正的 MemoryFlow 还需要进一步区分语义支持、实际使用和因果影响，并引入方向、Agent、时间和运行结构。

## 二、当前研究目标：我们最终想恢复什么？

### 2.1 从 Agent 粒度进一步细化到 Memory Chunk 粒度

传统多 Agent 日志通常能告诉我们：

```text
Researcher Agent → Writer Agent → Reviewer Agent
```

但这种记录只能说明 Agent 或步骤之间存在通信，不能说明 Writer 的某一段具体结论究竟使用了 Researcher 输出中的哪一段内容。

例如，Researcher 输出了三条 Memory：

```text
Memory A：实验准确率从 70% 提高到 80%。
Memory B：训练使用了 4 张 A800。
Memory C：模型采用 AdamW 优化器。
```

Writer 最终写出：

```text
新方法在测试集上取得了 10 个百分点的准确率提升。
```

理想的 MemoryFlow 应恢复：

```text
Memory A → Writer 的该段结论
```

而不是因为 Writer 看见过 A、B、C，就把三条全部连上；也不能仅仅记录 Researcher → Writer 这一条粗粒度边。

### 2.2 “文本相似”“语义支持”和“真实信息流”不是一回事

需要严格区分以下三种关系：

1. **文本或语义相似**：两段文本表达的主题接近。
2. **语义支持**：Source 的内容能够为 Target 的结论提供依据。
3. **真实信息流**：Target 在本次实际运行中确实读取、使用或受到 Source 影响。

例如：

```text
Source A：测试准确率从 70% 提高到 80%。
Source B：另一篇文章也报告了约 10% 的提升。
Target：新方法将准确率提高了 10 个百分点。
```

A 和 B 都可能在语义上支持 Target，但如果本次 Agent 只读取了 A，那么真实运行来源只有 A。进一步，如果删除 A 后 Agent 仍然能从其他上下文生成同样结论，那么 A 是否构成强因果依赖还需要反事实实验判断。

因此，MemoryFlow 的最终目标不能只是“找到最相似文本”，而应逐步回答：

- 哪些 Source 在语义上支持 Target？
- Target Agent 实际读取或引用了哪些 Source？
- 删除或替换某个 Source 后，Target 是否发生变化？

## 三、LongCite 验证集及其作用

### 3.1 LongCite Dev 是什么？

LongCite 原本提供长答案中的陈述及其引用来源。我们将它转换成一个多候选来源恢复任务：给定一段 Target 陈述和若干候选 Source，要求模型把正确引用来源排在前面，并判断每个 Target–Source 对是否存在支持关系。

目前的数据划分约为：

| 划分 | Target 数量 | 当前用途 |
|---|---:|---|
| Train | 854 | 训练 Anchor 或轻量关系评分器 |
| Dev | 228 | 比较方法、选超参数、选 checkpoint、做机制核查 |
| Blind | 218 | 方法完全冻结后的最终测试 |

当前 Dev 中每个 Target 有 8 个候选 Source，共 1,824 个 Target–Source 对，其中 496 个为正例、1,328 个为负例。LongCite 的引用标签是自动构造的 Silver 标签，不应称为人工 Gold。

### 3.2 我们是否使用了训练集？

使用了。R-SYM 并不是直接在 Dev 上拟合：

1. 在 Train 的 854 个 Target 组上训练轻量 MLP；
2. 在 Dev 的 228 个 Target 上选择结构、学习率和 checkpoint；
3. 使用 Dev 做置乱、Source-only、困难子集和统计显著性等核查；
4. 新方法尚未使用 Blind 进行选择。

需要特别说明：更早期的旧 Anchor 实验曾按当时协议评估过 Blind，并留下了可用但带有流程偏差说明的历史结果；本周新开发的 M6/M7 方法没有读取 Blind 文本、标签或指标。本文所说“保留 Blind”，指不再用历史 Blind 反馈指导新方法选择，并为最终冻结方案保留一次规范评估。

### 3.3 为什么当前不急着反复查看 Blind？

Blind 不会在物理上“用一次就消失”，但每查看一次结果，就会给后续方法修改提供信息。如果看到 Blind 不好后修改网络、再看 Blind、再改学习率，那么 Blind 实际上就变成了另一个 Dev，最终结果不再是无偏测试。

因此，正确原则不是“等分数足够高再测”，而是：

> 在方法、超参数、停止规则和主要指标冻结以后，再做一次正式 Blind 评估；评估以后不能继续根据 Blind 调参。

目前还有一个更实际的原因：LongCite 只是引用来源恢复代理任务，而论文最终目标是 SP 等真实多 Agent 场景。如果 LongCite 已经完成“筛选可行方法”的作用，就没有必要在它上面无限刷 Dev，也不必在主研究问题尚未对齐时急着消耗正式 Blind 决策。

### 3.4 MRR 和 AUPRC 分别在测什么？

MRR 衡量第一个正确来源排得是否靠前。

例如三个 Target 的第一个正确来源分别排在第 1、2、4 名，则：

```text
MRR = (1/1 + 1/2 + 1/4) / 3 = 0.583
```

所以 MRR=0.577 不表示“57.7% 准确率”，而是一个综合排名指标，越接近 1 越好。

AUPRC 衡量模型在不同阈值下区分正边和负边的整体能力。它不是某一个阈值下的 Precision，也不是 Accuracy。因为引用边远少于非引用边，AUPRC 比普通准确率更有意义。当前 Dev 正例比例约为 27.2%，因此旧 Anchor 的 AUPRC 约 0.335 虽然高于无信息水平，但正负边区分能力仍然较弱。

还要注意，排名、边识别和“所有候选都不正确”是三个不同任务：

- 排名：至少把一个正确 Source 排在前面；
- 边识别：独立判断每个 Target–Source 是否为边；
- None-of-the-above：允许候选中没有任何正确 Source。

当前 LongCite 候选组至少包含一个正例，因此尚不能原生验证第三种能力。

## 四、旧方法：统一 Anchor + Attention 到底做了什么？

### 4.1 旧方法的真实实现

旧方法没有扩展 Qwen 词表，也没有新建一个 Anchor token ID。它使用 Qwen 已有的 `<|im_end|>` 位置：

1. 程序在每个 Chunk 末尾确定性地设置 Anchor 位置；
2. 取 Qwen 原生 `<|im_end|>` embedding 作为 Anchor 初始值；
3. 冻结 Qwen 的其余参数；
4. 在这些位置注入一个独立、共享、可训练的 Anchor 向量；
5. Source 和 Target 使用相同的 Anchor 参数；
6. 从 Target Anchor 指向 Source Anchor 的 Attention 中构造候选关系分数。

因此，以下说法需要区分：

- “使用了 Qwen 原生 token”：对，使用其位置和 embedding 初始化。
- “Anchor 是程序插入的”：对，模型不会自己生成 Anchor。
- “我们给 Qwen 词表新增了 Anchor token”：不对。
- “不同 Chunk 各有一个永久独立的可训练 Anchor 参数”：不对，所有 Chunk 共用同一个输入 Anchor 参数，但经过上下文编码后的 hidden state 会不同。

更准确的名称是：

> 在原生 `<|im_end|>` 位置注入的共享软 Anchor，并使用 Anchor-to-Anchor Attention 进行候选排名。

### 4.2 旧方法的优点

旧方法并非完全无效：

- 训练后的 Anchor 优于 Frozen EOS 和普通 Token Attention；
- structured mask 和 packed forward 可以运行；
- packed 在既有实验中明显快于逐对顺序和逐对批处理验证；
- 它提供了一个将所有 Chunk 统一为图节点的清晰结构设想。

因此，旧方法的价值主要是验证了结构化、白盒和高效计算方向的可行部分，而不是证明 Attention 已经等于信息流。

## 五、旧方法为什么效果不理想？

旧方法的问题不是一个简单代码 bug，也不能全部归结为“它只会排序”。目前至少存在五个相互独立但会共同影响结果的问题。

### 5.1 一个共享 Anchor 不会自动成为每个 Chunk 的可靠摘要

需要区分输入 Anchor 参数和上下文化后的 Anchor 表示：

- 输入 Anchor 参数：所有 Chunk 共用同一个可训练向量；
- 上下文化 Anchor hidden state：Anchor 读过不同 Chunk 后产生的不同表示。

我们的最初设想是：把 Anchor 放在每个 Chunk 末尾，它经过 Qwen 后就会吸收前文，成为该 Chunk 的语义摘要。这个设想理论上可能成立，但当前损失没有直接要求它做到以下事情：

- 通过 Anchor 重建 Chunk 内容；
- 通过 Anchor 生成 Chunk 摘要；
- 相似 Chunk 的 Anchor 表示接近；
- 不同事实、数字和实体能在 Anchor 中被区分；
- 只读取 Anchor 就能完成下游任务。

当前训练只要求最后的候选排名有所改善。模型可能找到一些更简单的局部模式，而不必真正把完整语义写进 Anchor。

可以把它类比为：

> 给所有学生同一张空白便签，希望他们读完文章后写摘要；但考试只看最后选了哪个选项，从不检查便签上是否真的写了完整摘要。学生可能靠局部关键词做出部分选择，却没有形成可靠摘要。

所以这一点属于“表示学习是否成功”，不是“排名和边识别是否相同”。

### 5.2 Attention 高不天然等于存在引用关系或信息流

Qwen 的 Attention 是为语言建模形成的，可能关注语法、位置、标点、重复内容或下一个 token 所需的局部信息。Attention 权重表示模型计算时的内部关注分配，却不天然说明：

- Source 在语义上支持 Target；
- Target 实际使用了 Source；
- 删除 Source 会改变 Target。

旧方法的核心假设是：只训练一个共享 Anchor，就能让冻结 Qwen 的 Attention 变成可靠的信息流读出器。实验结果表明，这个假设目前过强。

### 5.3 候选之间存在 softmax 竞争，分数不够稳定

旧方法把多个候选放在同一个 packed 序列中进行比较。加入新的候选后，Attention 的归一化和 Target Anchor 的上下文都会发生变化。

例如 Source A 本身没有变化：

```text
候选组 1：A + 7 个明显无关候选
候选组 2：A + 7 个高度相关候选
```

A 在候选组 1 中可能得到很高概率，在候选组 2 中却明显下降。旧方法在候选数从 8 增加到 16、32 时显著退化，并观察到了 Target Anchor 表示漂移，说明它没有形成足够稳定、独立的 Source–Target 关系分数。

这一点是“候选竞争和表示受上下文干扰”，也不完全等于相对排序问题。

### 5.4 原训练目标主要是相对排名，不是可靠的稀疏边识别

旧目标主要要求：在一组候选中，让正确来源获得更高概率。组内 softmax 总和必须等于 1，因此即使 8 个候选全错，模型也必须选出一个最高者。

例如：

```text
候选 A：不支持 Target
候选 B：不支持 Target
……
候选 H：不支持 Target
```

相对排序器仍会产生 Top-1，但可靠边识别器应回答“全部不是”。

真正的稀疏边识别需要：

- 正负 Target–Source pair 标签；
- no-source 样本；
- 独立二分类或多标签目标；
- 在 Dev 上冻结阈值；
- 概率校准。

因此，第四点确实是在说“相对排序器不等于稀疏边识别器”。

### 5.5 早期 Anchor 优化过猛，出现表示漂移和过拟合

早期 7B 实验中：

- 初始 Anchor 范数约为 0.0105；
- 第一步更新范数约为 0.599，约为初始向量大小的 57 倍；
- Anchor 范数后来增长到约 13.46；
- 最终 Anchor 与初始 EOS embedding 的余弦接近 0；
- Train 明显优于 Dev/Blind。

可以把它理解为：方向盘只需轻微调整，但第一次更新就直接打了几十圈。Anchor 虽然可能记住训练集模式，却迅速偏离了原本较好的 Qwen 初始化。

后续 C5D/C5F 已经通过学习率、漂移约束和停止策略对这个问题进行了校准，最终最佳 C4 的 Anchor 范数约为 3.81，Dev MRR 提高到约 0.577。但校准后仍未追上强基线，说明：

> 早期确实存在优化问题；优化问题改善以后，剩余瓶颈主要来自 Anchor 表示监督和 Attention 读出结构，而不是继续微调一个学习率就能解决。

### 5.6 对旧方法最公允的结论

旧方法基本忠实实现了“共享 Anchor + 结构化 Attention + 单次 packed forward”的设想。真正没有被证明的是两个核心假设：

1. 共享软 Anchor 是否会自动成为可靠的 Chunk 摘要；
2. Anchor-to-Anchor Attention 是否能直接成为语义依赖或真实信息流分数。

因此不应写成“旧方法毫无价值”，也不应继续描述为已经成功的信息流模型。它更适合保留为：

- 白盒 Anchor-Attention 基线；
- packed 高效计算基线；
- 后续 Anchor 表示诊断的起点。

## 六、新方法：冻结 Qwen 文本表示 + 轻量关系评分器

### 6.1 Qwen 全文平均向量是什么？

Qwen 阅读一段文本后，会为每个 token 产生一个包含上下文信息的最后层 hidden state。当前 Qwen2.5-7B 的每个 token 向量为 3,584 维。我们对有效序列位置的最后层向量求平均，得到一个 3,584 维全文表示 `F_mean`。

这不是对 token ID 求平均，也不是简单平均词典中的词义，而是平均已经经过多层 Transformer 上下文化后的表示。

例如：

```text
“新方法显著提高了准确率。”
```

Qwen 会为“新方法”“显著”“提高”“准确率”等位置产生不同的上下文向量；将它们求平均后，得到整段文本的语义表示。

M6A 还比较了 `<|im_end|>` 最终上下文位置的表示 `F_im_end`。实验表明 `F_mean` 更强，因此当前“Qwen 向量”特指全文平均上下文向量，而不是原生 `<|im_end|>` 的固定 embedding。

### 6.2 新方法具体怎样判断关系？

假设 Target 为：

```text
新方法将测试准确率提高了 10 个百分点。
```

三个候选 Source 为：

```text
A：准确率从 70% 提高到了 80%。
B：训练使用了 4 张 A800。
C：BM25 是一种词项匹配方法。
```

第一步，冻结 Qwen 分别生成全文表示：

```text
t, s_A, s_B, s_C
```

第二步，为每个 Target–Source 对构造交互特征：

1. `t ⊙ s`：逐维乘积，用于观察两段文本是否在相同语义方向上同时活跃；
2. `|t - s|`：逐维绝对差，用于观察两段文本在哪些语义方面差异较大；
3. `cos(t, s)`：余弦相似度，用于概括整体语义接近程度。

第三步，小型 MLP 根据这些特征输出一个关系分数。以下数字只是解释流程的示例，不是实验记录：

```text
Source A： 2.4
Source B：-0.7
Source C：-1.2
```

A 因此被排在第一位。

新方法的关键变化是：

> 不再直接把“两个文本像不像”或某个 Attention 数值当成最终关系，而是从两个文本表示的相同与差异中，监督学习“什么样的关系符合当前标签”。

在 LongCite 上，这个标签是引用支持关系；更换训练标签后，同样的结构也可以用于问答匹配、文本蕴含、矛盾识别或 Memory 语义支持。但训练出来的具体参数会带有当前任务分布，不能未经验证就声称直接泛化到所有领域。

### 6.3 为什么 Qwen 冻结后还能训练？

可以把 Qwen 理解成固定的“语义相机”：

1. 先用 Qwen 为所有 Target 和 Source 拍好“语义照片”；
2. 将这些 3,584 维向量保存到磁盘；
3. 训练时不再运行或修改 Qwen，只训练后面的关系裁判。

这样做的优点是：

- 避免在小数据上破坏 Qwen 已有能力；
- 文本向量可预先缓存，后续训练和调参较快；
- 迁移到其他服务器时不必迁移庞大训练状态；
- 能清楚判断提升来自关系评分器，而不是 Qwen 被重新训练。

### 6.4 R-SYM 为什么是约 91.8 万参数？

R-SYM 输入维度为：

```text
3,584（逐维乘积）
+ 3,584（绝对差）
+ 1（余弦）
= 7,169
```

它先映射到 128 个隐藏节点，再输出 1 个分数：

```text
7,169 × 128 + 128 + 128 × 1 + 1 = 917,889
```

因此可训练参数约为 91.8 万。整个系统仍然依赖 7B Qwen，但 Qwen 的数十亿参数被冻结；91.8 万指实际会被优化器更新的关系评分器参数。

### 6.5 完整 MLP 为什么约为 183.5 万参数？

完整 MLP 额外直接输入 Target 和 Source 自己的向量：

```text
[t, s, |t-s|, t⊙s, cosine]
```

输入维度为：

```text
3,584 × 4 + 1 = 14,337
```

因此参数量为：

```text
14,337 × 128 + 128 + 128 × 1 + 1 = 1,835,393
```

它比 R-SYM 多的主要是原始 `t` 和 `s`。因为它们占据不同位置，完整 MLP 理论上可以区分 Target 和 Source 的角色，而 R-SYM 的三类特征在交换两者后不变。

但是现有实验没有发现完整 MLP 在主要指标上显著优于 R-SYM。按照预先确定的“统计持平时优先更简单模型”规则，当前选择参数更少、机制证据更完整的 R-SYM。

## 七、当前实验结果及其解释

### 7.1 Dev 主要结果

以下为当前最适合用于方法比较的 Dev 结果：

| 方法 | Ranking MRR | Edge AUPRC | 解释 |
|---|---:|---:|---|
| 旧 Anchor 最佳 C4 | 0.5770 | 0.3351 | 校准后的共享 Anchor + Attention |
| Qwen `F_mean` 直接余弦 | 0.5956 | 0.3639 | 不训练关系头，只比较全文向量 |
| BM25 | 0.7899 | 暂不冻结单一值 | LongCite 上词面重叠很强；历史 Edge 协议存在不一致，待统一 |
| R-SYM | 约 0.8498 | 约 0.5502 | 当前冻结的简单关系模型 |
| 完整 MLP（M6B 三种子冠军均值） | 约 0.8645 | 约 0.5338 | 与 R-SYM 统计持平 |

R-SYM 相比旧 Anchor 的提升非常明显。但不能只看最终数字，还要排除以下可能：

- Train 与 Dev 是否存在相同 Target 或文本泄漏；
- 某些 Source 是否天然更容易成为正例；
- 正例是否总位于固定候选位置；
- 模型是否只记住 Source，不看 Target；
- 提升是否由单个随机种子偶然造成。

### 7.2 已完成的机制与鲁棒性核查

目前已经得到以下证据：

1. 没有发现 Target、pair、候选指纹或文档组层面的 Train–Dev 泄漏。
2. 只依赖候选位置的模型接近随机水平。
3. 标签或 Source–pair 置乱后，模型效果明显崩溃。
4. Source-only 模型明显较弱：Dev-clean Ranking MRR 约 0.599、Edge AUPRC 约 0.373。
5. R-SYM 在 Source-controlled OOF 下仍保持较强结果，说明提升不只是记住某些高频 Source。
6. Target 置乱后，R-SYM Ranking MRR 从约 0.850 降到约 0.490，Edge AUPRC 从约 0.550 降到约 0.332；而 Source-only 模型基本不变。
7. 在 prior-challenging、BM25-hard 和 role-switching 等困难子集上，R-SYM 均显著优于 Source-only。

Target 置乱可以用一个简单例子理解：

```text
原配对：
Target：准确率提高了 10 个百分点。
Source：准确率从 70% 提高到 80%。

置乱后：
Target：模型使用了 4 张 A800。
Source：准确率从 70% 提高到 80%。
```

如果模型只记得“准确率从70%到80%这条 Source 经常是正例”，换掉 Target 后分数仍然会很高。现在 R-SYM 在 Target 置乱后明显下降，说明它确实依赖两段文本之间的匹配，而不是只看 Source。

这些核查支持：

> R-SYM 学到了可信的 Target–Source 语义关系，而非明显的数据泄漏、固定位置或单纯 Source 先验。

但它仍只能被称为语义关系恢复，尚不能称为有向执行信息流。

### 7.3 为什么选择 R-SYM，而不是分数略高的完整 MLP？

对六个冻结最佳 checkpoint 重新进行绑定核查和 10,000 次 bootstrap 后：

- R-SYM 相对完整 MLP 的 Ranking MRR 差约 -0.0145，置信区间跨 0；
- R-SYM 相对完整 MLP 的 Edge AUPRC 高约 +0.0161，置信区间同样跨 0。

也就是说，两者没有统计显著差异。R-SYM 参数约为完整 MLP 的一半，并且通过了更完整的 Source-controlled、置乱和困难子集机制核查，因此当前选择 R-SYM。

这不是说方向信息不重要，而是说：

> 仅仅把原始 `t`、`s` 向量拼接进一个普通 MLP，并没有在 LongCite 上可靠学出更好的方向性。真正的有向信息流可能需要时间、Agent 角色、Memory 类型和实际运行可见性，而不只是区分向量输入顺序。

### 7.4 BM25 融合的结果

M7 在不重新训练 R-SYM、不访问 Blind 的情况下测试了 BM25 晚期融合。Train OOF 选择的权重在 Dev 上带来小幅点估计提升，但置信区间均跨 0，且在 BM25-hard Edge 子集上出现负向点估计。

因此当前结论是：

- BM25 提供了有价值的词面信号；
- 融合暂未证明稳定优于纯 R-SYM；
- 纯 R-SYM 仍是统一主方法；
- LongCite 上 BM25 很强，也提示当前任务可能含有较强词面线索，不能只靠该数据集论证复杂语义推理能力。

## 八、新方法解决了什么，又没有解决什么？

### 8.1 新方法解决的问题

R-SYM 相比旧方法至少解决了三件事：

1. 不再依赖原始 Attention 数值直接代表关系；
2. 显式监督学习两个文本表示之间什么样的相同和差异对应正边；
3. Qwen 特征可缓存，训练和迁移成本更低，实验更容易复现。

它也证明了一个重要事实：

> Qwen 原有表示中已经包含足够强的语义信息，旧方法表现不佳并不是因为 7B 模型完全不懂文本，而更可能是 Anchor 压缩、Attention 读出和训练任务没有有效利用这些信息。

### 8.2 它为什么可以更换标签应用到其他关系任务？

R-SYM 的网络结构并不知道“引用”这个词。它只接收两个文本向量及它们的差异特征，然后根据标签学习关系。

如果换成不同训练标签，同样结构可以学习：

- 问题与答案是否匹配；
- 前提是否支持结论；
- 两句话是否矛盾；
- Source Memory 是否语义支持 Target Memory。

但“结构通用”不代表“LongCite 上训练的权重自动通用”。不同任务对关系的定义不同，仍需相应数据训练或迁移验证。

### 8.3 当前设计与原始 MemoryFlow 目标存在什么差距？

| 能力 | LongCite R-SYM 当前是否覆盖 |
|---|---|
| Chunk 粒度关系 | 部分覆盖 |
| 语义支持关系 | 覆盖 |
| 多 Agent 身份和角色 | 未覆盖 |
| 实际运行中的读取和使用 | 未覆盖 |
| Source → Target 方向 | 未证明 |
| 删除 Source 后 Target 是否改变 | 未覆盖 |
| 候选中没有正确来源 | 未覆盖 |
| 完整多跳传播链 | 未覆盖 |

尤其是，R-SYM 使用：

```text
t ⊙ s, |t-s|, cosine(t,s)
```

交换 Target 和 Source 后这些特征不变，因此：

```text
score(Target, Source) = score(Source, Target)
```

而真实信息流具有方向：Source 支持 Target，不一定意味着 Target 支持 Source。

因此，当前 R-SYM 最准确的定位是：

> LongCite 阶段选出的 Chunk-level 语义来源恢复器，而不是已经完成的有向多 Agent 信息流模型。

## 九、新方法的创新性判断

### 9.1 它和 CLIP 有多像？

相似之处在于：

- 都使用成对数据；
- 都让正确配对得分高于错误配对；
- Ranking 目标带有对比学习思想。

但 CLIP 联合训练图像编码器和文本编码器，将图像和文本对齐到共享空间，并支持大规模零样本迁移。R-SYM 两边都是文本，共用冻结 Qwen，不重新学习编码空间，而是通过手工定义的交互特征和小型 MLP 输出任务关系分数。

所以更准确的说法是：

> R-SYM 使用了对比式配对训练思想，但不是 CLIP 式跨模态预训练。

### 9.2 单独把 R-SYM 当论文主方法，创新度不足

“预训练句向量 + 逐维乘积/绝对差 + MLP”已有较长研究历史。InferSent、Sentence-BERT 和自然语言推断中的 heuristic matching 都使用过相近结构。因此如果论文主张只是：

```text
Qwen 全文平均向量 + 乘积/绝对差 + MLP
```

方法创新度大概率不足。

R-SYM 更适合承担两个角色：

- 当前最强且经过机制核查的语义关系基线；
- 未来 MemoryFlow 模型中的语义匹配底座或一个组成部分。

真正的创新需要来自任务定义、结构、方向、运行 provenance、反事实忠实性和效率的组合，而不是单层 MLP 本身。

## 十、HDT 为什么也使用 Anchor+Attention，却能够成功？

### 10.1 HDT 与旧 MemoryFlow 表面相似、目标不同

HDT 为长文档中的文档、章节、句子设置 `[DOC]`、`[SEC]`、`[SENT]` 等多层级 Anchor，并通过文档层级构造稀疏 Attention Mask。它的目标是利用已知文档结构高效编码长文档，而不是从 Attention 中发现未知来源边。

| 对比项 | HDT | 旧 MemoryFlow |
|---|---|---|
| 主要目标 | 高效理解层级长文档 | 恢复未知的引用/信息流边 |
| Anchor | 文档、章节、句子多层级 Anchor | 所有 Chunk 共用一种 Anchor 输入 |
| 层级关系 | 由文档结构预先给定 | 语义关系需要模型预测 |
| Mask | 已知父子、兄弟层级 | 规定可见候选，但不知真实语义边 |
| 训练 | 约 1.1 亿参数模型整体预训练 | 冻结 7B Qwen，只训练共享 Anchor |
| 数据规模 | 超过 1,200 万篇结构化长文档 | 854 个 LongCite Train Target 组 |
| 目标函数 | MLM、UL2及下游微调 | 主要为候选组内排名 |
| 是否把 Attention 当 Gold 边 | 否 | 旧方法主要依赖 Attention 读出 |

### 10.2 HDT 的 Anchor 为什么更容易形成有用表示？

HDT 的结构强迫跨层信息经过 Anchor。例如不同句子的信息可能沿下面路径传播：

```text
Token → [SENT] → [SEC] → [SENT] → Token
```

模型做 Masked Language Modeling 时，如果被遮盖词需要其他句子信息，梯度就必须训练 Anchor 和这些跨层通道。Anchor 因此是结构上的信息路由节点，而不只是“希望它顺便学会摘要”的特殊位置。

HDT 还通过 FacetSum 验证：解码器只访问部分 Anchor token 时，仍能获得接近读取全部 token 的摘要效果。这是对 Anchor 表示能力的直接下游验证。

相比之下，我们旧方法中的 Qwen 已经可以通过普通 token 完成大量上下文处理，Anchor 并非信息传播必经路径；损失也没有直接监督 Anchor 保留 Chunk 内容。

### 10.3 HDT 训练的是整个模型，不只是一个 Anchor

HDT 的 embedding、Q/K/V、Attention、FFN 和 Anchor 会共同适应层级结构。我们冻结 Qwen，只允许一个 3,584 维共享 Anchor 调整，却希望它改变整个 Attention 的语义。这两者的可学习能力差距很大。

### 10.4 HDT 对我们的正确启发

HDT 不能证明“Attention 高就是信息流”，但给出了五个有价值的启发：

1. Anchor 应通过结构和目标被迫承担信息汇聚功能；
2. 已知的层级关系可以写入 Mask，未知的语义边不能提前写入；
3. Anchor 的上下文 hidden state可能是有用的 Chunk 表示；
4. 原始 Attention 权重不应直接作为最终边；
5. 信息路由和关系判定应拆成两个模块。

## 十一、后续方法设想：Hierarchical Causal MemoryFlow

> 本节属于本轮讨论形成的研究假设，尚未完成实验，不应在汇报中表述为已实现方法或已有结果。

### 11.1 总体思路

下一阶段最值得探索的方向不是单纯扩大 R-SYM，也不是直接退回 Anchor Attention，而是结合两条路线：

> 使用 HDT 式结构化 Anchor 学习每个 Memory Chunk 的上下文表示，使用显式有方向的关系评分器预测 Source → Target 边，再通过真实执行记录和反事实实验验证边是否忠实。

### 11.2 层级化 Memory Anchor

可以把一次多 Agent 执行组织为：

```text
Run / Case
  └── Agent
       └── Memory Chunk
            └── Text Token
```

为不同结构单位设置 Anchor 位置：

- Run Anchor；
- Agent Anchor；
- Memory Chunk Anchor；
- 可选的报告段落或最终答案 Anchor。

Anchor 输入类型可以共享，但每个位置经过上下文编码后形成不同表示。同时注入少量结构元数据：

- Agent 身份；
- Memory 类型，如 Query、Observation、Outline、Report；
- 时间位置；
- 写入者和读取者；
- Target 生成前 Source 是否真实可见。

这些元数据提供方向和执行结构，但不能直接替代语义 Gold。

### 11.3 结构化 Mask 负责路由，不负责直接判边

Mask 可以规定：

- 普通 token 与所属 Chunk Anchor 交互；
- Chunk Anchor 与所属 Agent Anchor 交互；
- Target 只能访问时间上更早且运行时可见的 Source；
- 未来 Memory 不能反向影响过去；
- 无访问权限的 Source 不进入候选通道。

这里 Mask 的作用是限制合理信息通道，而不是把已知工作流边直接当成 semantic provenance Gold。

### 11.4 融合 Anchor 表示与全文平均表示

未来可以同时保留：

- `h_anchor`：Chunk Anchor 的上下文表示，可能更擅长保留结构、角色和邻域信息；
- `h_mean`：已验证有效的 Qwen 全文平均表示，擅长稳定语义匹配；
- `m`：Agent、时间、Memory 类型等结构特征。

再通过门控模块学习不同场景应依赖哪一种表示：

```text
z_i = Gate(h_anchor, h_mean, m_i)
```

这可以形成一个可检验的研究问题：

> 全文平均表示已经能够完成基本语义匹配，结构化 Anchor 是否能进一步补充方向、角色、上下文和多跳传播信息？

### 11.5 显式有方向的 Source → Target 评分器

使用不同的 Source 和 Target 投影：

```text
q_T = W_T z_T
k_S = W_S z_S
```

然后构造有方向关系分数：

```text
score(S → T) = MLP(q_T, k_S, q_T⊙k_S, q_T-k_S, m_ST)
```

由于 `W_T` 与 `W_S` 不同，交换 Source 和 Target 后分数会变化。模型还可以利用：

- 先后顺序；
- Agent 角色；
- Memory 类型；
- 是否跨 Agent；
- Target 是否有机会读取 Source。

不过，方向性是否真正成立必须通过角色交换、时间逆转和反事实实验验证，不能仅凭结构宣称。

### 11.6 将三种边分开建模

未来最有研究价值的设计，是区分：

1. **Semantic Support**：Source 内容是否能够支持 Target；
2. **Observed Use**：Target Agent 是否实际读取或引用过 Source；
3. **Causal Influence**：删除或替换 Source 后，Target 是否发生显著变化。

例如：

| 场景 | 语义支持 | 实际使用 | 因果影响 |
|---|---:|---:|---:|
| Source 能支持 Target，但 Agent 没读它 | 是 | 否 | 否 |
| Agent 读过 Source，但最后没采用 | 可能 | 是 | 否 |
| 删除 Source 后对应结论消失 | 通常是 | 是 | 是 |

这三层关系共同构成真正的 MemoryFlow，而不是一个普通文本相似图。

### 11.7 可能形成的论文贡献

如果后续证据成立，论文贡献可以组织为：

1. 提出多 Agent Memory 的 Chunk-level 有向 provenance 问题；
2. 提出层级 Anchor 路由与角色感知有向关系评分方法；
3. 建立语义支持、实际使用、因果影响三层数据和评测协议；
4. 通过删除、替换、角色交换和时间逆转验证信息流图忠实性；
5. 证明一次或少量 packed forward 相比逐对 Cross-Encoder/LLM 判断具有更高效率，并保持有竞争力的准确率；
6. 在引用检查、错误定位或 Memory 管理中证明恢复图的下游价值。

真正的创新不是某一层 MLP，而是把多 Agent Memory 的结构化表示、语义边恢复、运行 provenance、因果验证和计算效率统一起来。

## 十二、下一步建议与实验优先级

### 12.1 第一优先级：低成本定位旧 Anchor 的真正瓶颈

最值得先做的诊断是：

> 从旧方法中取出每个 Chunk 最终的 contextual Anchor hidden state，不再读取 Anchor-to-Anchor Attention，而是使用与 R-SYM 相同的小型关系评分器进行判断。

这个实验可以区分三种情况：

1. **Anchor hidden state + MLP 效果好**：说明 Anchor 表示有用，主要问题是 Attention 读出失败；
2. **Anchor hidden state + MLP 仍然差**：说明 Anchor 没有形成可靠 Chunk 表示；
3. **只有全文 `F_mean` 好**：说明语义分散在 token 层，一个共享 Anchor 的压缩能力是主要瓶颈。

这比直接上多 Anchor、LoRA 或大规模结构重做更能定位问题。

### 12.2 第二优先级：构造最小方向性验证

在已有 LongCite 或小规模 SP Pilot 上加入：

- Source/Target 交换；
- 时间逆转；
- 同文本不同 Agent 角色；
- 真实可见与不可见 Source；
- 相同主题但未被读取的困难负例。

比较：

- R-SYM；
- 完整 MLP；
- 不同 Source/Target 投影的有向评分器；
- Anchor hidden state + 有向评分器。

目标不是先追求更高总分，而是证明模型真的能区分 `S→T` 和 `T→S`。

### 12.3 第三优先级：冻结 SP Target、Source 和 Gold 定义

SP 数据构建暂时搁置，但在进入主实验前必须与师兄确认：

- Target 是报告句、报告段落还是下游 Memory Chunk；
- Source 是 Observation、Outline、其他 Agent Memory，还是多种类型；
- “支持”“实际使用”“因果影响”是否分开标注；
- 是否允许一个 Target 有多个 Source；
- 是否包含 no-source Target；
- 新运行能否传播稳定的 retrieval chunk ID 和 citation ID；
- 数据是否按 Case 划分，避免同一 Case 内容跨 Train/Dev/Test 泄漏。

现有 SP 日志适合作为候选池和工作流材料，但 workflow/containment 边不能直接作为语义 Gold，无法解析的引用编号也不能自动提升为 Gold。

### 12.4 第四优先级：小规模反事实 Pilot

选择少量可重复运行的 Case，对候选 Source 进行：

- 删除；
- 替换为相似但错误的文本；
- 替换数字、实体或结论方向；
- 屏蔽 Target 对 Source 的访问；
- 保留文本但改变其 Agent/时间来源。

观察 Target 内容、最终报告和预测边是否发生合理变化。反事实实验成本较高，不适合一开始全量运行，但可以作为小规模高质量参考。

### 12.5 Blind 与 LongCite 的后续处理

- R-SYM 已完成 LongCite Dev 方法选择，当前应保持冻结；
- 不继续为提高 LongCite Dev 分数无限扩展方法；
- 主线先验证 SP 对齐和方向/运行 provenance；
- 如果论文最终正式纳入 LongCite，再使用完全冻结的版本做一次 Blind 评估；
- Blind 之后不再根据其结果回头调参。

## 十三、目前的不足与待讨论问题

1. LongCite 是引用来源代理任务，词面线索较强，不能独立证明复杂语义推理或多 Agent provenance。
2. 当前 R-SYM 为对称模型，不具备已验证方向性。
3. LongCite 不包含原生 no-source 样本，不能验证“全部候选均不正确”。
4. 现有 SP 日志没有自动可恢复的 Observation → Report Paragraph 语义 Gold。
5. 旧 Anchor 的 contextual hidden state尚未与 `F_mean` 在相同关系头下公平比较。
6. HDT 能证明层级 Anchor 可作为结构化信息路由和压缩节点，但不能证明 Attention 权重等于真实信息流。
7. R-SYM 的网络结构创新不足，必须把它定位为强基线或组成模块。
8. 真正的论文贡献需要同时覆盖方向、运行证据、因果忠实性和下游价值，不能只报告 LongCite MRR/AUPRC。
9. BM25 历史 Edge AUPRC 存在评分协议不一致，正式周报或论文表格中应统一数据和 score lineage 后再给出单一数值。
10. 当前时间紧张，需要通过最小诊断逐步淘汰不成立的假设，避免同时启动多 Anchor、LoRA、HDT 全量预训练和大规模 SP 标注。

## 十四、本周结论

本周工作完成了从“围绕旧 Anchor 继续调参”到“基于证据进行方法选择和研究问题重构”的关键转变。

旧 Anchor 方法的思想仍然有价值：它提供了统一 Chunk 节点、结构化 Mask 和 packed 高效前向的框架。但实验表明，单个共享软 Anchor 在缺乏直接表示监督的情况下，无法保证形成可靠 Chunk 摘要；原始 Attention 也不能直接当作引用或信息流边。即使完成学习率和漂移校准，旧方法仍明显低于强基线。

新 R-SYM 方法利用冻结 Qwen 的全文平均语义表示，再从两个表示的乘积、差异和余弦中学习关系，Dev 指标从旧 Anchor 的约 0.577 MRR / 0.335 AUPRC 提高到约 0.850 MRR / 0.550 AUPRC。多项置乱、Source-only 和困难子集核查说明该提升主要来自真实 Target–Source 语义匹配，而非明显泄漏或简单捷径。因此，R-SYM 可以作为当前 LongCite 阶段的首选方法和后续强基线。

但 R-SYM 本身是已有句对建模范式的轻量应用，而且是对称评分器。它解决的是语义支持关系，不是完整的有向多 Agent Memory Flow。下一阶段最有潜力的方向，是吸收 HDT 对结构化 Anchor 表示学习的经验，将 Anchor 作为信息汇聚与路由节点，将显式关系评分器作为边判定模块，再通过 Agent、时间、Memory 类型、实际访问记录和反事实实验建立方向性与忠实性。

用一句话概括当前进展：

> 我们已经找到了一种能够较可靠恢复 Chunk 间语义支持关系的轻量方法，也明确解释了旧 Anchor-Attention 方案为什么没有达到预期；下一步的核心不是继续刷 LongCite 分数，而是把“语义匹配”推进为具有层级结构、明确方向、运行依据和因果证据的真正 MemoryFlow。

## 参考资料

- HDT: Hierarchical Document Transformer: https://arxiv.org/abs/2407.08330
- HDT 官方实现: https://github.com/autonomousvision/hdt
- CLIP: Learning Transferable Visual Models From Natural Language Supervision: https://arxiv.org/abs/2103.00020
- Sentence-BERT: https://arxiv.org/abs/1908.10084
- InferSent: https://aclanthology.org/D17-1070/
