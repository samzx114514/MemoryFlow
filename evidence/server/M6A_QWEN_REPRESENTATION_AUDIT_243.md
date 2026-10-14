# M6A Qwen Native Representation Audit

## Scope
Only conservative Train/Dev data were read. No model parameters were trained, no backward or generate was called, and no Blind path was accessed.

## Representation contract
- `F_mean`: the existing frozen Qwen mean-pool formatter: raw chunk text, tokenizer default special-token behavior, final hidden state, attention-mask mean, float32 storage; cosine uses row L2 normalization and dot uses raw hidden vectors.
- `F_im_end`: the same raw chunk text tokenized without automatic special tokens, truncated to leave room, then one native `<|im_end|>` token appended. The final hidden state at that actual anchor position is used. Padding is ignored.
- Qwen2.5-7B: hidden size 3584, 28 layers, 28 query heads, 4 KV heads, config dtype BF16; extraction was FP32 eager forward-only.
- `<|im_end|>` is existing EOS/special token ID 151645; embedding norm 0.0104735745.
- Current trained Anchor is an independent shared parameter initialized from that embedding row: `A = E_im_end + delta`, with delta initially zero and drift measured against the initial row. It does not update the embedding table.
- Therefore training a full-dimensional native-token delta is mathematically a reparameterization of the current Anchor when injected at the same positions. Updating the embedding-table row would additionally change every occurrence of that token and is not equivalent operationally.

## Data integrity
- Train: 854 targets / 6832 candidate edges; Dev: 228 targets / 1824 edges = 496 positive + 1328 negative; source catalog: 10400 rows.
- Candidate membership/order, labels and split were loaded from the frozen conservative files; hashes are recorded in `data_integrity.json` and match the C5F data binding.

## Dev zero-training metrics
| method | Hit@1 | MRR | nDCG@5 | Recall@5 | AUROC | AUPRC |
|---|---:|---:|---:|---:|---:|---:|
| F_mean_cosine | 0.438596 | 0.595598 | 0.568610 | 0.702073 | 0.503559 | 0.363948 |
| F_mean_dot | 0.263158 | 0.480509 | 0.468256 | 0.636722 | 0.468814 | 0.285885 |
| F_im_end_cosine | 0.350877 | 0.558782 | 0.550289 | 0.706803 | 0.567235 | 0.316224 |
| F_im_end_dot | 0.364035 | 0.555697 | 0.540355 | 0.681730 | 0.543704 | 0.292149 |

## Existing formal Dev-only comparisons
| method | Hit@1 | MRR | nDCG@5 | Recall@5 | AUROC | AUPRC |
|---|---:|---:|---:|---:|---:|---:|
| bm25 | 0.710526 | 0.789907 | 0.738026 | 0.797321 | 0.537420 | 0.397567 |
| qwen_frozen_mean_pool | 0.429825 | 0.591197 | 0.565402 | 0.696590 | 0.505204 | 0.363802 |
| c4_trained_anchor | 0.364035 | 0.576958 | 0.581699 | 0.781469 | 0.613192 | 0.335071 |

F_mean cosine is close to, but not bit-identical with, the prior frozen mean-pool aggregate: the new extraction is FP32, while the prior formal Qwen scorer was BF16. The current result is therefore recorded as a protocol-consistent reproduction with a dtype-induced numerical difference, not silently declared identical.

## Cache
- `feature_index.jsonl`: 22964 rows; all feature arrays are float32 with shape `[rows, 3584]`.
- Source cache: 10400 rows for each representation. Train target cache: 854 rows. Dev target cache: 228 rows.
- Cache manifest binds model manifest, all six data hashes, feature file SHA256, index SHA256, extraction contract and GPU/runtime metadata.
- Same-batch forward recheck on 8 Dev targets reproduced both cached representations with max absolute error 0.0 for F_mean and 0.0 for F_im_end; all sampled values were finite.

## Recommendation
For M6B, prefer F_mean cosine as the initial direction-aware readout input: it has the stronger Dev ranking and edge-free baseline among the two frozen representations, while F_im_end cosine does not improve on it. The cache is sufficient for a later Train/Dev-only Linear/MLP study, but this does not establish that an MLP will generalize or that labels are gold.

## Limitations
- LongCite labels remain silver. No none-of-the-above conclusion is possible here.
- Dev comparison is not a held-out final test and no Blind result was consulted.
- Raw dot products are scale-sensitive and behaved differently from cosine; they should not be treated as equivalent metrics.
