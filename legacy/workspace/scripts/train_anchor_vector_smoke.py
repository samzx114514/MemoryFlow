#!/usr/bin/env python3
from __future__ import annotations

import csv
from datetime import datetime, timezone
import gc
import hashlib
import json
import math
import os
from pathlib import Path
import sys
import time
import traceback

import numpy as np
import torch
from safetensors.torch import load_file, save_file
from torch import nn
from transformers import AutoModelForCausalLM, AutoTokenizer

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from memoryflow.anchor_attention import (  # noqa: E402
    build_anchor_attention_mask, build_packed_layout, maximum_masked_attention,
    stable_tolerance_ranking, validate_no_fully_masked_rows,
)
from memoryflow.c2b_analysis import WINDOWS, aggregate_feature_window  # noqa: E402
from memoryflow.ranking_baselines import METRIC_NAMES, compute_ranking_metrics  # noqa: E402
from memoryflow.trainable_anchor import (  # noqa: E402
    CheckpointScore, aggregate_last_layers_anchor_scores, all_positive_distribution_loss,
    anchor_drift_penalty, choose_better_checkpoint, inject_shared_anchor, trainable_parameter_count,
)

DATA = ROOT / "data" / "longcite_pilot_hard_v1"
C2B = ROOT / "results" / "longcite_c2b"
C2C = ROOT / "results" / "longcite_c2c_allpos"
OUT = ROOT / "results" / "longcite_c3a"
REPORT = ROOT / "reports" / "longcite_c3a_anchor_training_smoke.md"
MODEL_PATH = Path("/data2/pkuiti/songzhengxing_intern/model/Qwen2.5-1.5B-Instruct")
PYTORCH_MODEL = MODEL_PATH / "model.safetensors"
MAX_TOKENS = 128


def load_jsonl(path):
    with Path(path).open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def immutable_hashes():
    tokenizer_files = sorted(path for path in MODEL_PATH.iterdir() if "token" in path.name.lower() and path.is_file())
    return {
        "data": {name: sha256(DATA / name) for name in ("examples.jsonl", "source_catalog.jsonl", "manifest.json", "group_split.json")},
        "features": sha256(C2B / "anchor_attention_features.npz"),
        "feature_index": sha256(C2B / "feature_index.jsonl"),
        "model": sha256(PYTORCH_MODEL),
        "tokenizer": {path.name: sha256(path) for path in tokenizer_files},
    }


def pack(tokenizer, example, sources, anchor_id):
    return build_packed_layout(
        [tokenizer.encode(sources[source_id]["text"], add_special_tokens=False) for source_id in example["candidate_source_ids"]],
        tokenizer.encode(example["target"]["text"], add_special_tokens=False),
        anchor_token_id=anchor_id, max_source_tokens=MAX_TOKENS, max_target_tokens=MAX_TOKENS,
    )


def forward_scores(model, layout, anchor, *, grad, output_hidden=False, input_override=None):
    ids = torch.tensor([layout.input_ids if input_override is None else input_override], dtype=torch.long, device="cuda")
    with torch.no_grad():
        base = model.get_input_embeddings()(ids).detach()
    embeds = inject_shared_anchor(base, layout.source_anchor_positions + [layout.target_anchor_position], anchor)
    positions = torch.tensor([layout.position_ids], dtype=torch.long, device="cuda")
    mask = build_anchor_attention_mask(layout, mode="anchor", dtype=torch.float32, device="cuda")
    validate_no_fully_masked_rows(mask)
    context = torch.enable_grad() if grad else torch.no_grad()
    with context:
        outputs = model(
            inputs_embeds=embeds, position_ids=positions, attention_mask=mask,
            output_attentions=True, output_hidden_states=output_hidden,
            use_cache=False, return_dict=True, logits_to_keep=1,
        )
        scores = aggregate_last_layers_anchor_scores(outputs.attentions, layout, last_n_layers=8)
    masked = maximum_masked_attention(outputs.attentions, mask)
    source_hidden = None
    if output_hidden:
        source_hidden = outputs.hidden_states[-1][0, layout.source_anchor_positions].detach().cpu()
    finite = bool(torch.isfinite(outputs.logits).all().item()) and all(torch.isfinite(x).all().item() for x in outputs.attentions)
    del outputs, ids, base, embeds, positions, mask
    return scores, masked, finite, source_hidden


def rows_and_metrics(scores, examples):
    rows, rankings = [], []
    losses, masses, worst, all_top5 = [], [], [], []
    for values, example in zip(scores, examples):
        ids = example["candidate_source_ids"]
        ranking = stable_tolerance_ranking(ids, list(map(float, values)), tolerance=1e-6)
        gold = set(example["gold_source_ids"])
        row = compute_ranking_metrics(ranking, gold)
        positions = {source_id: rank for rank, source_id in enumerate(ranking, 1)}
        gold_values = [float(values[ids.index(source_id)]) for source_id in gold]
        losses.append(-float(np.mean(np.log(np.asarray(gold_values) + 1e-12))))
        masses.append(sum(gold_values)); worst.append(max(positions[x] for x in gold))
        all_top5.append(float(all(positions[x] <= 5 for x in gold)))
        rows.append(row); rankings.append(ranking)
    aggregate = {name: float(np.mean([row[name] for row in rows])) for name in METRIC_NAMES}
    aggregate.update({
        "all_positive_loss": float(np.mean(losses)), "positive_mass": float(np.mean(masses)),
        "all_positives_in_top5_rate": float(np.mean(all_top5)),
        "mean_worst_positive_rank": float(np.mean(worst)),
    })
    return aggregate, rows, rankings


def evaluate(model, anchor, packed_rows, examples, *, check_mask=False):
    values, masked_max, finite = [], 0.0, True
    for layout in packed_rows:
        scores, masked, okay, _ = forward_scores(model, layout, anchor, grad=False)
        values.append(scores.detach().cpu().numpy())
        if check_mask: masked_max = max(masked_max, masked)
        finite &= okay
    array = np.asarray(values, dtype=np.float32)
    metrics, rows, rankings = rows_and_metrics(array, examples)
    return array, metrics, rows, rankings, masked_max, finite


def split_strata(scores, examples):
    result = {}
    for name, predicate in (("single_positive", lambda x: len(x["gold_source_ids"]) == 1), ("multi_positive", lambda x: len(x["gold_source_ids"]) > 1)):
        indices = [i for i, row in enumerate(examples) if predicate(row)]
        result[name] = {"target_count": len(indices), "metrics": rows_and_metrics(scores[indices], [examples[i] for i in indices])[0]}
    return result


def embedding_moments(embedding):
    tensor = embedding.weight.detach()
    return {"sum": float(tensor.double().sum().item()), "squared_sum": float(tensor.double().square().sum().item()), "version": tensor._version}


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    started = time.perf_counter()
    result = {"status": "BLOCKED"}
    try:
        if os.environ.get("CUDA_VISIBLE_DEVICES") != "4" or os.environ.get("HF_HUB_OFFLINE") != "1" or os.environ.get("TRANSFORMERS_OFFLINE") != "1":
            raise RuntimeError("CUDA_VISIBLE_DEVICES=4 and offline flags are required")
        torch.manual_seed(0); np.random.seed(0)
        torch.backends.cuda.matmul.allow_tf32 = False; torch.backends.cudnn.allow_tf32 = False
        torch.use_deterministic_algorithms(True)
        hashes_before = immutable_hashes()
        examples = [row for row in load_jsonl(DATA / "examples.jsonl") if row["metadata"]["candidate_size"] == 8]
        sources = {row["source_id"]: row for row in load_jsonl(DATA / "source_catalog.jsonl")}
        split = json.loads((DATA / "group_split.json").read_text())
        tokenizer = AutoTokenizer.from_pretrained(MODEL_PATH, local_files_only=True)
        eos_id = tokenizer.eos_token_id
        if tokenizer.encode(tokenizer.eos_token, add_special_tokens=False) != [eos_id]:
            raise RuntimeError("EOS is not a single token")
        layouts = [pack(tokenizer, row, sources, eos_id) for row in examples]
        model = AutoModelForCausalLM.from_pretrained(MODEL_PATH, local_files_only=True, dtype=torch.float32, attn_implementation="eager").to("cuda")
        model.eval().requires_grad_(False)
        embedding = model.get_input_embeddings()
        eos_initial = embedding.weight[eos_id].detach().clone().float()
        trainable_anchor = nn.Parameter(eos_initial.clone())
        parameter_count = trainable_parameter_count(model, trainable_anchor)
        if parameter_count != model.config.hidden_size:
            raise RuntimeError("trainable parameter count differs from hidden size")
        versions_before = [parameter._version for parameter in model.parameters()]
        embedding_before = embedding_moments(embedding)
        torch.cuda.reset_peak_memory_stats()

        # Gate 1: all 97 initialized scores must match the frozen C2B EOS scores.
        initial_scores, initial_all_metrics, _, initial_rankings, initial_masked, initial_finite = evaluate(model, trainable_anchor, layouts, examples, check_mask=True)
        frozen_raw = np.load(C2B / "anchor_attention_features.npz")["attention"]
        frozen_scores = aggregate_feature_window(frozen_raw, WINDOWS["last8"])
        equivalence_error = float(np.max(np.abs(initial_scores - frozen_scores)))
        frozen_metrics, _, frozen_rankings = rows_and_metrics(frozen_scores, examples)
        ranking_equal = initial_rankings == frozen_rankings
        metric_error = max(abs(initial_all_metrics[name] - frozen_metrics[name]) for name in METRIC_NAMES)
        if equivalence_error >= 1e-6 or not ranking_equal or metric_error >= 1e-12:
            raise RuntimeError(f"EOS equivalence failed: score={equivalence_error} rank={ranking_equal} metric={metric_error}")

        docs = {name: set(value["document_group_ids"]) for name, value in split["splits"].items()}
        train_indices = [i for i, row in enumerate(examples) if row["document_group_id"] in docs["train"]]
        dev_indices = [i for i, row in enumerate(examples) if row["document_group_id"] in docs["dev"]]
        train_examples = [examples[i] for i in train_indices]; dev_examples = [examples[i] for i in dev_indices]
        train_layouts = [layouts[i] for i in train_indices]; dev_layouts = [layouts[i] for i in dev_indices]
        optimizer = torch.optim.AdamW([trainable_anchor], lr=0.01, weight_decay=0)
        if optimizer.param_groups[0]["params"] != [trainable_anchor]:
            raise RuntimeError("optimizer contains a parameter other than trainable_anchor")
        curve = []
        best_checkpoint = None; best_anchor = None; best_epoch = 0; stale = 0
        first_step = {}
        masked_max = initial_masked
        for epoch in range(1, 21):
            optimizer.zero_grad(set_to_none=True)
            epoch_losses = []; gradient_norms = []
            for offset, (layout, example) in enumerate(zip(train_layouts, train_examples), 1):
                scores, masked, finite, _ = forward_scores(model, layout, trainable_anchor, grad=True)
                gold = torch.tensor([source_id in set(example["gold_source_ids"]) for source_id in example["candidate_source_ids"]], dtype=torch.bool, device="cuda")
                rank_loss = all_positive_distribution_loss(scores, gold)
                loss = rank_loss + 1e-4 * anchor_drift_penalty(trainable_anchor, eos_initial)
                (loss / 8).backward()
                epoch_losses.append(float(loss.detach().item())); masked_max = max(masked_max, masked)
                if offset % 8 == 0:
                    norm = float(torch.nn.utils.clip_grad_norm_([trainable_anchor], 1.0).item())
                    gradient_norms.append(norm)
                    if epoch == 1 and offset == 8:
                        before_step = trainable_anchor.detach().clone()
                        first_step.update({"gradient_norm": norm, "gradient_nonzero": norm > 0, "gradient_finite": math.isfinite(norm), "qwen_gradients_all_none": all(p.grad is None for p in model.parameters())})
                    optimizer.step(); optimizer.zero_grad(set_to_none=True)
                    if epoch == 1 and offset == 8:
                        first_step["anchor_update_norm"] = float(torch.linalg.vector_norm(trainable_anchor.detach() - before_step).item())
            train_scores, train_metrics, _, _, _, train_finite = evaluate(model, trainable_anchor, train_layouts, train_examples)
            dev_scores, dev_metrics, _, _, dev_masked, dev_finite = evaluate(model, trainable_anchor, dev_layouts, dev_examples, check_mask=True)
            masked_max = max(masked_max, dev_masked)
            cosine = float(torch.nn.functional.cosine_similarity(trainable_anchor.detach(), eos_initial, dim=0).item())
            row = {"epoch": epoch, "optimization_loss": float(np.mean(epoch_losses)), "anchor_gradient_norm": float(np.mean(gradient_norms)), "anchor_eos_cosine": cosine, "anchor_norm": float(trainable_anchor.detach().norm().item())}
            row.update({f"train_{k}": v for k, v in train_metrics.items()}); row.update({f"dev_{k}": v for k, v in dev_metrics.items()})
            curve.append(row)
            candidate = CheckpointScore(dev_metrics["ndcg_at_5"], dev_metrics["recall_at_5"], dev_metrics["all_positive_loss"], epoch)
            if choose_better_checkpoint(best_checkpoint, candidate):
                best_checkpoint = candidate; best_anchor = trainable_anchor.detach().cpu().clone(); best_epoch = epoch; stale = 0
            else:
                stale += 1
            print(f"EPOCH {epoch} train_ndcg={train_metrics['ndcg_at_5']:.6f} dev_ndcg={dev_metrics['ndcg_at_5']:.6f} loss={dev_metrics['all_positive_loss']:.6f}", flush=True)
            if not train_finite or not dev_finite:
                raise RuntimeError("nonfinite model output")
            if stale >= 4:
                break

        if not first_step.get("gradient_nonzero") or not first_step.get("gradient_finite") or first_step.get("anchor_update_norm", 0) <= 0:
            raise RuntimeError("first-step anchor gradient/update integrity failed")
        if not first_step["qwen_gradients_all_none"] or any(parameter.grad is not None for parameter in model.parameters()):
            raise RuntimeError("Qwen received gradients")
        if [parameter._version for parameter in model.parameters()] != versions_before or embedding_moments(embedding) != embedding_before:
            raise RuntimeError("frozen Qwen parameters changed")
        trainable_anchor.data.copy_(best_anchor.to("cuda"))
        checkpoint_path = OUT / "best_anchor.safetensors"
        save_file({"trainable_anchor": best_anchor.contiguous()}, checkpoint_path)
        loaded_anchor = load_file(checkpoint_path)["trainable_anchor"]
        if not torch.equal(loaded_anchor, best_anchor):
            raise RuntimeError("saved Anchor does not round-trip exactly")
        metadata = {
            "status": "FROZEN_BEFORE_TEST", "frozen_at": datetime.now(timezone.utc).isoformat(),
            "test_used_for_selection": False, "selection_inputs": ["train", "dev"],
            "best_epoch": best_epoch, "selection_rule": ["dev_ndcg_at_5", "dev_recall_at_5", "dev_all_positive_loss", "earlier_epoch"],
            "trainable_parameter_count": parameter_count, "hidden_size": model.config.hidden_size,
            "anchor_type": "shared_trainable_anchor_initialized_from_existing_eos", "eos_token": tokenizer.eos_token, "eos_token_id": eos_id,
            "settings": {"dtype": "float32", "optimizer": "AdamW", "learning_rate": 0.01, "weight_decay": 0, "max_epochs": 20, "patience": 4, "gradient_accumulation_steps": 8, "gradient_clip": 1.0, "seed": 0, "aggregation": "uniform_last8_all_heads", "loss": "all_positive_distribution_cross_entropy", "drift_regularization": 1e-4},
            "checkpoint_sha256": sha256(checkpoint_path), "hashes_before": hashes_before,
        }
        (OUT / "checkpoint_metadata.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n")

        # Test is materialized only after the checkpoint and metadata are frozen.
        test_indices = [i for i, row in enumerate(examples) if row["document_group_id"] in docs["test"]]
        test_examples = [examples[i] for i in test_indices]; test_layouts = [layouts[i] for i in test_indices]
        final_train = evaluate(model, trainable_anchor, train_layouts, train_examples, check_mask=True)
        final_dev = evaluate(model, trainable_anchor, dev_layouts, dev_examples, check_mask=True)
        final_test = evaluate(model, trainable_anchor, test_layouts, test_examples, check_mask=True)
        masked_max = max(masked_max, final_train[4], final_dev[4], final_test[4])
        # Stable permutation check uses train examples only.
        permutation_max = 0.0
        for global_index in train_indices[:12]:
            example = examples[global_index]
            order = list(example["candidate_source_ids"]); perm = order[1:] + order[:1]
            changed = dict(example); changed["candidate_source_ids"] = perm
            perm_layout = pack(tokenizer, changed, sources, eos_id)
            perm_scores, _, _, _ = forward_scores(model, perm_layout, trainable_anchor, grad=False)
            left = dict(zip(order, final_train[0][train_indices.index(global_index)])); right = dict(zip(perm, perm_scores.detach().cpu().numpy()))
            permutation_max = max(permutation_max, max(abs(float(left[key]) - float(right[key])) for key in order))
        # Actual chunk isolation: replace source 0 tokens and compare other source anchors.
        iso_layout = train_layouts[0]
        _, _, _, hidden_a = forward_scores(model, iso_layout, trainable_anchor, grad=False, output_hidden=True)
        altered = list(iso_layout.input_ids)
        for position in iso_layout.source_content_positions[0]: altered[position] = tokenizer.unk_token_id or 0
        _, _, _, hidden_b = forward_scores(model, iso_layout, trainable_anchor, grad=False, output_hidden=True, input_override=altered)
        isolation_error = float((hidden_a[1:] - hidden_b[1:]).abs().max().item())

        initial_train = rows_and_metrics(initial_scores[train_indices], train_examples)[0]
        initial_dev = rows_and_metrics(initial_scores[dev_indices], dev_examples)[0]
        initial_test = rows_and_metrics(initial_scores[test_indices], test_examples)[0]
        train_payload = {"before": initial_train, "after": final_train[1], "strata_after": split_strata(final_train[0], train_examples)}
        dev_payload = {"before": initial_dev, "after": final_dev[1], "strata_after": split_strata(final_dev[0], dev_examples)}
        (OUT / "train_metrics.json").write_text(json.dumps(train_payload, indent=2) + "\n")
        (OUT / "dev_metrics.json").write_text(json.dumps(dev_payload, indent=2) + "\n")
        c2c_metrics = json.loads((C2C / "test_metrics.json").read_text())["metrics_by_method_and_split"]
        baselines = {name: c2c_metrics[name]["test"]["all"] for name in ("random_expected", "bm25", "qwen_frozen_mean_pool")}
        test_payload = {
            "frozen_eos_anchor_last8": initial_test, "trained_anchor_last8": final_test[1],
            "trained_anchor_strata": split_strata(final_test[0], test_examples), "baselines": baselines,
            "test_evaluated_after_checkpoint_freeze": True,
        }
        (OUT / "test_metrics.json").write_text(json.dumps(test_payload, ensure_ascii=False, indent=2) + "\n")
        with (OUT / "test_per_example.jsonl").open("w", encoding="utf-8") as handle:
            initial_rows = rows_and_metrics(initial_scores[test_indices], test_examples)
            for local, example in enumerate(test_examples):
                handle.write(json.dumps({
                    "example_id": example["example_id"], "document_group_id": example["document_group_id"], "gold_source_ids": example["gold_source_ids"],
                    "frozen_eos": {"scores": initial_scores[test_indices][local].tolist(), "ranking": initial_rows[2][local], "metrics": initial_rows[1][local]},
                    "trained_anchor": {"scores": final_test[0][local].tolist(), "ranking": final_test[3][local], "metrics": final_test[2][local]},
                }, ensure_ascii=False, separators=(",", ":")) + "\n")
        with (OUT / "training_curve.csv").open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(curve[0])); writer.writeheader(); writer.writerows(curve)
        hashes_after = immutable_hashes()
        final_cosine = float(torch.nn.functional.cosine_similarity(trainable_anchor.detach(), eos_initial, dim=0).item())
        metadata.update({
            "first_step": first_step, "eos_equivalence_max_abs_error": equivalence_error,
            "eos_equivalence_rankings_equal": ranking_equal, "eos_equivalence_metric_max_abs_error": metric_error,
            "masked_attention_max_abs": masked_max, "source_chunk_isolation_max_abs_error": isolation_error,
            "fp32_permutation_max_abs_error": permutation_max, "anchor_eos_final_cosine": final_cosine,
            "initial_anchor_norm": float(eos_initial.norm().item()), "final_anchor_norm": float(trainable_anchor.detach().norm().item()),
            "epochs_run": len(curve), "peak_memory_bytes": torch.cuda.max_memory_allocated(),
            "elapsed_seconds": time.perf_counter() - started, "hashes_after": hashes_after,
            "inputs_unchanged": hashes_before == hashes_after, "qwen_gradients_all_none": all(p.grad is None for p in model.parameters()),
            "qwen_parameter_versions_unchanged": [p._version for p in model.parameters()] == versions_before,
            "embedding_unchanged": embedding_moments(embedding) == embedding_before,
        })
        (OUT / "checkpoint_metadata.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n")
        result = metadata
        del model, embedding, trainable_anchor, eos_initial, layouts, train_layouts, dev_layouts, test_layouts
        gc.collect(); torch.cuda.empty_cache()
        result["gpu_released"] = torch.cuda.memory_allocated() == 0
        report = [
            "# LongCite C3A 共享 Anchor 训练冒烟", "",
            f"工程状态：PASS。仅训练 {parameter_count} 维共享 Anchor；Qwen、embedding、tokenizer 与数据均未修改。", "",
            f"EOS 初始化等价误差 {equivalence_error:.3g}，排名一致={ranking_equal}；首步梯度范数 {first_step['gradient_norm']:.6g}；最佳 epoch={best_epoch}。", "",
            f"Train nDCG@5 {initial_train['ndcg_at_5']:.4f} -> {final_train[1]['ndcg_at_5']:.4f}；Dev {initial_dev['ndcg_at_5']:.4f} -> {final_dev[1]['ndcg_at_5']:.4f}；Test {initial_test['ndcg_at_5']:.4f} -> {final_test[1]['ndcg_at_5']:.4f}。", "",
            f"最终 Anchor/EOS cosine={final_cosine:.8f}；norm {eos_initial.norm().item():.6f} -> {trainable_anchor.detach().norm().item():.6f}。", "",
            f"Mask 泄漏={masked_max:.3g}；Chunk isolation error={isolation_error:.3g}；FP32 permutation error={permutation_max:.3g}。", "",
            f"运行 {len(curve)} epochs，耗时 {result['elapsed_seconds']:.2f}s，峰值显存 {result['peak_memory_bytes']/1024**3:.3f} GiB。Test 仅在 checkpoint 冻结后评估一次，属于 11 条 pilot。", "",
        ]
        REPORT.write_text("\n".join(report), encoding="utf-8")
    except Exception as error:
        result.update({"error_type": type(error).__name__, "error": str(error), "traceback": traceback.format_exc(), "elapsed_seconds": time.perf_counter() - started})
        (OUT / "checkpoint_metadata.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
        raise
    finally:
        print(json.dumps({k: v for k, v in result.items() if k not in ("hashes_before", "hashes_after")}, ensure_ascii=False, indent=2), flush=True)


if __name__ == "__main__":
    main()
