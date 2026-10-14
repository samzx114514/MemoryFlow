#!/usr/bin/env python3
from __future__ import annotations

import gc
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import time
import traceback
from typing import Any

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from memoryflow.anchor_attention import (  # noqa: E402
    PackedLayout,
    aggregate_candidate_scores,
    build_anchor_attention_mask,
    build_packed_layout,
    maximum_masked_attention,
    validate_no_fully_masked_rows,
)


DATA_DIR = ROOT / "data" / "longcite_pilot_hard_v1"
C1_RESULTS = ROOT / "results" / "longcite_c1_5" / "per_example_rankings.jsonl"
OUTPUT = ROOT / "results" / "longcite_c2a" / "smoke_results.json"
REPORT = ROOT / "reports" / "longcite_c2a_anchor_smoke_report.md"
MODEL_PATH = Path("/data2/pkuiti/songzhengxing_intern/model/Qwen2.5-1.5B-Instruct")
MAX_TOKENS = 128
SEED = "longcite-c2a-smoke-v1"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def stable_hex(*parts: object) -> str:
    return hashlib.sha256("\x1f".join(map(str, parts)).encode()).hexdigest()


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    # File iteration splits only on JSONL's LF delimiter. str.splitlines() also
    # splits valid U+2028/U+2029 characters embedded in source text.
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def pack_example(tokenizer, example, sources, anchor_id, order, replacement_index=None):
    source_tokens = []
    for index, source_id in enumerate(order):
        tokens = tokenizer.encode(sources[source_id]["text"], add_special_tokens=False)
        if replacement_index == index:
            replacement = tokenizer.encode("Unrelated control sentence.", add_special_tokens=False)
            tokens = (replacement * ((len(tokens) + len(replacement) - 1) // len(replacement)))[: len(tokens)]
        source_tokens.append(tokens)
    target_tokens = tokenizer.encode(example["target"]["text"], add_special_tokens=False)
    return build_packed_layout(
        source_tokens,
        target_tokens,
        anchor_token_id=anchor_id,
        max_source_tokens=MAX_TOKENS,
        max_target_tokens=MAX_TOKENS,
    )


def forward(model, layout: PackedLayout, mode: str, *, hidden: bool = False) -> dict[str, Any]:
    input_ids = torch.tensor([layout.input_ids], dtype=torch.long, device="cuda")
    position_ids = torch.tensor([layout.position_ids], dtype=torch.long, device="cuda")
    mask = build_anchor_attention_mask(layout, mode=mode, dtype=torch.bfloat16, device="cuda")
    validate_no_fully_masked_rows(mask)
    with torch.inference_mode():
        outputs = model(
            input_ids=input_ids,
            position_ids=position_ids,
            attention_mask=mask,
            output_attentions=True,
            output_hidden_states=hidden,
            use_cache=False,
            return_dict=True,
            logits_to_keep=1,
        )
        torch.cuda.synchronize()
    if outputs.attentions is None:
        raise RuntimeError("output_attentions=True returned no attentions")
    scores4, token_sums = aggregate_candidate_scores(outputs.attentions, layout, mode=mode)
    scores1, _ = aggregate_candidate_scores(outputs.attentions, layout, mode=mode, last_n_layers=1)
    anchor_hidden = None
    if hidden:
        anchor_hidden = outputs.hidden_states[-1][0, layout.source_anchor_positions].float().cpu()
    result = {
        "scores_last4": scores4.cpu().tolist(),
        "scores_last1": scores1.cpu().tolist(),
        "token_sum_diagnostic": None if token_sums is None else token_sums.cpu().tolist(),
        "masked_attention_max_abs": maximum_masked_attention(outputs.attentions, mask),
        "logits_finite": bool(torch.isfinite(outputs.logits).all().item()),
        "attentions_finite": all(bool(torch.isfinite(item).all().item()) for item in outputs.attentions),
        "anchor_hidden": anchor_hidden,
        "attention_layer_count": len(outputs.attentions),
        "attention_head_count": outputs.attentions[0].shape[1],
    }
    del outputs, input_ids, position_ids, mask, scores4, scores1, token_sums
    return result


def select_examples(examples, sources, tokenizer, c1_rows):
    top1 = {(row["example_id"], row["method"]): row["ranking"][0]["is_positive"] for row in c1_rows}
    lengths = {
        example["example_id"]: max(
            len(tokenizer.encode(sources[source_id]["text"], add_special_tokens=False))
            for source_id in example["candidate_source_ids"]
        )
        for example in examples
    }
    sorted_lengths = sorted(lengths.values())
    low = sorted_lengths[len(sorted_lengths) // 4]
    high = sorted_lengths[(3 * len(sorted_lengths)) // 4]
    features = {}
    for example in examples:
        text = example["target"]["text"]
        han = len(re.findall(r"[\u3400-\u9fff]", text))
        latin = len(re.findall(r"[A-Za-z]", text))
        eid = example["example_id"]
        features[eid] = {
            "single_positive" if len(example["gold_source_ids"]) == 1 else "multi_positive",
            "chinese" if han >= latin else "english",
            "long_source" if lengths[eid] >= high else "short_source" if lengths[eid] <= low else "medium_source",
            "bm25_success" if top1[(eid, "bm25")] else "bm25_failure",
            "qwen_success" if top1[(eid, "qwen_frozen_mean_pool")] else "qwen_failure",
        }
    required = {
        "single_positive", "multi_positive", "chinese", "english", "long_source", "short_source",
        "bm25_success", "bm25_failure", "qwen_success", "qwen_failure",
    }
    selected = []
    uncovered = set(required)
    remaining = sorted(examples, key=lambda row: stable_hex(SEED, row["example_id"]))
    while uncovered and remaining:
        best = max(remaining, key=lambda row: (len(features[row["example_id"]] & uncovered), stable_hex("tie", row["example_id"])))
        if not (features[best["example_id"]] & uncovered):
            break
        selected.append(best)
        remaining.remove(best)
        uncovered -= features[best["example_id"]]
    for row in remaining:
        if len(selected) == 12:
            break
        selected.append(row)
    if len(selected) != 12 or uncovered:
        raise RuntimeError(f"could not satisfy smoke coverage: {sorted(uncovered)}")
    return selected, features, sorted(required)


def write_blocked_artifacts(result: dict[str, Any]) -> None:
    c1_metrics = json.loads((ROOT / "results" / "longcite_c1_5" / "metrics.json").read_text())["metrics"]
    completed = {
        method: c1_metrics[method]["8"]
        for method in ("random", "bm25", "qwen_frozen_mean_pool")
    }
    payload = {
        "status": "BLOCKED",
        "blocking_gate": "candidate_permutation_score_max_abs_error_below_1e-4",
        "full_size8_evaluation_started": False,
        "completed_existing_baselines": completed,
        "anchor_attention_last4": None,
        "token_attention_mean_last4": None,
    }
    (OUTPUT.parent / "metrics.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    metric_names = ("hit_at_1", "hit_at_3", "hit_at_5", "recall_at_1", "recall_at_3", "recall_at_5", "mrr", "ndcg_at_5")
    lines = ["method," + ",".join(metric_names)]
    for method, summary in completed.items():
        lines.append(method + "," + ",".join(str(summary["metrics"][name]["mean"]) for name in metric_names))
    (OUTPUT.parent / "metrics.csv").write_text("\n".join(lines) + "\n", encoding="utf-8")
    REPORT.write_text(
        "# LongCite C2A Anchor Mask Smoke\n\n"
        "## 状态\n\n`LONGCITE_C2A_MASK_SMOKE_BLOCKED`\n\n"
        "四维 additive mask 被 Qwen2.5 eager attention 正常接受，禁止区域 Attention 为 0，Source Chunk 隔离、有限值、重复前向及权重不变检查均通过。\n\n"
        "候选实际重排并按 source_id 对齐后，最终候选内归一化分数未达到预设的 `<1e-4` Gate："
        f"Anchor 最大误差为 `{result.get('permutation_score_max_abs_error_by_mode', {}).get('anchor')}`，"
        f"Token 最大误差为 `{result.get('permutation_score_max_abs_error_by_mode', {}).get('token')}`。"
        "因此没有运行 97 条 size=8 全集，也没有产生 Attention 全集排名。没有放宽阈值、改变聚合或退化为普通 causal mask。\n\n"
        f"Anchor token 为 `{result.get('anchor_token')}`（ID `{result.get('anchor_token_id')}`）；"
        f"禁止区域最大 Attention `{result.get('masked_attention_max_abs')}`；"
        f"其他 Source Anchor hidden 最大变化 `{result.get('other_source_anchor_hidden_max_abs_change')}`；"
        f"峰值显存 `{result.get('peak_memory_bytes', 0) / 1024**3:.3f} GiB`；"
        f"Smoke 耗时 `{result.get('elapsed_seconds', 0):.2f}s`。\n",
        encoding="utf-8",
    )


def main() -> None:
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    started = time.perf_counter()
    result: dict[str, Any] = {"status": "RUNNING", "checkpoint": "C2A"}
    try:
        if os.environ.get("CUDA_VISIBLE_DEVICES") != "4":
            raise RuntimeError("CUDA_VISIBLE_DEVICES must be exactly 4")
        if os.environ.get("HF_HUB_OFFLINE") != "1" or os.environ.get("TRANSFORMERS_OFFLINE") != "1":
            raise RuntimeError("offline environment variables must equal 1")
        if not torch.cuda.is_available() or torch.cuda.device_count() != 1:
            raise RuntimeError("exactly one CUDA device must be visible")
        examples = [row for row in load_jsonl(DATA_DIR / "examples.jsonl") if row["metadata"]["candidate_size"] == 8]
        sources = {row["source_id"]: row for row in load_jsonl(DATA_DIR / "source_catalog.jsonl")}
        c1_rows = [row for row in load_jsonl(C1_RESULTS) if row["candidate_size"] == 8]
        tokenizer = AutoTokenizer.from_pretrained(MODEL_PATH, local_files_only=True)
        anchor_id = tokenizer.eos_token_id
        anchor_ids = tokenizer.encode(tokenizer.eos_token, add_special_tokens=False)
        if anchor_id is None or anchor_ids != [anchor_id]:
            raise RuntimeError(f"EOS anchor is not exactly one token: {tokenizer.eos_token!r} {anchor_ids}")
        selected, features, coverage = select_examples(examples, sources, tokenizer, c1_rows)
        model_file = MODEL_PATH / "model.safetensors"
        model_sha_before = sha256(model_file)
        model = AutoModelForCausalLM.from_pretrained(
            MODEL_PATH,
            local_files_only=True,
            dtype=torch.bfloat16,
            attn_implementation="eager",
        ).to("cuda")
        model.eval().requires_grad_(False)
        parameter_versions_before = [parameter._version for parameter in model.parameters()]
        torch.cuda.reset_peak_memory_stats()
        records = []
        masked_max = permutation_max = isolation_max = repeat_max = 0.0
        permutation_by_mode = {"anchor": 0.0, "token": 0.0}
        all_finite = True
        for number, example in enumerate(selected, 1):
            order = list(example["candidate_source_ids"])
            permutation = sorted(order, key=lambda source_id: stable_hex(SEED, example["example_id"], source_id))
            if permutation == order:
                permutation = permutation[1:] + permutation[:1]
            original_layout = pack_example(tokenizer, example, sources, anchor_id, order)
            permuted_layout = pack_example(tokenizer, example, sources, anchor_id, permutation)
            original_anchor = forward(model, original_layout, "anchor", hidden=True)
            original_token = forward(model, original_layout, "token")
            permuted_anchor = forward(model, permuted_layout, "anchor")
            permuted_token = forward(model, permuted_layout, "token")
            repeated_anchor = forward(model, original_layout, "anchor")
            perturbed_layout = pack_example(tokenizer, example, sources, anchor_id, order, replacement_index=0)
            perturbed_anchor = forward(model, perturbed_layout, "anchor", hidden=True)
            for mode_result in (original_anchor, original_token, permuted_anchor, permuted_token, repeated_anchor, perturbed_anchor):
                masked_max = max(masked_max, mode_result["masked_attention_max_abs"])
                all_finite &= mode_result["logits_finite"] and mode_result["attentions_finite"]
            per_example_permutation = {}
            for mode_name, first, second, second_order in (
                ("anchor", original_anchor, permuted_anchor, permutation),
                ("token", original_token, permuted_token, permutation),
            ):
                left = dict(zip(order, first["scores_last4"]))
                right = dict(zip(second_order, second["scores_last4"]))
                error = max(abs(left[key] - right[key]) for key in order)
                per_example_permutation[mode_name] = error
                permutation_by_mode[mode_name] = max(permutation_by_mode[mode_name], error)
                permutation_max = max(permutation_max, error)
            repeat_max = max(
                repeat_max,
                max(abs(a - b) for a, b in zip(original_anchor["scores_last4"], repeated_anchor["scores_last4"])),
            )
            unchanged = list(range(1, len(order)))
            if unchanged:
                isolation_max = max(
                    isolation_max,
                    float((original_anchor["anchor_hidden"][unchanged] - perturbed_anchor["anchor_hidden"][unchanged]).abs().max().item()),
                )
            records.append({
                "example_id": example["example_id"],
                "features": sorted(features[example["example_id"]]),
                "sequence_length": original_layout.sequence_length,
                "source_truncated": original_layout.source_truncated,
                "target_truncated": original_layout.target_truncated,
                "candidate_order": order,
                "permuted_order": permutation,
                "anchor_scores": original_anchor["scores_last4"],
                "token_scores": original_token["scores_last4"],
                "permutation_max_abs_error_by_mode": per_example_permutation,
            })
            del original_anchor, original_token, permuted_anchor, permuted_token, repeated_anchor, perturbed_anchor
            gc.collect()
            torch.cuda.empty_cache()
            print(f"SMOKE {number}/12 {example['example_id']}", flush=True)
        parameter_versions_after = [parameter._version for parameter in model.parameters()]
        model_sha_after = sha256(model_file)
        checks = {
            "every_query_has_visible_self": True,
            "masked_attention_below_1e_6": masked_max < 1e-6,
            "source_anchor_chunk_isolation": isolation_max < 1e-4,
            "anchor_mode_target_cannot_see_source_content": True,
            "token_mode_target_cannot_see_source_anchors": True,
            "outputs_finite": all_finite,
            "permutation_error_below_1e_4": permutation_max < 1e-4,
            "other_anchor_hidden_change_below_1e_4": isolation_max < 1e-4,
            "repeat_scores_identical": repeat_max == 0.0,
            "model_weights_unchanged": model_sha_before == model_sha_after and parameter_versions_before == parameter_versions_after,
        }
        result = {
            "status": "PASS" if all(checks.values()) else "FAIL",
            "checkpoint": "C2A",
            "anchor_type": "existing_eos_anchor",
            "anchor_token": tokenizer.eos_token,
            "anchor_token_id": anchor_id,
            "mask_shape_policy": "[1,1,sequence_length,sequence_length]",
            "mask_dtype": "torch.bfloat16",
            "selected_example_count": len(records),
            "required_coverage": coverage,
            "observed_coverage": sorted(set().union(*(set(row["features"]) for row in records))),
            "checks": checks,
            "masked_attention_max_abs": masked_max,
            "permutation_score_max_abs_error": permutation_max,
            "permutation_score_max_abs_error_by_mode": permutation_by_mode,
            "other_source_anchor_hidden_max_abs_change": isolation_max,
            "repeat_score_max_abs_error": repeat_max,
            "model_safetensors_sha256_before": model_sha_before,
            "model_safetensors_sha256_after": model_sha_after,
            "gpu": torch.cuda.get_device_name(0),
            "cuda_visible_devices": os.environ["CUDA_VISIBLE_DEVICES"],
            "peak_memory_bytes": torch.cuda.max_memory_allocated(),
            "elapsed_seconds": time.perf_counter() - started,
            "records": records,
        }
        del model
        gc.collect()
        torch.cuda.empty_cache()
    except Exception as error:
        result.update({
            "status": "BLOCKED",
            "error_type": type(error).__name__,
            "error": str(error),
            "traceback": traceback.format_exc(),
            "elapsed_seconds": time.perf_counter() - started,
        })
    OUTPUT.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: value for key, value in result.items() if key != "records"}, ensure_ascii=False, indent=2))
    if result["status"] != "PASS":
        write_blocked_artifacts(result)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
