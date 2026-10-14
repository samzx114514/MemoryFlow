# LC-Sent-15-Q1C R-SYM Convergence Closure

- Resume path: **B_RETRAIN_PREFIX**, because Q1 had no epoch-30 model/optimizer/RNG resume state.
- Prefix reproduction tolerance: 1e-08; see `PREFIX_REPRODUCTION.json`.
- Convergence state: `Q1_CONVERGENCE_CLOSED`.
- Transfer gate: `RSYM_TRANSFER_CONDITIONAL`; 90% target: `INTERPRETABLE_90_TARGET_NOT_REACHED`.
- Dev R-SYM Hit@1=0.754385964912, BM25=0.684210526316, CI=[0.0, 0.14035087719298234].

No Qwen, Blind, Reserve, multi-positive, or mixed catalog was accessed.
