# 受控两轮溯源：最终原文排名（离线复算）

只读已保存的 frozen/spec/scores，不加载模型、不用 GPU。

## 口径

- 每跳前 5：`m2`（第二轮单元，含中间结论）与 `m1`（第一轮材料）各自的 top-5，保留在原始矩阵顺序里。
- 路径计分沿用 CUAD 原型的乘积规则：直达 = hop-1 分数；经中间结论 = hop-1(结论) × hop-2(分数)。
- 同一原文合并直达与间接路径：分数相加（`max` 作敏感性复核），按原文文本去重，排除中间结论，取全局前 5。
- 参照：CUAD 案例 0.4872 = 0.7569 × 0.6437，直达 0.3563，合并 0.8435（sum）。

## 三组最终原文排名

| 样例 | 组 | 1 | 2 | 3 | 4 | 5 | A 名次 | B 名次 | A 齐 | B 齐 | 找齐 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| T03 | G1 最后一轮 | `a0293:u38-103` **B** | `a0293:u0-37` | `a0296:u126-258` | `a0296:u0-88` | `a0007:u0-67` | — | 1 | 否 | 是 | 否 |
| T03 | G2 平铺 | `a0293:u38-103` **B** | `a0305:u0-82` **A** | `a0294:u0-142` | `a0296:u126-258` | `a0007:u68-126` | 2 | 1 | 是 | 是 | 是 |
| T03 | G3 多轮全局 | `a0293:u38-103` **B** | `a0305:u0-82` **A** | `a0293:u0-37` | `a0296:u126-258` | `a0296:u0-88` | 2 | 1 | 是 | 是 | 是 |
| T09 | G1 最后一轮 | `a0275:u0-109` **B** | `a0223:u0-149` | `a0279:u0-42` | `a0281:u0-34` | `a0236:u0-152` | — | 1 | 否 | 是 | 否 |
| T09 | G2 平铺 | `a0505:u112-200` **A** | `a0505:u0-111` | `a0374:u0-152` | `a0505:u201-276` | `a0236:u0-152` | 1 | 8 | 是 | 否 | 否 |
| T09 | G3 多轮全局 | `a0505:u112-200` **A** | `a0275:u0-109` **B** | `a0223:u0-149` | `a0279:u0-42` | `a0236:u0-152` | 1 | 2 | 是 | 是 | 是 |
| T06 | G1 最后一轮 | `a0284:u137-154` **B** | `a0279:u0-42` | `a0236:u0-152` | `a0282:u0-43` | `a0284:u0-16` | — | 1 | 否 | 是 | 否 |
| T06 | G2 平铺 | `a0284:u137-154` **B** | `a0284:u0-16` | `a0377:u290-342` **A** | `a0374:u0-152` | `a0223:u0-149` | 3 | 1 | 是 | 是 | 是 |
| T06 | G3 多轮全局 | `a0284:u137-154` **B** | `a0279:u0-42` | `a0236:u0-152` | `a0282:u0-43` | `a0284:u0-16` | 8 | 1 | 否 | 是 | 否 |

## 主例 T09（`case_02:selected_09`）

### 原文位置

| 标签 | unit | artifact | span | event | text |
|---|---|---|---|---|---|
| A | `a0505:u112-200` | `a0505` | [112,200) | 56 | Zero Zero – Mike’s quirky futuristic 1982 5th solo album and fantasy album-length video. |
| B | `a0275:u0-109` | `a0275` | [0,109) | 31 | The album, featuring Batt with the Sydney Symphony Orchestra, was released on Epic as a Mike Batt solo album. |

### 两轮输入

**第一轮**（问题：Which is Mike Batt's fifth solo album, and in what year was it released?）

| # | unit | span | role | text |
|---|---|---|---|---|
| 1 | `a0503:u0-20` | [0,20) | locator | Projects — Mike Batt |
| 2 | `a0505:u0-111` | [0,111) | context | Six Days In Berlin – 4th solo album for Epic – made at Hansa (Berlin) and Montserrat durin |
| 3 | `a0505:u112-200` | [112,200) | evidence_a | Zero Zero – Mike’s quirky futuristic 1982 5th solo album and fantasy album-length video. |
| 4 | `a0505:u201-276` | [201,276) | distractor | Songs Of Love And War - 6th solo album (made for RCA in a break from Sony). |
| 5 | `a0375:u0-44` | [0,44) | locator_distractor | Mike Batt Short Discography - friedl.heim.at |
| 6 | `a0371:u0-83` | [0,83) | distractor | Mike Batt discography and songs: Music profile for Mike Batt, born 6 February 1949. |
| 7 | `a0374:u0-152` | [0,152) | distractor | Jan 24, 2018 · In 1977, Batt conducted the all-star symphonic-rock recording Schizophonia, |
| 8 | `a0153:u0-63` | [0,63) | distractor | Explore Mike Batt's biography, discography, and artist credits. |
| 9 | `a0310:u0-69` | [0,69) | distractor | " Nine Million Bicycles " is a song written and produced by Mike Batt |
| 10 | `a0236:u0-152` | [0,152) | distractor | From mikebatt.com, the album list appears to include: Schizophonia, Tarot Suite, Waves, Si |
| 11 | `a0223:u0-149` | [0,149) | distractor | As a singer, Batt's solo albums included Schizophonia[11][12] and Tarot Suite[13][14] (197 |

**第二轮**（问题：Which label released Mike Batt's fifth solo album?）

前一步结论逐字放入：Mike Batt's fifth solo album was "Zero Zero," released in 1982.

| # | unit | span | role | text |
|---|---|---|---|---|
| 1 | `a0273:u0-21` | [0,21) | locator | Mike Batt - Wikipedia |
| 2 | `a0275:u0-109` | [0,109) | evidence_b | The album, featuring Batt with the Sydney Symphony Orchestra, was released on Epic as a Mi |
| 3 | `a0275:u110-223` | [110,223) | context | Batt's character "Number 17" falls in love and is sent to an emotional decontamination cen |
| 4 | `a0279:u0-42` | [0,42) | locator_distractor | Mike Batt – Zero Zero | Releases | Discogs |
| 5 | `a0282:u0-43` | [0,43) | locator_distractor | Mike Batt Zero Zero - EXC Vinyl LP FE 38454 |
| 6 | `a0281:u0-34` | [0,34) | distractor | Mike Batt - Zero Zero album cover. |
| 7 | `a0310:u0-69` | [0,69) | distractor | " Nine Million Bicycles " is a song written and produced by Mike Batt |
| 8 | `a0223:u0-149` | [0,149) | distractor | As a singer, Batt's solo albums included Schizophonia[11][12] and Tarot Suite[13][14] (197 |
| 9 | `a0153:u0-63` | [0,63) | distractor | Explore Mike Batt's biography, discography, and artist credits. |
| 10 | `a0236:u0-152` | [0,152) | distractor | From mikebatt.com, the album list appears to include: Schizophonia, Tarot Suite, Waves, Si |
| 11 | `a0371:u0-83` | [0,83) | distractor | Mike Batt discography and songs: Music profile for Mike Batt, born 6 February 1949. |

### 每跳前 5

**hop-1：最终句 → 第二轮单元（含中间结论）**

| rank | unit | score |
|---|---|---|
| 1 | `conclusion:r1` | 0.450708 |
| 2 | `a0275:u0-109` | 0.156913 |
| 3 | `a0223:u0-149` | 0.073494 |
| 4 | `a0279:u0-42` | 0.041154 |
| 5 | `a0281:u0-34` | 0.032385 |

**hop-2：中间结论 → 第一轮材料**

| rank | unit | score |
|---|---|---|
| 1 | `a0505:u112-200` | 0.618949 |
| 2 | `a0374:u0-152` | 0.077180 |
| 3 | `a0505:u0-111` | 0.065301 |
| 4 | `a0375:u0-44` | 0.024158 |
| 5 | `a0371:u0-83` | 0.021227 |

### 两组最终前 5

**G2 平铺**（池 17，A 第 1、B 第 8）

| rank | unit | role | score | 直达 | 间接 | text |
|---|---|---|---|---|---|---|
| 1 | `a0505:u112-200` | evidence_a | 0.472038 | — | — | Zero Zero – Mike’s quirky futuristic 1982 5th solo album and fantasy album-lengt |
| 2 | `a0505:u0-111` | context | 0.217755 | — | — | Six Days In Berlin – 4th solo album for Epic – made at Hansa (Berlin) and Montse |
| 3 | `a0374:u0-152` | distractor | 0.056885 | — | — | Jan 24, 2018 · In 1977, Batt conducted the all-star symphonic-rock recording Sch |
| 4 | `a0505:u201-276` | distractor | 0.025367 | — | — | Songs Of Love And War - 6th solo album (made for RCA in a break from Sony). |
| 5 | `a0236:u0-152` | distractor | 0.025322 | — | — | From mikebatt.com, the album list appears to include: Schizophonia, Tarot Suite, |

**G3 多轮全局（直达 + 经中间结论，合并后）**（池 17，A 第 1、B 第 2）

| rank | unit | role | score | 直达 | 间接 | text |
|---|---|---|---|---|---|---|
| 1 | `a0505:u112-200` | evidence_a | 0.278965 | 0.000000 | 0.278965 | Zero Zero – Mike’s quirky futuristic 1982 5th solo album and fantasy album-lengt |
| 2 | `a0275:u0-109` | evidence_b | 0.156913 | 0.156913 | 0.000000 | The album, featuring Batt with the Sydney Symphony Orchestra, was released on Ep |
| 3 | `a0223:u0-149` | distractor | 0.076479 | 0.073494 | 0.002986 | As a singer, Batt's solo albums included Schizophonia[11][12] and Tarot Suite[13 |
| 4 | `a0279:u0-42` | locator_distractor | 0.041154 | 0.041154 | 0.000000 | Mike Batt – Zero Zero | Releases | Discogs |
| 5 | `a0236:u0-152` | distractor | 0.038989 | 0.030504 | 0.008485 | From mikebatt.com, the album list appears to include: Schizophonia, Tarot Suite, |

### 核对

- 平铺 B 第 8（池 17）；多轮全局 A 第 1、B 第 2。
- 平铺 A 第 1；最后一轮 A 不可见。
- 第二轮同义断言扫描：无显式 fifth/5th 断言。
- 可计数影子证据：`a0236:u0-152`（From mikebatt.com, the album list appears to include: Schizophonia, Tarot Suite, Waves, Six Days In Berlin, Ze）。清单里 Zero Zero 在去掉 Caravans 的计数下是第 5 项；它不是显式 fifth 断言，也不是 GT 的 A。

## T06 对照：最终轮自身已有足够证据

- 最终句只要求“专辑 + 发行年”；第二轮材料里题名（`a0279`、`a0282`）与年份 `a0284:u137-154` 都在，最终轮 top-5 直接包含 B 与题名，因此不需要沿中间结论追到列表项 A。
- 多轮全局 A 第 8、B 第 1：A 被最终轮的直接材料挤出前 5，这是“自足对照”的预期结果，不作为链失败。

## 另两题的最终轮同义原文核对

- **T03**：同文 A 支持位置 3 个，落入第二轮 0 个；第二轮显式断言命中 0 个；可计数清单 0 个；最长公共子串 16 字符、8-token shingle 0。
- **T09**：同文 A 支持位置 2 个，落入第二轮 0 个；第二轮显式断言命中 0 个；可计数清单 1 个；最长公共子串 11 字符、8-token shingle 0。

## 不同主题的合格样例

- `case_08` 两个开发目标各只有一段主证据（`a0030[108,222)`、`a0024[164,214)`），无法满足“第二轮不含 A、同时含同组 B”的两轮构造；`case_02` 其余目标都属于同一 Katie Melua/Mike Batt 主题，且多为单段或等价来源。结论：现有获准开发轨迹里没有不同主题的合格样例，本轮不新增。

