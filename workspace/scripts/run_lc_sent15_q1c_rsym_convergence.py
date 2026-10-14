#!/usr/bin/env python3
"""Q1C convergence closure: exact Q1 prefix replay, then ranking-patience continuation."""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import pickle
import random
import shutil
import sys
import time
from pathlib import Path

import numpy as np
import torch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src")); sys.path.insert(0, str(ROOT / "scripts"))
from memoryflow.lc_sent15_q1_rsym import DIM, PARAMETER_COUNT, bootstrap_seed_first, listwise_single_positive_loss, validate_rsym_contract
from memoryflow.source_prior_relational import SymmetricRelation
from run_lc_sent15_q1_rsym_transfer import (
    BM25, DATA, EXPECTED_CACHES, GROUP_BATCH, LR, PATIENCE, Q0, SEEDS, WEIGHT_DECAY,
    aggregate, listwise_eval_loss, load_split, model_logits, scores_and_targets, sha, tensors,
    unpack_features, validate_inputs,
)

Q1 = ROOT / "results/lc_sent15_v1_q1_rsym_transfer_v1"
OUT = ROOT / "results/lc_sent15_v1_q1c_rsym_convergence_v1"
MAX_EPOCH = 100
CLIP = 1.0
TOLERANCE = 1e-8


def dump(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")
    os.replace(temp, path)


def write_jsonl(path: Path, rows: list[dict]) -> None:
    temp = path.with_suffix(path.suffix + ".tmp")
    with temp.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows: handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True, allow_nan=False) + "\n")
    os.replace(temp, path)


def seed_all(seed: int, device: torch.device) -> None:
    random.seed(seed); np.random.seed(seed); torch.manual_seed(seed)
    if device.type == "cuda": torch.cuda.manual_seed_all(seed)


def selection_key(metrics: dict, epoch: int) -> tuple[float, float, float, int]:
    return (-metrics["overall"]["mrr"], -metrics["overall"]["ndcg_at_5"], metrics["ranking_loss"], epoch)


def encode_rng(device: torch.device) -> dict:
    result = {
        "python_pickle_b64": base64.b64encode(pickle.dumps(random.getstate())).decode("ascii"),
        "numpy_pickle_b64": base64.b64encode(pickle.dumps(np.random.get_state())).decode("ascii"),
        "torch_cpu": torch.get_rng_state().cpu(),
    }
    if device.type == "cuda": result["torch_cuda"] = torch.cuda.get_rng_state(device).cpu()
    return result


def restore_rng(payload: dict, device: torch.device) -> None:
    random.setstate(pickle.loads(base64.b64decode(payload["python_pickle_b64"])))
    np.random.set_state(pickle.loads(base64.b64decode(payload["numpy_pickle_b64"])))
    torch.set_rng_state(payload["torch_cpu"])
    if device.type == "cuda": torch.cuda.set_rng_state(payload["torch_cuda"], device)


def q1_audit() -> dict:
    if sha(Q1 / "Q1_INTEGRITY.json") != "f350016fd1a431f640a50937c547a738daa503f532d851c83be8ee4d03882ef0":
        raise RuntimeError("Q1 integrity SHA mismatch")
    missing = {}
    for seed in SEEDS:
        directory = Q1 / "runs" / f"seed_{seed}"
        present = sorted(path.name for path in directory.iterdir())
        required = {"epoch_30_model.pt", "epoch_30_optimizer.pt", "epoch_30_rng.pt", "epoch_30_state.json"}
        missing[str(seed)] = sorted(required - set(present))
    return {"q1_integrity_sha256": sha(Q1 / "Q1_INTEGRITY.json"), "path": "B_RETRAIN_PREFIX", "missing_exact_resume_material": missing, "reason": "Q1 stores only best.pt/history/predictions; no committed epoch-30 model, optimizer, RNG, or sampler state."}


def prepare() -> None:
    if OUT.exists():
        allowed = {"q1c_frozen_config.json", "input_manifest.json", "q1_resume_audit.json", "PREFIX_REPRODUCTION.json", "runs", "metrics.json", "predictions_dev.jsonl", "Q1C_REPORT.md", "checksums.sha256", "Q1C_INTEGRITY.json", "COMPLETED"}
        extra = {path.name for path in OUT.iterdir()} - allowed
        if extra: raise RuntimeError(f"CONFLICT unexpected Q1C files: {sorted(extra)}")
    else:
        OUT.mkdir(parents=True)
    inputs = validate_inputs(); audit = q1_audit(); validate_rsym_contract()
    frozen = {"checkpoint": "LC-Sent-15-Q1C", "path": "B_RETRAIN_PREFIX", "q1_integrity_sha256": audit["q1_integrity_sha256"], "feature_cache_sha256": EXPECTED_CACHES, "architecture": "SymmetricRelation: [t*s; abs(t-s); cosine], Linear(7169,128), GELU, Dropout(0.1), Linear(128,1)", "parameter_count": PARAMETER_COUNT, "optimizer": "AdamW", "lr": LR, "weight_decay": WEIGHT_DECAY, "group_batch_size": GROUP_BATCH, "loss": "all-positive distribution listwise CE; exact c15 single-positive CE", "seeds": list(SEEDS), "selection": "Dev MRR desc, nDCG@5 desc, ranking loss asc, earlier epoch", "patience": PATIENCE, "prefix_epochs": 30, "max_epoch": MAX_EPOCH, "numerical_tolerance": TOLERANCE, "no_qwen": True, "no_blind": True, "no_reserve": True, "no_multi_positive": True, "no_mixed_catalog": True}
    for name, value in (("q1c_frozen_config.json", frozen), ("input_manifest.json", inputs), ("q1_resume_audit.json", audit)):
        path = OUT / name
        if path.exists() and json.loads(path.read_text()) != value: raise RuntimeError(f"CONFLICT {name}")
        if not path.exists(): dump(path, value)


def epoch_dir(seed: int, epoch: int) -> Path:
    return OUT / "runs" / f"seed_{seed}" / "epochs" / f"epoch_{epoch:03d}"


def complete_epoch(seed: int, epoch: int) -> bool:
    directory = epoch_dir(seed, epoch)
    required = ("model.pt", "optimizer.pt", "rng.pt", "state.json", "integrity.json", "COMPLETED")
    if not all((directory / name).is_file() for name in required): return False
    integrity = json.loads((directory / "integrity.json").read_text())
    return all(sha(directory / name) == digest for name, digest in integrity["files"].items())


def last_complete_epoch(seed: int) -> int:
    result = 0
    while complete_epoch(seed, result + 1): result += 1
    return result


def load_epoch(seed: int, epoch: int, device: torch.device) -> tuple[SymmetricRelation, torch.optim.Optimizer, dict]:
    directory = epoch_dir(seed, epoch)
    model = SymmetricRelation(DIM).to(device).float(); optimizer = torch.optim.AdamW(model.parameters(), lr=LR, weight_decay=WEIGHT_DECAY)
    model.load_state_dict(torch.load(directory / "model.pt", map_location=device, weights_only=True))
    optimizer.load_state_dict(torch.load(directory / "optimizer.pt", map_location=device, weights_only=False))
    rng = torch.load(directory / "rng.pt", map_location="cpu", weights_only=False); restore_rng(rng, device)
    state = json.loads((directory / "state.json").read_text())
    return model, optimizer, state


def initial_state(seed: int, device: torch.device) -> tuple[SymmetricRelation, torch.optim.Optimizer, dict, list[dict]]:
    seed_all(seed, device)
    model = SymmetricRelation(DIM).to(device).float(); optimizer = torch.optim.AdamW(model.parameters(), lr=LR, weight_decay=WEIGHT_DECAY)
    return model, optimizer, {"best_epoch": None, "best_key": None, "bad_count": 0}, []


def validate_prefix_seed(seed: int) -> dict:
    q1_history = json.loads((Q1 / "runs" / f"seed_{seed}" / "history.json").read_text())
    q1_best = json.loads((Q1 / "runs" / f"seed_{seed}" / "best.json").read_text())
    q1c = [json.loads((epoch_dir(seed, epoch) / "state.json").read_text()) for epoch in range(1, 31)]
    max_error = 0.0; violations = []
    for old, new in zip(q1_history[:30], q1c):
        for split in ("train", "dev"):
            for scope in ("overall", "zh", "en"):
                for metric in ("hit_at_1", "mrr", "ndcg_at_5", "mean_gold_rank"):
                    error = abs(float(old[split][scope][metric]) - float(new[split][scope][metric]))
                    max_error = max(max_error, error)
                    if error > TOLERANCE: violations.append({"epoch": new["epoch"], "split": split, "scope": scope, "metric": metric, "error": error})
        error = abs(float(old["dev"]["ranking_loss"]) - float(new["dev"]["ranking_loss"])); max_error = max(max_error, error)
        if error > TOLERANCE: violations.append({"epoch": new["epoch"], "metric": "ranking_loss", "error": error})
    best_epoch = min(q1c, key=lambda state: tuple(state["best_key"]) if state["epoch"] == state["best_epoch"] else (float("inf"),))
    actual_best_epoch = q1c[-1]["best_epoch"]
    if actual_best_epoch != q1_best["epoch"]: violations.append({"field": "best_epoch", "expected": q1_best["epoch"], "actual": actual_best_epoch})
    return {"seed": seed, "expected_best_epoch": q1_best["epoch"], "actual_best_epoch": actual_best_epoch, "max_abs_error": max_error, "violations": violations, "pass": not violations}


def commit_epoch(seed: int, epoch: int, model: SymmetricRelation, optimizer: torch.optim.Optimizer, state: dict, device: torch.device) -> None:
    final = epoch_dir(seed, epoch); work = final.with_name("." + final.name + ".tmp")
    if final.exists():
        if complete_epoch(seed, epoch): return
        raise RuntimeError(f"incomplete committed epoch conflict: {final}")
    if work.exists(): raise RuntimeError(f"stale temporary epoch: {work}")
    work.mkdir(parents=True)
    torch.save({key: value.detach().cpu() for key, value in model.state_dict().items()}, work / "model.pt")
    torch.save(optimizer.state_dict(), work / "optimizer.pt")
    torch.save(encode_rng(device), work / "rng.pt")
    dump(work / "state.json", state)
    files = {path.name: sha(path) for path in (work / "model.pt", work / "optimizer.pt", work / "rng.pt", work / "state.json")}
    dump(work / "integrity.json", {"files": files, "q1c_config_sha256": sha(OUT / "q1c_frozen_config.json")})
    (work / "COMPLETED").write_text("completed\n", encoding="utf-8")
    os.replace(work, final)


def run_seed(seed: int, phase: str, device: torch.device) -> None:
    train, train_catalog, train_packed = load_split("train"); dev, dev_catalog, dev_packed = load_split("dev")
    train_targets, train_sources = unpack_features(train, train_catalog, train_packed); dev_targets, dev_sources = unpack_features(dev, dev_catalog, dev_packed)
    tt, ts, ty, tg = tensors(train, train_targets, train_sources, device); dt, ds, _, _ = tensors(dev, dev_targets, dev_sources, device)
    latest = last_complete_epoch(seed)
    if latest:
        model, optimizer, current = load_epoch(seed, latest, device); history = [json.loads((epoch_dir(seed, i) / "state.json").read_text()) for i in range(1, latest + 1)]
    else:
        model, optimizer, current, history = initial_state(seed, device)
    stop = 30 if phase == "prefix" else MAX_EPOCH
    for epoch in range(latest + 1, stop + 1):
        model.train(); losses = []; order = np.random.default_rng(seed + 1000 + epoch).permutation(len(train))
        for start in range(0, len(train), GROUP_BATCH):
            chosen = order[start:start+GROUP_BATCH]; mask = torch.zeros(len(ty), dtype=torch.bool, device=device)
            for group in chosen: mask |= tg == int(group)
            optimizer.zero_grad(set_to_none=True); loss = listwise_single_positive_loss(model_logits(model, tt[mask], ts[mask]), ty[mask], tg[mask])
            if not torch.isfinite(loss): raise RuntimeError("non-finite loss")
            loss.backward(); grad_norm = float(torch.nn.utils.clip_grad_norm_(model.parameters(), CLIP)); optimizer.step(); losses.append(float(loss.detach().cpu()))
        model.eval()
        with torch.inference_mode():
            train_logits = model_logits(model, tt, ts).cpu().numpy(); dev_logits = model_logits(model, dt, ds).cpu().numpy()
        if not (np.isfinite(train_logits).all() and np.isfinite(dev_logits).all()): raise RuntimeError("non-finite logits")
        _, train_rows = scores_and_targets(train, train_logits, "train", seed); _, dev_rows = scores_and_targets(dev, dev_logits, "dev", seed)
        train_metrics, dev_metrics = aggregate(train_rows), aggregate(dev_rows); train_metrics["ranking_loss"] = listwise_eval_loss(train_logits, train); dev_metrics["ranking_loss"] = listwise_eval_loss(dev_logits, dev)
        key = selection_key(dev_metrics, epoch); improved = current["best_key"] is None or key < tuple(current["best_key"])
        bad = 0 if improved else current["bad_count"] + 1
        if improved: best_epoch, best_key = epoch, list(key)
        else: best_epoch, best_key = current["best_epoch"], current["best_key"]
        state = {"epoch": epoch, "train_loss": float(np.mean(losses)), "grad_norm_preclip": grad_norm, "train": train_metrics, "dev": dev_metrics, "improved": improved, "bad_count": bad, "best_epoch": best_epoch, "best_key": best_key, "sampler": {"algorithm": "np.random.default_rng(seed + 1000 + epoch).permutation(train_group_count)", "seed": seed + 1000 + epoch, "group_count": len(train)}}
        commit_epoch(seed, epoch, model, optimizer, state, device); current = state; history.append(state)
        if phase == "continue" and bad >= PATIENCE: break
    dump(OUT / "runs" / f"seed_{seed}" / "current_state.json", current)


def prefix_gate() -> None:
    result = {"path": "B_RETRAIN_PREFIX", "tolerance": TOLERANCE, "seeds": [validate_prefix_seed(seed) for seed in SEEDS]}
    result["pass"] = all(row["pass"] for row in result["seeds"])
    dump(OUT / "PREFIX_REPRODUCTION.json", result)
    if not result["pass"]: raise RuntimeError("MEMORYFLOW_LC_SENT15_Q1C_PREFIX_REPRO_FAIL")


def best_epoch_state(seed: int) -> dict:
    latest = last_complete_epoch(seed)
    if not latest: raise RuntimeError("missing seed epochs")
    latest_state = json.loads((epoch_dir(seed, latest) / "state.json").read_text())
    return json.loads((epoch_dir(seed, latest_state["best_epoch"]) / "state.json").read_text())


def finalise(device: torch.device) -> None:
    if (OUT / "COMPLETED").exists(): return
    prefix_gate()
    train, train_catalog, train_packed = load_split("train"); dev, dev_catalog, dev_packed = load_split("dev")
    train_targets, train_sources = unpack_features(train, train_catalog, train_packed); dev_targets, dev_sources = unpack_features(dev, dev_catalog, dev_packed)
    tt, ts, _, _ = tensors(train, train_targets, train_sources, device); dt, ds, _, _ = tensors(dev, dev_targets, dev_sources, device)
    seed_rows = []; all_predictions = []
    for seed in SEEDS:
        latest = last_complete_epoch(seed); latest_state = json.loads((epoch_dir(seed, latest) / "state.json").read_text()); best = best_epoch_state(seed)
        model, _, _ = load_epoch(seed, best["epoch"], device); model.eval()
        with torch.inference_mode(): train_logits = model_logits(model, tt, ts).cpu().numpy(); dev_logits = model_logits(model, dt, ds).cpu().numpy()
        train_predictions, train_targets_rows = scores_and_targets(train, train_logits, "train", seed); dev_predictions, dev_targets_rows = scores_and_targets(dev, dev_logits, "dev", seed)
        write_jsonl(OUT / "runs" / f"seed_{seed}" / "best_train_predictions.jsonl", train_predictions); write_jsonl(OUT / "runs" / f"seed_{seed}" / "best_dev_predictions.jsonl", dev_predictions); dump(OUT / "runs" / f"seed_{seed}" / "best_train_targets.json", train_targets_rows); dump(OUT / "runs" / f"seed_{seed}" / "best_dev_targets.json", dev_targets_rows)
        torch.save(model.state_dict(), OUT / "runs" / f"seed_{seed}" / "best.pt")
        summary = {"seed": seed, "best_epoch": best["epoch"], "terminal_epoch": latest, "post_peak_bad_count": latest_state["bad_count"], "terminal_reason": "patience_5" if latest_state["bad_count"] >= PATIENCE else "max_epoch_100", "train": aggregate(train_targets_rows), "dev": aggregate(dev_targets_rows), "checkpoint_sha256": sha(OUT / "runs" / f"seed_{seed}" / "best.pt"), "best_epoch_state_sha256": sha(epoch_dir(seed, best["epoch"]) / "state.json"), "terminal_epoch_state_sha256": sha(epoch_dir(seed, latest) / "state.json"), "peak_gpu_bytes": int(torch.cuda.max_memory_allocated(device)) if device.type == "cuda" else 0}
        dump(OUT / "runs" / f"seed_{seed}" / "summary.json", summary); seed_rows.append(summary); all_predictions.extend(dev_predictions)
    bm25 = [json.loads(line) for line in (BM25 / "bm25_legacy_dev_predictions.jsonl").read_text().splitlines() if line]
    bm25_map = {row["example_id"]: row for row in bm25}; ids = [row["example_id"] for row in json.loads((OUT / "runs/seed_0/best_dev_targets.json").read_text())]
    ranks = np.asarray([[row["gold_rank"] for row in json.loads((OUT / f"runs/seed_{seed}/best_dev_targets.json").read_text())] for seed in SEEDS], dtype=np.int64); bm25_ranks = np.asarray([bm25_map[key]["gold_rank"] for key in ids], dtype=np.int64)
    indices = np.load(Q0 / "bootstrap_indices.npy"); boot = bootstrap_seed_first(ranks, bm25_ranks, indices)
    old = json.loads((Q1 / "metrics.json").read_text())["three_seed_mean"]
    mean = {split: {scope: {metric: float(np.mean([row[split][scope][metric] for row in seed_rows])) for metric in ("hit_at_1", "mrr", "ndcg_at_5", "mean_gold_rank")} for scope in ("overall", "zh", "en")} for split in ("train", "dev")}
    delta_q1 = {metric: mean["dev"]["overall"][metric] - old["dev"]["overall"][metric] for metric in ("hit_at_1", "mrr", "ndcg_at_5", "mean_gold_rank")}
    hit = boot["hit_at_1"]; transfer = "RSYM_TRANSFER_PASS" if hit["rsym_mean"] > hit["bm25"] and hit["delta_ci95"][0] > 0 else "RSYM_TRANSFER_CONDITIONAL" if hit["rsym_mean"] > hit["bm25"] else "RSYM_TRANSFER_FAIL"
    ninety = "INTERPRETABLE_90_TARGET_REACHED" if hit["rsym_mean"] >= .90 else "INTERPRETABLE_90_TARGET_NOT_REACHED"
    terminal = "Q1_CONVERGENCE_CLOSED" if all(row["terminal_reason"] == "patience_5" for row in seed_rows) else "Q1_CONVERGENCE_CENSORED_AT_100"
    write_jsonl(OUT / "predictions_dev.jsonl", all_predictions)
    dump(OUT / "metrics.json", {"seed_metrics": seed_rows, "three_seed_mean": mean, "q1_to_q1c_dev_delta": delta_q1, "bootstrap_rsym_minus_bm25": {"seed": 20260815, "reps": 10000, "indices_sha256": sha(Q0 / "bootstrap_indices.npy"), "metrics": boot}, "convergence": terminal, "transfer_gate": transfer, "ninety_target": ninety})
    report = ["# LC-Sent-15-Q1C R-SYM Convergence Closure", "", f"- Resume path: **B_RETRAIN_PREFIX**, because Q1 had no epoch-30 model/optimizer/RNG resume state.", f"- Prefix reproduction tolerance: {TOLERANCE}; see `PREFIX_REPRODUCTION.json`.", f"- Convergence state: `{terminal}`.", f"- Transfer gate: `{transfer}`; 90% target: `{ninety}`.", f"- Dev R-SYM Hit@1={hit['rsym_mean']:.12f}, BM25={hit['bm25']:.12f}, CI={hit['delta_ci95']}.", "", "No Qwen, Blind, Reserve, multi-positive, or mixed catalog was accessed."]
    (OUT / "Q1C_REPORT.md").write_text("\n".join(report) + "\n", encoding="utf-8")
    files = {str(path.relative_to(OUT)): sha(path) for path in sorted(OUT.rglob("*")) if path.is_file() and path.name not in {"checksums.sha256", "Q1C_INTEGRITY.json", "COMPLETED"}}
    (OUT / "checksums.sha256").write_text("".join(f"{digest}  {name}\n" for name, digest in sorted(files.items())), encoding="utf-8")
    dump(OUT / "Q1C_INTEGRITY.json", {"status": "PASS", "files": files, "q1_integrity_sha256": sha(Q1 / "Q1_INTEGRITY.json"), "input_manifest_sha256": sha(OUT / "input_manifest.json"), "prefix_sha256": sha(OUT / "PREFIX_REPRODUCTION.json"), "convergence": terminal, "transfer_gate": transfer, "no_qwen": True, "no_blind": True, "no_reserve": True, "no_multi_positive": True, "no_mixed_catalog": True})
    (OUT / "COMPLETED").write_text("MEMORYFLOW_LC_SENT15_Q1C_CONVERGENCE_COMPLETE\n", encoding="utf-8")


def device() -> torch.device:
    # Q1 used physical GPU4; preserve its math setting only if its 8 GiB safety gate is free.
    if torch.cuda.is_available() and torch.cuda.mem_get_info(4)[0] >= 8 * 1024**3:
        return torch.device("cuda:4")
    raise RuntimeError("Q1C needs free GPU4 for strict Q1 prefix reproduction")


def main() -> None:
    parser = argparse.ArgumentParser(); parser.add_argument("mode", choices=("prepare", "prefix", "continue", "finalize")); args = parser.parse_args()
    if args.mode == "prepare": prepare(); return
    prepare(); chosen = device()
    if args.mode == "prefix":
        for seed in SEEDS: run_seed(seed, "prefix", chosen)
        prefix_gate(); return
    if args.mode == "continue":
        prefix_gate()
        for seed in SEEDS: run_seed(seed, "continue", chosen)
        return
    finalise(chosen)


if __name__ == "__main__": main()
