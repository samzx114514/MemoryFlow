# MemoryFlow Project Context

> Canonical living context for all local and remote Codex sessions.
>
> Last verified update: 2026-08-29
>
> Status: Pure R-SYM remains the frozen LongCite-selected baseline; M7 fusion is conditional and M8 paused. The 2026-08-13 meeting authorized one bounded LongCite optimization sprint before returning to SP citation provenance: rebuild a clean sentence-level 15-candidate protocol, freeze interpretable accuracy and edge metrics, audit head/loss choices, then test DFAMS-style internal representations only if cheaper controls justify them. Existing SP logs remain raw material rather than semantic Gold. HDT stays an isolated baseline-study side track. Blind remains blocked.

C5D was launched on 2026-08-07 using two authorized 49 GB GPUs as two serial queues: GPU4 runs A then C, and GPU5 runs B then D. All four configs have frozen SHA256-bound configuration files, isolated result/log directories, independent tmux sessions, and epoch-boundary resume support. A/B are active and C/D are queued; no Blind artifact was accessed. Results live under `workspace/results/c5d_full_calibration_10025_v1/` on server 10025.

Latest C5D snapshot: A and B completed after four committed epochs; C and D were training after two committed epochs on GPU4/GPU5, each using about 40.2 GB with no OOM, NaN, traceback, or checkpoint error. A/B have valid `COMPLETED` markers, but their `current_state.json` files remain stale at `RUNNING`. This is a bookkeeping inconsistency to audit after all jobs stop; it is not currently evidence of invalid training and must not be patched while C/D are using the shared runner.

C5D execution is now complete: A/B/D committed four epochs and selected epoch 2; C committed three epochs and selected epoch 1. Every configuration has a `COMPLETED` marker, best Anchor, epoch checkpoints, optimizer/RNG state, and SHA256 files; no `FAILED`, OOM, NaN, Inf, traceback, or checkpoint-write error was found. GPU4/GPU5 are released. All four `current_state.json` files remain stale at `RUNNING`, confirming a shared finalization-metadata bug; raw files should remain unchanged and the discrepancy should be documented in the final integrity report.

C5D finalization found that the training runner recorded Dev all-positive loss but omitted Dev Hit@1, MRR, nDCG@5, Recall@5, AUROC, AUPRC, Anchor norm, and Train-Dev gap. The reported `K3 — CALIBRATION_FAILS` is therefore an evaluation-incompleteness label, not scientific evidence that calibration failed. All 15 committed epoch checkpoints remain valid (A4+B4+C3+D4). Before any Blind access or method redesign, every epoch checkpoint must be rescored on Dev with the frozen formal method, and the pre-registered epoch/config selection rule must then be applied.

C5E Dev rescoring has been launched on server 10025 with two isolated forward-only queues: GPU4 scores A1-A4 and C1-C3, while GPU5 scores B1-B4 and D1-D4. The inventory contains all 15 committed checkpoints, tests passed, model weights remain frozen, no optimizer/backward/generation is used, per-checkpoint results are atomic/resumable, and Blind access is explicitly blocked. Outputs are under `workspace/results/c5e_dev_rescore_10025/`.

C5E completed all 15 Dev rescores. The best observed epochs are A3 (`nDCG=.5329`), B2 (`.5587`), C3 (`.5707`), and D3 (`.5699`). C3 is the provisional winner and improves over C5B by `+0.0115` MRR and `+0.0091` nDCG while reducing Anchor norm from `13.46` to `3.34`; however AUPRC falls by `0.0156`. It narrowly misses the pre-registered K1 gates (`nDCG` short by about `.00092`; `AUPRC` short by about `.00562`). C and D are effectively close on Dev and require the predefined stopping schedule rather than an ad hoc choice.

The current decision is `K0 — SELECTION_CENSORED`, because C's ranking peak is its final committed epoch and training stopped on Dev loss instead of the pre-registered ranking metric. Under patience 2, A and D also have only one post-peak non-improving ranking epoch and therefore require continuation; B has two and is complete. Continue A/C/D from their exact optimizer/RNG epoch states up to max epoch 6, using nDCG/MRR/loss for stopping and recording the full Dev metrics after every new epoch. Blind remains forbidden.

The shared C5E `checkpoint_inventory.csv` contains only B/D rows due to a parallel-writer metadata race, but all A/C per-checkpoint C5D SHA values, scoring SHA values, and C5E integrity records agree. Reconstruct a derived immutable inventory from the per-checkpoint artifacts; do not modify the raced original CSV or rerun completed scoring.

Server 10025 migration audit (initially mislabeled `M0-10023`) found: the project and Qwen2.5-7B model are structurally complete; an existing compatible Python environment is available; eight RTX 4090-class GPUs report approximately 49,140 MiB each; C5D configuration A has unauditable epoch 1-3 partial checkpoints and B/C/D were not started. The partial A artifacts must not be resumed or used for final selection because their config/log/seed/hash binding is incomplete.

The exact-method M1 gate on server 10025 passed (`F0 — SINGLE_GPU_SAFE`) on GPU4. For the longest Train packed sequence (908 tokens), Forward peak allocated memory was 33.78 GB and Backward/optimizer peak was 41.38 GB, leaving approximately 9.45 GiB. The Anchor update, model-freeze checks, mask checks, EOS-copy initialization, FP32 Anchor, and formal Attention aggregation all passed. Existing audit artifacts remain under the historically misnamed `migration_audit_10023/` directory; this path is retained as a legacy label and future artifacts should use `10025`.

The new GPUs are not ordinary 24 GB cards. Historical C5D0 peak allocated memory was about 43.7 GB, so one 49 GB card may fit the unchanged method with a narrow margin. Multiple cards do not automatically combine memory under the current single-device code. If a one-card exact-method memory gate passes, the preferred use of four GPUs is independent parallel execution of configurations A-D, one complete model per GPU. If the gate fails, model parallelism/FSDP would require a separate correctness-equivalence checkpoint.

## 1. Project Goal

MemoryFlow aims to recover a directed Chunk-level information-flow matrix from multi-Agent memories. The proposed mechanism gives every Chunk a unified Anchor representation and reads `Target Anchor -> Source Anchor` Attention under a structured mask. Multiple candidate relations are packed into one white-box model forward to reduce the cost of pairwise verification.

The intended evidence chain is:

1. **Edge signal:** the recovered score ranks or classifies real information dependencies.
2. **Faithfulness:** scores survive counterfactual deletion/replacement and are not merely lexical overlap or raw Attention artifacts.
3. **Efficiency:** packed evaluation is faster than strong pairwise batched evaluation.
4. **Downstream value:** the recovered matrix improves citation checking, error attribution, or another concrete multi-Agent task.

Current work only partially establishes items 1 and 3 on a citation-ranking proxy. It has not established a complete multi-Agent semantic provenance system.

## 2. Current Audited Method

Checkpoint: `C4B-Method-Audit`

| Item | Verified implementation |
|---|---|
| Base model | Qwen2.5-1.5B-Instruct |
| Hidden size / layers / heads | 1536 / 28 / 12 |
| Anchor position token | Existing `<|im_end|>`, token ID `151645` |
| Vocabulary expansion | None |
| Trainable object | Independent shared `trainable_anchor`, shape `[1536]` |
| Injection | `inputs_embeds`; Source and Target use the same vector |
| Trainable parameters | 1536 total |
| Loss | All-positive distribution cross-entropy + `1e-4` Anchor drift regularization |
| Generation loss | None |
| SFT | No |
| `generate()` / autoregressive decode | Not used |
| Packed inference | One full Transformer forward per Target per method |
| Pairwise sequential | N forwards for N candidates |
| Pairwise batched | One batched forward containing independent pairs |

The program inserts Anchor positions deterministically. The model does not generate Anchors or reproduce the input text.

The current method is best described as a one-vector, shared soft Anchor/input-embedding tuning method with Attention-based ranking readout.

The exact audited artifacts are on the remote server:

- `/home/songzhengxing_intern/work/codex_files/smallest_experiment/workspace/reports/C4A_METHOD_CONTRACT.md`
- `/home/songzhengxing_intern/work/codex_files/smallest_experiment/workspace/results/c4a_method_audit/method_audit.json`

## 3. Data and Evaluation Tasks

### 3.1 LongCite Proxy

LongCite is used as a controlled citation-source recovery proxy, not as the final multi-Agent benchmark.

Approximate expanded data:

| Split | Targets |
|---|---:|
| Train | 854 |
| Dev | 228 |
| Blind | 218 |

Candidate sizes are 8, 16, and 32. Candidate labels are Silver citation labels. Every current candidate set contains at least one positive.

Three tasks must not be conflated:

- **Ranking:** rank at least one positive above candidates.
- **Edge detection:** classify each `(Target, Source)` pair as edge/non-edge.
- **None-of-the-above:** allow a Target to have no valid Source in the candidate set.

The current LongCite data supports ranking and retrospective pair-level edge evaluation. It does not contain valid native none-of-the-above examples.

### 3.2 SP Logs

Local raw-log export produced:

| Item | Count |
|---|---:|
| Cases | 253 |
| Structurally complete Cases | 243 |
| Nodes | 5898 |
| Query | 253 |
| Retrieval Observation | 292 |
| Outline | 251 |
| Report Paragraph | 3712 |
| Other workflow nodes | 1390 |

Local files:

- `F:/CodexProject/MemoryFlow/smallest_experiment/data/sp_natural_v1_raw/sp_nodes.jsonl`
- `F:/CodexProject/MemoryFlow/smallest_experiment/data/sp_natural_v1_raw/manifest.json`
- `F:/CodexProject/MemoryFlow/smallest_experiment/data/sp_natural_v1_raw/checksums.sha256`

Important limitation: recovered explicit edges are workflow/containment relations, not semantic provenance.

Pilot-20 audit:

| Relation | Count |
|---|---:|
| Workflow edges | 108 |
| Containment edges | 445 |
| Existing semantic provenance edges | 0 |
| Report paragraphs requiring semantic annotation | 445 |

There are no automatically recoverable `Observation -> Report Paragraph` or `Outline -> Report Paragraph` Gold edges. Report citation numbers cannot be resolved to stable Observation IDs. The current SP export is a useful node/workflow corpus, but not a semantic-edge training benchmark.

## 4. Verified LongCite Results

### 4.1 Size-8 Ranking

Primary blind view:

| Method | Hit@1 | Recall@5 | MRR | nDCG@5 |
|---|---:|---:|---:|---:|
| Random | 0.259 | 0.625 | 0.471 | 0.451 |
| BM25 | 0.775 | 0.806 | 0.834 | 0.771 |
| Qwen mean pool | 0.459 | 0.716 | 0.599 | 0.580 |
| Token Attention | 0.229 | 0.524 | 0.421 | 0.386 |
| Frozen EOS | 0.284 | 0.600 | 0.479 | 0.454 |
| Trained Anchor | 0.376 | 0.705 | 0.569 | 0.546 |

Interpretation:

- Training the Anchor improves over Frozen EOS and ordinary Token Attention.
- Recall@5 is not a strong headline at size 8 because its random expectation is 0.625.
- Trained Anchor remains below Qwen mean-pool and far below BM25 on this lexical citation proxy.
- `0.376` is citation-source ranking Hit@1, not generation accuracy or end-to-end SP success.

### 4.2 Candidate-Scale Behavior

Trained Anchor, Primary blind:

| Candidate size | Hit@1 | Recall@5 | MRR |
|---:|---:|---:|---:|
| 8 | 0.376 | 0.705 | 0.569 |
| 16 | 0.217 | 0.397 | 0.391 |
| 32 | 0.116 | 0.235 | 0.252 |

The decline is not mathematically inevitable: BM25 and Qwen mean-pool are substantially more stable. Diagnostics show both softmax competition and Target Anchor representation drift when candidates are added.

### 4.3 Edge Detection

Trained Anchor, Primary blind:

| Candidate size | Positive / Negative edges | AUROC | AUPRC |
|---:|---:|---:|---:|
| 8 | 452 / 1292 | 0.563 | 0.318 |
| 16 | 451 / 3021 | 0.553 | 0.163 |
| 32 | 446 / 6434 | 0.543 | 0.081 |

Interpretation: current Anchor scores provide weak binary-edge separation, and edge detection degrades as the candidate set becomes more imbalanced. C4A saved blind scores but not dev per-candidate scores, so no threshold may be selected on blind. Dev scores are required before reporting precision, recall, F1, or a frozen threshold.

### 4.4 Dev-Selected Threshold Evaluation

Checkpoint `C4D-Dev-Scoring-Threshold` generated 125,600 document-disjoint Dev candidate scores. Thresholds were selected only on Dev and then frozen for Blind evaluation.

Trained Anchor, Primary Blind:

| Candidate size | Precision | Recall | F1 | AUROC | Predict-all-positive F1 |
|---:|---:|---:|---:|---:|---:|
| 8 | 0.270 | 0.912 | 0.416 | 0.563 | 0.412 |
| 16 | 0.146 | 0.541 | 0.230 | 0.553 | 0.230 |
| 32 | 0.088 | 0.166 | 0.115 | 0.543 | 0.122 |

Interpretation: the Dev-selected threshold gives almost no F1 gain over predicting every candidate as an edge at sizes 8 and 16, and is worse at size 32. The current method is a weak relative ranker and is not yet a useful sparse-edge detector. None-of-the-above remains unsupported on current LongCite.

### 4.5 Packed Efficiency and Equivalence

Packed speedup for 30 Targets:

| Candidate size | vs sequential pairwise | vs batched pairwise | Packed peak memory |
|---:|---:|---:|---:|
| 8 | 6.40x | 2.02x | 6.33 GiB |
| 16 | 8.14x | 3.03x | 7.92 GiB |
| 32 | 8.25x | 3.28x | 14.52 GiB |

Packed is clearly faster, including against batched pairwise, but is not accuracy-equivalent to pairwise. On the 30-Target comparison, Top-1 agreement is 0.467 and Kendall tau is 0.459.

### 4.6 Controlled 7B Model-Scale Result

Checkpoint `C5B-Qwen7B-Controlled` kept candidate size 8, data, mask, readout, loss, seed, and training protocol fixed while changing Qwen2.5-1.5B-Instruct to Qwen2.5-7B-Instruct.

Primary Blind:

| Method | 1.5B Hit@1 | 7B Hit@1 | 1.5B MRR | 7B MRR |
|---|---:|---:|---:|---:|
| Qwen frozen mean pool | 0.459 | 0.505 | 0.599 | 0.656 |
| Trained Anchor | 0.376 | 0.321 | 0.569 | 0.526 |

The 7B mean-pool improvement is statistically supported for MRR (`+0.057`, 95% CI `[+0.027,+0.089]`) and nDCG@5 (`+0.045`, CI `[+0.018,+0.074]`). In contrast, the trained Anchor point estimate became worse: Hit@1 `-0.055` with CI `[-0.136,+0.022]`, and MRR `-0.043` with CI `[-0.100,+0.008]`. These Anchor differences are not statistically conclusive, but they do not support model scale as the current fix.

The 7B Anchor fits Train strongly but generalizes weakly: Train Hit@1 `0.505`, Dev `0.333`, and Blind `0.321`. Its norm grew from `0.0105` to `13.464`, while its final cosine similarity with the EOS embedding was only `0.014`. With learning rate `0.01` and drift regularization `1e-4`, this is a warning that the Anchor optimization is poorly calibrated or overfitting.

The trained 7B Anchor remains a weak edge detector. Primary Blind predicted-edge density is `0.818` while true density is `0.259`; Edge F1 is `0.417`, only slightly above predict-all-positive F1 `0.412`.

The maximum tested sequence length was 908 tokens. Forward and backward peak memory were approximately 41.0 and 41.8 GB on one A800 80GB, with no OOM.

Protocol note: the inherited preflight script read the Blind file SHA256 before training, but did not read Blind text, labels, or metrics for model selection. The first Blind scoring attempt failed before writing and was rerun with the same frozen checkpoint and threshold. This is a procedural deviation requiring an audit note, not currently evidence of semantic Blind leakage.

### 4.7 C5C Protocol and Optimization Audit

The Blind audit concluded `P1`: only the Blind file SHA256 was computed before training; Blind JSON, text, labels, and metrics were not parsed for selection. The failed first scoring attempt did not change the checkpoint, Dev threshold, data, or scoring configuration. The existing Blind result is usable with a documented procedural-deviation note.

The optimization audit exposed a new comparability issue:

| Model | Initial Anchor norm | Best Anchor norm | Growth | First-step gradient norm | First-step update norm |
|---|---:|---:|---:|---:|---:|
| Qwen2.5-1.5B | 0.4220 | 5.1151 | 12.12x | 2.8101 | 0.3919 |
| Qwen2.5-7B | 0.01047 | 13.4644 | 1285.8x | 10.9915 | 0.5987 |

Because the initial Anchor norms differ by roughly 40x, the previous model-scale comparison may not have held Anchor initialization scale fixed. Before running the proposed learning-rate/regularization grid, the exact initialization code, distribution, reference vector, and drift-loss formula must be audited. The 7B result remains valid for its tested configuration, but it is not yet a perfectly isolated model-scale ablation if initialization policy differed.

C5C.1 confirmed that both models used the same policy: copy the model's own `<|im_end|>` embedding into a trainable FP32 Anchor. Therefore the experiment is controlled at the policy level (`I1`), but the pretrained EOS scales differ strongly and the same AdamW learning rate produces very different relative first steps. For 7B, the first update norm `0.5987` was about 57x its initial norm `0.01047`; for 1.5B, `0.3919` was about 0.93x its initial norm `0.4220`.

The drift term is `lambda * mean((anchor - initial_anchor)^2)`. At the recorded best 7B Anchor, the estimated raw MSE is about `0.05058`. Consequently, `lambda=1e-4`, `1e-3`, and `1e-2` contribute only approximately `5e-6`, `5e-5`, and `5e-4`, respectively, versus a ranking loss around `1.9`. The originally proposed `1e-3/1e-2` grid is therefore too weak to meaningfully test drift control. Approximate meaningful candidates under the current mean reduction are `lambda=1` and `lambda=10`.

### 4.8 C5D0 Short Learning-Rate Pilot

A 50-optimizer-step, Train/Dev-only Qwen2.5-7B pilot compared learning rates `1e-4`, `3e-4`, `1e-3`, and `3e-3` while retaining EOS-copy initialization and the original negligible drift coefficient. No Blind artifact was read.

| LR | Step-1 update / initial norm | Step-50 Anchor norm | Dev MRR | Dev nDCG@5 | Dev AUPRC |
|---:|---:|---:|---:|---:|---:|
| 0.0001 | 0.57x | 0.0490 | 0.5220 | 0.5312 | 0.3046 |
| 0.0003 | 1.71x | 0.1485 | 0.5515 | 0.5476 | 0.3154 |
| 0.0010 | 5.72x | 0.5188 | 0.5386 | 0.5374 | 0.3142 |
| 0.0030 | 17.15x | 1.4573 | 0.5519 | 0.5476 | 0.3110 |

All settings were finite, leak-free, and kept the base model frozen. `3e-4` and `3e-3` were selected for the full calibration because they expose a useful stability/speed contrast. This pilot does not itself beat or replace the complete C5B baseline: its best short-run Dev nDCG@5 `0.5476` is below C5B's best-epoch `0.5616`.

## 5. Stable Conclusions

Supported:

1. A trained shared Anchor learns more citation-ranking signal than Frozen EOS or ordinary Token Attention in the current size-8 setting.
2. Packed evaluation gives a material throughput advantage over sequential and batched pairwise baselines.
3. The current ranking formulation is candidate-set dependent and does not directly solve sparse edge detection.
4. The current SP logs contain rich workflow nodes but no directly recoverable semantic provenance Gold.
5. Scaling the frozen base model from 1.5B to 7B improves mean-pooled semantic representations, but does not improve the current trained-Anchor method.
6. The 7B Anchor shows substantial norm drift and a Train-to-Dev/Blind gap, making optimization and generalization the next bottlenecks to diagnose.
7. The Blind protocol deviation did not expose semantic Blind information and does not invalidate the current frozen result.

Not supported:

1. Anchor Attention is already a reliable multi-Agent information-flow matrix.
2. Packed and pairwise scoring are accuracy-equivalent.
3. The method supports a calibrated global threshold or none-of-the-above.
4. The current LongCite Hit@1 is directly comparable to a collaborator's reported 0.8 precision/recall without protocol alignment.
5. File separators, multiple Anchors, or LoRA have been shown to fix the problem.
6. The current 7B result proves that all larger models are ineffective; it only shows that 7B does not help under the present Anchor training configuration.

## 6. Research Decisions

| Decision | Reason |
|---|---|
| Keep LongCite as the current main experimental line | The 2026-08-04 meeting requested raising and understanding this result before moving to SP experiments |
| Keep SP as a data-preparation side line | Data are valuable, but semantic edge labels are absent |
| Correct evaluation before running 7B | Threshold and random-baseline issues change how results must be interpreted |
| Run model scale as a one-variable experiment | Do not mix 7B, token type, Anchor count, and candidate-size training |
| Stop model scaling after the controlled 7B result | The model itself improved, but the trained Anchor did not; capacity is not the immediate bottleneck |
| Audit and calibrate Anchor optimization before structural ablations | The 7B Anchor norm expanded by over three orders of magnitude and shows a clear generalization gap |
| Do not use Blind again during calibration | Select learning rate and regularization only on Train/Dev; preserve Blind for a final frozen confirmation |
| Audit Anchor initialization before the optimizer grid | 1.5B and 7B initial Anchor norms differ by about 40x, so the scale comparison may contain a second changing variable |
| Treat length-aware packing as lower priority | Accuracy and edge validity are currently the bottlenecks |
| Defer collaborator-result alignment | First complete the project's own controlled 7B and method diagnosis |
| Let Anchor, native-Qwen representation and embedding Adapter/MLP variants compete as method candidates | Anchor-Attention is an initial hypothesis, not a protected conclusion. A materially better reproducible method may become the main method, but its mechanism must be described honestly and compared under the same protocol |
| Finish the censored C5F continuation before another Blind read | C3 improves Dev ranking and controls drift, but A/C/D were stopped using Dev loss rather than the pre-registered ranking rule |
| Return canonical remote execution to server 243 after a staged handoff | 10025 contains unique C5D/C5E code and results that must be checksum-verified before merge; environments/models/caches should not be copied |
| Select GPUs dynamically rather than by fixed index | Server occupancy changes; each job must choose any card meeting its measured peak plus safety margin without disturbing external processes |
| Maintain portable core/resume handoff profiles | Future servers may replace 243/10025; code, non-Blind Train/Dev state and compact artifacts should move safely while models/environments remain external requirements |
| Treat the P0 scientific-contract audit as core-complete but sample-lineage-blocked | Counts, losses and unified metrics are verified; the only missing full examples require an unsafe mixed Blind-containing catalog, so the correct recovery is a fresh local non-Blind dataset build rather than reopening M8 |
| Run a bounded meeting-driven LongCite optimization sprint before SP | The senior requested an interpretable accuracy target, a sentence-level 15-candidate task, loss/head ablations and DFAMS-inspired representations; these must be evaluated under a newly frozen protocol before agent-specific provenance work resumes |
| Stop LC-Sent-15-v1 when the official raw payload is absent | The local source gate found no fixed-revision LongCite-45k payload and correctly refused processed-data substitution; acquire the exact official `long.jsonl` and bind its checksum before construction |
| Decouple LongCite source identity from transport | Both local and 243 official single-connection routes are too slow; a mirror or parallel range transport is acceptable only if the final 5,726,201,192-byte file exactly matches the official Git LFS SHA256 `8eb96dad6496d8d28d983982e6f623adc1e44ffa9dce215ffc7d56fd0336623b` |
| Accept the locally sealed LongCite-45k source | Parallel transport completed and an independent full-file recheck matched both the official 5,726,201,192-byte size and Git LFS SHA256; the source schema is `prompt`/`response`, so LC-Sent-15-v1 construction is now unblocked |
| Accept LC-Sent-15-v1 but slim the first remote package | The reproducible c15 single-positive Train/Dev/Reserve tracks pass all ID-level isolation gates, but the full multi-positive sidecar expands catalogs to over 1.67M Sources and the current duplicate counts combine both tracks; first audit and package only the 16,230 single-track pairs and their referenced Sources |
| Promote the LC-Sent-15-v1 baseline core to remote import | The 2.89 MiB create-only archive contains only the 16,230 single-track pairs and referenced catalogs, has no positive-text/pair leakage, and matches SHA256 `9fd6746f5d4ef2c276ad46283f3ff61c2fa2d8e97e33734f9520ad076e38eb6b`; run BM25 before any Qwen encoding because short/layout-noise negatives may make the random-negative protocol easy |
| Pass the LC-Sent-15-v1 BM25 headroom gate | The create-only 243 import reverified all c15 counts and exclusions. Both frozen BM25 implementations reach Dev Hit@1 `.6842` (156/228), MRR `.7470` and nDCG@5 `.7433`, below the preregistered `.90` easy-task threshold, so v1 has sufficient headroom for the next frozen-Qwen baseline. Zh/en Hit@1 is `.6037`/`.8906` over 164/64 Targets, requiring stratified reporting. Preserve v1 and do not switch to hard-negative construction at this gate. |
| Complete LC-Sent-15 Q0 and reject raw F_mean cosine as a strong standalone baseline | Frozen Qwen F_mean cosine reaches Dev Hit@1 `.451754`, MRR `.595358` and nDCG@5 `.619916`, significantly below BM25 on all three paired bootstrap comparisons. It contributes 13 Qwen-only correct Targets but misses 66 that BM25 gets right, so semantic features retain complementary signal but require a learned relation scorer. The canonical fixed-batch cache contract is reproducible; cross-batch composition can perturb cosine scores by about `1e-5` and a few near ties, which remains a disclosed numerical limitation. |
| Treat the Q1 R-SYM c15 transfer as promising but convergence-censored | The exact frozen M6D Ranking recipe reaches three-seed Dev Hit@1 `.754386`, MRR `.827306` and nDCG@5 `.843610`. It significantly improves MRR/nDCG over BM25, while the Hit@1 CI lower bound is exactly zero, yielding `RSYM_TRANSFER_CONDITIONAL`. Best epochs 29/30/30 under patience 5 mean every seed is selection-censored and two peak at the epoch cap. Preserve Q1 unchanged and close convergence in a separate run before comparing heads or losses. |
| Accept Q1C as the convergence-closed R-SYM c15 baseline | A from-scratch deterministic rerun reproduced all first-30-epoch Q1 values exactly, then all seeds satisfied patience 5 at epochs 34/35/35 while retaining best epochs 29/30/30. Q1C metrics and bootstrap intervals are identical to Q1, eliminating the selection-censoring concern without changing the scientific conclusion. Head/loss comparison may now begin from this sealed baseline. |
| Treat Q2 D-Full-64 plus listwise CE as the leading but conditional Dev candidate | The complete 3-head x 3-loss x 3-seed matrix shows linear scoring is inadequate, nonlinear interaction is necessary, and listwise CE is the best overall objective. At nearly the same parameter count as R-SYM, retaining Target/Source roles raises Dev Hit@1 from `.754386` to `.780702`, but the paired CI crosses zero and the Train-Dev gap expands from about `.044` to `.091`. The directionality signal is promising, not yet a frozen final-method win. Run one bounded Full-128 capacity control before representation changes; keep Reserve sealed. |
| Stop D-Full capacity scaling after Q2C | Doubling the direction-aware head to 1,835,393 parameters changes Dev Hit@1 by only `+.001462`, with CI `[-.004386,.007310]`, and slightly increases the Train-Dev gap. D-Full-64 is therefore the preferred capacity point. The next cheap evidence step is Train-OOF lexical-semantic fusion, motivated by the substantial BM25/neural error complementarity; do not repeat loss experiments or open Reserve. |
| Promote Q3 fusion as the strongest current Dev system, not the final novel method | Train-five-fold OOF freezes alpha `.65` before Dev. The resulting D-Full-64/BM25 fusion reaches `.831871` Hit@1 and significantly improves both components. English crosses `.90`, but zh remains `.804878`, and the seed-1 component oracle union is only `.890351`. Further hand-designed fusion tuning has limited headroom; proceed to a Train-selected internal-layer representation ablation while keeping Reserve sealed. |
| Recover Q4A after confirming double final RMSNorm | D1 proved that `last_hidden_state`/`hidden_states[-1]` are already final-normalized in the pinned runtime and the first extractor normalized them again. No OOF or Dev selection used the invalid caches. Preserve that failed lineage, copy Q0 as canonical R28, and regenerate R7/R14/R21/R_LAST4 together in one correct forward pass before resuming Train-OOF selection. |
| Resume Q4A with bounded CUDA memory after confirming hook retention | V4 OOM came from accumulating detached CUDA hook outputs across Source batches. R5 moves pooled features to CPU, shows stable post-warm-up allocation in a 50-batch audit, and writes fixed-order batch-8 features in atomic 512-item chunks with a 12 GiB GPU margin. This changes execution safety only, not the representation contract. |
| Reprioritize toward report-generation transfer after the 2026-08-22 meeting | The paper contribution must center on Agent information-flow modeling, not internal-layer/neuron selection. Finish only the bounded Q4A recovery if useful, then obtain a fast zero-shot `Document -> Researcher Memory Summary` score before further LongCite optimization or DFAMS-style work. |
| Use `all_samples.json` for a two-track Summary pilot | The supplied file has 10 Chinese queries and 139 document slots (138 non-empty), but no Summary outputs. Track A generates one fixed-prompt Summary per unique non-empty document and gives a fast, optimistic provenance-by-construction Hit@1 test. Track B adapts the collaborator code to concatenate each full document group and generate 10 realistic multi-document Researcher Summaries for clause-to-document citation evaluation. Track A is a smoke test, not the final Summary claim. |
| Treat the collaborator attention method as a later complementary baseline | *From Attention to Attribution* uses a probed generation-time attention head, clause-to-source normalize-then-sum aggregation and a peak-minus-entropy decision. The supplied code lacks the selected head artifact, so its 200-example head probe must not block the first post-hoc MemoryFlow transfer score. |
| Replace synthetic Track B with real SP2.0 trajectories as the primary report-generation evidence | Track B was a coordinator-created adapter that concatenated documents and asked Qwen to simulate a Researcher Summary; it is useful only as a smoke test and may make methods look artificially similar. The primary dataset should rerun `all_samples.json` queries through SP2.0 and export retrieved sources, Researcher observations and final reports with stable run/call/source IDs. SP2.0 is used as a data generator, not optimized as part of MemoryFlow. |
| Close the synthetic Summary transfer pilot as smoke evidence | Track A completed on 137 unique Targets and is nearly saturated by BM25 (Hit@1 `.9416`), ahead of fusion `.8954`, R-SYM `.7129`, D-Full `.7032` and Qwen `.5912`; it mainly rewards direct lexical overlap. Track B produced 10 synthetic multi-document Summaries/143 clauses but has no Gold, so its method agreements are diagnostic rather than accuracy. Preserve the artifacts and stop optimizing this pilot. |
| Use stable SP1.0 rather than SP2.0 for real trajectory generation | The user reports unstable SP2.0 generation and selected `PKU-SIS/Stack-Planner@zb_demo_v11`, recommended by the senior as a relatively stable SP1.0 version. Run query-only natural trajectories and capture Source/Researcher Summary/Reporter state; do not optimize Stack-Planner as the MemoryFlow contribution. This supersedes the SP2.0 choice above without changing the intended benchmark semantics. |
| Replace long-lived remote Codex with a local SSH execution Codex | A dedicated local execution session operates 243 using preconfigured credentials, while the local coordinator owns research reasoning, prompt design, audits and context. Credentials stay outside prompts/logs/repos; the worker executes bounded checkpoints and returns ambiguity rather than inventing scientific decisions. |

## 7. Active Work Queue

### Immediate Mainline

1. Preserve the completed Track A/B outputs as smoke tests; do not spend the next iteration on their optional Judge.
2. Have the local SSH execution Codex clone and inspect `PKU-SIS/Stack-Planner@zb_demo_v11` on 243 under a new directory, record the exact commit, and report environment/config/secret requirements without exposing secret values.
3. Configure credentials outside prompts and tracked files, pass a minimal health check, then run one `all_samples.json` query through SP1.0 as a trace-schema gate.
4. If Source IDs/text, Researcher observations, visible inputs and Reporter output are recoverable, freeze the schema and run the remaining nine queries; otherwise add only the smallest create-only exporter/logger patch and repeat the gate query.
5. Build the real Source-to-Summary benchmark from SP1 traces and compare Random, BM25, Qwen cosine, frozen R-SYM/D-Full and fixed fusion. Report point estimates and denominators first; do not force a unique Gold for unlabeled multi-source calls.
6. Diagnose disagreements before adapting training, then build Summary-to-Reporter mappings. Do not optimize SP1.0 itself. Q4A and the collaborator citation-head probe are secondary; do not expand DFAMS neuron search or open LongCite Reserve/Blind.

### Subsequent Ablations

1. Pre-softmax or independent edge-logit objectives if optimizer calibration does not repair Dev ranking and edge separation.
2. Existing separator versus current soft Anchor initialization.
3. Anchor count 1 versus 2 versus 4 with normalized aggregation.
4. Fixed-N versus mixed-N training over 8/16/32 candidates.
5. Length bucketing/first-fit-decreasing across independent examples without changing candidate membership.

### SP Later Track

1. Decide whether to annotate a small subset of `Observation -> Report Paragraph` edges.
2. Prefer explicit citation-ID mapping if future logs expose stable IDs.
3. Do not run an Anchor semantic-edge benchmark on the current workflow/containment labels.

## 8. Open Questions from the Latest Meeting

| Question | Status | Required evidence |
|---|---|---|
| What exactly is Anchor training? | Closed | C4A method contract |
| Is inference one prefill or decoding? | Closed | Runtime guard and score reproduction |
| Is Recall@5=0.705 meaningful? | Closed/corrected | Random Recall@5=0.625 |
| Can the method reject all candidates? | Open | Native null data or a justified Null-Anchor task |
| Can current scores support a useful threshold? | Closed for current 1.5B method: effectively no | Dev-selected Blind F1 is approximately the predict-all baseline |
| Does 7B materially improve the method? | Closed for the current training configuration: no | 7B improves mean-pool MRR/nDCG but trained Anchor is slightly worse with CIs crossing zero |
| Why do 1.5B and 7B initial Anchor norms differ by about 40x? | Closed | Both copy their own pretrained EOS embedding; the pretrained EOS rows have different RMS scales |
| Is the 7B Anchor optimization calibrated? | Open | Initialization audit followed by a Train/Dev-only learning-rate and drift-regularization check |
| Is the collaborator's 0.8 comparable? | Deferred | Protocol alignment after the project's own 7B result |
| Is an existing separator better? | Open | Token initialization ablation |
| Did the meeting intend a native special token, a frozen Qwen hidden representation, or an MLP over Qwen features? | Open | Audit tokenizer/model representations, then compare explicitly specified variants under the same Train/Dev split |
| Do multiple Anchors help? | Open | 1/2/4 Anchor ablation |
| Can SP supply semantic Gold edges? | Closed for current logs: no | Pilot-20 recoverability audit |

## 9. Multi-Session Handoff Protocol

`AGENTS.md` and `PROJECT_CONTEXT.md` are maintained locally as the canonical coordinator record. They do not need to be copied to the remote server for every checkpoint. Remote execution prompts should be self-contained and should reference only stable remote artifacts needed for that checkpoint. Sync the context files only for a major handoff or when a remote session must independently coordinate several checkpoints.

Every new session should begin by stating:

```text
I have read AGENTS.md and PROJECT_CONTEXT.md.
My assigned checkpoint is: <checkpoint>.
I will not modify: <sealed inputs/results>.
Success is: <exact marker and artifacts>.
```

Every session should end with:

```text
Checkpoint status:
Success/failure marker:
Inputs and checksums:
Files created/modified:
Tests:
Metrics with denominators and baselines:
Limitations:
Recommended next task:
Context updates proposed to coordinator:
```

Only the coordinator should merge proposed updates into this document after verifying the returned artifacts.

## 10. Key Paths

Local project root:

- `F:/CodexProject/MemoryFlow`

Local experiment root:

- `F:/CodexProject/MemoryFlow/smallest_experiment`

Remote experiment root:

- `/home/songzhengxing_intern/work/codex_files/smallest_experiment`

Temporary server 10025 experiment root containing unique C5D/C5E artifacts:

- `/home/songzhengxing_intern/work/memoryflow`

Current research plan:

- `C:/Users/25779/.codex/.chatgpt-projects/g-p-6a5de08590fc81919be9495a753d672b/docs/superpowers/plans/2026-08-05-memoryflow-post-meeting-correction-plan.md`

Latest meeting record:

- `F:/HuaweiMoveData/Users/25779/Desktop/meeting-record/2026-08/2026-08-04-溯源工作.txt`
