# informative30 真实中间消息首批（2026-11-07）

**状态：** 从 36 个优先目标里核对 3 条有实际 agent 中间消息的题：2 条合格并实测，1 条保留诊断。
真实回放批主表 2 题 / 2 条轨迹；人工构造首批 3 题继续单列。旧 batch10 直接复用 17 题。

## 36 优先清单

来源：`GenMem_informative30_接入预检_20261107.md` 的“优先复核的 36 个目标”（覆盖 21 条轨迹）。
本轮先核 3 条有真实 agent 中间消息的：case_01 T10、case_03 T04、case_06 T10。

## 三题的事件链

| 题 | 上游原文 | 真实中间消息 | 后面补到什么 | 支撑最终哪一项 |
|---|---|---|---|---|
| case_01:T10 | `C0036` ev29：父亲 Demetrios，母 Anna；并说“现在要找 Demetrios 的母亲” | ev29 agent 原文：确认父母身份，提出要找 paternal grandmother | ev30 `C0037`（Demetrios 身份）、ev31 `C0042`（Theodora of Arta） | ev32 结论：paternal grandmother = Theodora of Arta |
| case_03:T04 | `C0008` ev4：Ruby 的 `alias` 关键字 | ev8 agent 原文：Ruby 有 `alias`，但以宝石命名，不是人名；继续查其他候选 | ev10 `C0024`（同事 birthstone）、ev12 `C0028`（July birthstone） | ev14 结论：Ruby 以同事的生日石命名 |
| case_06:T10 | `C0008` ev4：Mayberry R.F.D. 第一集 | ev8 agent 原文只说“分别查角色和演员的结局”，**没有承接 A 的具体内容** | ev9 `C0017`（Helen 与 Andy 结婚）、ev10 `C0023`（演员 1995 年癌症去世） | ev11 结论 |

`case_06:T10` 的 ev8 是真实消息，但不是有效传递（没有带入 A 的内容），因此只作诊断，不计入“真实中间消息回放”主表。

## 真实回放主表（2 题，2 条轨迹）

| 题 | MF 完整 | BM25 完整 | head 完整 | last | MF A/B |
|---|---|---|---|---|---|
| case_01:T10 | 3 | 6 | 8 | — | 3 / 1 |
| case_03:T04 | 5 | 5 | 7 | — | 5 / 2 |

| 方法 | Hit@3 | 完整@5 | 完整@10 | 平均完整名次 |
|---|---|---|---|---|
| last_round | 2/2 | 0/2 | 0/2 | 11.00 |
| bm25_history | 2/2 | 0/2 | 2/2 | 5.50 |
| head_full_history | 2/2 | 2/2 | 2/2 | 7.50 |
| memoryflow | 2/2 | 2/2 | 2/2 | 4.00 |

**配对（MF 对基线，n=2）**

| 基线 | 完整名次 W/T/L | 首个证据 W/T/L |
|---|---|---|
| last_round | 2/0/0 | 0/2/0 |
| bm25_history | 1/1/0 | 0/2/0 |
| head_full_history | 2/0/0 | 0/2/0 |

两题 MF 都完整；head 虽完整但名次更慢（8/7），BM25 一题 5、一题 6。
`case_06:T10` 诊断：MF 失败（A 未进最终列表），BM25 6、head 9 完整；不进入真实主表。

## 人工构造首批（3 题，单列）

case_03 T02、case_05 T07、case_06 T02；全部 `controlled` 中间句。结果不变：
MF 完整@5/@10 2/3、2/3；head 3/3、3/3；BM25 2/3、3/3；last 0。
真实批与构造批不混算。

## 36 清单进度

已核对 3 条：2 条真实回放合格，1 条保留诊断。36 题覆盖 21 条轨迹；本轮覆盖 2 条真实轨迹
（case_01、case_03）。剩余 33 条按清单继续，优先不同轨迹；每题继续记录
“上游原文 → 真实中间消息 → 后补证据 → 支撑结论哪一项”。

## 产物

- 真实批明细：[BATCH_REAL_20261107.md](BATCH_REAL_20261107.md)
- 真实批预检：[precheck.json](precheck.json)
- 构造首批：[FIRST_20261107.md](../../informative30/reports/FIRST_20261107.md)
- 旧 batch10：17 题主表不变；case_03 selected_08 仍只作诊断。
