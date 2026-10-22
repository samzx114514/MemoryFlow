#!/usr/bin/env python3
"""M6A: frozen native Qwen representations and zero-training scoring.

This script intentionally has no optimizer, backward, generation, or Blind
data path.  It stores raw float32 features plus normalized copies so cosine
and raw dot-product scores can be audited independently.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import sys
import time
from pathlib import Path
from typing import Any

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from memoryflow.ranking_baselines import BM25Index, compute_ranking_metrics, rank_scored_candidates

MODEL = Path("/data2/pkuiti/songzhengxing_intern/model/Qwen2.5-7B-Instruct")
DATA = ROOT / "data/longcite_anchor_expanded_v1_conservative"
OUT = ROOT / "results/m6a_qwen_representation_audit_243_v1"
C5F = ROOT / "results/c5f_dev_rescore_243_v1"
MAX_LENGTH = 512
BATCH_SIZE = 8
RANDOM_BASELINE = {
    "hit_at_1": 0.2719298245614035,
    "mrr": 0.48438063163862094,
    "recall_at_5": 0.625,
    "ndcg_at_5": 0.4573921636840349,
}


def forbid_blind(path: Path | str) -> None:
    if "blind" in str(path).lower():
        raise RuntimeError(f"Blind path access forbidden: {path}")


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(8 * 1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    forbid_blind(path)
    rows = []
    with path.open(encoding="utf-8") as f:
        for line_no, line in enumerate(f, 1):
            if line.strip():
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError as exc:
                    raise RuntimeError(f"invalid JSONL {path}:{line_no}: {exc}") from exc
    return rows


def json_dump(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def load_data() -> tuple[list[dict], list[dict], dict[str, dict]]:
    train = load_jsonl(DATA / "train_examples.jsonl")
    dev = load_jsonl(DATA / "dev_examples.jsonl")
    sources_list = load_jsonl(DATA / "source_catalog.jsonl")
    sources = {r["source_id"]: r for r in sources_list}
    if len(train) != 854 or len(dev) != 228 or len(sources) != 10400:
        raise RuntimeError(f"unexpected data shape train={len(train)} dev={len(dev)} source={len(sources)}")
    for ex in train + dev:
        ids = ex["candidate_source_ids"]
        if len(ids) != 8 or len(ids) != len(set(ids)) or not set(ex["gold_source_ids"]).issubset(ids):
            raise RuntimeError(f"invalid candidate set {ex['example_id']}")
        if any(sid not in sources for sid in ids):
            raise RuntimeError(f"missing source for {ex['example_id']}")
    return train, dev, sources


def normalize(x: np.ndarray) -> np.ndarray:
    denom = np.linalg.norm(x, axis=1, keepdims=True)
    if np.any(denom == 0) or not np.isfinite(denom).all():
        raise RuntimeError("zero/non-finite feature norm")
    return x / denom


def auc(labels: list[int], scores: list[float]) -> float:
    pos = [s for y, s in zip(labels, scores) if y]
    neg = [s for y, s in zip(labels, scores) if not y]
    if not pos or not neg:
        return float("nan")
    wins = sum(1.0 if p > n else 0.5 if p == n else 0.0 for p in pos for n in neg)
    return wins / (len(pos) * len(neg))


def auprc(labels: list[int], scores: list[float]) -> float:
    count = sum(labels)
    if not count:
        return float("nan")
    order = sorted(range(len(scores)), key=lambda i: (-scores[i], i))
    seen = 0
    area = 0.0
    for rank, i in enumerate(order, 1):
        if labels[i]:
            seen += 1
            area += seen / rank
    return area / count


def score_rows(examples: list[dict], source_vec: dict[str, np.ndarray], target_vec: dict[str, np.ndarray],
               *, representation: str, metric: str) -> tuple[list[dict], dict]:
    rows: list[dict] = []
    per_target: list[dict] = []
    labels: list[int] = []
    scores: list[float] = []
    for ex in examples:
        target = target_vec[ex["target_group_id"]]
        vals = {}
        for sid in ex["candidate_source_ids"]:
            source = source_vec[sid]
            vals[sid] = float(np.dot(target, source))
        ranking = rank_scored_candidates(ex["candidate_source_ids"], vals, tie_namespace=f"m6a:{representation}:{metric}:{ex['example_id']}")
        rm = compute_ranking_metrics(ranking, set(ex["gold_source_ids"]))
        per_target.append(rm)
        for order, sid in enumerate(ex["candidate_source_ids"]):
            label = int(sid in set(ex["gold_source_ids"]))
            raw = vals[sid]
            rows.append({
                "example_id": ex["example_id"], "target_group_id": ex["target_group_id"],
                "document_group_id": ex["document_group_id"], "candidate_id": sid,
                "candidate_order": order, "label": label, "raw_score": raw,
                "normalized_score": raw, "representation": representation, "metric": metric,
                "candidate_size": 8,
            })
            labels.append(label); scores.append(raw)
    metrics = {name: float(np.mean([x[name] for x in per_target])) for name in ("hit_at_1", "hit_at_3", "recall_at_5", "mrr", "ndcg_at_5")}
    positives = [s for y, s in zip(labels, scores) if y]
    negatives = [s for y, s in zip(labels, scores) if not y]
    metrics.update({"target_count": len(examples), "candidate_edges": len(rows), "positive_edges": sum(labels),
                    "negative_edges": len(labels) - sum(labels), "auroc": auc(labels, scores),
                    "auprc": auprc(labels, scores), "positive_score_mean": float(np.mean(positives)),
                    "negative_score_mean": float(np.mean(negatives)), "random_baseline": RANDOM_BASELINE})
    return rows, metrics


def extract(model, tokenizer, texts: list[str], *, mode: str, device: str) -> tuple[np.ndarray, dict]:
    import torch
    features = []
    truncated = 0
    lengths = []
    for start in range(0, len(texts), BATCH_SIZE):
        batch = texts[start:start + BATCH_SIZE]
        if mode == "mean":
            encoded = tokenizer(batch, padding=True, truncation=True, max_length=MAX_LENGTH, return_tensors="pt")
            raw_lengths = [len(tokenizer(t, add_special_tokens=True, truncation=False)["input_ids"]) for t in batch]
            truncated += sum(n > MAX_LENGTH for n in raw_lengths)
        else:
            ids = []
            for text in batch:
                token_ids = tokenizer.encode(text, add_special_tokens=False, truncation=False)
                if len(token_ids) >= MAX_LENGTH:
                    truncated += 1
                    token_ids = token_ids[:MAX_LENGTH - 1]
                token_ids.append(tokenizer.eos_token_id)
                ids.append(token_ids)
            encoded = tokenizer.pad({"input_ids": ids}, padding=True, return_tensors="pt")
            lengths.extend([len(x) for x in ids])
        encoded = {k: v.to(device) for k, v in encoded.items()}
        with torch.inference_mode():
            hidden = model(**encoded, return_dict=True).last_hidden_state.float()
        if mode == "mean":
            mask = encoded["attention_mask"].unsqueeze(-1).to(hidden.dtype)
            vec = (hidden * mask).sum(1) / mask.sum(1).clamp_min(1.0)
        else:
            vec = torch.stack([hidden[i, int(encoded["attention_mask"][i].sum().item()) - 1] for i in range(len(batch))])
        features.append(vec.cpu().numpy().astype(np.float32, copy=False))
    raw = np.concatenate(features, axis=0)
    if not np.isfinite(raw).all():
        raise RuntimeError(f"non-finite {mode} features")
    return raw, {"count": len(texts), "shape": list(raw.shape), "dtype": "float32", "truncated_count": truncated,
                 "max_length": MAX_LENGTH, "mode": mode, "lengths_recorded": len(lengths)}


def main() -> int:
    if os.environ.get("CUDA_VISIBLE_DEVICES") != "3":
        raise RuntimeError("M6A requires CUDA_VISIBLE_DEVICES=3")
    os.environ["HF_HUB_OFFLINE"] = "1"; os.environ["TRANSFORMERS_OFFLINE"] = "1"
    import torch
    from transformers import AutoModel, AutoTokenizer
    if not torch.cuda.is_available() or torch.cuda.device_count() != 1:
        raise RuntimeError("one visible CUDA device required")
    if not MODEL.is_dir(): raise FileNotFoundError(MODEL)
    if OUT.exists() and any(OUT.iterdir()):
        raise RuntimeError(f"refusing to overwrite non-empty M6A output {OUT}")
    forbid_blind(OUT); OUT.mkdir(parents=True)
    started = time.time()
    train, dev, sources = load_data()
    data_files = ["train_examples.jsonl", "dev_examples.jsonl", "source_catalog.jsonl", "manifest.json", "FROZEN.json", "group_split.json"]
    data_hashes = {name: sha256(DATA / name) for name in data_files}
    tokenizer = AutoTokenizer.from_pretrained(str(MODEL), local_files_only=True)
    im_end_ids = tokenizer.encode("<|im_end|>", add_special_tokens=False)
    if len(im_end_ids) != 1: raise RuntimeError(f"<|im_end|> is not one token: {im_end_ids}")
    if tokenizer.eos_token_id != im_end_ids[0]:
        raise RuntimeError("<|im_end|> is not tokenizer EOS in this model")
    model = AutoModel.from_pretrained(str(MODEL), local_files_only=True, dtype=torch.float32, attn_implementation="eager").to("cuda").eval()
    model.requires_grad_(False)
    if any(p.requires_grad or p.grad is not None for p in model.parameters()): raise RuntimeError("model not frozen")
    model_manifest = C5F / "model_manifest/model_sha256_manifest.json"
    model_manifest_hash = sha256(model_manifest) if model_manifest.is_file() else None
    source_ids = sorted(sources)
    source_texts = [sources[sid]["text"] for sid in source_ids]
    target_maps = {"train": {e["target_group_id"]: e["target"]["text"] for e in train}, "dev": {e["target_group_id"]: e["target"]["text"] for e in dev}}
    tokenizer_info = {"special_tokens_map": tokenizer.special_tokens_map, "all_special_tokens": tokenizer.all_special_tokens,
                      "all_special_ids": [int(x) for x in tokenizer.all_special_ids], "eos_token": tokenizer.eos_token,
                      "eos_token_id": int(tokenizer.eos_token_id), "im_end_token_ids": im_end_ids}
    audit = {"model_path": str(MODEL), "model_manifest_sha256": model_manifest_hash,
             "config": {"hidden_size": int(model.config.hidden_size), "num_hidden_layers": int(model.config.num_hidden_layers),
                        "num_attention_heads": int(model.config.num_attention_heads), "num_key_value_heads": int(getattr(model.config, "num_key_value_heads", model.config.num_attention_heads)),
                        "max_position_embeddings": int(model.config.max_position_embeddings), "config_torch_dtype": str(getattr(model.config, "torch_dtype", None))},
             "loaded_dtype": "float32", "tokenizer": tokenizer_info,
             "im_end_embedding_norm": float(model.get_input_embeddings().weight[tokenizer.eos_token_id].norm().item()),
             "anchor_contract": {"initialization": "independent float32 Parameter copied from input embedding row; model embedding table remains frozen", "injection": "shared Source/Target anchor positions", "math": "A = E_im_end + delta, delta initialized to zero", "drift_reference": "initial E_im_end row", "drift_penalty": "mean((A - E_im_end)^2)"},
             "blind_accessed": False}
    json_dump(OUT / "representation_audit.json", audit)
    json_dump(OUT / "data_integrity.json", {"data_hashes": data_hashes, "train_targets": len(train), "dev_targets": len(dev), "source_count": len(sources), "train_candidate_edges": len(train)*8, "dev_candidate_edges": len(dev)*8, "dev_positive_edges": sum(len(e['gold_source_ids']) for e in dev), "dev_negative_edges": len(dev)*8-sum(len(e['gold_source_ids']) for e in dev), "blind_accessed": False})
    cache_meta = {"representations": {}, "data_hashes": data_hashes, "model_manifest_sha256": model_manifest_hash, "blind_accessed": False, "gpu": "physical GPU3 / visible cuda:0", "started_at": started}
    all_features: dict[str, dict[str, np.ndarray]] = {"mean": {}, "im_end": {}}
    for mode in ("mean", "im_end"):
        raw, info = extract(model, tokenizer, source_texts, mode=mode, device="cuda")
        norm = normalize(raw)
        np.savez_compressed(OUT / f"{mode}_source_features.npz", raw=raw, normalized=norm)
        all_features[mode]["__source_matrix__"] = raw
        info["source_file"] = f"{mode}_source_features.npz"
        cache_meta["representations"].setdefault(mode, {})["source"] = info
        for split, examples in (("train", train), ("dev", dev)):
            keys = list(target_maps[split].keys())
            texts = [target_maps[split][k] for k in keys]
            traw, tinfo = extract(model, tokenizer, texts, mode=mode, device="cuda")
            tnorm = normalize(traw)
            np.savez_compressed(OUT / f"{mode}_{split}_target_features.npz", raw=traw, normalized=tnorm)
            all_features[mode][split] = traw
            cache_meta["representations"][mode][split] = {**tinfo, "target_ids": keys, "feature_file": f"{mode}_{split}_target_features.npz"}
        json_dump(OUT / f"{mode}_index.json", {"source_ids": source_ids, "train_target_ids": list(target_maps["train"]), "dev_target_ids": list(target_maps["dev"]), "row_order": "source_ids/target_ids as listed", "representation": mode})
    for p in OUT.glob("*.npz"):
        cache_meta.setdefault("feature_files", {})[p.name] = {"sha256": sha256(p), "bytes": p.stat().st_size}
    cache_meta["peak_memory_allocated"] = int(torch.cuda.max_memory_allocated())
    cache_meta["elapsed_seconds"] = time.time() - started
    json_dump(OUT / "cache_manifest.json", cache_meta)
    # Re-load the cache and score both raw dot products and cosine-normalized vectors.
    score_manifest = {"splits": {}, "blind_accessed": False}
    for mode in ("mean", "im_end"):
        source_npz = np.load(OUT / f"{mode}_source_features.npz")
        source_raw, source_norm = source_npz["raw"], source_npz["normalized"]
        sid_to_raw = dict(zip(source_ids, source_raw)); sid_to_norm = dict(zip(source_ids, source_norm))
        for split, examples in (("train", train), ("dev", dev)):
            idx = json.loads((OUT / f"{mode}_index.json").read_text())
            target_npz = np.load(OUT / f"{mode}_{split}_target_features.npz")
            target_raw = dict(zip(idx[f"{split}_target_ids"], target_npz["raw"]))
            target_norm = dict(zip(idx[f"{split}_target_ids"], target_npz["normalized"]))
            for metric, sv, tv in (("dot", sid_to_raw, target_raw), ("cosine", sid_to_norm, target_norm)):
                rows, metrics = score_rows(examples, sv, tv, representation=f"F_{'mean' if mode=='mean' else 'im_end'}", metric=metric)
                path = OUT / f"{split}_scores.jsonl"
                with path.open("a", encoding="utf-8") as f:
                    for row in rows: f.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")
                score_manifest["splits"].setdefault(split, {})[f"F_{mode}_{metric}"] = metrics
    # Existing formal C4 Anchor comparison and BM25; no new model forward.
    c4_rows = load_jsonl(C5F / "checkpoint_C4/per_candidate.jsonl")
    c4_metrics = json.loads((C5F / "checkpoint_C4/summary.json").read_text())
    score_manifest["existing_formal_baselines"] = {"C4_anchor": c4_metrics, "C4_per_candidate_rows": len(c4_rows), "source": str(C5F / "checkpoint_C4")}
    json_dump(OUT / "metrics.json", score_manifest)
    (OUT / "feature_cache_complete").write_text("M6A frozen feature cache complete; blind_accessed=false\n")
    print(json.dumps({"output": str(OUT), "audit": audit, "cache": cache_meta, "metrics": score_manifest}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
