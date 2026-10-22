#!/usr/bin/env python3
"""LC-Sent-15-Q1: cache-only transfer of the frozen M6D R-SYM rank recipe."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import random
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
import torch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from memoryflow.lc_sent15_fmean import assert_allowed_path
from memoryflow.lc_sent15_q1_rsym import (
    CANDIDATE_SIZE, DIM, PARAMETER_COUNT, bootstrap_seed_first, listwise_single_positive_loss,
    normalize_rows, rank_ids, ranking_metrics_from_ranks, validate_rsym_contract,
)
from memoryflow.source_prior_relational import SymmetricRelation

DATA = ROOT / "data/lc_sent15_v1"
Q0 = ROOT / "results/lc_sent15_v1_qwen_fmean_cosine_v1"
BM25 = ROOT / "results/lc_sent15_v1_bm25_gate_v1"
M6D = ROOT / "results/m6d_source_prior_relational_v1"
M6D3 = ROOT / "results/m6d3_best_checkpoint_paired_selection_v1"
OUT = ROOT / "results/lc_sent15_v1_q1_rsym_transfer_v1"
SEEDS = (0, 1, 2)
LR, WEIGHT_DECAY, GROUP_BATCH, EPOCHS, PATIENCE, CLIP = 3e-4, 1e-4, 32, 50, 5, 1.0
BOOTSTRAP_SEED, BOOTSTRAP_REPS = 20260815, 10000
EXPECTED_CACHES = {
    "train_target_fmean.npz": "175b64c2c7314965c06f1ccdaceea977246d7edfd971f1eabf8571cbb2afc285",
    "train_source_fmean.npz": "eec02451107aca8eee1672b14c7564aee9ea1e2c9a03ada2e67a4b61253440a9",
    "dev_target_fmean.npz": "52895a4c00d67616bb53392e0a0561b227175d619afbcf5fc85d616200adf888",
    "dev_source_fmean.npz": "9ee9b5c1ec195aa13b884d01dc68c769f5ffd36d821fb7b9e9ff38a2bad9845a",
}


def sha(path: Path) -> str:
    assert_allowed_path(str(path))
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def dump(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def write_jsonl(path: Path, rows: list[dict]) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True, allow_nan=False) + "\n")
    os.replace(temporary, path)


def read_jsonl(path: Path) -> list[dict]:
    assert_allowed_path(str(path))
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def seed_all(seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)


def frozen_recipe() -> dict:
    config = M6D / "runs/rank/R_SYM/seed_0/config.json"
    best = M6D / "runs/rank/R_SYM/seed_0/best.json"
    if not config.is_file() or not best.is_file():
        raise RuntimeError("NEEDS_FROZEN_RSYM_CONTRACT: M6D R-SYM rank files missing")
    payload = json.loads(config.read_text())
    expected = {
        "track": "rank", "variant": "R_SYM", "base_variant": "R_SYM", "lr": LR,
        "objective": "all_positive_distribution_cross_entropy", "parameter_count": PARAMETER_COUNT,
    }
    if any(payload.get(key) != value for key, value in expected.items()):
        raise RuntimeError("NEEDS_FROZEN_RSYM_CONTRACT: M6D config differs")
    validate_rsym_contract()
    return {
        "source_code": {
            "model": "workspace/src/memoryflow/source_prior_relational.py:SymmetricRelation/symmetric_features",
            "loss": "workspace/src/memoryflow/directional_scorer.py:all_positive_distribution_loss",
            "runner": "workspace/scripts/run_m6d_source_prior_relational.py:train_one/selection_key",
        },
        "source_sha256": {
            "model": sha(ROOT / "src/memoryflow/source_prior_relational.py"),
            "loss": sha(ROOT / "src/memoryflow/directional_scorer.py"),
            "runner": sha(ROOT / "scripts/run_m6d_source_prior_relational.py"),
            "seed0_config": sha(config), "seed0_best": sha(best),
        },
        "input": "concat(target*source, abs(target-source), dot(target,source)) using L2-normalized FP32 F_mean",
        "input_dim": 7169, "architecture": "Linear(7169,128) -> GELU -> Dropout(0.1) -> Linear(128,1)",
        "parameter_initialization": "PyTorch nn.Linear default reset_parameters after seed_all(seed)",
        "parameter_count": PARAMETER_COUNT, "optimizer": "AdamW", "learning_rate": LR,
        "weight_decay": WEIGHT_DECAY, "group_batch_size": GROUP_BATCH, "max_epochs": EPOCHS,
        "patience": PATIENCE, "gradient_clip_norm": CLIP, "seeds": list(SEEDS),
        "loss": "mean_groups[-log_softmax(logits_group)[unique_positive]]; c15 single-positive reduces to CE(logits_group, gold_index)",
        "selection": "Dev MRR descending, then Dev nDCG@5 descending, then Dev ranking loss ascending, then earlier epoch",
        "symmetry": "score(t,s) == score(s,t) in eval mode",
        "m6d_seed0_config": payload,
    }


def validate_inputs() -> dict:
    for path in (Q0 / "integrity_report.json", BM25 / "integrity_report.json", DATA / "manifest.json"):
        assert_allowed_path(str(path))
        if not path.is_file():
            raise RuntimeError(f"missing input: {path}")
    if sha(Q0 / "integrity_report.json") != "a69e1906e388ecaf5567f76bcae957a621e713e3abf18d2d65388ec98a47cf53":
        raise RuntimeError("Q0 integrity SHA mismatch")
    if sha(BM25 / "integrity_report.json") != "3ee549b93827bf715b7b0c7be3742ea0bc65e686a15cf6db407a0bacaded9d20":
        raise RuntimeError("BM25 integrity SHA mismatch")
    if sha(DATA / "manifest.json") != "9762b68d08a45683f796db6beae8b493f9bf359ecb7814f2af8c132774df8bb4":
        raise RuntimeError("data manifest SHA mismatch")
    for name, digest in EXPECTED_CACHES.items():
        if sha(Q0 / name) != digest:
            raise RuntimeError(f"feature cache SHA mismatch: {name}")
    return {
        "data_manifest": sha(DATA / "manifest.json"), "q0_integrity": sha(Q0 / "integrity_report.json"),
        "bm25_integrity": sha(BM25 / "integrity_report.json"), "feature_caches": EXPECTED_CACHES,
        "no_qwen": True, "no_blind": True, "no_reserve": True, "no_multi_positive": True,
        "no_mixed_catalog": True,
    }


def load_split(split: str) -> tuple[list[dict], dict[str, dict], dict[str, np.ndarray]]:
    examples = read_jsonl(DATA / split / "single_positive_15.jsonl")
    catalog_rows = read_jsonl(DATA / split / "source_catalog.jsonl")
    expected_targets = {"train": 854, "dev": 228}[split]
    if len(examples) != expected_targets or any(row.get("split") != split for row in examples):
        raise RuntimeError(f"split/target contract mismatch: {split}")
    if any(len(row["candidates"]) != CANDIDATE_SIZE or sum(int(c["label"]) for c in row["candidates"]) != 1 for row in examples):
        raise RuntimeError(f"c15 one-positive contract mismatch: {split}")
    catalog = {row["id"]: row for row in catalog_rows}
    referenced = {candidate["source_id"] for row in examples for candidate in row["candidates"]}
    if set(catalog) != referenced or len(catalog) != {"train": 12774, "dev": 3411}[split]:
        raise RuntimeError(f"catalog coverage mismatch: {split}")
    target_raw = np.load(Q0 / f"{split}_target_fmean.npz")["raw"]
    source_raw = np.load(Q0 / f"{split}_source_fmean.npz")["raw"]
    if target_raw.shape != (expected_targets, DIM) or source_raw.shape != (len(catalog), DIM):
        raise RuntimeError(f"feature shape mismatch: {split}")
    target_ids = [row["example_id"] for row in examples]
    source_ids = sorted(catalog)
    targets = dict(zip(target_ids, normalize_rows(target_raw)))
    sources = dict(zip(source_ids, normalize_rows(source_raw)))
    if len(targets) != expected_targets or len(sources) != len(catalog):
        raise RuntimeError("feature ID mapping mismatch")
    return examples, catalog, {**targets, **{}} | {f"source::{key}": value for key, value in sources.items()}


def unpack_features(examples: list[dict], catalog: dict[str, dict], packed: dict[str, np.ndarray]) -> tuple[dict[str, np.ndarray], dict[str, np.ndarray]]:
    targets = {row["example_id"]: packed[row["example_id"]] for row in examples}
    sources = {source_id: packed[f"source::{source_id}"] for source_id in catalog}
    return targets, sources


def tensors(examples: list[dict], targets: dict[str, np.ndarray], sources: dict[str, np.ndarray], device: torch.device):
    target_values, source_values, labels, groups = [], [], [], []
    for group, row in enumerate(examples):
        target = targets[row["example_id"]]
        for candidate in row["candidates"]:
            target_values.append(target); source_values.append(sources[candidate["source_id"]])
            labels.append(float(candidate["label"])); groups.append(group)
    if len(labels) != len(examples) * CANDIDATE_SIZE or any(sum(labels[i:i+CANDIDATE_SIZE]) != 1 for i in range(0, len(labels), CANDIDATE_SIZE)):
        raise RuntimeError("labels/groups must be exactly c15 single-positive")
    return tuple(torch.from_numpy(np.asarray(value, dtype=np.float32)).to(device) for value in (target_values, source_values, np.asarray(labels, np.float32), np.asarray(groups, np.int64)))


def model_logits(model: torch.nn.Module, targets: torch.Tensor, sources: torch.Tensor) -> torch.Tensor:
    return model(targets, sources)


def scores_and_targets(examples: list[dict], logits: np.ndarray, split: str, seed: int) -> tuple[list[dict], list[dict]]:
    predictions, summaries = [], []
    for index, row in enumerate(examples):
        offset = index * CANDIDATE_SIZE
        candidates = row["candidates"]
        ids = [candidate["source_id"] for candidate in candidates]
        values = logits[offset:offset+CANDIDATE_SIZE]
        ranking = rank_ids(ids, values.tolist())
        gold = next(candidate["source_id"] for candidate in candidates if int(candidate["label"]) == 1)
        gold_rank = ranking.index(gold) + 1
        top_score = float(values[ids.index(ranking[0])])
        second_score = float(values[ids.index(ranking[1])])
        gold_score = float(values[ids.index(gold)])
        boundary_index = max(0, gold_rank - 2)
        boundary_score = float(values[ids.index(ranking[boundary_index])]) if gold_rank > 1 else second_score
        summaries.append({"example_id": row["example_id"], "language": row["language"], "gold_source_id": gold, "gold_rank": gold_rank, "top1_source_id": ranking[0], "ranking": ranking, "gold_score": gold_score, "top1_score": top_score, "top1_margin": top_score - second_score, "gold_boundary_margin": gold_score - boundary_score})
        for position, candidate in enumerate(candidates):
            source_id = candidate["source_id"]
            predictions.append({"split": split, "seed": seed, "example_id": row["example_id"], "language": row["language"], "candidate_id": source_id, "candidate_position": position, "label": int(candidate["label"]), "raw_logit": float(values[position]), "ranking_score": float(values[position]), "rank": ranking.index(source_id) + 1})
    return predictions, summaries


def aggregate(targets: list[dict]) -> dict:
    return {name: ranking_metrics_from_ranks([row["gold_rank"] for row in subset]) for name, subset in {
        "overall": targets, "zh": [row for row in targets if row["language"] == "zh"], "en": [row for row in targets if row["language"] == "en"]}.items()}


def listwise_eval_loss(logits: np.ndarray, examples: list[dict]) -> float:
    values = []
    for index, row in enumerate(examples):
        local = logits[index*CANDIDATE_SIZE:(index+1)*CANDIDATE_SIZE]
        gold_index = next(i for i, candidate in enumerate(row["candidates"]) if int(candidate["label"]) == 1)
        shifted = local - local.max(); values.append(float(-(shifted[gold_index] - math.log(np.exp(shifted).sum()))))
    return float(np.mean(values))


def selection_key(metrics: dict, epoch: int) -> tuple[float, float, float, int]:
    return (-metrics["overall"]["mrr"], -metrics["overall"]["ndcg_at_5"], metrics["ranking_loss"], epoch)


def train_seed(seed: int, device: torch.device) -> None:
    run_dir = OUT / "runs" / f"seed_{seed}"
    if (run_dir / "COMPLETED").is_file():
        return
    if run_dir.exists():
        raise RuntimeError(f"refusing non-complete existing seed output: {run_dir}")
    train, train_catalog, packed_train = load_split("train")
    dev, dev_catalog, packed_dev = load_split("dev")
    train_targets, train_sources = unpack_features(train, train_catalog, packed_train)
    dev_targets, dev_sources = unpack_features(dev, dev_catalog, packed_dev)
    if set(train_sources) != set(train_catalog) or set(dev_sources) != set(dev_catalog):
        raise RuntimeError("source cache coverage mismatch")
    working = run_dir.with_name("." + run_dir.name + ".tmp")
    if working.exists():
        raise RuntimeError(f"incomplete staging exists: {working}")
    working.mkdir(parents=True)
    seed_all(seed)
    model = SymmetricRelation(DIM).to(device).float()
    optimizer = torch.optim.AdamW(model.parameters(), lr=LR, weight_decay=WEIGHT_DECAY)
    tt, ts, ty, tg = tensors(train, train_targets, train_sources, device)
    dt, ds, dy, dg = tensors(dev, dev_targets, dev_sources, device)
    best, bad, history = None, 0, []
    started = time.time()
    for epoch in range(1, EPOCHS + 1):
        model.train(); losses = []; order = np.random.default_rng(seed + 1000 + epoch).permutation(len(train))
        for start in range(0, len(train), GROUP_BATCH):
            selected = order[start:start+GROUP_BATCH]
            mask = torch.zeros(len(ty), dtype=torch.bool, device=device)
            for group in selected:
                mask |= tg == int(group)
            optimizer.zero_grad(set_to_none=True)
            loss = listwise_single_positive_loss(model_logits(model, tt[mask], ts[mask]), ty[mask], tg[mask])
            if not torch.isfinite(loss): raise RuntimeError("non-finite loss")
            loss.backward(); grad_norm = float(torch.nn.utils.clip_grad_norm_(model.parameters(), CLIP))
            optimizer.step(); losses.append(float(loss.detach().cpu()))
        model.eval()
        with torch.inference_mode():
            train_logits = model_logits(model, tt, ts).detach().cpu().numpy()
            dev_logits = model_logits(model, dt, ds).detach().cpu().numpy()
        if not (np.isfinite(train_logits).all() and np.isfinite(dev_logits).all()): raise RuntimeError("non-finite score")
        _, train_target_rows = scores_and_targets(train, train_logits, "train", seed)
        _, dev_target_rows = scores_and_targets(dev, dev_logits, "dev", seed)
        train_metrics, dev_metrics = aggregate(train_target_rows), aggregate(dev_target_rows)
        train_metrics["ranking_loss"] = listwise_eval_loss(train_logits, train)
        dev_metrics["ranking_loss"] = listwise_eval_loss(dev_logits, dev)
        key = selection_key(dev_metrics, epoch); improved = best is None or key < best["key"]
        bad = 0 if improved else bad + 1
        history.append({"epoch": epoch, "train_loss": float(np.mean(losses)), "grad_norm_preclip": grad_norm, "train": train_metrics, "dev": dev_metrics, "improved": improved, "bad_count": bad})
        if improved:
            best = {"epoch": epoch, "key": key, "dev": dev_metrics, "train": train_metrics, "state": {name: value.detach().cpu() for name, value in model.state_dict().items()}}
        if bad >= PATIENCE: break
    assert best is not None
    torch.save(best.pop("state"), working / "best.pt")
    restored = SymmetricRelation(DIM).to(device).float(); restored.load_state_dict(torch.load(working / "best.pt", map_location=device, weights_only=True)); restored.eval()
    with torch.inference_mode():
        train_logits = model_logits(restored, tt, ts).cpu().numpy(); dev_logits = model_logits(restored, dt, ds).cpu().numpy()
    train_predictions, train_rows = scores_and_targets(train, train_logits, "train", seed)
    dev_predictions, dev_rows = scores_and_targets(dev, dev_logits, "dev", seed)
    train_metrics, dev_metrics = aggregate(train_rows), aggregate(dev_rows)
    train_metrics["ranking_loss"] = listwise_eval_loss(train_logits, train); dev_metrics["ranking_loss"] = listwise_eval_loss(dev_logits, dev)
    config = {"seed": seed, "recipe": "frozen M6D R-SYM ranking", "lr": LR, "weight_decay": WEIGHT_DECAY, "group_batch_size": GROUP_BATCH, "max_epochs": EPOCHS, "patience": PATIENCE, "gradient_clip_norm": CLIP, "objective": "all_positive_distribution_cross_entropy (single-positive c15 CE)", "parameter_count": PARAMETER_COUNT, "device": str(device), "no_qwen": True, "no_blind": True, "no_bm25_input": True}
    best_out = {key: value for key, value in best.items()}; best_out.update({"best_checkpoint_metrics_after_reload": {"train": train_metrics, "dev": dev_metrics}, "stopping_reason": "patience_5" if bad >= PATIENCE else "max_epoch_50", "runtime_seconds": time.time() - started, "peak_gpu_bytes": int(torch.cuda.max_memory_allocated(device)) if device.type == "cuda" else 0})
    dump(working / "config.json", config); dump(working / "history.json", history); dump(working / "best.json", best_out)
    write_jsonl(working / "train_predictions.jsonl", train_predictions); write_jsonl(working / "dev_predictions.jsonl", dev_predictions); dump(working / "train_targets.json", train_rows); dump(working / "dev_targets.json", dev_rows)
    files = {path.name: sha(path) for path in sorted(working.iterdir()) if path.is_file()}
    dump(working / "integrity.json", {"files": files, "input_manifest_sha256": sha(OUT / "input_manifest.json"), "frozen_config_sha256": sha(OUT / "q1_frozen_config.json")})
    (working / "COMPLETED").write_text("completed\n", encoding="utf-8")
    os.replace(working, run_dir)


def load_seed_outputs(seed: int) -> tuple[list[dict], list[dict], list[dict], list[dict]]:
    directory = OUT / "runs" / f"seed_{seed}"
    required = ("best.pt", "config.json", "history.json", "best.json", "train_predictions.jsonl", "dev_predictions.jsonl", "train_targets.json", "dev_targets.json", "integrity.json", "COMPLETED")
    if not all((directory / name).is_file() for name in required): raise RuntimeError(f"incomplete seed output: {seed}")
    integrity = json.loads((directory / "integrity.json").read_text())
    for name, digest in integrity["files"].items():
        if sha(directory / name) != digest: raise RuntimeError(f"seed integrity mismatch: {seed}/{name}")
    return (read_jsonl(directory / "train_predictions.jsonl"), read_jsonl(directory / "dev_predictions.jsonl"), json.loads((directory / "train_targets.json").read_text()), json.loads((directory / "dev_targets.json").read_text()))


def bootstrap_indices() -> np.ndarray:
    existing = Q0 / "bootstrap_indices.npy"
    indices = np.load(existing)
    if indices.shape != (BOOTSTRAP_REPS, 228): raise RuntimeError("Q0 bootstrap index shape mismatch")
    return indices


def finalise() -> None:
    if (OUT / "COMPLETED").exists(): return
    outputs = {seed: load_seed_outputs(seed) for seed in SEEDS}
    dev_by_seed = [outputs[seed][3] for seed in SEEDS]
    train_by_seed = [outputs[seed][2] for seed in SEEDS]
    dev_ids = [row["example_id"] for row in dev_by_seed[0]]
    if any([row["example_id"] for row in rows] != dev_ids for rows in dev_by_seed[1:]): raise RuntimeError("seed target ordering mismatch")
    bm25_targets = read_jsonl(BM25 / "bm25_legacy_dev_predictions.jsonl")
    bm25_map = {row["example_id"]: row for row in bm25_targets}
    if set(dev_ids) != set(bm25_map) or len(dev_ids) != 228: raise RuntimeError("BM25 target mismatch")
    ranks_by_seed = np.asarray([[row["gold_rank"] for row in rows] for rows in dev_by_seed], dtype=np.int64)
    bm25_ranks = np.asarray([bm25_map[key]["gold_rank"] for key in dev_ids], dtype=np.int64)
    bootstrap = bootstrap_seed_first(ranks_by_seed, bm25_ranks, bootstrap_indices())
    seed_metrics = []
    for seed in SEEDS:
        best = json.loads((OUT / "runs" / f"seed_{seed}" / "best.json").read_text())
        seed_metrics.append({"seed": seed, "train": aggregate(train_by_seed[seed]), "dev": aggregate(dev_by_seed[seed]), "best_epoch": best["epoch"], "best_checkpoint_sha256": sha(OUT / "runs" / f"seed_{seed}" / "best.pt"), "runtime_seconds": best["runtime_seconds"], "peak_gpu_bytes": best["peak_gpu_bytes"], "stopping_reason": best["stopping_reason"]})
    mean_metrics = {}
    for split in ("train", "dev"):
        mean_metrics[split] = {}
        for segment in ("overall", "zh", "en"):
            mean_metrics[split][segment] = {name: float(np.mean([row[split][segment][name] for row in seed_metrics])) for name in ("hit_at_1", "mrr", "ndcg_at_5", "mean_gold_rank")}
            mean_metrics[split][segment]["target_count"] = seed_metrics[0][split][segment]["target_count"]
    q0_targets = read_jsonl(Q0 / "dev_qwen_targets.jsonl"); q0_map = {row["example_id"]: row for row in q0_targets}
    if set(q0_map) != set(dev_ids): raise RuntimeError("Q0 target mismatch")
    median_seed = 1
    rsym_map = {row["example_id"]: row for row in dev_by_seed[median_seed]}
    complement = {segment: {key: 0 for key in ("both_correct", "bm25_only", "rsym_only", "both_wrong")} for segment in ("overall", "zh", "en")}
    errors = []
    qwen_only_retained = bm25_only_recovered = 0
    dev_rows = {row["example_id"]: row for row in read_jsonl(DATA / "dev" / "single_positive_15.jsonl")}
    dev_catalog = {row["id"]: row for row in read_jsonl(DATA / "dev" / "source_catalog.jsonl")}
    for key in dev_ids:
        r, b, q = rsym_map[key], bm25_map[key], q0_map[key]
        r_ok, b_ok, q_ok = r["gold_rank"] == 1, b["gold_rank"] == 1, q["gold_rank"] == 1
        category = "both_correct" if r_ok and b_ok else "bm25_only" if b_ok else "rsym_only" if r_ok else "both_wrong"
        for segment in ("overall", r["language"]): complement[segment][category] += 1
        qwen_only_retained += int(q_ok and not b_ok and r_ok); bm25_only_recovered += int(b_ok and not q_ok and r_ok)
        if category != "both_correct":
            example = dev_rows[key]; errors.append({"category": category, "example_id": key, "language": r["language"], "gold_source_id": r["gold_source_id"], "rsym_top1_source_id": r["top1_source_id"], "bm25_top1_source_id": b["top1_source_id"], "qwen_top1_source_id": q["top1_source_id"], "rsym_gold_rank": r["gold_rank"], "bm25_gold_rank": b["gold_rank"], "qwen_gold_rank": q["gold_rank"], "rsym_top1_margin": r["top1_margin"], "target_text": example["target"]["text"], "gold_text": dev_catalog[r["gold_source_id"]]["text"], "rsym_top1_text": dev_catalog[r["top1_source_id"]]["text"]})
    selected = []
    for language in ("zh", "en"):
        for category in ("bm25_only", "rsym_only", "both_wrong"):
            selected.extend([row for row in errors if row["language"] == language and row["category"] == category][:4])
    seen = set(); selected = [row for row in selected if not (row["example_id"] in seen or seen.add(row["example_id"]))]
    selected.extend([row for row in errors if row["example_id"] not in seen][:max(0, 20-len(selected))])
    write_jsonl(OUT / "predictions_dev.jsonl", [row for seed in SEEDS for row in outputs[seed][1]])
    write_jsonl(OUT / "predictions_train.jsonl", [row for seed in SEEDS for row in outputs[seed][0]])
    dump(OUT / "metrics.json", {"seed_metrics": seed_metrics, "three_seed_mean": mean_metrics, "bootstrap_rsym_minus_bm25": {"seed": BOOTSTRAP_SEED, "reps": BOOTSTRAP_REPS, "indices_sha256": sha(Q0 / "bootstrap_indices.npy"), "metrics": bootstrap}, "complementarity_median_seed_1": complement, "qwen_only_correct_retained_by_rsym_seed1": qwen_only_retained, "bm25_only_in_q0_recovered_by_rsym_seed1": bm25_only_recovered})
    write_jsonl(OUT / "dev_errors.jsonl", errors); dump(OUT / "representative_errors_max20.json", selected[:20])
    h1 = bootstrap["hit_at_1"]
    transfer = "RSYM_TRANSFER_PASS" if h1["rsym_mean"] > h1["bm25"] and h1["delta_ci95"][0] > 0 else "RSYM_TRANSFER_CONDITIONAL" if h1["rsym_mean"] > h1["bm25"] else "RSYM_TRANSFER_FAIL"
    ninety = "INTERPRETABLE_90_TARGET_REACHED" if h1["rsym_mean"] >= .90 else "INTERPRETABLE_90_TARGET_NOT_REACHED"
    report = ["# LC-Sent-15-Q1 Frozen R-SYM Ranking Transfer", "", "## Frozen M6D contract", "- Input: `[t*s; abs(t-s); cosine(t,s)]` on independently L2-normalized FP32 F_mean vectors.", "- Architecture: Linear(7169,128) -> GELU -> Dropout(0.1) -> Linear(128,1), 917,889 parameters.", "- AdamW lr=3e-4, weight decay=1e-4; 32 candidate groups/batch; clip=1; max 50 epochs; patience=5.", "- Listwise all-positive distribution CE. With exactly one positive among 15 candidates this is standard 15-way CE.", "- Selection: Dev MRR, then nDCG@5, then loss, then earlier epoch. Three seed metrics are computed before scalar averaging.", "", "## Result", f"- Transfer gate: `{transfer}`.", f"- 90% target: `{ninety}`.", f"- R-SYM Dev Hit@1={h1['rsym_mean']:.12f}; BM25={h1['bm25']:.12f}; delta CI={h1['delta_ci95']}.", "", "No Qwen/model forward, BM25 fusion, Reserve, multi-positive, mixed catalog, or Blind input was used."]
    (OUT / "Q1_REPORT.md").write_text("\n".join(report) + "\n", encoding="utf-8")
    files = {str(path.relative_to(OUT)): sha(path) for path in sorted(OUT.rglob("*")) if path.is_file() and path.name not in {"checksums.sha256", "Q1_INTEGRITY.json", "COMPLETED"}}
    (OUT / "checksums.sha256").write_text("".join(f"{digest}  {name}\n" for name, digest in sorted(files.items())), encoding="utf-8")
    integrity = {"status": "PASS", "files": files, "input_manifest_sha256": sha(OUT / "input_manifest.json"), "frozen_config_sha256": sha(OUT / "q1_frozen_config.json"), "transfer_gate": transfer, "ninety_target": ninety, "no_qwen": True, "no_blind": True, "no_reserve": True, "no_multi_positive": True, "no_mixed_catalog": True}
    dump(OUT / "Q1_INTEGRITY.json", integrity)
    (OUT / "COMPLETED").write_text("MEMORYFLOW_LC_SENT15_Q1_RSYM_TRANSFER_COMPLETE\n", encoding="utf-8")


def prepare() -> None:
    if OUT.exists():
        allowed = {"M6D_RSYM_CONTRACT.json", "M6D_RSYM_CONTRACT.md", "q1_frozen_config.json", "input_manifest.json", "runs", "predictions_dev.jsonl", "predictions_train.jsonl", "metrics.json", "dev_errors.jsonl", "representative_errors_max20.json", "Q1_REPORT.md", "checksums.sha256", "Q1_INTEGRITY.json", "COMPLETED"}
        extra = {path.name for path in OUT.iterdir()} - allowed
        if extra: raise RuntimeError(f"CONFLICT unexpected output files: {sorted(extra)}")
    else:
        OUT.mkdir(parents=True)
    recipe, inputs = frozen_recipe(), validate_inputs()
    train = read_jsonl(DATA / "train" / "single_positive_15.jsonl"); dev = read_jsonl(DATA / "dev" / "single_positive_15.jsonl")
    counts = {"train_targets": len(train), "train_pairs": len(train)*CANDIDATE_SIZE, "dev_targets": len(dev), "dev_pairs": len(dev)*CANDIDATE_SIZE, "dev_positive": sum(sum(int(candidate["label"]) for candidate in row["candidates"]) for row in dev), "dev_negative": len(dev)*(CANDIDATE_SIZE-1), "candidate_size": CANDIDATE_SIZE, "all_groups_single_positive": True}
    frozen = {"checkpoint": "LC-Sent-15-Q1", "before_new_training_metrics": True, "contract": recipe, "input_integrity": inputs, "data_contract": counts, "selection_metric": "Dev MRR", "bootstrap": {"seed": BOOTSTRAP_SEED, "reps": BOOTSTRAP_REPS, "unit": "target", "seed_first_metrics": True}, "prohibitions": {"qwen": True, "blind": True, "reserve": True, "multi_positive": True, "mixed_catalog": True, "bm25_input": True, "new_hyperparameter_search": True}}
    for name, value in (("M6D_RSYM_CONTRACT.json", recipe), ("q1_frozen_config.json", frozen), ("input_manifest.json", inputs)):
        path = OUT / name
        if path.exists() and json.loads(path.read_text()) != value: raise RuntimeError(f"CONFLICT frozen file differs: {name}")
        if not path.exists(): dump(path, value)
    markdown = "# LC-Sent-15-Q1 Frozen R-SYM Contract\n\nThis checkpoint transfers only the exact M6D `rank/R_SYM` recipe to the immutable LC-Sent-15 c15 single-positive cache. The preregistration is in `q1_frozen_config.json`.\n"
    path = OUT / "M6D_RSYM_CONTRACT.md"
    if not path.exists(): path.write_text(markdown, encoding="utf-8")


def gpu_device() -> torch.device:
    if not torch.cuda.is_available(): return torch.device("cpu")
    snapshot = subprocess.check_output(["nvidia-smi", "--query-gpu=index,memory.free", "--format=csv,noheader,nounits"], text=True).splitlines()
    free = [(int(line.split(",")[0]), int(line.split(",")[1])) for line in snapshot]
    # With a 918k-parameter head and c15 batch this needs under 1 GiB; retain 8 GiB safety room.
    safe = [entry for entry in free if entry[1] >= 8192]
    if not safe: return torch.device("cpu")
    chosen = max(safe, key=lambda item: (item[1], -item[0]))[0]
    # Torch is already imported here, so preserve an explicit physical-device mapping.
    return torch.device(f"cuda:{chosen}")


def main() -> None:
    parser = argparse.ArgumentParser(); parser.add_argument("mode", choices=("prepare", "train", "finalize")); parser.add_argument("--seed", type=int)
    args = parser.parse_args()
    if args.mode == "prepare": prepare(); return
    if args.mode == "train":
        if args.seed not in SEEDS: raise RuntimeError("seed must be one of frozen 0,1,2")
        prepare(); device = gpu_device(); train_seed(args.seed, device); return
    if args.mode == "finalize": finalise(); return


if __name__ == "__main__":
    main()
