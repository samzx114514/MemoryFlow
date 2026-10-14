# C5F Frozen Dev Rescore and Finalization

Status: PASS. Six frozen checkpoints were rescored on Dev only with FP32 eager attention, `torch.no_grad()`, no optimizer, no backward and no generation. Blind was not accessed.

## Checkpoints

| checkpoint | Hit@1 | MRR | nDCG@5 | Recall@5 | all-positive loss | AUROC | AUPRC | Anchor norm |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| A5 | 0.320175 | 0.526493 | 0.541566 | 0.763226 | 2.148437 | 0.550049 | 0.295372 | 0.432916 |
| A6 | 0.328947 | 0.535093 | 0.542052 | 0.755185 | 2.154829 | 0.553916 | 0.302576 | 0.468542 |
| C4 | 0.364035 | 0.576958 | 0.581699 | 0.781469 | 2.107694 | 0.613192 | 0.335071 | 3.806621 |
| C5 | 0.342105 | 0.568150 | 0.565224 | 0.757785 | 2.146717 | 0.607098 | 0.329941 | 4.210004 |
| C6 | 0.289474 | 0.530869 | 0.536925 | 0.739761 | 2.209547 | 0.588465 | 0.318446 | 4.583283 |
| D5 | 0.302632 | 0.518510 | 0.517811 | 0.712495 | 2.214132 | 0.541692 | 0.297640 | 3.664886 |

Dev denominator: 228 targets, 1,824 candidate edges, 496 positive and 1,328 negative edges. Random baseline: Hit@1 0.271930, MRR 0.484381, Recall@5 0.625000, nDCG@5 0.457392.

## Metric consistency
The exact scorer ranking uses the frozen `stable_tolerance_ranking` rule with tolerance 1e-6. All six checkpoint aggregate metrics match the committed C5F metrics within 1e-9. C4 MRR is reconciled after applying the registered near-tie rule.

## Derived terminal states
A latest=6/best=6: MAX_EPOCH. B latest=4/best=2: PATIENCE_2. C latest=6/best=4: PATIENCE_2_AND_MAX_EPOCH. D latest=5/best=3: PATIENCE_2.

## Dev selection and K1
Final Dev winner: config C epoch 4.

K1 nDCG@5: 0.581699 (margin +0.010077); MRR: 0.576958 (margin +0.028054); AUPRC: 0.335071 (margin +0.006981).

The original C5F state files remain unchanged; these terminal states and inventory are derived artifacts. No Blind content, labels, scores or hashes were accessed.
