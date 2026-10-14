#!/usr/bin/env python3
"""LC-Sent-15-Q2C: one frozen D-Full-128 listwise capacity control."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
import torch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "scripts")]
from memoryflow.lc_sent15_q2c import EXPECTED_PARAMETERS, HEAD, LOSS, DirectionalFull128, grouped_loss, validate_contract
from run_lc_sent15_q1_rsym_transfer import (
    BM25, DATA, EXPECTED_CACHES, GROUP_BATCH, LR, Q0, SEEDS, WEIGHT_DECAY,
    aggregate, bootstrap_seed_first, listwise_eval_loss, load_split, scores_and_targets,
    sha, tensors, unpack_features, validate_inputs,
)

Q1C = ROOT / "results/lc_sent15_v1_q1c_rsym_convergence_v1"
Q2 = ROOT / "results/lc_sent15_v1_q2_head_loss_v1"
OUT = ROOT / "results/lc_sent15_v1_q2c_dfull128_capacity_v1"
PATIENCE, EPOCHS, CLIP, BOOT_SEED, REPS = 5, 100, 1.0, 20260815, 10_000


def dump(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def jsonl(path: Path, rows: list[dict]) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False, sort_keys=True, allow_nan=False) + "\n")
    os.replace(tmp, path)


def seed_all(seed: int) -> None:
    random.seed(seed); np.random.seed(seed); torch.manual_seed(seed); torch.cuda.manual_seed_all(seed)


def selection_key(metrics: dict, epoch: int) -> tuple:
    return (-metrics["overall"]["hit_at_1"], -metrics["overall"]["mrr"], -metrics["overall"]["ndcg_at_5"], metrics["cell_loss"], epoch)


def choose_device() -> tuple[torch.device, list[dict]]:
    lines = subprocess.check_output(["nvidia-smi", "--query-gpu=index,memory.free,memory.total", "--format=csv,noheader,nounits"], text=True).splitlines()
    snap = []
    for line in lines:
        index, free, total = [int(x.strip()) for x in line.split(",")]
        snap.append({"physical_gpu": index, "free_mib": free, "total_mib": total})
    safe = [x for x in snap if x["free_mib"] >= 8192]
    if not safe:
        raise RuntimeError("NO_SAFE_GPU")
    selected = max(safe, key=lambda x: (x["free_mib"], -x["physical_gpu"]))
    return torch.device(f"cuda:{selected['physical_gpu']}"), snap


def run_dir(seed: int) -> Path:
    return OUT / "runs" / f"seed_{seed}"


def files_ok(directory: Path) -> bool:
    if not (directory / "COMPLETED").is_file() or not (directory / "integrity.json").is_file():
        return False
    integrity = json.loads((directory / "integrity.json").read_text())
    return all(sha(directory / name) == value for name, value in integrity["files"].items())


def prepare() -> None:
    if OUT.exists():
        allowed = {"q2c_frozen_config.json", "input_manifest.json", "gpu_snapshot.json", "q2c_run.log", "runs", "metrics.json", "predictions_dev.jsonl", "bootstrap.json", "Q2C_REPORT.md", "Q2C_INTEGRITY.json", "checksums.sha256", "COMPLETED"}
        extra = {p.name for p in OUT.iterdir()} - allowed
        if extra:
            raise RuntimeError(f"CONFLICT unexpected output entries: {sorted(extra)}")
    else:
        OUT.mkdir(parents=True)
    validate_contract(); validate_inputs()
    expected = {
        Q2 / "Q2_INTEGRITY.json": "45eeca3adf1572ee924c363ed0146a030e4afe587b63253fa47bfd4479bb9824",
        Q1C / "Q1C_INTEGRITY.json": "dd0070676c296df85cf50142cf2b5522b4afc876a8ff6a140edb57d24698252b",
        Q0 / "integrity_report.json": "a69e1906e388ecaf5567f76bcae957a621e713e3abf18d2d65388ec98a47cf53",
    }
    for path, expected_sha in expected.items():
        if sha(path) != expected_sha:
            raise RuntimeError(f"input integrity SHA mismatch: {path}")
    config = {
        "checkpoint": "LC-Sent-15-Q2C", "head": HEAD, "loss": LOSS,
        "input": "[t;s;t*s;abs(t-s);cosine]", "input_dim": 14337, "params": EXPECTED_PARAMETERS,
        "network": "Linear(14337,128)->GELU->Dropout(0.1)->Linear(128,1)",
        "optimizer": "AdamW", "lr": LR, "weight_decay": WEIGHT_DECAY, "groups_per_batch": GROUP_BATCH,
        "max_epoch": EPOCHS, "patience": PATIENCE, "gradient_clip_norm": CLIP, "seeds": list(SEEDS),
        "selection": "Dev Hit@1 desc, MRR desc, nDCG@5 desc, cell loss asc, earlier epoch",
        "bootstrap": {"seed": BOOT_SEED, "reps": REPS, "unit": "target", "seed_first_metrics": True},
        "prohibitions": {"qwen": True, "blind": True, "reserve": True, "multi_positive": True, "mixed_catalog": True, "bm25_input": True, "new_hyperparameters": True},
    }
    inputs = validate_inputs() | {"feature_caches": EXPECTED_CACHES, "q2_integrity": sha(Q2 / "Q2_INTEGRITY.json"), "q1c_integrity": sha(Q1C / "Q1C_INTEGRITY.json")}
    for name, value in (("q2c_frozen_config.json", config), ("input_manifest.json", inputs)):
        path = OUT / name
        if path.exists() and json.loads(path.read_text()) != value:
            raise RuntimeError(f"CONFLICT {name}")
        if not path.exists():
            dump(path, value)


def run_one(seed: int, device: torch.device) -> None:
    directory = run_dir(seed)
    if files_ok(directory): return
    if directory.exists(): raise RuntimeError(f"incomplete run conflict: {directory}")
    work = directory.with_name("." + directory.name + ".tmp")
    if work.exists(): raise RuntimeError(f"staging conflict: {work}")
    work.mkdir(parents=True)
    train, train_catalog, train_pairs = load_split("train")
    dev, dev_catalog, dev_pairs = load_split("dev")
    train_target, train_source = unpack_features(train, train_catalog, train_pairs)
    dev_target, dev_source = unpack_features(dev, dev_catalog, dev_pairs)
    tt, ts, ty, tg = tensors(train, train_target, train_source, device)
    dt, ds, _, _ = tensors(dev, dev_target, dev_source, device)
    seed_all(seed)
    model = DirectionalFull128().to(device).float()
    optimizer = torch.optim.AdamW(model.parameters(), lr=LR, weight_decay=WEIGHT_DECAY)
    best, bad, history, started = None, 0, [], time.time()
    torch.cuda.reset_peak_memory_stats(device)
    for epoch in range(1, EPOCHS + 1):
        model.train(); losses = []
        order = np.random.default_rng(seed + 1000 + epoch).permutation(len(train))
        for start in range(0, len(train), GROUP_BATCH):
            take = order[start:start + GROUP_BATCH]
            mask = torch.zeros(len(ty), dtype=torch.bool, device=device)
            for group in take: mask |= tg == int(group)
            optimizer.zero_grad(set_to_none=True)
            loss = grouped_loss(LOSS, model(tt[mask], ts[mask]), ty[mask].bool(), tg[mask])
            if not torch.isfinite(loss): raise RuntimeError("nonfinite loss")
            loss.backward()
            grad = float(torch.nn.utils.clip_grad_norm_(model.parameters(), CLIP))
            optimizer.step(); losses.append(float(loss.detach().cpu()))
        model.eval()
        with torch.inference_mode():
            train_logits = model(tt, ts).cpu().numpy(); dev_logits = model(dt, ds).cpu().numpy()
        if not (np.isfinite(train_logits).all() and np.isfinite(dev_logits).all()): raise RuntimeError("nonfinite logits")
        _, train_targets = scores_and_targets(train, train_logits, "train", seed)
        _, dev_targets = scores_and_targets(dev, dev_logits, "dev", seed)
        train_metrics, dev_metrics = aggregate(train_targets), aggregate(dev_targets)
        train_metrics["ranking_loss"] = listwise_eval_loss(train_logits, train)
        dev_metrics["ranking_loss"] = listwise_eval_loss(dev_logits, dev)
        dev_metrics["cell_loss"] = dev_metrics["ranking_loss"]
        key = selection_key(dev_metrics, epoch)
        improved = best is None or key < tuple(best["key"])
        bad = 0 if improved else bad + 1
        history.append({"epoch": epoch, "train_loss": float(np.mean(losses)), "grad_norm_preclip": grad, "train": train_metrics, "dev": dev_metrics, "improved": improved, "bad_count": bad})
        if improved:
            best = {"epoch": epoch, "key": list(key), "state": {n: x.detach().cpu() for n, x in model.state_dict().items()}, "train": train_metrics, "dev": dev_metrics}
        if bad >= PATIENCE: break
    assert best is not None
    torch.save(best.pop("state"), work / "best.pt")
    torch.save(optimizer.state_dict(), work / "terminal_optimizer.pt")
    torch.save({"torch_cpu": torch.get_rng_state().cpu(), "torch_cuda": torch.cuda.get_rng_state(device).cpu()}, work / "terminal_rng.pt")
    restored = DirectionalFull128().to(device).float(); restored.load_state_dict(torch.load(work / "best.pt", map_location=device, weights_only=True)); restored.eval()
    with torch.inference_mode():
        train_logits = restored(tt, ts).cpu().numpy(); dev_logits = restored(dt, ds).cpu().numpy()
    train_predictions, train_targets = scores_and_targets(train, train_logits, "train", seed)
    dev_predictions, dev_targets = scores_and_targets(dev, dev_logits, "dev", seed)
    train_metrics, dev_metrics = aggregate(train_targets), aggregate(dev_targets)
    train_metrics["ranking_loss"] = listwise_eval_loss(train_logits, train); dev_metrics["ranking_loss"] = listwise_eval_loss(dev_logits, dev)
    config = {"head": HEAD, "loss": LOSS, "seed": seed, "params": EXPECTED_PARAMETERS, "lr": LR, "weight_decay": WEIGHT_DECAY, "groups_per_batch": GROUP_BATCH, "max_epoch": EPOCHS, "patience": PATIENCE, "selection": "Hit@1/MRR/nDCG@5/cell-loss/earlier", "device": str(device), "no_qwen": True, "no_blind": True, "no_bm25_input": True}
    best.update({"best_checkpoint_metrics_after_reload": {"train": train_metrics, "dev": dev_metrics}, "terminal_epoch": history[-1]["epoch"], "post_peak_bad_count": bad, "terminal_reason": "patience_5" if bad >= PATIENCE else "CENSORED_AT_100", "runtime_seconds": time.time() - started, "peak_gpu_bytes": int(torch.cuda.max_memory_allocated(device))})
    dump(work / "config.json", config); dump(work / "history.json", history); dump(work / "best.json", best)
    jsonl(work / "train_predictions.jsonl", train_predictions); jsonl(work / "dev_predictions.jsonl", dev_predictions)
    dump(work / "train_targets.json", train_targets); dump(work / "dev_targets.json", dev_targets)
    files = {p.name: sha(p) for p in work.iterdir() if p.is_file()}
    dump(work / "integrity.json", {"files": files, "input_manifest_sha256": sha(OUT / "input_manifest.json"), "frozen_config_sha256": sha(OUT / "q2c_frozen_config.json")})
    (work / "COMPLETED").write_text("completed\n")
    os.replace(work, directory)


def pair_boot(a: np.ndarray, b: np.ndarray, indices: np.ndarray) -> dict:
    output = {}
    for name, fun in {"hit_at_1": lambda x: x == 1, "mrr": lambda x: 1 / x, "ndcg_at_5": lambda x: np.where(x <= 5, 1 / np.log2(x + 1), 0)}.items():
        av, bv = fun(a.astype(float)), fun(b.astype(float))
        deltas = av[:, indices].mean(2).mean(0) - bv[:, indices].mean(2).mean(0)
        output[name] = {"delta": float(av.mean(1).mean() - bv.mean(1).mean()), "ci95": [float(np.quantile(deltas, .025)), float(np.quantile(deltas, .975))]}
    return output


def finalise() -> None:
    if (OUT / "COMPLETED").exists(): return
    rows = []
    for seed in SEEDS:
        directory = run_dir(seed)
        if not files_ok(directory): raise RuntimeError(f"incomplete {directory}")
        best = json.loads((directory / "best.json").read_text())
        rows.append({"seed": seed, "best_epoch": best["epoch"], "terminal_epoch": best["terminal_epoch"], "terminal_reason": best["terminal_reason"], "params": EXPECTED_PARAMETERS, "runtime_seconds": best["runtime_seconds"], "peak_gpu_bytes": best["peak_gpu_bytes"], "train": best["best_checkpoint_metrics_after_reload"]["train"], "dev": best["best_checkpoint_metrics_after_reload"]["dev"], "checkpoint_sha256": sha(directory / "best.pt")})
    mean = {metric: float(np.mean([r["dev"]["overall"][metric] for r in rows])) for metric in ("hit_at_1", "mrr", "ndcg_at_5", "mean_gold_rank")}
    idx = np.load(Q0 / "bootstrap_indices.npy")
    ranks128 = np.asarray([[x["gold_rank"] for x in json.loads((run_dir(seed) / "dev_targets.json").read_text())] for seed in SEEDS], dtype=np.int64)
    ranks64 = np.asarray([[x["gold_rank"] for x in json.loads((Q2 / f"runs/H3_D_FULL_64/L1_LISTWISE_CE/seed_{seed}/dev_targets.json").read_text())] for seed in SEEDS], dtype=np.int64)
    comparison = pair_boot(ranks128, ranks64, idx)
    hit = comparison["hit_at_1"]
    status = "Q2C_CAPACITY_GAIN_PASS" if hit["delta"] > 0 and hit["ci95"][0] > 0 and comparison["mrr"]["ci95"][0] >= 0 and comparison["ndcg_at_5"]["ci95"][0] >= 0 else "Q2C_CAPACITY_GAIN_CONDITIONAL" if hit["delta"] > 0 else "Q2C_CAPACITY_NO_GAIN"
    q2rows = json.loads((Q2 / "metrics_by_run.json").read_text())["runs"]
    q264 = [x for x in q2rows if x["head"] == "H3_D_FULL_64" and x["loss"] == "L1_LISTWISE_CE"]
    gap128 = float(np.mean([r["train"]["overall"]["hit_at_1"] - r["dev"]["overall"]["hit_at_1"] for r in rows]))
    gap64 = float(np.mean([r["train"]["overall"]["hit_at_1"] - r["dev"]["overall"]["hit_at_1"] for r in q264]))
    gap_note = "GAP_INCREASED_OVER_2PP" if gap128 - gap64 > .02 else "GAP_NOT_INCREASED_OVER_2PP"
    # Seed 1 is a fixed descriptive representation only; all inference remains seed-first.
    a = {x["example_id"]: x for x in json.loads((run_dir(1) / "dev_targets.json").read_text())}
    b = {x["example_id"]: x for x in json.loads((Q2 / "runs/H3_D_FULL_64/L1_LISTWISE_CE/seed_1/dev_targets.json").read_text())}
    matrix = {}
    for lang in ("overall", "zh", "en"):
        ids = [k for k in a if lang == "overall" or a[k]["language"] == lang]
        matrix[lang] = {"both_correct": sum(a[k]["gold_rank"] == 1 and b[k]["gold_rank"] == 1 for k in ids), "64_only": sum(a[k]["gold_rank"] != 1 and b[k]["gold_rank"] == 1 for k in ids), "128_only": sum(a[k]["gold_rank"] == 1 and b[k]["gold_rank"] != 1 for k in ids), "both_wrong": sum(a[k]["gold_rank"] != 1 and b[k]["gold_rank"] != 1 for k in ids)}
    ninety = "INTERPRETABLE_90_TARGET_REACHED" if mean["hit_at_1"] >= .9 else "INTERPRETABLE_90_TARGET_NOT_REACHED"
    dump(OUT / "metrics.json", {"runs": rows, "dev_mean": mean, "status": status, "ninety_target": ninety, "train_dev_hit_gap": {"dfull128": gap128, "dfull64": gap64, "delta": gap128 - gap64, "assessment": gap_note}, "seed_std": {m: float(np.std([r["dev"]["overall"][m] for r in rows], ddof=0)) for m in ("hit_at_1", "mrr", "ndcg_at_5")}, "error_complementarity_seed1": matrix})
    dump(OUT / "bootstrap.json", {"comparison": "D-Full-128 minus D-Full-64", "seed": BOOT_SEED, "reps": REPS, "indices_sha256": sha(Q0 / "bootstrap_indices.npy"), "metrics": comparison})
    jsonl(OUT / "predictions_dev.jsonl", [r for seed in SEEDS for r in [json.loads(line) for line in (run_dir(seed) / "dev_predictions.jsonl").read_text().splitlines() if line]])
    (OUT / "Q2C_REPORT.md").write_text("\n".join(["# LC-Sent-15-Q2C D-Full Capacity Control", "", f"Decision: `{status}`.", f"90% target: `{ninety}`.", f"Train-Dev Hit@1 gap: D-Full-128={gap128:.6f}, D-Full-64={gap64:.6f}; `{gap_note}`.", "", "Only the frozen D-Full-128/L1 cell was trained. No Qwen, Blind, Reserve, multi-positive, mixed catalog, or BM25 training feature was used."]) + "\n")
    files = {str(p.relative_to(OUT)): sha(p) for p in OUT.rglob("*") if p.is_file() and p.name not in {"checksums.sha256", "Q2C_INTEGRITY.json", "COMPLETED"}}
    (OUT / "checksums.sha256").write_text("".join(f"{value}  {name}\n" for name, value in sorted(files.items())), encoding="utf-8")
    dump(OUT / "Q2C_INTEGRITY.json", {"status": "PASS", "files": files, "input_manifest_sha256": sha(OUT / "input_manifest.json"), "frozen_config_sha256": sha(OUT / "q2c_frozen_config.json"), "no_qwen": True, "no_blind": True, "no_reserve": True, "no_multi_positive": True, "no_mixed_catalog": True, "decision": status})
    (OUT / "COMPLETED").write_text("MEMORYFLOW_LC_SENT15_Q2C_CAPACITY_COMPLETE\n")


def main() -> None:
    parser = argparse.ArgumentParser(); parser.add_argument("mode", choices=("prepare", "run", "finalize")); args = parser.parse_args()
    prepare()
    if args.mode == "prepare": return
    if args.mode == "run":
        device, snapshot = choose_device(); dump(OUT / "gpu_snapshot.json", {"selected_device": str(device), "cuda_visible_devices": "unchanged", "logical_device": device.index, "snapshot": snapshot})
        for seed in SEEDS: run_one(seed, device)
    else: finalise()


if __name__ == "__main__":
    main()
