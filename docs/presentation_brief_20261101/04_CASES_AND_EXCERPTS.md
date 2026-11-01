# 页面可用案例与短摘录

## C1：旧 CUAD 机制案例（E04）

身份：旧系统真实运行，任务是定位合同 preferential-rights 相关条款；不是新版正式 DCCv2 case，不进行法律定性。

### 原文

> 2.1 Party A shall have a preemptive right to carry out mobile game services with Party B on a nationwide basis.

中文辅助：甲方在与乙方开展全国范围移动游戏服务上享有优先权。来源片段 2593:3850，实际完整片段还含相邻条款。

### 研究者摘要中的关键内容

摘要引用该句，并将 preemptive right 解释为功能上近似 first offer/negotiation；同时注明合同未出现 right of first refusal/offer/negotiation 的明确术语，并建议律师复核。

可直接引用的短句：

> No explicit 'right of first refusal', 'right of first offer', or 'right of first negotiation' terminology appears in the contract.

### 最终报告

最终返回与原文一致的 2.1 条。任务要求原句，不能因未保留摘要全部解释而判错。

### 可确认的流程

研究者 call4 看见 13 个原始片段并形成摘要；报告者 call7 看见摘要和 2593:3850，产生最终条款。原文→摘要、摘要→报告的语义关联来自回放估计；输入可见与生成归属来自记录。

展示重点：中间加工可以引入解释和保留意见，最终引用未展示这些过程。不是证明本例多跳比直接来源更准。

## C2：新版 DCCv2 NBA（E05）

身份：正式新版、单条完整运行，答案错误。分析基于任务材料，不用本文件中的模型说法作为 NBA 规则的权威解释。

### 公开事实（从实际交付摘取，原输入映射已记录）

| 条目 | 本次任务/交付中的值 |
|---|---:|
| 2024—25 Salary Cap | $140,588,000 |
| Team B salary | $136,000,000 |
| 模型算出的差值 | $4,588,000 |
| Operation A 首年金额 | $7,000,000 |
| Operation B 首年金额 | $4,000,000 |

### 所选规则解释句（实际输出，字面定位 call10）

> Since Team B is **under the Salary Cap** ($136M < $140.588M), Team B must use its **cap room** to sign free agents, not a salary cap exception.

中文辅助：模型认为 B 队在工资帽以下，必须使用空间而非例外签约。这是待核查的模型解释，不是本资料包认证的规则。

### 所选操作判断句（实际输出，字面定位 call22）

> Operation B ($4,000,000) is within Team B's $4,588,000 cap room and complies.

### 最终结论

> Answer: True. Illegal Operation: A. Problematic Team: B.

官方标签：True / B / B。正文确实分析 A 违规、B 合规，不能只当末尾字母笔误。任务、交付和判断正确性三个状态分开。

### 可用的核查线索

交付 metadata 自述相关 Bird/Early Bird/Non-Bird 检索未命中，并采用它所称的 standard NBA CBA exception framework。执行侧关键词检索未定位相关表述，但尚未完成充分的语义支撑核查。

页面可以写“当前检索尚未定位到支持该解释的具体原文，依据待核查”，不能写“已证明原文无依据”“MemoryFlow 识别了幻觉”。

### 传递与版本素材

最终报告为 report_revision v2，parent 为 v1；还存在前版摘要/partial 结果、修订说明与同一回答前文。它们已经进入局部回放候选，但新读出分类和候选的原始生成归属仍需核准。

图中可先展示真实目标、call10/call22 和 v1→v2 的记录关系；“最终句—前版摘要—更早来源”的估计路径标 P01 待补，不把两个不相连的局部矩阵画成完整实测链。

## C3：报告数字改写（应用说明，E08）

会议批注提供的情景：原始材料含“9899 万农村贫困人口全部脱贫、832 个贫困县全部摘帽”；摘要保留这些数字；报告将数字改写为汉字并附引用。

可展示：“9899 万 / 832 个”经过摘要与措辞变换仍需回到具体出处。标明“会议材料中的场景说明，未核对本研究可追踪运行”。不要额外加来源分数或实验成功标记。

## C4：内容变化追查（概念示意，E08）

仅用结构说明：原文带条件 C；中间摘要未保留 C；最终判断沿用摘要。三个框的文字明确写“示意条件”，不伪造某个真实任务的遗漏。

研究希望支持审阅者定位值得复核的变化；本次未进行独立用户实验或因果干预。正文可一句说明用途，不必扩成一页未做实验。
