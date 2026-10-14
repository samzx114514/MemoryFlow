# LC-Sent-15-v1 BM25 Gate

Marker: `MEMORYFLOW_LC_SENT15_BM25_HEADROOM_PASS`, `LANGUAGE_STRATIFICATION_REQUIRED`

Strongest frozen BM25: `BM25_LEGACY`.

## Contract
- Query: target statement only.
- Documents: the fixed 15 candidate source texts per target.
- Ranking: score descending, then source_id ascending.
- No Qwen, GPU, embedding, training, Reserve, multi-positive, or Blind access.

## Metrics
### BM25_LEGACY
- Dev overall: Hit@1=0.684211, MRR=0.746968, nDCG@5=0.743273.
- Dev zh (164): Hit@1=0.603659; en (64): Hit@1=0.890625.
### BM25_MIXED_V1
- Dev overall: Hit@1=0.684211, MRR=0.746968, nDCG@5=0.743273.
- Dev zh (164): Hit@1=0.603659; en (64): Hit@1=0.890625.
