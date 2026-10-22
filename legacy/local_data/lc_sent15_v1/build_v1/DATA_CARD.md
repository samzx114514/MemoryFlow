# LC-Sent-15-v1 Data Card

## Source

- Dataset: `zai-org/LongCite-45k`
- Revision: `b776b01faf6e132a3d9cc373de1b46cd6630d772`
- Official payload: `long.jsonl`
- Size: `5,726,201,192` bytes
- SHA-256: `8eb96dad6496d8d28d983982e6f623adc1e44ffa9dce215ffc7d56fd0336623b`
- License: Apache-2.0
- Raw fields: `prompt`, `response`

The source was parsed line by line. It was never loaded into memory as one object.

## Unit definitions

- Document/context: the complete ordered set of official `<C#>` units between `[Document Start]` and `[Document End]`.
- Document ID: SHA-256 of the exact ordered `(official index, exact unit text)` sequence.
- Instance ID: the stable row index in the pinned official JSONL revision.
- Target: exact `<statement>` content after removing its one `<cite>…</cite>` markup block.
- Source: one exact official numbered `<C#>` unit. Citation `[12-14]` therefore produces C12, C13 and C14 as three Sources.

No semantic label repair, re-sentencing, model scoring, embedding, BM25, Qwen, GPU, Blind data, historical processed data, or mixed catalog was used.

## Internal split

The official payload is a single pool. Exact-context document IDs are assigned by a SHA-derived value:

- Train: `[0.00, 0.66)`
- Dev: `[0.66, 0.84)`
- Reserve: `[0.84, 1.00)`

Assignment is frozen before Target filtering. Within each split, eligible single-positive Targets are ordered by a stable SHA-256 selection key and truncated to 854/228/218.

## Main-track counts

| Split | Targets | Pairs | Target documents | Catalog Sources |
|---|---:|---:|---:|---:|
| Train | 854 | 12,810 | 826 | 1,313,148 |
| Dev | 228 | 3,420 | 220 | 360,610 |
| Reserve | 218 | 3,270 | 208 | 3,264 |

Train language counts are 599 `zh` and 255 `en`; Dev counts are 164 `zh` and 64 `en`. Language is inferred from the query: any CJK character gives `zh`; otherwise any Latin letter gives `en`; otherwise `other`.

## Multi-positive sidecar

- Train: 97,532 Targets and 1,462,980 pairs.
- Dev: 26,880 Targets and 403,200 pairs.
- Reserve multi-positive text is not exported.

The sidecar retains every positive and is excluded when positives exceed 15 or there are too few same-document negatives to reach 15 candidates.

## Known limitations

- Labels are Silver citation mappings, not human Gold.
- Official `<C#>` units are preserved even when a unit contains multiple natural-language sentences or layout noise.
- Exact IDs do not cross splits. Nevertheless, repeated boilerplate across distinct document hashes creates normalized-text overlaps: 15 Target texts, 5,023 Source texts, and 17 normalized Target–Source pairs overlap between Train and Dev. These were reported rather than silently deleted or used to alter the frozen document split.
- Reserve is sealed and must remain inaccessible during development.
