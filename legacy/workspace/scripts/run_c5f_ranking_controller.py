#!/usr/bin/env python3
"""C5F external epoch-boundary controller.

This controller rebuilds ranking state from C5E scores and never reads the
legacy C5D current_state.json.  It writes only the isolated C5F directory.
"""
from __future__ import annotations

import argparse
import gc
import hashlib
import json
import math
import os
import random
import sys
import time
from pathlib import Path

import numpy as np
import torch
from safetensors.torch import load_file, save_file
from torch import nn
from transformers import AutoModelForCausalLM, AutoTokenizer

ROOT = Path(__file__).resolve().parents[1]
PROJECT = ROOT.parent
MODEL = Path("/data2/pkuiti/songzhengxing_intern/model/Qwen2.5-7B-Instruct")
DATA = ROOT / "data/longcite_anchor_expanded_v1_conservative"
C5D = ROOT / "results/c5d_full_calibration_10025_v1"
C5E = ROOT / "results/c5e_dev_rescore_10025"
OUT = ROOT / "results/c5f_ranking_continuation_243_v1"
MODEL_MANIFEST = OUT / "model_manifest/model_sha256_manifest.json"
CONFIGS = {"a": (0.0003, 1.0), "b": (0.0003, 10.0), "c": (0.003, 1.0), "d": (0.003, 10.0)}
EXPECTED = {
    "a": (3, 0.5329115666458376, 0.5124895572263993, 0.301961),
    "b": (2, 0.5586520944354825, 0.5449665831244779, 0.315856),
    "c": (3, 0.5707005284732624, 0.5604375522138682, 0.322470),
    "d": (3, 0.5698783691676733, 0.5580983709273183, 0.320081),
}
ACCUMULATION = 8
CLIP = 1.0


def forbid_blind_path(path: str | Path) -> None:
    if "blind" in str(path).lower():
        raise RuntimeError("Blind path access is forbidden")


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(8 * 1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def model_manifest_sha256() -> str:
    if not MODEL_MANIFEST.is_file():
        raise RuntimeError("model checksum manifest is missing")
    return sha256(MODEL_MANIFEST)


def atomic_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name("." + path.name + ".tmp")
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
    os.replace(tmp, path)


def save_torch_atomic(path: Path, value: object) -> None:
    tmp = path.with_name("." + path.name + ".tmp")
    torch.save(value, tmp)
    os.replace(tmp, path)


def save_anchor_atomic(path: Path, anchor: torch.Tensor) -> None:
    tmp = path.with_name("." + path.name + ".tmp")
    save_file({"trainable_anchor": anchor.detach().cpu().contiguous()}, str(tmp))
    os.replace(tmp, path)


def load_jsonl(path: Path) -> list[dict]:
    forbid_blind_path(path)
    rows = []
    with path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            if line.strip():
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError as exc:
                    raise RuntimeError(f"invalid JSONL {path}:{line_number}: {exc}") from exc
    return rows


def ranking_tuple(metrics: dict, epoch: int) -> tuple[float, float, float, int]:
    return (float(metrics["ndcg_at_5"]), float(metrics["mrr"]), -float(metrics["all_positive_loss"]), -int(epoch))


def is_improvement(candidate: tuple, current: tuple) -> bool:
    return candidate > current


def rebuild_initial_state(config: str) -> dict:
    if config not in CONFIGS:
        raise ValueError(config)
    if config == "b":
        return {"config": "b", "status": "COMPLETE", "job_created": False, "reason": "ranking_bad_count_already_2"}
    entries = []
    last_scored_epoch = 3 if config == "c" else 4
    for epoch in range(1, last_scored_epoch + 1):
        p = C5E / f"config_{config}/epoch_{epoch}/metrics.json"
        if not p.exists():
            raise FileNotFoundError(p)
        metrics = json.loads(p.read_text())
        entries.append((epoch, metrics))
    best_epoch, best_metrics = max(entries, key=lambda x: ranking_tuple(x[1], x[0]))
    expected_epoch, exp_ndcg, exp_mrr, exp_auprc = EXPECTED[config]
    if best_epoch != expected_epoch or abs(best_metrics["ndcg_at_5"] - exp_ndcg) > 1e-9 or abs(best_metrics["mrr"] - exp_mrr) > 1e-9 or abs(best_metrics["auprc"] - exp_auprc) > 1e-6:
        raise RuntimeError(f"C5E ranking reconstruction mismatch for {config}")
    latest = {"a": 4, "c": 3, "d": 4}[config]
    bad = {"a": 1, "c": 0, "d": 1}[config]
    return {"config": config, "status": "RUNNING", "job_created": True, "latest_epoch": latest, "best_epoch": best_epoch, "best_metrics": best_metrics, "bad_count": bad, "source": "C5E per-checkpoint metrics; legacy C5D current_state ignored", "blind_accessed": False}


def checkpoint_complete(config: str, epoch: int) -> bool:
    out = C5D / f"config_{config}"
    paths = [out / f"epoch_{epoch:02d}.safetensors", out / f"epoch_{epoch:02d}_optimizer.pt", out / f"epoch_{epoch:02d}_rng.pt", out / f"epoch_{epoch:02d}_metrics.json", out / f"epoch_{epoch:02d}_sha256.json"]
    return all(p.is_file() for p in paths)


def _c5e_epochs(config: str) -> int:
    return 3 if config == "c" else 4


def _c5f_epoch_record(config: str, epoch: int) -> dict | None:
    base = OUT / f"config_{config}"
    paths = [base / f"epoch_{epoch:02d}.safetensors", base / f"epoch_{epoch:02d}_optimizer.pt", base / f"epoch_{epoch:02d}_rng.pt", base / f"epoch_{epoch:02d}_metrics.json", base / f"epoch_{epoch:02d}_sha256.json"]
    if not all(p.is_file() for p in paths):
        return None
    sha_record = json.loads(paths[-1].read_text())
    observed = {p.name: sha256(p) for p in paths[:-1]}
    if observed != sha_record:
        return None
    metrics = json.loads(paths[3].read_text())
    if "dev_metrics" not in metrics or not metrics.get("finite", False) or metrics.get("blind_accessed", True):
        return None
    return {"epoch": epoch, "metrics": metrics["dev_metrics"], "source": "c5f", "sha256": sha_record}


def reconcile_config(config: str) -> dict:
    """Replay C5E plus complete C5F epochs; never consults C5D current_state."""
    if config == "b":
        return {"config": "b", "status": "COMPLETE", "job_created": False, "reason": "ranking_bad_count_already_2", "blind_accessed": False}
    records = []
    old_count = _c5e_epochs(config)
    for epoch in range(1, old_count + 1):
        metrics_path = C5E / f"config_{config}/epoch_{epoch}/metrics.json"
        integrity_path = C5E / f"config_{config}/epoch_{epoch}/integrity.json"
        score_path = C5E / f"config_{config}/epoch_{epoch}/dev_scores.jsonl"
        if not all(p.is_file() for p in (metrics_path, integrity_path, score_path)):
            raise RuntimeError(f"incomplete C5E epoch {config}{epoch}")
        integrity = json.loads(integrity_path.read_text())
        if integrity.get("status") not in ("PASS", "VALID"):
            raise RuntimeError(f"invalid C5E integrity {config}{epoch}")
        metrics = json.loads(metrics_path.read_text())
        records.append({"epoch": epoch, "metrics": metrics, "source": "c5e"})
    extra = []
    for epoch in range(old_count + 1, 7):
        rec = _c5f_epoch_record(config, epoch)
        if rec is None:
            break
        extra.append(rec)
    records.extend(extra)
    if [r["epoch"] for r in records] != list(range(1, len(records) + 1)):
        raise RuntimeError(f"non-contiguous committed epochs for {config}")
    best_epoch = records[0]["epoch"]; best_metrics = records[0]["metrics"]; best_tuple = ranking_tuple(best_metrics, best_epoch); bad = 0
    trace = []
    for rec in records[1:]:
        candidate = ranking_tuple(rec["metrics"], rec["epoch"]); improved = candidate > best_tuple
        if improved:
            best_epoch, best_metrics, best_tuple, bad = rec["epoch"], rec["metrics"], candidate, 0
        else:
            bad += 1
        trace.append({"epoch": rec["epoch"], "source": rec["source"], "tuple": list(candidate), "improvement": improved, "best_epoch": best_epoch, "bad_count": bad})
    latest = records[-1]["epoch"]
    status = "COMPLETE" if bad >= 2 or latest >= 6 else "RUNNING"
    return {"config": config, "status": status, "job_created": status != "COMPLETE", "latest_epoch": latest, "next_epoch": latest + 1, "best_epoch": best_epoch, "best_metrics": best_metrics, "best_tuple": list(best_tuple), "bad_count": bad, "reconciliation_trace": trace, "source": "C5E plus complete C5F epochs; legacy C5D current_state ignored", "model_manifest_sha256": model_manifest_sha256(), "blind_accessed": False}


def update_patience(state: dict, metrics: dict, epoch: int) -> dict:
    candidate = ranking_tuple(metrics, epoch)
    current = tuple(state["best_tuple"])
    if is_improvement(candidate, current):
        state.update({"best_epoch": epoch, "best_metrics": metrics, "best_tuple": list(candidate), "bad_count": 0, "improvement": True})
    else:
        state.update({"bad_count": int(state["bad_count"]) + 1, "improvement": False})
    state["stop_reason"] = "ranking_patience_2" if state["bad_count"] >= 2 else ("epoch_6_limit" if epoch >= 6 else "continue")
    return state


def visible_gpu_free_bytes() -> int:
    return int(torch.cuda.mem_get_info()[0])


def rng_state() -> dict:
    return {"python": random.getstate(), "numpy": np.random.get_state(), "torch": torch.get_rng_state(), "cuda": torch.cuda.get_rng_state_all()}


def restore_rng(state: dict) -> None:
    random.setstate(state["python"]); np.random.set_state(state["numpy"]); torch.set_rng_state(state["torch"])
    if torch.cuda.is_available(): torch.cuda.set_rng_state_all(state["cuda"])


def run_config(config: str, physical_gpu: str) -> None:
    os.environ["CUDA_VISIBLE_DEVICES"] = physical_gpu
    forbid_blind_path(OUT)
    state_path = OUT / f"config_{config}/c5f_state.json"
    config_out = state_path.parent
    config_out.mkdir(parents=True, exist_ok=True)
    if config == "b":
        atomic_json(state_path, rebuild_initial_state(config)); return
    state = reconcile_config(config)
    atomic_json(state_path, state)
    if state.get("status") == "COMPLETE": return
    if state.get("status") == "COMPLETE": return
    # Avoid loading a 15.2 GB FP32 model into an already crowded GPU.
    while visible_gpu_free_bytes() < 38 * 1024**3:
        free_bytes = visible_gpu_free_bytes()
        atomic_json(config_out / "queue_status.json", {"status": "WAITING_FOR_GPU_MEMORY", "physical_gpu": physical_gpu, "free_bytes": free_bytes, "pid": os.getpid(), "blind_accessed": False})
        print(f"WAITING_FOR_GPU_MEMORY physical_gpu={physical_gpu} free_bytes={free_bytes}", flush=True)
        time.sleep(30)
    sys.path[:0] = [str(ROOT / "src"), str(ROOT / "scripts")]
    from memoryflow.trainable_anchor import all_positive_distribution_loss, anchor_drift_penalty
    from train_anchor_vector_smoke import evaluate, forward_scores, pack
    random.seed(0); np.random.seed(0); torch.manual_seed(0); torch.backends.cuda.matmul.allow_tf32 = False; torch.backends.cudnn.allow_tf32 = False
    tokenizer = AutoTokenizer.from_pretrained(MODEL, local_files_only=True)
    sources = {r["source_id"]: r for r in load_jsonl(DATA / "source_catalog.jsonl")}
    train = [r for r in load_jsonl(DATA / "train_examples.jsonl") if r.get("metadata", {}).get("candidate_size") == 8]
    dev = [r for r in load_jsonl(DATA / "dev_examples.jsonl") if r.get("metadata", {}).get("candidate_size") == 8]
    train_layouts = [pack(tokenizer, r, sources, tokenizer.eos_token_id) for r in train]; dev_layouts = [pack(tokenizer, r, sources, tokenizer.eos_token_id) for r in dev]
    model = AutoModelForCausalLM.from_pretrained(MODEL, local_files_only=True, dtype=torch.float32, attn_implementation="eager").to("cuda").eval(); model.requires_grad_(False)
    initial = model.get_input_embeddings().weight[tokenizer.eos_token_id].detach().clone().float(); anchor = nn.Parameter(initial.clone()); lr, lam = CONFIGS[config]; optimizer = torch.optim.AdamW([anchor], lr=lr, weight_decay=0.0)
    latest = int(state["latest_epoch"]); checkpoint_root = OUT if latest > _c5e_epochs(config) else C5D
    anchor.data.copy_(load_file(str(checkpoint_root / f"config_{config}/epoch_{latest:02d}.safetensors"))["trainable_anchor"].to("cuda")); optimizer.load_state_dict(torch.load(checkpoint_root / f"config_{config}/epoch_{latest:02d}_optimizer.pt", map_location="cuda", weights_only=False)); restore_rng(torch.load(checkpoint_root / f"config_{config}/epoch_{latest:02d}_rng.pt", map_location="cpu", weights_only=False))
    for epoch in range(latest + 1, 7):
        start = time.perf_counter(); optimizer.zero_grad(set_to_none=True); train_loss=[]; drift=[]; updates=[]; masks=[]
        for i,(layout,example) in enumerate(zip(train_layouts,train),1):
            scores, masked, finite, _ = forward_scores(model, layout, anchor, grad=True); gold=torch.tensor([x in set(example["gold_source_ids"]) for x in example["candidate_source_ids"]],dtype=torch.bool,device="cuda"); rank=all_positive_distribution_loss(scores,gold); raw=anchor_drift_penalty(anchor,initial); total=rank+lam*raw; (total/ACCUMULATION).backward(); train_loss.append(float(rank.detach())); drift.append(float(raw.detach())); masks.append(float(masked))
            if i%ACCUMULATION==0 or i==len(train): torch.nn.utils.clip_grad_norm_([anchor],CLIP); before=anchor.detach().clone(); optimizer.step(); optimizer.zero_grad(set_to_none=True); updates.append(float(torch.linalg.vector_norm(anchor.detach()-before)))
            if not finite or not bool(torch.isfinite(total)): raise FloatingPointError(f"nonfinite {config} epoch {epoch}")
        _, train_metrics, _, _, train_mask, train_finite = evaluate(model,anchor,train_layouts,train,check_mask=True); _, dev_metrics, _, _, dev_mask, dev_finite = evaluate(model,anchor,dev_layouts,dev,check_mask=True)
        metrics={"config":config,"epoch":epoch,"train_rows":len(train),"dev_rows":len(dev),"train_metrics":train_metrics,"dev_metrics":dev_metrics,"train_ranking_loss":float(np.mean(train_loss)),"raw_drift_mse":float(np.mean(drift)),"weighted_drift":float(lam*np.mean(drift)),"update_norm":float(np.mean(updates)),"mask_leakage_max":max(train_mask,dev_mask),"finite":bool(train_finite and dev_finite),"model_gradients_all_none":all(p.grad is None for p in model.parameters()),"anchor_norm":float(anchor.norm()),"physical_gpu":physical_gpu,"runtime_seconds":time.perf_counter()-start,"peak_memory":{"allocated":int(torch.cuda.max_memory_allocated()),"reserved":int(torch.cuda.max_memory_reserved())},"model_manifest_sha256":model_manifest_sha256(),"blind_accessed":False}
        if not metrics["finite"] or metrics["mask_leakage_max"] != 0: raise RuntimeError(f"mechanics gate failed {config} epoch {epoch}")
        # Commit the complete epoch before advancing state; all files are isolated per config.
        save_anchor_atomic(config_out/f"epoch_{epoch:02d}.safetensors",anchor); save_torch_atomic(config_out/f"epoch_{epoch:02d}_optimizer.pt",optimizer.state_dict()); save_torch_atomic(config_out/f"epoch_{epoch:02d}_rng.pt",rng_state()); atomic_json(config_out/f"epoch_{epoch:02d}_metrics.json",metrics)
        hashes={p.name:sha256(p) for p in [config_out/f"epoch_{epoch:02d}.safetensors",config_out/f"epoch_{epoch:02d}_optimizer.pt",config_out/f"epoch_{epoch:02d}_rng.pt",config_out/f"epoch_{epoch:02d}_metrics.json"]}; atomic_json(config_out/f"epoch_{epoch:02d}_sha256.json",hashes)
        state["latest_epoch"]=epoch; state=update_patience(state,dev_metrics,epoch); state["model_manifest_sha256"]=model_manifest_sha256(); state["blind_accessed"]=False; atomic_json(state_path,state)
        if state["stop_reason"] != "continue": break
    atomic_json(config_out/"final_summary.json",state); del model; gc.collect(); torch.cuda.empty_cache()


def main() -> int:
    ap=argparse.ArgumentParser(); ap.add_argument("--config",choices=sorted(CONFIGS),required=True); ap.add_argument("--physical-gpu",required=True); args=ap.parse_args()
    if args.config == "b": rebuild_initial_state("b"); return 0
    run_config(args.config,args.physical_gpu); return 0


if __name__ == "__main__": raise SystemExit(main())
