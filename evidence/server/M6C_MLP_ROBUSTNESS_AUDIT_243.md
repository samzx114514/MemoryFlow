# M6C MLP Leakage, Shortcut and Robustness Audit

This is a Train/Dev-only audit. Qwen was not loaded. No Blind path was opened,
hashed, parsed, or scored. The result is **ROBUSTNESS_CONDITIONAL**.

## Frozen contract and runtime

- M6A cache manifest: `cea1a8ecc3d869439d783fc720b55cc0182b52fc44b4d1e09f4448ada63ff3bd`.
- M6A feature index: `8f66d98fbbca4ef1e54e0e2389f01fd1dcaeb55715b3d508f7470a02c8dd9b0d`.
- M6B champion/config/LR hashes are recorded in `freeze_manifest.json`.
- Input is exactly ordered `target, source, target*source, abs(target-source), cosine`; no IDs, slots, labels, split fields, BM25/C4 scores, or aggregate statistics enter the model.
- Train/Dev: 854/228 targets and 6,832/1,824 candidate edges.
- Dynamic selection chose physical GPU3 (`cuda:3`), max allocated 123,635,712 bytes; Qwen was not loaded.
- M6B architecture/LR/objective/seed choices were frozen. Ablation and CV diagnostics used a full-train-group batch to avoid repeated mask construction; this is recorded in `audit_summary.json`.

## Leakage and overlap

No target-ID, candidate-set, exact pair, document-group, or connected-component overlap was found. Source IDs also did not overlap between the candidate sets. There were 2 normalized source-text hashes shared across Train/Dev, so source-text reuse is not literally zero. No target text hash overlap was found. Complete counts are in `leakage_audit.json`.

## Position audit

The position-only Dev baseline was Hit@1=0.2807 and MRR=0.4763. Frozen M-RANK/M-EDGE candidate permutation changed no candidate membership, but maximum mapped-logit drift was 1.907e-6 and 3.099e-6 respectively. This is a small numerical batch-order effect, but it exceeds the provisional 1e-6 audit tolerance and is retained as a limitation; it is not evidence of slot leakage.

## Frozen champions

M-RANK: Hit@1=0.7807, MRR=0.8613, nDCG@5=0.8282, Recall@5=0.8829, AUROC=0.7190, AUPRC=0.5025.

M-EDGE: Hit@1=0.6886, MRR=0.8166, nDCG@5=0.8076, Recall@5=0.8954, AUROC=0.7474, AUPRC=0.5396.

## Negative controls

Corrected controls were run with three seeds and the actual permutation arrays passed into training. NC1 label permutation gave M-RANK H1/MRR/AUPRC = 0.2427/0.4573/0.2602 and M-EDGE = 0.2880/0.4958/0.3373. NC2 target permutation gave M-RANK = 0.3801/0.5797/0.3368 and M-EDGE = 0.3567/0.5571/0.3505. NC3 source-pair permutation gave M-RANK = 0.2310/0.4537/0.2785 and M-EDGE = 0.2880/0.4976/0.3363. NC1/NC3 are near or below random; NC2 is degraded but remains above random, so a residual target/candidate or dataset shortcut cannot be ruled out.

## Component ablations

Three-seed means (H1/MRR/nDCG/AUROC/AUPRC):

| input | M-RANK | M-EDGE |
|---|---|---|
| target only | .2675/.4734/.4300/.5033/.2772 | .2675/.4734/.4300/.5433/.3211 |
| source only | .3962/.5963/.5937/.5909/.3401 | .3465/.5538/.5419/.6217/.3708 |
| symmetric | .7105/.8049/.7674/.6515/.4429 | .6974/.8041/.7802/.6833/.5014 |
| full ordered | .7456/.8357/.7912/.6697/.4582 | .6608/.7821/.7611/.6535/.4700 |

Target-only is near random; source-only has real signal but is weaker than full. Symmetric is strong and close to full, so directionality is not proven necessary. No single component alone explains the full gain.

## Group CV and bootstrap

Five document-group folds used fixed 50 epochs with no Dev early stopping or selection. M-RANK mean across folds was H1=.7165, MRR=.8103, nDCG=.7664, AUROC=.6447, AUPRC=.4373. M-EDGE was H1=.6968, MRR=.8008, nDCG=.7701, AUROC=.7235, AUPRC=.5335. Fold group overlap was zero.

The new 5,000-replicate target-group bootstrap is diagnostic because Dev selected the champions. M-RANK minus BM25 MRR=.0749, 95% CI [.0276,.1234], nDCG=.1067, CI [.0645,.1530]. Against C4, MRR=.2836 CI [.2276,.3377], nDCG=.2462 CI [.1997,.2931]. Against F_mean, MRR=.2657 CI [.2172,.3135], nDCG=.2596 CI [.2165,.3050]. M-EDGE minus BM25 AUROC=.1156 CI [.0757,.1555], AUPRC=.0370 CI [-.0070,.0820]; against C4 AUROC=.1981 CI [.1583,.2389], AUPRC=.2444 CI [.1973,.2923]; against F_mean AUROC=.2437 CI [.2008,.2890], AUPRC=.2112 CI [.1688,.2535]. Exact prior M6B 2,000-replicate intervals are preserved inside `bootstrap_results.json`. The bootstrap unit is target group, not edge.

## Decision boundary

The audit is **ROBUSTNESS_CONDITIONAL**, not `ROBUSTNESS_PASS`: leakage fields were absent, group CV and three seeds support a real signal, and label/source-pair controls degrade. However, the remaining NC2 performance, two repeated source-text hashes, the small permutation drift, and the near-parity of symmetric/full inputs prevent a clean claim that the gain is purely generalizable directional semantics. LongCite labels remain silver and have no native no-source examples.

Lexical-semantic fusion is **not** authorized by this audit. First resolve the NC2 shortcut and repeat on an independent, group-disjoint evaluation. No Blind conclusion is made.

M6B did not record matching Train ranking/edge metrics, so Train–Dev gaps are `NOT_RECORDED` in `train_dev_gap.json`; no gap was inferred.

All detailed artifacts, checksums, and the final status are in `workspace/results/m6c_mlp_robustness_audit_243_v1/`.
