# DCC Stage 1 逐例人工评审包

**程序验证通过不等于独立人工批准。** 所有 `independent_human_status=NOT_REVIEWED`。本文列出完整公开材料、规则、每个发生对象的计算与原文依据；请人工确认语义和对象全集。八例仅为校准，不是模型效果样本。

## x5a1cc088f80a | T1 v1（评审用，模型不见家族/版本/焦点）

**家族变动：**d1 完整且含 4.2；焦点存在。  **焦点对象：**`xe23e1d168cd9`（仅评审端）。

**审核指令：**Check every explicit clause-reference occurrence in d1 against the supplied scope and material register.

**完整规则：**
- `R-REF` Check each explicit internal clause reference in d1 and the in-scope annex d2. When the target document is fully provided, a cited clause exists only if that exact clause label appears there. External Standard Q-7 in d3 is excluded from this rule. If an in-scope target's provided coverage is partial or unavailable, do not infer absence.

**统一材料清单：**
- d1: provided; coverage COMPLETE.
- d2: provided; coverage COMPLETE.
- d3: not provided; coverage UNAVAILABLE.
- d4: provided; coverage COMPLETE.

**三批公开材料（全文原样）：**
### b1

`d1`：
```text
1.1: Definitions govern this agreement.
2.1: Delivery shall occur by noon.
3.1: The following four directions contain the reviewable references.
R2: For delivery, see Section 2.1.
R3: For schedule, see Annex A Clause A.3.
R4: For definitions, see Section 1.1.
R1: For retention, see Section 4.2.
4.2: Retain audit records for thirty days.
```

### b2

`d2`：
```text
A.3: The schedule is attached and effective.
```

### b3

`d4`：
```text
G.1: Clause labels identify exact positions; no other clause is incorporated here.
```

**逐对象 Gold 与原文：**

#### `xe23e1d168cd9` → `COMPLIANT`

- 发生位置：`d1[260:296]` “R1: For retention, see Section 4.2.”
- 目标：`d1` 的 `4.2`；引用范围 `IN_SCOPE`。
- 可见目标：`d1[296:339]` “4.2: Retain audit records for thirty days.”
- 计算：范围适用=TRUE；目标存在=TRUE；材料范围=d1。完整范围才能由未出现推出不存在；已出现可直接确认。
- 缺失范围依据：不需要；未知条件：无。

#### `xff00b42292cd` → `COMPLIANT`

- 发生位置：`d1[145:180]` “R2: For delivery, see Section 2.1.”
- 目标：`d1` 的 `2.1`；引用范围 `IN_SCOPE`。
- 可见目标：`d1[40:75]` “2.1: Delivery shall occur by noon.”
- 计算：范围适用=TRUE；目标存在=TRUE；材料范围=d1。完整范围才能由未出现推出不存在；已出现可直接确认。
- 缺失范围依据：不需要；未知条件：无。

#### `xf4f4ff468d1b` → `COMPLIANT`

- 发生位置：`d1[180:222]` “R3: For schedule, see Annex A Clause A.3.”
- 目标：`d2` 的 `A.3`；引用范围 `IN_SCOPE`。
- 可见目标：`d2[0:45]` “A.3: The schedule is attached and effective.”
- 计算：范围适用=TRUE；目标存在=TRUE；材料范围=d2。完整范围才能由未出现推出不存在；已出现可直接确认。
- 缺失范围依据：不需要；未知条件：无。

#### `xbf5440d56bb3` → `COMPLIANT`

- 发生位置：`d1[222:260]` “R4: For definitions, see Section 1.1.”
- 目标：`d1` 的 `1.1`；引用范围 `IN_SCOPE`。
- 可见目标：`d1[0:40]` “1.1: Definitions govern this agreement.”
- 计算：范围适用=TRUE；目标存在=TRUE；材料范围=d1。完整范围才能由未出现推出不存在；已出现可直接确认。
- 缺失范围依据：不需要；未知条件：无。

**评审提示：**规则例外、完整性和全部四个发生对象均已在公开材料中呈现；请独立确认其足以支持上述结构化 Gold，而非只相信程序映射。

## xcc73d4efd362 | T1 v2（评审用，模型不见家族/版本/焦点）

**家族变动：**d1 完整但不含 4.2；焦点缺失可判违反。  **焦点对象：**`xe23e1d168cd9`（仅评审端）。

**审核指令：**Check every explicit clause-reference occurrence in d1 against the supplied scope and material register.

**完整规则：**
- `R-REF` Check each explicit internal clause reference in d1 and the in-scope annex d2. When the target document is fully provided, a cited clause exists only if that exact clause label appears there. External Standard Q-7 in d3 is excluded from this rule. If an in-scope target's provided coverage is partial or unavailable, do not infer absence.

**统一材料清单：**
- d1: provided; coverage COMPLETE.
- d2: provided; coverage COMPLETE.
- d3: not provided; coverage UNAVAILABLE.
- d4: provided; coverage COMPLETE.

**三批公开材料（全文原样）：**
### b1

`d1`：
```text
1.1: Definitions govern this agreement.
2.1: Delivery shall occur by noon.
3.1: The following four directions contain the reviewable references.
R2: For delivery, see Section 2.1.
R3: For schedule, see Annex A Clause A.3.
R4: For definitions, see Section 1.1.
R1: For retention, see Section 4.2.
```

### b2

`d2`：
```text
A.3: The schedule is attached and effective.
```

### b3

`d4`：
```text
G.1: Clause labels identify exact positions; no other clause is incorporated here.
```

**逐对象 Gold 与原文：**

#### `xe23e1d168cd9` → `VIOLATION`

- 发生位置：`d1[260:296]` “R1: For retention, see Section 4.2.”
- 目标：`d1` 的 `4.2`；引用范围 `IN_SCOPE`。
- 计算：范围适用=TRUE；目标存在=FALSE；材料范围=d1。完整范围才能由未出现推出不存在；已出现可直接确认。
- 缺失范围依据：['d1']；未知条件：无。

#### `xff00b42292cd` → `COMPLIANT`

- 发生位置：`d1[145:180]` “R2: For delivery, see Section 2.1.”
- 目标：`d1` 的 `2.1`；引用范围 `IN_SCOPE`。
- 可见目标：`d1[40:75]` “2.1: Delivery shall occur by noon.”
- 计算：范围适用=TRUE；目标存在=TRUE；材料范围=d1。完整范围才能由未出现推出不存在；已出现可直接确认。
- 缺失范围依据：不需要；未知条件：无。

#### `xf4f4ff468d1b` → `COMPLIANT`

- 发生位置：`d1[180:222]` “R3: For schedule, see Annex A Clause A.3.”
- 目标：`d2` 的 `A.3`；引用范围 `IN_SCOPE`。
- 可见目标：`d2[0:45]` “A.3: The schedule is attached and effective.”
- 计算：范围适用=TRUE；目标存在=TRUE；材料范围=d2。完整范围才能由未出现推出不存在；已出现可直接确认。
- 缺失范围依据：不需要；未知条件：无。

#### `xbf5440d56bb3` → `COMPLIANT`

- 发生位置：`d1[222:260]` “R4: For definitions, see Section 1.1.”
- 目标：`d1` 的 `1.1`；引用范围 `IN_SCOPE`。
- 可见目标：`d1[0:40]` “1.1: Definitions govern this agreement.”
- 计算：范围适用=TRUE；目标存在=TRUE；材料范围=d1。完整范围才能由未出现推出不存在；已出现可直接确认。
- 缺失范围依据：不需要；未知条件：无。

**评审提示：**规则例外、完整性和全部四个发生对象均已在公开材料中呈现；请独立确认其足以支持上述结构化 Gold，而非只相信程序映射。

## x78ffd00c3146 | T1 v3（评审用，模型不见家族/版本/焦点）

**家族变动：**同一方向改为明确排除的 External Standard Q-7；不适用。  **焦点对象：**`xe23e1d168cd9`（仅评审端）。

**审核指令：**Check every explicit clause-reference occurrence in d1 against the supplied scope and material register.

**完整规则：**
- `R-REF` Check each explicit internal clause reference in d1 and the in-scope annex d2. When the target document is fully provided, a cited clause exists only if that exact clause label appears there. External Standard Q-7 in d3 is excluded from this rule. If an in-scope target's provided coverage is partial or unavailable, do not infer absence.

**统一材料清单：**
- d1: provided; coverage COMPLETE.
- d2: provided; coverage COMPLETE.
- d3: not provided; coverage UNAVAILABLE.
- d4: provided; coverage COMPLETE.

**三批公开材料（全文原样）：**
### b1

`d1`：
```text
1.1: Definitions govern this agreement.
2.1: Delivery shall occur by noon.
3.1: The following four directions contain the reviewable references.
R2: For delivery, see Section 2.1.
R3: For schedule, see Annex A Clause A.3.
R4: For definitions, see Section 1.1.
R1: For retention, see External Standard Q-7 Clause 4.2.
```

### b2

`d2`：
```text
A.3: The schedule is attached and effective.
```

### b3

`d4`：
```text
G.1: Clause labels identify exact positions; no other clause is incorporated here.
```

**逐对象 Gold 与原文：**

#### `xe23e1d168cd9` → `NOT_APPLICABLE`

- 发生位置：`d1[260:317]` “R1: For retention, see External Standard Q-7 Clause 4.2.”
- 目标：`d3` 的 `4.2`；引用范围 `EXTERNAL_EXCLUDED`。
- 计算：范围适用=FALSE；目标存在=UNKNOWN；材料范围=d3。完整范围才能由未出现推出不存在；已出现可直接确认。
- 缺失范围依据：不需要；未知条件：['xe23e1d168cd9:target_present']。

#### `xff00b42292cd` → `COMPLIANT`

- 发生位置：`d1[145:180]` “R2: For delivery, see Section 2.1.”
- 目标：`d1` 的 `2.1`；引用范围 `IN_SCOPE`。
- 可见目标：`d1[40:75]` “2.1: Delivery shall occur by noon.”
- 计算：范围适用=TRUE；目标存在=TRUE；材料范围=d1。完整范围才能由未出现推出不存在；已出现可直接确认。
- 缺失范围依据：不需要；未知条件：无。

#### `xf4f4ff468d1b` → `COMPLIANT`

- 发生位置：`d1[180:222]` “R3: For schedule, see Annex A Clause A.3.”
- 目标：`d2` 的 `A.3`；引用范围 `IN_SCOPE`。
- 可见目标：`d2[0:45]` “A.3: The schedule is attached and effective.”
- 计算：范围适用=TRUE；目标存在=TRUE；材料范围=d2。完整范围才能由未出现推出不存在；已出现可直接确认。
- 缺失范围依据：不需要；未知条件：无。

#### `xbf5440d56bb3` → `COMPLIANT`

- 发生位置：`d1[222:260]` “R4: For definitions, see Section 1.1.”
- 目标：`d1` 的 `1.1`；引用范围 `IN_SCOPE`。
- 可见目标：`d1[0:40]` “1.1: Definitions govern this agreement.”
- 计算：范围适用=TRUE；目标存在=TRUE；材料范围=d1。完整范围才能由未出现推出不存在；已出现可直接确认。
- 缺失范围依据：不需要；未知条件：无。

**评审提示：**规则例外、完整性和全部四个发生对象均已在公开材料中呈现；请独立确认其足以支持上述结构化 Gold，而非只相信程序映射。

## x535edd54c125 | T1 v4（评审用，模型不见家族/版本/焦点）

**家族变动：**d1 为部分范围且未见 4.2；不能由缺席推断不存在。  **焦点对象：**`xe23e1d168cd9`（仅评审端）。

**审核指令：**Check every explicit clause-reference occurrence in d1 against the supplied scope and material register.

**完整规则：**
- `R-REF` Check each explicit internal clause reference in d1 and the in-scope annex d2. When the target document is fully provided, a cited clause exists only if that exact clause label appears there. External Standard Q-7 in d3 is excluded from this rule. If an in-scope target's provided coverage is partial or unavailable, do not infer absence.

**统一材料清单：**
- d1: provided; coverage PARTIAL.
- d2: provided; coverage COMPLETE.
- d3: not provided; coverage UNAVAILABLE.
- d4: provided; coverage COMPLETE.

**三批公开材料（全文原样）：**
### b1

`d1`：
```text
1.1: Definitions govern this agreement.
2.1: Delivery shall occur by noon.
3.1: The following four directions contain the reviewable references.
R2: For delivery, see Section 2.1.
R3: For schedule, see Annex A Clause A.3.
R4: For definitions, see Section 1.1.
R1: For retention, see Section 4.2.
```

### b2

`d2`：
```text
A.3: The schedule is attached and effective.
```

### b3

`d4`：
```text
G.1: Clause labels identify exact positions; no other clause is incorporated here.
```

**逐对象 Gold 与原文：**

#### `xe23e1d168cd9` → `INSUFFICIENT_EVIDENCE`

- 发生位置：`d1[260:296]` “R1: For retention, see Section 4.2.”
- 目标：`d1` 的 `4.2`；引用范围 `IN_SCOPE`。
- 计算：范围适用=TRUE；目标存在=UNKNOWN；材料范围=d1。完整范围才能由未出现推出不存在；已出现可直接确认。
- 缺失范围依据：不需要；未知条件：['xe23e1d168cd9:target_present']。

#### `xff00b42292cd` → `COMPLIANT`

- 发生位置：`d1[145:180]` “R2: For delivery, see Section 2.1.”
- 目标：`d1` 的 `2.1`；引用范围 `IN_SCOPE`。
- 可见目标：`d1[40:75]` “2.1: Delivery shall occur by noon.”
- 计算：范围适用=TRUE；目标存在=TRUE；材料范围=d1。完整范围才能由未出现推出不存在；已出现可直接确认。
- 缺失范围依据：不需要；未知条件：无。

#### `xf4f4ff468d1b` → `COMPLIANT`

- 发生位置：`d1[180:222]` “R3: For schedule, see Annex A Clause A.3.”
- 目标：`d2` 的 `A.3`；引用范围 `IN_SCOPE`。
- 可见目标：`d2[0:45]` “A.3: The schedule is attached and effective.”
- 计算：范围适用=TRUE；目标存在=TRUE；材料范围=d2。完整范围才能由未出现推出不存在；已出现可直接确认。
- 缺失范围依据：不需要；未知条件：无。

#### `xbf5440d56bb3` → `COMPLIANT`

- 发生位置：`d1[222:260]` “R4: For definitions, see Section 1.1.”
- 目标：`d1` 的 `1.1`；引用范围 `IN_SCOPE`。
- 可见目标：`d1[0:40]` “1.1: Definitions govern this agreement.”
- 计算：范围适用=TRUE；目标存在=TRUE；材料范围=d1。完整范围才能由未出现推出不存在；已出现可直接确认。
- 缺失范围依据：不需要；未知条件：无。

**评审提示：**规则例外、完整性和全部四个发生对象均已在公开材料中呈现；请独立确认其足以支持上述结构化 Gold，而非只相信程序映射。

## x76c5d5439312 | T2 v1（评审用，模型不见家族/版本/焦点）

**家族变动：**焦点批准范围不符，但匹配的有效法院命令构成替代满足。  **焦点对象：**`xe379efe00b0b`（仅评审端）。

**审核指令：**Check each of the four sending events under R.1–R.3. Treat missing entries in a partial register as unknown, not absent.

**完整规则：**
- `R.1` A sending obligation applies when material is sent to an external recipient, is restricted, and was not lawfully public before sending.
- `R.2` If applicable, sending requires either prior effective written approval or a valid court order for this same sending.
- `R.3` Approval and order each require matching subject, data scope and sending event, effective status, and sending time inside the UTC validity interval including both endpoints. An incomplete register cannot establish absence; a known valid alternative still suffices.

**统一材料清单：**
- d1: provided; coverage COMPLETE.
- d2: provided; coverage COMPLETE.
- d3: provided; coverage COMPLETE.
- d4: provided; coverage COMPLETE.
- d5: provided; coverage COMPLETE.

**三批公开材料（全文原样）：**
### b1

`d1`：
```text
R.1: A sending obligation applies when material is sent to an external recipient, is restricted, and was not lawfully public before sending.
R.2: If applicable, sending requires either prior effective written approval or a valid court order for this same sending.
R.3: Approval and order each require matching subject, data scope and sending event, effective status, and sending time inside the UTC validity interval including both endpoints. An incomplete register cannot establish absence; a known valid alternative still suffices.
```

`d2`：
```text
TX-01: Orion Labs sent Dataset Cedar to external recipient Northbay on 2026-04-10T10:00:00Z.
TX-02: Cobalt Works sent Dataset Hazel to external recipient Bayfield on 2026-04-11T09:00:00Z.
TX-03: Elm Institute sent Dataset Maple to external recipient Shoreline on 2026-04-12T12:00:00Z.
TX-04: Vale Group sent Dataset Birch to internal archive team on 2026-04-13T08:00:00Z.
```

### b2

`d3`：
```text
TX-01: Dataset Cedar was restricted and not lawfully public before sending.
TX-02: Dataset Hazel was restricted and not lawfully public before sending.
TX-03: Dataset Maple was restricted and not lawfully public before sending.
TX-04: Dataset Birch was restricted and not lawfully public before sending.
```

### b3

`d4`：
```text
Approval register: complete for all listed TX events.
TX-01 approval record: subject Orion Labs; scope Dataset Pine; event TX-01; valid 2026-04-01T00:00:00Z through 2026-04-30T23:59:59Z inclusive UTC; effective yes.
TX-02 approval record: subject Cobalt Works; scope Dataset Hazel; event TX-02; valid 2026-04-01T00:00:00Z through 2026-04-30T23:59:59Z inclusive UTC; effective yes.
TX-03 approval record: subject Elm Institute; scope Dataset Fir; event TX-03; valid 2026-04-01T00:00:00Z through 2026-04-30T23:59:59Z inclusive UTC; effective no.
TX-04 approval record: subject Vale Group; scope Dataset Pine; event TX-04; valid 2026-04-01T00:00:00Z through 2026-04-30T23:59:59Z inclusive UTC; effective no.
```

`d5`：
```text
Order register: complete for all listed TX events.
TX-01 order record: subject Orion Labs; scope Dataset Cedar; event TX-01; valid 2026-04-01T00:00:00Z through 2026-04-30T23:59:59Z inclusive UTC; effective yes.
TX-02 order record: subject Cobalt Works; scope Dataset Hazel; event TX-02; valid 2026-04-01T00:00:00Z through 2026-04-30T23:59:59Z inclusive UTC; effective yes.
TX-03 order record: subject Elm Institute; scope Dataset Maple; event TX-03; valid 2026-04-01T00:00:00Z through 2026-04-30T23:59:59Z inclusive UTC; effective yes.
TX-04 order record: subject Vale Group; scope Dataset Pine; event TX-04; valid 2026-04-01T00:00:00Z through 2026-04-30T23:59:59Z inclusive UTC; effective no.
```

**逐对象 Gold 与原文：**

#### `xe379efe00b0b` → `COMPLIANT`

- 发生位置：`d2[0:93]` “TX-01: Orion Labs sent Dataset Cedar to external recipient Northbay on 2026-04-10T10:00:00Z.”
- 资料状态：`d3[0:75]` “TX-01: Dataset Cedar was restricted and not lawfully public before sending.”
- 书面批准：`d4[54:215]` “TX-01 approval record: subject Orion Labs; scope Dataset Pine; event TX-01; valid 2026-04-01T00:00:00Z through 2026-04-30T23:59:59Z inclusive UTC; effective yes.”
- 法院命令：`d5[51:210]` “TX-01 order record: subject Orion Labs; scope Dataset Cedar; event TX-01; valid 2026-04-01T00:00:00Z through 2026-04-30T23:59:59Z inclusive UTC; effective yes.”
- 计算：适用性 external=TRUE AND restricted=TRUE AND NOT public=TRUE => TRUE；批准候选无效项=['scope_match']，批准登记完整性=TRUE，批准分支=FALSE；命令候选无效项=[]，命令登记完整性=TRUE，命令分支=TRUE；OR 后满足性=TRUE，最终=COMPLIANT。时间按含端点 UTC 区间核查。
- 缺失范围依据：不需要；未知条件：无。

#### `x633d821f3561` → `COMPLIANT`

- 发生位置：`d2[93:188]` “TX-02: Cobalt Works sent Dataset Hazel to external recipient Bayfield on 2026-04-11T09:00:00Z.”
- 资料状态：`d3[76:151]` “TX-02: Dataset Hazel was restricted and not lawfully public before sending.”
- 书面批准：`d4[216:380]` “TX-02 approval record: subject Cobalt Works; scope Dataset Hazel; event TX-02; valid 2026-04-01T00:00:00Z through 2026-04-30T23:59:59Z inclusive UTC; effective yes.”
- 法院命令：`d5[211:372]` “TX-02 order record: subject Cobalt Works; scope Dataset Hazel; event TX-02; valid 2026-04-01T00:00:00Z through 2026-04-30T23:59:59Z inclusive UTC; effective yes.”
- 计算：适用性 external=TRUE AND restricted=TRUE AND NOT public=TRUE => TRUE；批准候选无效项=[]，批准登记完整性=TRUE，批准分支=TRUE；命令候选无效项=[]，命令登记完整性=TRUE，命令分支=TRUE；OR 后满足性=TRUE，最终=COMPLIANT。时间按含端点 UTC 区间核查。
- 缺失范围依据：不需要；未知条件：无。

#### `x8bc1690ccdf4` → `COMPLIANT`

- 发生位置：`d2[188:285]` “TX-03: Elm Institute sent Dataset Maple to external recipient Shoreline on 2026-04-12T12:00:00Z.”
- 资料状态：`d3[152:227]` “TX-03: Dataset Maple was restricted and not lawfully public before sending.”
- 书面批准：`d4[381:543]` “TX-03 approval record: subject Elm Institute; scope Dataset Fir; event TX-03; valid 2026-04-01T00:00:00Z through 2026-04-30T23:59:59Z inclusive UTC; effective no.”
- 法院命令：`d5[373:535]` “TX-03 order record: subject Elm Institute; scope Dataset Maple; event TX-03; valid 2026-04-01T00:00:00Z through 2026-04-30T23:59:59Z inclusive UTC; effective yes.”
- 计算：适用性 external=TRUE AND restricted=TRUE AND NOT public=TRUE => TRUE；批准候选无效项=['scope_match', 'effective']，批准登记完整性=TRUE，批准分支=FALSE；命令候选无效项=[]，命令登记完整性=TRUE，命令分支=TRUE；OR 后满足性=TRUE，最终=COMPLIANT。时间按含端点 UTC 区间核查。
- 缺失范围依据：不需要；未知条件：无。

#### `xf92359101665` → `NOT_APPLICABLE`

- 发生位置：`d2[285:372]` “TX-04: Vale Group sent Dataset Birch to internal archive team on 2026-04-13T08:00:00Z.”
- 资料状态：`d3[228:303]` “TX-04: Dataset Birch was restricted and not lawfully public before sending.”
- 书面批准：`d4[544:704]` “TX-04 approval record: subject Vale Group; scope Dataset Pine; event TX-04; valid 2026-04-01T00:00:00Z through 2026-04-30T23:59:59Z inclusive UTC; effective no.”
- 法院命令：`d5[536:693]` “TX-04 order record: subject Vale Group; scope Dataset Pine; event TX-04; valid 2026-04-01T00:00:00Z through 2026-04-30T23:59:59Z inclusive UTC; effective no.”
- 计算：适用性 external=FALSE AND restricted=TRUE AND NOT public=TRUE => FALSE；批准候选无效项=['scope_match', 'effective']，批准登记完整性=TRUE，批准分支=FALSE；命令候选无效项=['scope_match', 'effective']，命令登记完整性=TRUE，命令分支=FALSE；OR 后满足性=FALSE，最终=NOT_APPLICABLE。时间按含端点 UTC 区间核查。
- 缺失范围依据：不需要；未知条件：无。

**评审提示：**规则例外、完整性和全部四个发生对象均已在公开材料中呈现；请独立确认其足以支持上述结构化 Gold，而非只相信程序映射。

## x0c6e16395eb8 | T2 v2（评审用，模型不见家族/版本/焦点）

**家族变动：**焦点批准、命令均有记录但范围/时间不符，两个登记均完整。  **焦点对象：**`xe379efe00b0b`（仅评审端）。

**审核指令：**Check each of the four sending events under R.1–R.3. Treat missing entries in a partial register as unknown, not absent.

**完整规则：**
- `R.1` A sending obligation applies when material is sent to an external recipient, is restricted, and was not lawfully public before sending.
- `R.2` If applicable, sending requires either prior effective written approval or a valid court order for this same sending.
- `R.3` Approval and order each require matching subject, data scope and sending event, effective status, and sending time inside the UTC validity interval including both endpoints. An incomplete register cannot establish absence; a known valid alternative still suffices.

**统一材料清单：**
- d1: provided; coverage COMPLETE.
- d2: provided; coverage COMPLETE.
- d3: provided; coverage COMPLETE.
- d4: provided; coverage COMPLETE.
- d5: provided; coverage COMPLETE.

**三批公开材料（全文原样）：**
### b1

`d1`：
```text
R.1: A sending obligation applies when material is sent to an external recipient, is restricted, and was not lawfully public before sending.
R.2: If applicable, sending requires either prior effective written approval or a valid court order for this same sending.
R.3: Approval and order each require matching subject, data scope and sending event, effective status, and sending time inside the UTC validity interval including both endpoints. An incomplete register cannot establish absence; a known valid alternative still suffices.
```

`d2`：
```text
TX-01: Orion Labs sent Dataset Cedar to external recipient Northbay on 2026-04-10T10:00:00Z.
TX-02: Cobalt Works sent Dataset Hazel to external recipient Bayfield on 2026-04-11T09:00:00Z.
TX-03: Elm Institute sent Dataset Maple to external recipient Shoreline on 2026-04-12T12:00:00Z.
TX-04: Vale Group sent Dataset Birch to internal archive team on 2026-04-13T08:00:00Z.
```

### b2

`d3`：
```text
TX-01: Dataset Cedar was restricted and not lawfully public before sending.
TX-02: Dataset Hazel was restricted and not lawfully public before sending.
TX-03: Dataset Maple was restricted and not lawfully public before sending.
TX-04: Dataset Birch was restricted and not lawfully public before sending.
```

### b3

`d4`：
```text
Approval register: complete for all listed TX events.
TX-01 approval record: subject Orion Labs; scope Dataset Pine; event TX-01; valid 2026-04-01T00:00:00Z through 2026-04-09T23:59:59Z inclusive UTC; effective yes.
TX-02 approval record: subject Cobalt Works; scope Dataset Hazel; event TX-02; valid 2026-04-01T00:00:00Z through 2026-04-30T23:59:59Z inclusive UTC; effective yes.
TX-03 approval record: subject Elm Institute; scope Dataset Fir; event TX-03; valid 2026-04-01T00:00:00Z through 2026-04-30T23:59:59Z inclusive UTC; effective no.
TX-04 approval record: subject Vale Group; scope Dataset Pine; event TX-04; valid 2026-04-01T00:00:00Z through 2026-04-30T23:59:59Z inclusive UTC; effective no.
```

`d5`：
```text
Order register: complete for all listed TX events.
TX-01 order record: subject Orion Labs; scope Dataset Pine; event TX-01; valid 2026-04-01T00:00:00Z through 2026-04-09T23:59:59Z inclusive UTC; effective no.
TX-02 order record: subject Cobalt Works; scope Dataset Hazel; event TX-02; valid 2026-04-01T00:00:00Z through 2026-04-30T23:59:59Z inclusive UTC; effective yes.
TX-03 order record: subject Elm Institute; scope Dataset Maple; event TX-03; valid 2026-04-01T00:00:00Z through 2026-04-30T23:59:59Z inclusive UTC; effective yes.
TX-04 order record: subject Vale Group; scope Dataset Pine; event TX-04; valid 2026-04-01T00:00:00Z through 2026-04-30T23:59:59Z inclusive UTC; effective no.
```

**逐对象 Gold 与原文：**

#### `xe379efe00b0b` → `VIOLATION`

- 发生位置：`d2[0:93]` “TX-01: Orion Labs sent Dataset Cedar to external recipient Northbay on 2026-04-10T10:00:00Z.”
- 资料状态：`d3[0:75]` “TX-01: Dataset Cedar was restricted and not lawfully public before sending.”
- 书面批准：`d4[54:215]` “TX-01 approval record: subject Orion Labs; scope Dataset Pine; event TX-01; valid 2026-04-01T00:00:00Z through 2026-04-09T23:59:59Z inclusive UTC; effective yes.”
- 法院命令：`d5[51:208]` “TX-01 order record: subject Orion Labs; scope Dataset Pine; event TX-01; valid 2026-04-01T00:00:00Z through 2026-04-09T23:59:59Z inclusive UTC; effective no.”
- 计算：适用性 external=TRUE AND restricted=TRUE AND NOT public=TRUE => TRUE；批准候选无效项=['scope_match', 'time_match']，批准登记完整性=TRUE，批准分支=FALSE；命令候选无效项=['scope_match', 'time_match', 'effective']，命令登记完整性=TRUE，命令分支=FALSE；OR 后满足性=FALSE，最终=VIOLATION。时间按含端点 UTC 区间核查。
- 缺失范围依据：['d4', 'd5']；未知条件：无。

#### `x633d821f3561` → `COMPLIANT`

- 发生位置：`d2[93:188]` “TX-02: Cobalt Works sent Dataset Hazel to external recipient Bayfield on 2026-04-11T09:00:00Z.”
- 资料状态：`d3[76:151]` “TX-02: Dataset Hazel was restricted and not lawfully public before sending.”
- 书面批准：`d4[216:380]` “TX-02 approval record: subject Cobalt Works; scope Dataset Hazel; event TX-02; valid 2026-04-01T00:00:00Z through 2026-04-30T23:59:59Z inclusive UTC; effective yes.”
- 法院命令：`d5[209:370]` “TX-02 order record: subject Cobalt Works; scope Dataset Hazel; event TX-02; valid 2026-04-01T00:00:00Z through 2026-04-30T23:59:59Z inclusive UTC; effective yes.”
- 计算：适用性 external=TRUE AND restricted=TRUE AND NOT public=TRUE => TRUE；批准候选无效项=[]，批准登记完整性=TRUE，批准分支=TRUE；命令候选无效项=[]，命令登记完整性=TRUE，命令分支=TRUE；OR 后满足性=TRUE，最终=COMPLIANT。时间按含端点 UTC 区间核查。
- 缺失范围依据：不需要；未知条件：无。

#### `x8bc1690ccdf4` → `COMPLIANT`

- 发生位置：`d2[188:285]` “TX-03: Elm Institute sent Dataset Maple to external recipient Shoreline on 2026-04-12T12:00:00Z.”
- 资料状态：`d3[152:227]` “TX-03: Dataset Maple was restricted and not lawfully public before sending.”
- 书面批准：`d4[381:543]` “TX-03 approval record: subject Elm Institute; scope Dataset Fir; event TX-03; valid 2026-04-01T00:00:00Z through 2026-04-30T23:59:59Z inclusive UTC; effective no.”
- 法院命令：`d5[371:533]` “TX-03 order record: subject Elm Institute; scope Dataset Maple; event TX-03; valid 2026-04-01T00:00:00Z through 2026-04-30T23:59:59Z inclusive UTC; effective yes.”
- 计算：适用性 external=TRUE AND restricted=TRUE AND NOT public=TRUE => TRUE；批准候选无效项=['scope_match', 'effective']，批准登记完整性=TRUE，批准分支=FALSE；命令候选无效项=[]，命令登记完整性=TRUE，命令分支=TRUE；OR 后满足性=TRUE，最终=COMPLIANT。时间按含端点 UTC 区间核查。
- 缺失范围依据：不需要；未知条件：无。

#### `xf92359101665` → `NOT_APPLICABLE`

- 发生位置：`d2[285:372]` “TX-04: Vale Group sent Dataset Birch to internal archive team on 2026-04-13T08:00:00Z.”
- 资料状态：`d3[228:303]` “TX-04: Dataset Birch was restricted and not lawfully public before sending.”
- 书面批准：`d4[544:704]` “TX-04 approval record: subject Vale Group; scope Dataset Pine; event TX-04; valid 2026-04-01T00:00:00Z through 2026-04-30T23:59:59Z inclusive UTC; effective no.”
- 法院命令：`d5[534:691]` “TX-04 order record: subject Vale Group; scope Dataset Pine; event TX-04; valid 2026-04-01T00:00:00Z through 2026-04-30T23:59:59Z inclusive UTC; effective no.”
- 计算：适用性 external=FALSE AND restricted=TRUE AND NOT public=TRUE => FALSE；批准候选无效项=['scope_match', 'effective']，批准登记完整性=TRUE，批准分支=FALSE；命令候选无效项=['scope_match', 'effective']，命令登记完整性=TRUE，命令分支=FALSE；OR 后满足性=FALSE，最终=NOT_APPLICABLE。时间按含端点 UTC 区间核查。
- 缺失范围依据：不需要；未知条件：无。

**评审提示：**规则例外、完整性和全部四个发生对象均已在公开材料中呈现；请独立确认其足以支持上述结构化 Gold，而非只相信程序映射。

## x3aa1ac1de9a4 | T2 v3（评审用，模型不见家族/版本/焦点）

**家族变动：**状态文件明确焦点资料在发送前已依法公开。  **焦点对象：**`xe379efe00b0b`（仅评审端）。

**审核指令：**Check each of the four sending events under R.1–R.3. Treat missing entries in a partial register as unknown, not absent.

**完整规则：**
- `R.1` A sending obligation applies when material is sent to an external recipient, is restricted, and was not lawfully public before sending.
- `R.2` If applicable, sending requires either prior effective written approval or a valid court order for this same sending.
- `R.3` Approval and order each require matching subject, data scope and sending event, effective status, and sending time inside the UTC validity interval including both endpoints. An incomplete register cannot establish absence; a known valid alternative still suffices.

**统一材料清单：**
- d1: provided; coverage COMPLETE.
- d2: provided; coverage COMPLETE.
- d3: provided; coverage COMPLETE.
- d4: provided; coverage COMPLETE.
- d5: provided; coverage COMPLETE.

**三批公开材料（全文原样）：**
### b1

`d1`：
```text
R.1: A sending obligation applies when material is sent to an external recipient, is restricted, and was not lawfully public before sending.
R.2: If applicable, sending requires either prior effective written approval or a valid court order for this same sending.
R.3: Approval and order each require matching subject, data scope and sending event, effective status, and sending time inside the UTC validity interval including both endpoints. An incomplete register cannot establish absence; a known valid alternative still suffices.
```

`d2`：
```text
TX-01: Orion Labs sent Dataset Cedar to external recipient Northbay on 2026-04-10T10:00:00Z.
TX-02: Cobalt Works sent Dataset Hazel to external recipient Bayfield on 2026-04-11T09:00:00Z.
TX-03: Elm Institute sent Dataset Maple to external recipient Shoreline on 2026-04-12T12:00:00Z.
TX-04: Vale Group sent Dataset Birch to internal archive team on 2026-04-13T08:00:00Z.
```

### b2

`d3`：
```text
TX-01: Dataset Cedar was restricted and lawfully public before sending.
TX-02: Dataset Hazel was restricted and not lawfully public before sending.
TX-03: Dataset Maple was restricted and not lawfully public before sending.
TX-04: Dataset Birch was restricted and not lawfully public before sending.
```

### b3

`d4`：
```text
Approval register: complete for all listed TX events.
TX-01 approval record: subject Orion Labs; scope Dataset Pine; event TX-01; valid 2026-04-01T00:00:00Z through 2026-04-30T23:59:59Z inclusive UTC; effective yes.
TX-02 approval record: subject Cobalt Works; scope Dataset Hazel; event TX-02; valid 2026-04-01T00:00:00Z through 2026-04-30T23:59:59Z inclusive UTC; effective yes.
TX-03 approval record: subject Elm Institute; scope Dataset Fir; event TX-03; valid 2026-04-01T00:00:00Z through 2026-04-30T23:59:59Z inclusive UTC; effective no.
TX-04 approval record: subject Vale Group; scope Dataset Pine; event TX-04; valid 2026-04-01T00:00:00Z through 2026-04-30T23:59:59Z inclusive UTC; effective no.
```

`d5`：
```text
Order register: complete for all listed TX events.
TX-01 order record: subject Orion Labs; scope Dataset Pine; event TX-01; valid 2026-04-01T00:00:00Z through 2026-04-30T23:59:59Z inclusive UTC; effective no.
TX-02 order record: subject Cobalt Works; scope Dataset Hazel; event TX-02; valid 2026-04-01T00:00:00Z through 2026-04-30T23:59:59Z inclusive UTC; effective yes.
TX-03 order record: subject Elm Institute; scope Dataset Maple; event TX-03; valid 2026-04-01T00:00:00Z through 2026-04-30T23:59:59Z inclusive UTC; effective yes.
TX-04 order record: subject Vale Group; scope Dataset Pine; event TX-04; valid 2026-04-01T00:00:00Z through 2026-04-30T23:59:59Z inclusive UTC; effective no.
```

**逐对象 Gold 与原文：**

#### `xe379efe00b0b` → `NOT_APPLICABLE`

- 发生位置：`d2[0:93]` “TX-01: Orion Labs sent Dataset Cedar to external recipient Northbay on 2026-04-10T10:00:00Z.”
- 资料状态：`d3[0:71]` “TX-01: Dataset Cedar was restricted and lawfully public before sending.”
- 书面批准：`d4[54:215]` “TX-01 approval record: subject Orion Labs; scope Dataset Pine; event TX-01; valid 2026-04-01T00:00:00Z through 2026-04-30T23:59:59Z inclusive UTC; effective yes.”
- 法院命令：`d5[51:208]` “TX-01 order record: subject Orion Labs; scope Dataset Pine; event TX-01; valid 2026-04-01T00:00:00Z through 2026-04-30T23:59:59Z inclusive UTC; effective no.”
- 计算：适用性 external=TRUE AND restricted=TRUE AND NOT public=FALSE => FALSE；批准候选无效项=['scope_match']，批准登记完整性=TRUE，批准分支=FALSE；命令候选无效项=['scope_match', 'effective']，命令登记完整性=TRUE，命令分支=FALSE；OR 后满足性=FALSE，最终=NOT_APPLICABLE。时间按含端点 UTC 区间核查。
- 缺失范围依据：不需要；未知条件：无。

#### `x633d821f3561` → `COMPLIANT`

- 发生位置：`d2[93:188]` “TX-02: Cobalt Works sent Dataset Hazel to external recipient Bayfield on 2026-04-11T09:00:00Z.”
- 资料状态：`d3[72:147]` “TX-02: Dataset Hazel was restricted and not lawfully public before sending.”
- 书面批准：`d4[216:380]` “TX-02 approval record: subject Cobalt Works; scope Dataset Hazel; event TX-02; valid 2026-04-01T00:00:00Z through 2026-04-30T23:59:59Z inclusive UTC; effective yes.”
- 法院命令：`d5[209:370]` “TX-02 order record: subject Cobalt Works; scope Dataset Hazel; event TX-02; valid 2026-04-01T00:00:00Z through 2026-04-30T23:59:59Z inclusive UTC; effective yes.”
- 计算：适用性 external=TRUE AND restricted=TRUE AND NOT public=TRUE => TRUE；批准候选无效项=[]，批准登记完整性=TRUE，批准分支=TRUE；命令候选无效项=[]，命令登记完整性=TRUE，命令分支=TRUE；OR 后满足性=TRUE，最终=COMPLIANT。时间按含端点 UTC 区间核查。
- 缺失范围依据：不需要；未知条件：无。

#### `x8bc1690ccdf4` → `COMPLIANT`

- 发生位置：`d2[188:285]` “TX-03: Elm Institute sent Dataset Maple to external recipient Shoreline on 2026-04-12T12:00:00Z.”
- 资料状态：`d3[148:223]` “TX-03: Dataset Maple was restricted and not lawfully public before sending.”
- 书面批准：`d4[381:543]` “TX-03 approval record: subject Elm Institute; scope Dataset Fir; event TX-03; valid 2026-04-01T00:00:00Z through 2026-04-30T23:59:59Z inclusive UTC; effective no.”
- 法院命令：`d5[371:533]` “TX-03 order record: subject Elm Institute; scope Dataset Maple; event TX-03; valid 2026-04-01T00:00:00Z through 2026-04-30T23:59:59Z inclusive UTC; effective yes.”
- 计算：适用性 external=TRUE AND restricted=TRUE AND NOT public=TRUE => TRUE；批准候选无效项=['scope_match', 'effective']，批准登记完整性=TRUE，批准分支=FALSE；命令候选无效项=[]，命令登记完整性=TRUE，命令分支=TRUE；OR 后满足性=TRUE，最终=COMPLIANT。时间按含端点 UTC 区间核查。
- 缺失范围依据：不需要；未知条件：无。

#### `xf92359101665` → `NOT_APPLICABLE`

- 发生位置：`d2[285:372]` “TX-04: Vale Group sent Dataset Birch to internal archive team on 2026-04-13T08:00:00Z.”
- 资料状态：`d3[224:299]` “TX-04: Dataset Birch was restricted and not lawfully public before sending.”
- 书面批准：`d4[544:704]` “TX-04 approval record: subject Vale Group; scope Dataset Pine; event TX-04; valid 2026-04-01T00:00:00Z through 2026-04-30T23:59:59Z inclusive UTC; effective no.”
- 法院命令：`d5[534:691]` “TX-04 order record: subject Vale Group; scope Dataset Pine; event TX-04; valid 2026-04-01T00:00:00Z through 2026-04-30T23:59:59Z inclusive UTC; effective no.”
- 计算：适用性 external=FALSE AND restricted=TRUE AND NOT public=TRUE => FALSE；批准候选无效项=['scope_match', 'effective']，批准登记完整性=TRUE，批准分支=FALSE；命令候选无效项=['scope_match', 'effective']，命令登记完整性=TRUE，命令分支=FALSE；OR 后满足性=FALSE，最终=NOT_APPLICABLE。时间按含端点 UTC 区间核查。
- 缺失范围依据：不需要；未知条件：无。

**评审提示：**规则例外、完整性和全部四个发生对象均已在公开材料中呈现；请独立确认其足以支持上述结构化 Gold，而非只相信程序映射。

## x2cc52577dad0 | T2 v4（评审用，模型不见家族/版本/焦点）

**家族变动：**焦点现有记录无效，命令登记仅为部分摘录；仍可能有未给出的有效命令。  **焦点对象：**`xe379efe00b0b`（仅评审端）。

**审核指令：**Check each of the four sending events under R.1–R.3. Treat missing entries in a partial register as unknown, not absent.

**完整规则：**
- `R.1` A sending obligation applies when material is sent to an external recipient, is restricted, and was not lawfully public before sending.
- `R.2` If applicable, sending requires either prior effective written approval or a valid court order for this same sending.
- `R.3` Approval and order each require matching subject, data scope and sending event, effective status, and sending time inside the UTC validity interval including both endpoints. An incomplete register cannot establish absence; a known valid alternative still suffices.

**统一材料清单：**
- d1: provided; coverage COMPLETE.
- d2: provided; coverage COMPLETE.
- d3: provided; coverage COMPLETE.
- d4: provided; coverage COMPLETE.
- d5: provided; coverage PARTIAL.

**三批公开材料（全文原样）：**
### b1

`d1`：
```text
R.1: A sending obligation applies when material is sent to an external recipient, is restricted, and was not lawfully public before sending.
R.2: If applicable, sending requires either prior effective written approval or a valid court order for this same sending.
R.3: Approval and order each require matching subject, data scope and sending event, effective status, and sending time inside the UTC validity interval including both endpoints. An incomplete register cannot establish absence; a known valid alternative still suffices.
```

`d2`：
```text
TX-01: Orion Labs sent Dataset Cedar to external recipient Northbay on 2026-04-10T10:00:00Z.
TX-02: Cobalt Works sent Dataset Hazel to external recipient Bayfield on 2026-04-11T09:00:00Z.
TX-03: Elm Institute sent Dataset Maple to external recipient Shoreline on 2026-04-12T12:00:00Z.
TX-04: Vale Group sent Dataset Birch to internal archive team on 2026-04-13T08:00:00Z.
```

### b2

`d3`：
```text
TX-01: Dataset Cedar was restricted and not lawfully public before sending.
TX-02: Dataset Hazel was restricted and not lawfully public before sending.
TX-03: Dataset Maple was restricted and not lawfully public before sending.
TX-04: Dataset Birch was restricted and not lawfully public before sending.
```

### b3

`d4`：
```text
Approval register: complete for all listed TX events.
TX-01 approval record: subject Orion Labs; scope Dataset Pine; event TX-01; valid 2026-04-01T00:00:00Z through 2026-04-30T23:59:59Z inclusive UTC; effective yes.
TX-02 approval record: subject Cobalt Works; scope Dataset Hazel; event TX-02; valid 2026-04-01T00:00:00Z through 2026-04-30T23:59:59Z inclusive UTC; effective yes.
TX-03 approval record: subject Elm Institute; scope Dataset Fir; event TX-03; valid 2026-04-01T00:00:00Z through 2026-04-30T23:59:59Z inclusive UTC; effective no.
TX-04 approval record: subject Vale Group; scope Dataset Pine; event TX-04; valid 2026-04-01T00:00:00Z through 2026-04-30T23:59:59Z inclusive UTC; effective no.
```

`d5`：
```text
Order register: partial extract for TX-01; additional entries may exist.
TX-01 order record: subject Orion Labs; scope Dataset Pine; event TX-01; valid 2026-04-01T00:00:00Z through 2026-04-30T23:59:59Z inclusive UTC; effective no.
TX-02 order record: subject Cobalt Works; scope Dataset Hazel; event TX-02; valid 2026-04-01T00:00:00Z through 2026-04-30T23:59:59Z inclusive UTC; effective yes.
TX-03 order record: subject Elm Institute; scope Dataset Maple; event TX-03; valid 2026-04-01T00:00:00Z through 2026-04-30T23:59:59Z inclusive UTC; effective yes.
TX-04 order record: subject Vale Group; scope Dataset Pine; event TX-04; valid 2026-04-01T00:00:00Z through 2026-04-30T23:59:59Z inclusive UTC; effective no.
```

**逐对象 Gold 与原文：**

#### `xe379efe00b0b` → `INSUFFICIENT_EVIDENCE`

- 发生位置：`d2[0:93]` “TX-01: Orion Labs sent Dataset Cedar to external recipient Northbay on 2026-04-10T10:00:00Z.”
- 资料状态：`d3[0:75]` “TX-01: Dataset Cedar was restricted and not lawfully public before sending.”
- 书面批准：`d4[54:215]` “TX-01 approval record: subject Orion Labs; scope Dataset Pine; event TX-01; valid 2026-04-01T00:00:00Z through 2026-04-30T23:59:59Z inclusive UTC; effective yes.”
- 法院命令：`d5[73:230]` “TX-01 order record: subject Orion Labs; scope Dataset Pine; event TX-01; valid 2026-04-01T00:00:00Z through 2026-04-30T23:59:59Z inclusive UTC; effective no.”
- 计算：适用性 external=TRUE AND restricted=TRUE AND NOT public=TRUE => TRUE；批准候选无效项=['scope_match']，批准登记完整性=TRUE，批准分支=FALSE；命令候选无效项=['scope_match', 'effective']，命令登记完整性=UNKNOWN，命令分支=UNKNOWN；OR 后满足性=UNKNOWN，最终=INSUFFICIENT_EVIDENCE。时间按含端点 UTC 区间核查。
- 缺失范围依据：不需要；未知条件：['xe379efe00b0b:order_registry_complete']。

#### `x633d821f3561` → `COMPLIANT`

- 发生位置：`d2[93:188]` “TX-02: Cobalt Works sent Dataset Hazel to external recipient Bayfield on 2026-04-11T09:00:00Z.”
- 资料状态：`d3[76:151]` “TX-02: Dataset Hazel was restricted and not lawfully public before sending.”
- 书面批准：`d4[216:380]` “TX-02 approval record: subject Cobalt Works; scope Dataset Hazel; event TX-02; valid 2026-04-01T00:00:00Z through 2026-04-30T23:59:59Z inclusive UTC; effective yes.”
- 法院命令：`d5[231:392]` “TX-02 order record: subject Cobalt Works; scope Dataset Hazel; event TX-02; valid 2026-04-01T00:00:00Z through 2026-04-30T23:59:59Z inclusive UTC; effective yes.”
- 计算：适用性 external=TRUE AND restricted=TRUE AND NOT public=TRUE => TRUE；批准候选无效项=[]，批准登记完整性=TRUE，批准分支=TRUE；命令候选无效项=[]，命令登记完整性=UNKNOWN，命令分支=TRUE；OR 后满足性=TRUE，最终=COMPLIANT。时间按含端点 UTC 区间核查。
- 缺失范围依据：不需要；未知条件：无。

#### `x8bc1690ccdf4` → `COMPLIANT`

- 发生位置：`d2[188:285]` “TX-03: Elm Institute sent Dataset Maple to external recipient Shoreline on 2026-04-12T12:00:00Z.”
- 资料状态：`d3[152:227]` “TX-03: Dataset Maple was restricted and not lawfully public before sending.”
- 书面批准：`d4[381:543]` “TX-03 approval record: subject Elm Institute; scope Dataset Fir; event TX-03; valid 2026-04-01T00:00:00Z through 2026-04-30T23:59:59Z inclusive UTC; effective no.”
- 法院命令：`d5[393:555]` “TX-03 order record: subject Elm Institute; scope Dataset Maple; event TX-03; valid 2026-04-01T00:00:00Z through 2026-04-30T23:59:59Z inclusive UTC; effective yes.”
- 计算：适用性 external=TRUE AND restricted=TRUE AND NOT public=TRUE => TRUE；批准候选无效项=['scope_match', 'effective']，批准登记完整性=TRUE，批准分支=FALSE；命令候选无效项=[]，命令登记完整性=UNKNOWN，命令分支=TRUE；OR 后满足性=TRUE，最终=COMPLIANT。时间按含端点 UTC 区间核查。
- 缺失范围依据：不需要；未知条件：无。

#### `xf92359101665` → `NOT_APPLICABLE`

- 发生位置：`d2[285:372]` “TX-04: Vale Group sent Dataset Birch to internal archive team on 2026-04-13T08:00:00Z.”
- 资料状态：`d3[228:303]` “TX-04: Dataset Birch was restricted and not lawfully public before sending.”
- 书面批准：`d4[544:704]` “TX-04 approval record: subject Vale Group; scope Dataset Pine; event TX-04; valid 2026-04-01T00:00:00Z through 2026-04-30T23:59:59Z inclusive UTC; effective no.”
- 法院命令：`d5[556:713]` “TX-04 order record: subject Vale Group; scope Dataset Pine; event TX-04; valid 2026-04-01T00:00:00Z through 2026-04-30T23:59:59Z inclusive UTC; effective no.”
- 计算：适用性 external=FALSE AND restricted=TRUE AND NOT public=TRUE => FALSE；批准候选无效项=['scope_match', 'effective']，批准登记完整性=TRUE，批准分支=FALSE；命令候选无效项=['scope_match', 'effective']，命令登记完整性=UNKNOWN，命令分支=UNKNOWN；OR 后满足性=UNKNOWN，最终=NOT_APPLICABLE。时间按含端点 UTC 区间核查。
- 缺失范围依据：不需要；未知条件：无。

**评审提示：**规则例外、完整性和全部四个发生对象均已在公开材料中呈现；请独立确认其足以支持上述结构化 Gold，而非只相信程序映射。

## A/B/C 索引与潜在侧信道

- A 只有完整公开材料；B 额外获得全部对象位置；T2 C 再获得每对象固定五类原文区域：规则、事项、资料状态、批准、命令。T1 C 禁止。
- 8 个案例 ID 和对象 ID 是固定种子生成的不透明哈希，名称不含结论；模型不见 `family_id`、`variant_id`、焦点、Gold、状态、依赖或评审备注。
- T2 C 所有版本、所有对象均有 5 个候选，顺序恒为 d1–d5；无空列表、`NO_MATCH`、候选缺失哨兵或正例优先排序。批准与命令中始终保留有效和无效记录。
- 统一清单每案同格式；T1 d1 完整/部分、T2 d5 完整/部分本身是判定所必需的公开事实。版本间正文长度会因真实的条款/状态变化而不同，不能机械保证等长；这仍是需人工关注的侧信道和可读性权衡。
- 生成时曾发现 T1 的 PARTIAL 情形会错误地使已出现的其他条款也变成证据不足；已修正为‘出现即可证存在，未出现须完整范围才证不存在’，并加入回归测试。

## 尚需独立人工判断

1. 每案是否真的只含列出的四个适用发生对象；自然语言对象全集不能由程序绝对证明。
2. 公开英文文字是否足以证明 Gold 中的每个结构化事实、例外及登记完整性；有无事实冲突或歧义。
3. C 的位置索引及正文长度是否形成不可接受的答案侧信道；虽无显式标签，仍是诊断性 Oracle 辅助。
4. T2 条件关联是否足够困难，是否仍可被浅层关键词猜中。
5. 后续被测模型、费用上限与调用授权仍未确定。
