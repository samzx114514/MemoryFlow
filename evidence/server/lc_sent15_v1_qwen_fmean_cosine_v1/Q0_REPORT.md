# LC-Sent-15-Q0 Frozen Qwen F_mean Cosine

## Contract
- Fixed attempt-2 cache scoring only; no Qwen loaded, no GPU used, no training.
- F_mean cache stores FP32 last-layer attention-mask means; rows L2 normalized and scored by cosine.
- Tie: score descending, source_id ascending.

## Numerical limitation
- The historical cross-batch audit remains `MEMORYFLOW_LC_SENT15_Q0_NUMERICAL_STABILITY_FAIL`: changed batch composition can perturb cosine scores around 1e-5 and may alter rare near ties.
- Correction: its minimum vector cosine 0.999999762 is greater than 0.999999.
- R2 fixed batch contract reproduced all Dev Top-1 and Gold ranks exactly.

## Dev
- Qwen Hit@1 0.451754385965, MRR 0.595358491411, nDCG@5 0.619915724799.
- BM25 Hit@1 0.684210526316.
