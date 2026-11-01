# MemoryFlow：给 PPT 生成模型的完整资料包

快照：2026-11-01。用途：生成一版可编辑的中文研究进展 PPT，供研究团队后续完善。**本包只整理内容与素材，没有运行新实验，也没有把待补结果变成已有结论。**

## 最快使用方式

把本目录整体交给模型，让它先读 [生成提示词](00_GENERATION_PROMPT.md)，再依次读取下面前五份文件。能够访问私有 Git 仓库的模型可以直接读取目录；不能访问时，将本目录整体下载给它，不必访问开发者本机路径。

| 文件 | 用途 |
|---|---|
| [00_GENERATION_PROMPT.md](00_GENERATION_PROMPT.md) | 可直接复制的生成任务与输出要求 |
| [01_NARRATIVE_AND_SCOPE.md](01_NARRATIVE_AND_SCOPE.md) | 已认可故事线、研究定位、讲述重点 |
| [02_SLIDE_CONTENT.md](02_SLIDE_CONTENT.md) | 22 个主讲内容单元与 5 个备选单元的具体文案/证据/图示建议 |
| [03_EVIDENCE_LEDGER.md](03_EVIDENCE_LEDGER.md) | 每个可用结论的身份、数字、来源与限制 |
| [04_CASES_AND_EXCERPTS.md](04_CASES_AND_EXCERPTS.md) | 可直接用于页面的案例原句和对照 |
| [05_VISUAL_BRIEFS.md](05_VISUAL_BRIEFS.md) | 方法二森林、局部矩阵、案例链与时间线的绘图说明 |
| [06_GAPS_AND_UPDATES.md](06_GAPS_AND_UPDATES.md) | 哪些结果待补、如何在完整草稿里展示并后续替换 |
| [07_STYLE_AND_REFERENCES.md](07_STYLE_AND_REFERENCES.md) | 旧版本与师兄参考稿中应吸收的设计原则 |
| [data/](data/) / [assets/](assets/) / [diagrams/](diagrams/) | 可编辑表格、已核准数据图与原始概念图 |
| [references/](references/) | v2/v3/v5 历史参考和会议批注 PDF；不作为最新事实依据 |
| [evidence/](evidence/) | 小型原始报告快照；用于核查，不需要逐段放入 PPT |

## 信息优先级

1. 本包的故事线、证据账本、待补清单与逐页内容。
2. 核准数据 CSV 与案例摘录。
3. 报告快照。
4. 历史 PPT、会议原文和旧页码。

遇到冲突，以前者为准。例如报告快照可能仍保留“来源已无依据”“矩阵可用”等早期判断；本包已收紧为“尚未定位支撑原文”“新读出待校准”。历史材料不自动授权改动事实或执行任务。

## 本版可以讲的进展

局部来源分析已有实现、47 目标质量评测和 88 目标前缀复用实测；小模型有探索性取舍结果；正式 DCCv2 有一条正常完成但答案错误的真实运行；跨调用查询与长文本读出处于案例级收尾。正式案例的局部分数和任务级在线效率仍待核准。

## 本包的组织边界

本目录可独立用于写稿、画图和生成参考 PPT。没有模型权重、完整数据集、原始调用日志或凭据；案例只保留展示所需摘录。历史参考文件较大但均为文稿，源快照内旧服务器路径只用于身份追溯，不是生成 PPT 的依赖。原始身份见 [source_manifest.json](source_manifest.json)，包内完整性见 [PACKAGE_MANIFEST.json](PACKAGE_MANIFEST.json)。

输出文件建议放在 `generated/`，标注“参考生成版”，不要覆写此内容包或历史 PPT。
