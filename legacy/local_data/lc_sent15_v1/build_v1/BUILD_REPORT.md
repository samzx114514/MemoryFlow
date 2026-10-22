# LC-Sent-15-v1 Build Report

Marker: `MEMORYFLOW_LC_SENT15_V1_READY`

## Source and parser gate

The pinned official source was rechecked at 5,726,201,192 bytes and SHA-256 `8eb96dad6496d8d28d983982e6f623adc1e44ffa9dce215ffc7d56fd0336623b`.

The mandatory 20-example parser audit passed after individual review. Range expansion, separated ranges, exact official-unit replay, Chinese/English text, and repeated Source reuse were all observed. LongCite mappings remain `silver_longcite`.

## Full parse

- JSONL lines: 44,600.
- Successfully parsed rows: 44,599.
- Row-level format errors: 1 (`duplicate_source_index`).
- Statement records: 450,851.
- Malformed statements: 20 (18 invalid cite-tag counts; 2 reversed ranges).
- No-citation statements skipped: 163,521.
- Single-positive eligible: 133,126.
- Single-positive ineligible: 608, all because the context had fewer than 15 valid official units.
- Multi-positive eligible: 148,534.
- Multi-positive ineligible: 5,042 (4,859 with more than 15 positives; 183 with insufficient same-document negatives).

No malformed label was repaired.

## Main track

| Split | Assigned documents | Eligible single Targets | Selected Targets | Selected documents | Pairs |
|---|---:|---:|---:|---:|---:|
| Train | 25,750 | 87,854 | 854 | 826 | 12,810 |
| Dev | 7,070 | 23,975 | 228 | 220 | 3,420 |
| Reserve | 6,314 | 21,297 | 218 | 208 | 3,270 |

All three quantity gates passed without cross-split movement.

## Language

- Train: `zh=599`, `en=255`.
- Dev: `zh=164`, `en=64`.
- No language was filtered.

## Positive positions

Train positions 0–14: `[63,59,64,66,54,45,49,52,64,58,52,59,55,56,58]`.

Dev positions 0–14: `[18,13,14,18,12,16,15,16,17,10,19,16,13,16,15]`.

Every slot is populated; the positive is not fixed to one position.

## Isolation and duplicate audit

Cross-split intersections for document ID, Target ID, Source ID and candidate pair ID are all zero. Train/Dev/Reserve files are physically separated, and no Reserve readable example exists.

Normalized exact-text hashes are not IDs. Repeated text across distinct document groups was retained and reported:

- Train/Dev normalized Target overlap: 15.
- Train/Dev normalized Source overlap: 5,023.
- Train/Dev normalized Target–Source pair overlap: 17.
- Train/Reserve normalized Target/Source/pair overlaps: 2/108/0.
- Dev/Reserve normalized Target/Source/pair overlaps: 0/67/0.

The deterministic rule is to preserve the exact-context SHA split and report these overlaps. No sample was silently removed and no split was altered using content, language, difficulty or model score.

## Validation

- Parser and artifact suite: 20 passed.
- Full independent rebuild: passed.
- Deterministic payload SHA comparison: 12/12 files matched exactly.
- Source and Target candidate invariants: passed.
- Six complete readable examples: present (three Train, three Dev).
- Reserve excluded from normal samples and migration inputs: passed.

No model, training, GPU, BM25, embedding, Qwen, Attention, Blind, sealed historical data, old processed data or 243 mixed catalog was used.
