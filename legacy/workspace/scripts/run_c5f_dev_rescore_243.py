#!/usr/bin/env python3
"""Forward-only Dev rescore for the six frozen C5F Anchor checkpoints."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import shutil
import time
from pathlib import Path

import numpy as np
import torch
from safetensors.torch import load_file
from transformers import AutoModelForCausalLM, AutoTokenizer

ROOT = Path(__file__).resolve().parents[1]
import sys
sys.path.insert(0, str(ROOT / "src"))
MODEL = Path("/data2/pkuiti/songzhengxing_intern/model/Qwen2.5-7B-Instruct")
DATA = ROOT / "data/longcite_anchor_expanded_v1_conservative"
C5F = ROOT / "results/c5f_ranking_continuation_243_v1"
OUT = ROOT / "results/c5f_dev_rescore_243_v1"
SCORER = Path(__file__).resolve()
MODEL_MANIFEST = C5F / "model_manifest/model_sha256_manifest.json"
CHECKPOINTS = {"A5": ("a", 5), "A6": ("a", 6), "C4": ("c", 4), "C5": ("c", 5), "C6": ("c", 6), "D5": ("d", 5)}


def forbid_blind(path: Path) -> None:
    if "blind" in str(path).lower():
        raise RuntimeError(f"forbidden path: {path}")


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(8 * 1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def load_jsonl(path: Path) -> list[dict]:
    forbid_blind(path)
    rows = []
    with path.open(encoding="utf-8") as f:
        for n, line in enumerate(f, 1):
            if line.strip():
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError as e:
                    raise RuntimeError(f"invalid JSONL {path}:{n}: {e}") from e
    return rows


def pack(tokenizer, example: dict, sources: dict, anchor_id: int):
    from memoryflow.anchor_attention import build_packed_layout
    return build_packed_layout(
        [tokenizer.encode(sources[s]["text"], add_special_tokens=False) for s in example["candidate_source_ids"]],
        tokenizer.encode(example["target"]["text"], add_special_tokens=False),
        anchor_token_id=anchor_id, max_source_tokens=128, max_target_tokens=128,
    )


def inject(base: torch.Tensor, positions: list[int], anchor: torch.Tensor) -> torch.Tensor:
    length = base.shape[1]
    mask = torch.zeros((1, length, 1), dtype=base.dtype, device=base.device)
    mask[:, positions] = 1
    return base.detach() * (1 - mask) + anchor.view(1, 1, -1) * mask


@torch.no_grad()
def score_one(model, layout, anchor):
    from memoryflow.anchor_attention import build_anchor_attention_mask, validate_no_fully_masked_rows
    from memoryflow.trainable_anchor import aggregate_last_layers_anchor_scores
    ids = torch.tensor([layout.input_ids], dtype=torch.long, device="cuda")
    base = model.get_input_embeddings()(ids).detach()
    positions = torch.tensor([layout.position_ids], dtype=torch.long, device="cuda")
    mask = build_anchor_attention_mask(layout, mode="anchor", dtype=torch.float32, device="cuda")
    validate_no_fully_masked_rows(mask)
    outputs = model(inputs_embeds=inject(base, layout.source_anchor_positions + [layout.target_anchor_position], anchor),
                    position_ids=positions, attention_mask=mask, output_attentions=True,
                    output_hidden_states=False, use_cache=False, return_dict=True, logits_to_keep=1)
    layers = []
    for attention in outputs.attentions[-8:]:
        layers.append(attention[0, :, layout.target_anchor_position, layout.source_anchor_positions].mean(dim=0))
    raw = torch.stack(layers).mean(dim=0)
    norm = raw / raw.sum()
    finite = bool(torch.isfinite(outputs.logits).all() and torch.isfinite(raw).all() and torch.isfinite(norm).all())
    return raw.float().cpu().numpy(), norm.float().cpu().numpy(), finite, int(layout.input_ids.__len__())


def ranking_metrics(scores: list[float], ids: list[str], gold: set[str]) -> dict[str, float]:
    order = sorted(range(len(ids)), key=lambda i: (-scores[i], ids[i]))
    ranked = [ids[i] for i in order]
    ranks = [i + 1 for i, x in enumerate(ranked) if x in gold]
    first = min(ranks)
    def hit(k): return float(any(r <= k for r in ranks))
    def recall(k): return sum(r <= k for r in ranks) / len(gold)
    dcg = sum(1.0 / math.log2(r + 1) for r in ranks if r <= 5)
    ideal = sum(1.0 / math.log2(i + 2) for i in range(min(len(gold), 5)))
    return {"hit_at_1": hit(1), "mrr": 1.0 / first, "ndcg_at_5": dcg / ideal,
            "recall_at_5": recall(5), "ranking": ranked}


def binary_auc(labels: list[int], scores: list[float]) -> float:
    positives = [s for y, s in zip(labels, scores) if y == 1]
    negatives = [s for y, s in zip(labels, scores) if y == 0]
    if not positives or not negatives:
        raise ValueError("AUROC requires both classes")
    wins = sum(1.0 if p > n else 0.5 if p == n else 0.0 for p in positives for n in negatives)
    return wins / (len(positives) * len(negatives))


def binary_auprc(labels: list[int], scores: list[float]) -> float:
    positive_count = sum(labels)
    if not positive_count:
        raise ValueError("AUPRC requires a positive class")
    order = sorted(range(len(scores)), key=lambda i: (-scores[i], i))
    seen_positive = 0
    area = 0.0
    for rank, i in enumerate(order, 1):
        if labels[i]:
            seen_positive += 1
            area += seen_positive / rank
    return area / positive_count


def aggregate(records: list[dict]) -> dict:
    groups: dict[str, list[dict]] = {}
    for r in records:
        groups.setdefault(r["example_id"], []).append(r)
    rank_rows = []
    labels = []; scores = []; raw_scores = []
    losses = []; masses = []
    for exid, rows in groups.items():
        rows.sort(key=lambda x: x["candidate_order"])
        ids = [r["candidate_id"] for r in rows]
        norm = [float(r["normalized_score"]) for r in rows]
        gold = {r["candidate_id"] for r in rows if r["label"] == 1}
        m = ranking_metrics(norm, ids, gold)
        rank_rows.append(m)
        losses.append(-float(np.mean([math.log(x + 1e-12) for x, r in zip(norm, rows) if r["label"] == 1])))
        masses.append(sum(x for x, r in zip(norm, rows) if r["label"] == 1))
        labels.extend([r["label"] for r in rows]); scores.extend(norm); raw_scores.extend([r["raw_score"] for r in rows])
    metrics = {k: float(np.mean([r[k] for r in rank_rows])) for k in ("hit_at_1", "mrr", "ndcg_at_5", "recall_at_5")}
    metrics.update({"all_positive_loss": float(np.mean(losses)), "positive_mass": float(np.mean(masses)),
                    "target_count": len(groups), "candidate_count": len(records),
                    "positive_edges": int(sum(labels)), "negative_edges": int(len(labels) - sum(labels)),
                    "random_baseline": {"hit_at_1": 0.2719298245614035, "mrr": 0.48438063163862094,
                                        "recall_at_5": 0.625, "ndcg_at_5": 0.4573921636840349},
                    "auroc": float(binary_auc(labels, raw_scores)),
                    "auprc": float(binary_auprc(labels, raw_scores)),
                    "raw_score_type": "last8_all_head_mean_source_anchor_attention",
                    "normalized_score_type": "source_candidate_renormalized_attention"})
    return metrics


def validate_checkpoint(config: str, epoch: int) -> dict:
    base = C5F / f"config_{config}"
    files = [base / f"epoch_{epoch:02d}.safetensors", base / f"epoch_{epoch:02d}_metrics.json",
             base / f"epoch_{epoch:02d}_optimizer.pt", base / f"epoch_{epoch:02d}_rng.pt",
             base / f"epoch_{epoch:02d}_sha256.json"]
    if not all(p.is_file() for p in files):
        raise RuntimeError(f"incomplete checkpoint {config}{epoch}")
    side = json.loads(files[-1].read_text())
    observed = {p.name: sha256(p) for p in files[:-1]}
    if observed != side:
        raise RuntimeError(f"checkpoint SHA mismatch {config}{epoch}")
    metrics = json.loads(files[1].read_text())
    if metrics.get("blind_accessed") is not False or not metrics.get("finite") or metrics.get("mask_leakage_max") != 0:
        raise RuntimeError(f"checkpoint integrity flags failed {config}{epoch}")
    return {"config": config, "epoch": epoch, "checkpoint_sha256": side[files[0].name],
            "metrics_sha256": side[files[1].name], "optimizer_sha256": side[files[2].name],
            "rng_sha256": side[files[3].name], "metrics": metrics}


def main() -> int:
    os.environ["CUDA_VISIBLE_DEVICES"] = "3"
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"
    forbid_blind(OUT)
    OUT.mkdir(parents=True, exist_ok=True)
    started = time.time()
    entries = [validate_checkpoint(c, e) for c, e in CHECKPOINTS.values()]
    tokenizer = AutoTokenizer.from_pretrained(MODEL, local_files_only=True)
    if tokenizer.eos_token_id is None or tokenizer.encode(tokenizer.eos_token, add_special_tokens=False) != [tokenizer.eos_token_id]:
        raise RuntimeError("EOS token is not a single token")
    examples = load_jsonl(DATA / "dev_examples.jsonl")
    examples = [x for x in examples if x.get("metadata", {}).get("candidate_size") == 8]
    sources = {x["source_id"]: x for x in load_jsonl(DATA / "source_catalog.jsonl")}
    if len(examples) != 228 or any(len(x["candidate_source_ids"]) != 8 for x in examples):
        raise RuntimeError("unexpected Dev shape")
    layouts = [pack(tokenizer, x, sources, tokenizer.eos_token_id) for x in examples]
    model = AutoModelForCausalLM.from_pretrained(MODEL, local_files_only=True, dtype=torch.float32, attn_implementation="eager").to("cuda").eval()
    model.requires_grad_(False)
    model_manifest_hash = sha256(MODEL_MANIFEST)
    data_hashes = {name: sha256(DATA / name) for name in ("train_examples.jsonl", "dev_examples.jsonl", "source_catalog.jsonl", "manifest.json", "FROZEN.json", "group_split.json")}
    scorer_hash = sha256(SCORER)
    summaries = []
    for item in entries:
        label = next(k for k, v in CHECKPOINTS.items() if v == (item["config"], item["epoch"]))
        target = OUT / f"checkpoint_{label}"
        if (target / "COMPLETED").is_file():
            summaries.append(json.loads((target / "summary.json").read_text())); continue
        target.mkdir(parents=True, exist_ok=True)
        anchor = load_file(str(C5F / f"config_{item['config']}/epoch_{item['epoch']:02d}.safetensors"))["trainable_anchor"].to("cuda", dtype=torch.float32)
        rows = []
        t0 = time.time(); peak = 0
        for ex, layout in zip(examples, layouts):
            raw, norm, finite, seq_len = score_one(model, layout, anchor)
            if not finite: raise RuntimeError(f"nonfinite score {label} {ex['example_id']}")
            for order, (cid, rs, ns) in enumerate(zip(ex["candidate_source_ids"], raw, norm)):
                rows.append({"checkpoint": label, "example_id": ex["example_id"], "target_id": ex["target"]["target_id"],
                             "candidate_id": cid, "candidate_order": order, "label": int(cid in set(ex["gold_source_ids"])),
                             "raw_score": float(rs), "normalized_score": float(ns), "checkpoint_sha256": item["checkpoint_sha256"],
                             "model_manifest_sha256": model_manifest_hash, "data_sha256": data_hashes,
                             "scorer_sha256": scorer_hash, "config": item["config"], "epoch": item["epoch"], "sequence_length": seq_len})
            peak = max(peak, int(torch.cuda.max_memory_allocated()))
        metrics = aggregate(rows)
        metrics.update({"checkpoint": label, "config": item["config"], "epoch": item["epoch"], "anchor_norm": float(anchor.norm().item()),
                        "train_dev_gap": None, "runtime_seconds": time.time() - t0, "peak_memory_allocated": peak,
                        "checkpoint_sha256": item["checkpoint_sha256"], "model_manifest_sha256": model_manifest_hash,
                        "data_sha256": data_hashes, "scorer_sha256": scorer_hash, "blind_accessed": False})
        tmp = target / ".per_candidate.jsonl.tmp"
        with tmp.open("w", encoding="utf-8") as f:
            for row in rows: f.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
        os.replace(tmp, target / "per_candidate.jsonl")
        (target / "summary.json").write_text(json.dumps(metrics, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
        (target / "COMPLETED").write_text("forward_only_dev_rescore_complete\n")
        summaries.append(metrics)
    summaries.sort(key=lambda x: list(CHECKPOINTS).index(x["checkpoint"]))
    (OUT / "all_metrics.json").write_text(json.dumps(summaries, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
    with (OUT / "integrity_manifest.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["checkpoint", "config", "epoch", "checkpoint_sha256", "metrics_sha256", "optimizer_sha256", "rng_sha256", "score_sha256", "summary_sha256"]); w.writeheader()
        for item, metrics in zip(entries, summaries):
            score_path = OUT / f"checkpoint_{metrics['checkpoint']}" / "per_candidate.jsonl"
            summary_path = OUT / f"checkpoint_{metrics['checkpoint']}" / "summary.json"
            w.writerow({**{k: item[k] for k in ("config", "epoch", "checkpoint_sha256", "metrics_sha256", "optimizer_sha256", "rng_sha256")}, "checkpoint": metrics["checkpoint"], "score_sha256": sha256(score_path), "summary_sha256": sha256(summary_path)})
    manifest = {"status": "PASS", "checkpoint_count": 6, "dev_targets": len(examples), "positive_edges": 496, "negative_edges": 1328,
                "model": str(MODEL), "model_manifest_sha256": model_manifest_hash, "data_sha256": data_hashes, "scorer_sha256": scorer_hash,
                "dtype": "float32", "attention": "eager", "forward_only": True, "optimizer_loaded": False, "backward": False, "generate_calls": 0,
                "blind_accessed": False, "runtime_seconds": time.time() - started}
    (OUT / "run_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
    del model; torch.cuda.empty_cache()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
