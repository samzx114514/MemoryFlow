# M6B Direction-Aware Linear/MLP Competition 243

Train/Dev-only. No Qwen weights were loaded, no feature cache was modified, and no Blind path was accessed.

## Reconciliation
Candidate membership/order/labels matched 1824/1824 edges. Comparing raw per-candidate scores (not the prior candidate-normalized mass), maximum absolute difference is 0.116616, mean 0.008173, and Top-1 disagreed on 16/228 targets. The documented source is M6A FP32 extraction versus the prior BF16 scorer; the M6A `F_mean_M6A` contract remains frozen.

## Fixed models
LinearPair: 14,338 parameters. MLPPair: 1,835,393 parameters. Input is ordered concat(target, source, target*source, abs(target-source), cosine), with separately L2-normalized float32 target/source features. AdamW, weight decay 1e-4, batch 32 candidate groups, max 50 epochs, patience 5, gradient clip 1.0.

## Three-seed final results
| variant | seed | lr | best epoch | Hit@1 | MRR | nDCG@5 | Recall@5 | AUROC | AUPRC | edge F1 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| L-RANK | 0 | 0.001 | 37 | 0.7807 | 0.8613 | 0.8251 | 0.8796 | 0.7171 | 0.5325 | 0.5134 |
| L-RANK | 1 | 0.001 | 7 | 0.7632 | 0.8457 | 0.8057 | 0.8631 | 0.6842 | 0.4787 | 0.4873 |
| L-RANK | 2 | 0.001 | 8 | 0.7632 | 0.8454 | 0.8046 | 0.8631 | 0.6817 | 0.4763 | 0.4831 |
| M-RANK | 0 | 0.0003 | 15 | 0.7807 | 0.8613 | 0.8282 | 0.8829 | 0.7190 | 0.5025 | 0.5178 |
| M-RANK | 1 | 0.0003 | 11 | 0.7939 | 0.8678 | 0.8280 | 0.8783 | 0.7141 | 0.5131 | 0.5074 |
| M-RANK | 2 | 0.0003 | 9 | 0.7895 | 0.8645 | 0.8245 | 0.8743 | 0.7094 | 0.5116 | 0.5027 |
| L-EDGE | 0 | 0.0001 | 7 | 0.6623 | 0.7797 | 0.7578 | 0.8444 | 0.6528 | 0.4775 | 0.4585 |
| L-EDGE | 1 | 0.0001 | 6 | 0.6798 | 0.7915 | 0.7614 | 0.8418 | 0.6564 | 0.4715 | 0.4604 |
| L-EDGE | 2 | 0.0001 | 10 | 0.6623 | 0.7828 | 0.7598 | 0.8521 | 0.6508 | 0.4734 | 0.4592 |
| M-EDGE | 0 | 0.001 | 21 | 0.6886 | 0.8166 | 0.8076 | 0.8954 | 0.7474 | 0.5396 | 0.5305 |
| M-EDGE | 1 | 0.001 | 8 | 0.7018 | 0.8233 | 0.8120 | 0.8944 | 0.7315 | 0.5325 | 0.5360 |
| M-EDGE | 2 | 0.001 | 7 | 0.7105 | 0.8288 | 0.8117 | 0.8893 | 0.7263 | 0.5293 | 0.5258 |

## Fixed baselines (Dev)
| method | Hit@1 | MRR | nDCG@5 | Recall@5 | AUROC | AUPRC |
|---|---:|---:|---:|---:|---:|---:|
| BM25 | 0.7105 | 0.7899 | 0.7380 | 0.7973 | 0.5374 | 0.3976 |
| C4_Anchor | 0.3640 | 0.5770 | 0.5817 | 0.7815 | 0.6132 | 0.3351 |
| F_mean_M6A_cosine | 0.4386 | 0.5956 | 0.5686 | 0.7021 | 0.5036 | 0.3639 |
| Qwen_mean_pool | 0.4298 | 0.5912 | 0.5654 | 0.6966 | 0.5052 | 0.3638 |
| Random | 0.2719 | 0.4844 | 0.4574 | 0.6250 | 0.0000 | 0.0000 |

## Selection and bootstrap
Ranking and edge champions are separate. Selection uses only the preregistered track comparator. `bootstrap_results.json` contains 2000 target-group resamples for ranking MRR/nDCG and edge AUROC/AUPRC against BM25, F_mean_M6A and C4. Dev thresholds are diagnostics only; there are no Blind thresholds.

## Limits
The dataset has no native no-source examples, so BCE does not establish None-of-the-above. Lexical-semantic fusion is not tested in M6B.
