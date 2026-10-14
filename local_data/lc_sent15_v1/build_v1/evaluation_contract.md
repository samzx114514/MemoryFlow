# LC-Sent-15-v1 Evaluation Contract

## Label meaning

All citation mappings are `silver_longcite`: they reproduce LongCite-45k's official citation indices and are not human-verified factual Gold. The task ranks official numbered context units for one cited response statement.

## Single-positive main track

- Candidate count: exactly 15.
- Positive count: exactly 1.
- Primary metric: Hit@1.
- Secondary metrics: MRR and nDCG@5.
- Random Hit@1 baseline: `1/15 = 0.066666…`.
- Scores are sorted descending; exact score ties use ascending `candidate source_id` as the second key.
- BM25 uses its raw score by default. Any group-normalized BM25 result is a separately named protocol and must not replace raw BM25 silently.
- Overall metrics must retain the ability to report `zh` and `en` strata using the frozen query-language rule.

## Multi-positive sidecar

The sidecar is not part of the first 90% Hit@1 experiment. It retains every valid positive Source and uses exactly 15 candidates when all positives and sufficient same-document negatives fit.

Report MRR, AUPRC, Set Precision, Set Recall, Set F1, and Exact-set Accuracy. Do not mix these values with single-positive Hit@1.

## Candidate policy

- Source units are official `<C#>` units; no re-sentencing, half-sentence cutting, adjacent merging, or range-as-one-chunk transformation is permitted.
- Negatives are uncited units from the same exact context only.
- Negative membership and final order use independent SHA-256-derived seeds recorded in `build_summary.json`.
- Candidate position is a manifest order only and may not be used as a model feature.

## Split discipline

Train, Dev, and Reserve are assigned at exact-context document SHA level before Target selection. Reserve is sealed, excluded from readable samples and remote transfer, and may not be used for method selection, threshold selection, hyperparameter tuning, or interim evaluation.
