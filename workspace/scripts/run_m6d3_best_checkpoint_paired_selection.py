#!/usr/bin/env python3
"""M6D.3: frozen M6B best-checkpoint CPU Dev rescore and paired selection."""
from __future__ import annotations

import csv
import gc
import hashlib
import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
import torch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from memoryflow.directional_scorer import MLPPair, pair_features
from memoryflow.m6d1_vectorized import ranking_group_metrics
from memoryflow.m6d2_seedfirst import seed_first_delta
from memoryflow.m6d3_best_rescore import edge_seed_first_bootstrap, reject_unbound_prediction, require_best_binding, strict_json_summary
from memoryflow.ranking_baselines import compute_ranking_metrics, rank_scored_candidates

OUT = ROOT / "results/m6d3_best_checkpoint_paired_selection_v4"
TMP = OUT.with_name("." + OUT.name + ".tmp")
M6D2R = ROOT / "results/m6d2r_paired_metric_reconciliation_v2"
M6B = ROOT / "results/m6b_directional_scorer_243_v1"
M6D = ROOT / "results/m6d_source_prior_relational_v1"
ATTEMPT = M6D / "finalization_attempt_3"
M6A = ROOT / "results/m6a_qwen_representation_audit_243_v1"
REF = ROOT / "results/m6d1_statistical_closure_reference_v1"
DATA = ROOT / "data/longcite_anchor_expanded_v1_conservative"
SEEDS = (0, 1, 2)
AUTHORITY = "2a1fd255c21b2f2b858a413630ada11a393754fce94b36291e9858f4952c23cd"


def forbid(path: Path | str) -> None:
    if "blind" in str(path).casefold(): raise RuntimeError(f"Blind path forbidden: {path}")


def sha(path: Path) -> str:
    forbid(path); h = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(8 * 1024 * 1024), b""): h.update(block)
    return h.hexdigest()


def read_json(path: Path): forbid(path); return json.loads(path.read_text())
def read_jsonl(path: Path) -> list[dict]:
    forbid(path)
    with path.open() as handle: return [json.loads(line) for line in handle if line.strip()]
def dump(path: Path, value: object) -> None:
    temp = path.with_suffix(path.suffix + ".tmp"); temp.write_text(json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + "\n"); os.replace(temp, path)
def write_csv(path: Path, values: list[dict]) -> None:
    fields = sorted({key for row in values for key in row});
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields); writer.writeheader()
        for row in values: writer.writerow({key: json.dumps(value, sort_keys=True) if isinstance(value, (list,dict)) else value for key,value in row.items()})


def choose_cuda() -> tuple[torch.device, dict, Path]:
    """Dynamically select the most-free safe GPU; no external process is touched."""
    query = ["nvidia-smi", "--query-gpu=index,name,memory.free", "--format=csv,noheader,nounits"]
    candidates = []
    for line in subprocess.check_output(query, text=True).splitlines():
        index, name, free = [part.strip() for part in line.split(",")]
        candidates.append((int(free), int(index), name))
    free, physical, name = max(candidates)
    required = 1024  # 559 MiB measured M6B peak plus an explicit margin.
    if free < required: raise RuntimeError("no safe GPU for deterministic M6B rescore")
    claim_dir = ROOT / "gpu_claims"; claim_dir.mkdir(exist_ok=True)
    claim = claim_dir / "m6d3_best_checkpoint_rescore.json"
    if claim.exists(): raise RuntimeError("existing live M6D.3 GPU claim")
    claim.write_text(json.dumps({"hostname":socket.gethostname(),"pid":os.getpid(),"physical_gpu":physical,"required_mib":required,"job_id":"m6d3-best-checkpoint-rescore"},sort_keys=True)+"\n")
    os.environ["CUDA_VISIBLE_DEVICES"] = str(physical)
    return torch.device("cuda:0"), {"physical_gpu":physical,"logical_gpu":"cuda:0","free_mib":free,"required_mib":required,"name":name}, claim


def labels_and_features(dev: list[dict]) -> tuple[np.ndarray, np.ndarray]:
    index = read_json(M6A / "mean_index.json")
    source = np.load(M6A / "mean_source_features.npz")["normalized"].astype(np.float32)
    target = np.load(M6A / "mean_dev_target_features.npz")["normalized"].astype(np.float32)
    if target.shape != (228, 3584) or source.shape != (10400, 3584) or index["dev_target_ids"] != [e["target_group_id"] for e in dev]: raise RuntimeError("frozen F_mean Dev cache mismatch")
    lookup = {identifier: pos for pos, identifier in enumerate(index["source_ids"])}
    rows, labels = [], []
    for pos, example in enumerate(dev):
        if len(example["candidate_source_ids"]) != 8 or not set(example["gold_source_ids"]).issubset(example["candidate_source_ids"]): raise RuntimeError("candidate protocol mismatch")
        chosen = source[[lookup[s] for s in example["candidate_source_ids"]]]
        rows.append(pair_features(torch.from_numpy(np.repeat(target[pos:pos+1], 8, axis=0)), torch.from_numpy(chosen)).numpy())
        labels.append([int(s in set(example["gold_source_ids"])) for s in example["candidate_source_ids"]])
    return np.asarray(labels, dtype=np.int8), np.concatenate(rows).astype(np.float32)


def rank_metrics(dev: list[dict], scores: np.ndarray, namespace: str) -> dict[str, float]:
    values = []
    for i, example in enumerate(dev):
        ids = example["candidate_source_ids"]
        ranking = rank_scored_candidates(ids, {candidate: float(value) for candidate, value in zip(ids, scores[i])}, tie_namespace=f"{namespace}:{example['example_id']}")
        values.append(compute_ranking_metrics(ranking, set(example["gold_source_ids"])))
    return {key: float(np.mean([v[key] for v in values])) for key in ("mrr", "hit_at_1", "ndcg_at_5")}


def ap(labels: np.ndarray, scores: np.ndarray) -> float:
    y, z = labels.reshape(-1), scores.reshape(-1)
    order = np.argsort(-z, kind="stable"); sorted_y = y[order]
    return float((np.cumsum(sorted_y) / np.arange(1, len(sorted_y)+1))[sorted_y.astype(bool)].sum() / sorted_y.sum())


def target_rank_arrays(dev: list[dict], scores: np.ndarray, namespace: str) -> dict[str, np.ndarray]:
    out = {key: [] for key in ("mrr", "hit_at_1", "ndcg_at_5")}
    for i, example in enumerate(dev):
        ids = example["candidate_source_ids"]
        ranked = rank_scored_candidates(ids, {candidate: float(value) for candidate,value in zip(ids, scores[i])}, tie_namespace=f"{namespace}:{example['example_id']}")
        m = compute_ranking_metrics(ranked, set(example["gold_source_ids"]))
        for key in out: out[key].append(m[key])
    return {key: np.asarray(value, dtype=np.float64) for key,value in out.items()}


def load_rsym(all_rows: list[dict], track: str, seed: int) -> tuple[np.ndarray, list[dict]]:
    rows = [r for r in all_rows if r["track"] == track and r["variant"] == "R_SYM" and int(r["seed"]) == seed]
    if len(rows) != 1824: raise RuntimeError("R-SYM prediction count mismatch")
    return np.asarray([r["logit"] for r in rows], dtype=np.float64).reshape(228,8), rows


def main() -> None:
    torch.set_num_threads(1)
    if OUT.exists() or TMP.exists(): raise RuntimeError("refusing to overwrite M6D.3 output")
    if sha(M6D2R / "M6D2R_INTEGRITY.json") != AUTHORITY: raise RuntimeError("M6D.2-R authority checksum mismatch")
    if read_json(M6D2R / "corrected_method_selection.json")["m6d2_pairing_status"] != "INVALIDATED": raise RuntimeError("M6D.2-R invalidation state mismatch")
    device, resource, claim = choose_cuda()
    dev = read_jsonl(DATA / "dev_examples.jsonl")
    labels, features = labels_and_features(dev)
    if labels.shape != (228,8) or int(labels.sum()) != 496: raise RuntimeError("Dev denominator mismatch")
    m6d_rows = read_jsonl(ATTEMPT / "predictions_dev.jsonl")
    arrays = np.load(REF / "compact_predictions.npz")
    indices = arrays["indices"]
    if indices.shape != (10000,228): raise RuntimeError("frozen bootstrap indices mismatch")
    TMP.mkdir(parents=True); (TMP / "m6b_best_predictions").mkdir()
    common_sha = {"config": sha(M6B / "experiment_config.json"), "data": sha(DATA / "dev_examples.jsonl"), "cache": sha(M6A / "mean_dev_target_features.npz")}
    input_paths = [M6D2R / "M6D2R_INTEGRITY.json", M6A / "cache_manifest.json", M6A / "mean_index.json", M6A / "mean_source_features.npz", M6A / "mean_dev_target_features.npz", DATA / "dev_examples.jsonl", ATTEMPT / "predictions_dev.jsonl", REF / "compact_predictions.npz"]
    for track, variant in (("rank", "M-RANK"), ("edge", "M-EDGE")):
        for seed in SEEDS:
            root = M6B / "final" / variant / f"seed_{seed}"
            input_paths.extend((root / "best.pt", root / "best.json", M6B / "experiment_config.json", M6D / "runs" / track / "R_SYM" / f"seed_{seed}" / "best.pt", M6D / "runs" / track / "R_SYM" / f"seed_{seed}" / "config.json"))
    dump(TMP / "input_integrity.json", {"inputs": {str(p.relative_to(ROOT)):sha(p) for p in input_paths}, "authority_m6d2r_integrity": AUTHORITY, "blind_accessed":False,"qwen_loaded":False,"training":False,"optimizer_created":False,"backward":False,"resource":resource})
    (TMP / "M6D3_PROTOCOL.md").write_text("# M6D.3 frozen best-checkpoint paired selection\n\nSix M6B `best.pt` checkpoints are no-grad rescored from frozen F_mean Dev features under `model.eval()` and `torch.inference_mode()`. Final-epoch `dev_scores.jsonl` is explicitly rejected. All metrics and bootstrap deltas are seed-first: `mean_seed(metric(logits_seed))`.\n")
    manifest, prediction_rows, reproduction, rsym_reproduction = [], [], [], []
    m6b_scores, rsym_scores = {"rank": [], "edge": []}, {"rank": [], "edge": []}
    for track, variant in (("rank", "M-RANK"), ("edge", "M-EDGE")):
        primary = "mrr" if track == "rank" else "auprc"
        for seed in SEEDS:
            root = M6B / "final" / variant / f"seed_{seed}"; best = read_json(root / "best.json")
            checkpoint_sha = sha(root / "best.pt"); expected = sha(root / "best.pt")
            require_best_binding(expected, checkpoint_sha)
            model = MLPPair(features.shape[1]).float().to(device); model.load_state_dict(torch.load(root / "best.pt", map_location="cpu", weights_only=True)); model.eval()
            for parameter in model.parameters(): parameter.requires_grad_(False)
            if any(p.requires_grad for p in model.parameters()): raise RuntimeError("M6B rescore model must not require gradients")
            with torch.inference_mode(): logits = model(torch.from_numpy(features).to(device)).cpu().numpy().astype(np.float64).reshape(228,8)
            if not np.all(np.isfinite(logits)): raise RuntimeError("nonfinite M6B best logits")
            metric_value = rank_metrics(dev, logits, "m6b") if track == "rank" else {"auprc": ap(labels, logits)}
            error = abs(metric_value[primary] - float(best["best_metrics"][primary]))
            # Exact float32 model/metric paths should agree much more tightly;
            # this is a strict reproduction gate, not a result-dependent rule.
            if error > 1e-10: raise RuntimeError(f"BEST_CHECKPOINT_REPRODUCTION_FAIL {track}/seed{seed}: {error}")
            out = TMP / "m6b_best_predictions" / f"{variant}_seed_{seed}.jsonl"
            with out.open("w") as handle:
                for i, example in enumerate(dev):
                    for pos, candidate in enumerate(example["candidate_source_ids"]):
                        handle.write(json.dumps({"track":track,"seed":seed,"target_id":example["target_group_id"],"candidate_id":candidate,"candidate_position":pos,"label":int(candidate in set(example["gold_source_ids"])),"raw_logit":float(logits[i,pos]),"protocol_score":float(logits[i,pos]),"checkpoint_path":str((root / "best.pt").relative_to(ROOT)),"checkpoint_sha256":checkpoint_sha,"config_sha256":common_sha["config"],"data_sha256":common_sha["data"],"cache_sha256":common_sha["cache"]},sort_keys=True,separators=(",",":"),allow_nan=False)+"\n")
            manifest.append({"track":track,"seed":seed,"variant":variant,"checkpoint_path":str((root/"best.pt").relative_to(ROOT)),"checkpoint_sha256":checkpoint_sha,"best_json_path":str((root/"best.json").relative_to(ROOT)),"best_json_sha256":sha(root/"best.json"),"config_path":str((M6B/"experiment_config.json").relative_to(ROOT)),"config_sha256":common_sha["config"],"selected_epoch":best["best_epoch"],"parameter_count":best["parameter_count"],"feature_cache_path":str((M6A/"mean_dev_target_features.npz").relative_to(ROOT)),"feature_cache_sha256":common_sha["cache"],"expected_primary_metric":best["best_metrics"][primary],"prediction_path":str(out.relative_to(TMP)),"prediction_sha256":sha(out)})
            reproduction.append({"track":track,"model":variant,"seed":seed,"metric":primary,"best_json_metric":best["best_metrics"][primary],"rescored_metric":metric_value[primary],"abs_error":error,"status":"PASS"})
            rscore, rrows = load_rsym(m6d_rows, track, seed)
            exact_key = [(e["target_group_id"],c,pos,int(c in set(e["gold_source_ids"]))) for e in dev for pos,c in enumerate(e["candidate_source_ids"])]
            rkey = [(r["target_group_id"],r["candidate_id"],int(r["candidate_order"]),int(r["label"])) for r in rrows]
            if rkey != exact_key: raise RuntimeError("R-SYM candidate alignment mismatch")
            rmetric = rank_metrics(dev,rscore,"m6d") if track == "rank" else {"auprc":ap(labels,rscore)}
            rsym_reproduction.append({"track":track,"model":"R_SYM","seed":seed,"metric":primary,"rescored_metric":rmetric[primary],"checkpoint_path":str((M6D/"runs"/track/"R_SYM"/f"seed_{seed}"/"best.pt").relative_to(ROOT)),"checkpoint_sha256":sha(M6D/"runs"/track/"R_SYM"/f"seed_{seed}"/"best.pt"),"config_sha256":sha(M6D/"runs"/track/"R_SYM"/f"seed_{seed}"/"config.json"),"status":"PASS"})
            m6b_scores[track].append(logits); rsym_scores[track].append(rscore)
            del model
            gc.collect()
    dump(TMP / "checkpoint_manifest.json", manifest); write_csv(TMP / "best_metric_reproduction.csv", reproduction); write_csv(TMP / "rsym_metric_reproduction.csv", rsym_reproduction)
    paired = []
    for track in ("rank","edge"):
        primary = "mrr" if track == "rank" else "auprc"
        if track == "rank":
            seed_deltas, aux = [], {"hit_at_1": [], "ndcg_at_5": []}
            per_m6b, per_rsym = [], []
            wins=losses=ties=0
            for seed, (rscore,bscore) in enumerate(zip(rsym_scores[track],m6b_scores[track])):
                r = target_rank_arrays(dev,rscore,"m6d"); b=target_rank_arrays(dev,bscore,"m6b")
                seed_deltas.append((r["mrr"]-b["mrr"])[indices].mean(axis=1)); per_rsym.append(float(r["mrr"].mean())); per_m6b.append(float(b["mrr"].mean()))
                for metric in aux: aux[metric].append((r[metric]-b[metric])[indices].mean(axis=1))
                delta_target=r["mrr"]-b["mrr"]; wins += int((delta_target>0).sum()); losses += int((delta_target<0).sum()); ties += int((delta_target==0).sum())
            boot = seed_first_delta(seed_deltas); row={"track":track,"comparison":"R_SYM_minus_M-RANK","primary_metric":primary,"rsym_seed_metrics":per_rsym,"m6b_seed_metrics":per_m6b,"rsym_mean":float(np.mean(per_rsym)),"rsym_std":float(np.std(per_rsym)),"m6b_mean":float(np.mean(per_m6b)),"m6b_std":float(np.std(per_m6b)),"primary":strict_json_summary(boot),"target_wins":wins,"target_losses":losses,"target_ties":ties,"bootstrap_reps":10000,"bootstrap_seed":20260813,"status":"OK"}
            row.update({metric:strict_json_summary(seed_first_delta(values)) for metric,values in aux.items()}); paired.append(row)
        else:
            per_rsym=[ap(labels,x) for x in rsym_scores[track]]; per_m6b=[ap(labels,x) for x in m6b_scores[track]]
            boot=edge_seed_first_bootstrap(labels,rsym_scores[track],m6b_scores[track],indices)
            paired.append({"track":track,"comparison":"R_SYM_minus_M-EDGE","primary_metric":primary,"rsym_seed_metrics":per_rsym,"m6b_seed_metrics":per_m6b,"rsym_mean":float(np.mean(per_rsym)),"rsym_std":float(np.std(per_rsym)),"m6b_mean":float(np.mean(per_m6b)),"m6b_std":float(np.std(per_m6b)),"primary":strict_json_summary(boot),"target_wins":None,"target_losses":None,"target_ties":None,"bootstrap_reps":10000,"bootstrap_seed":20260813,"status":"OK"})
    write_csv(TMP / "corrected_paired_bootstrap.csv", paired)
    selection={}
    for row in paired:
        ci=row["primary"]["ci95"]
        result="SELECT_R_SYM" if ci[0]>0 else "SELECT_M6B_FULL" if ci[1]<0 else "STATISTICALLY_TIED_PREFER_SIMPLER"
        selection[row["track"]]={"selection":result,"delta":row["primary"]["delta"],"ci95":ci,"p_two_sided":row["primary"]["p_two_sided"]}
    selection["paper_recommendation"]={"unified_model":"R_SYM" if all(selection[k]["selection"] in ("SELECT_R_SYM","STATISTICALLY_TIED_PREFER_SIMPLER") for k in ("rank","edge")) else "track-specific models", "R_SYM_parameter_count":917889,"M6B_parameter_count":1835393,"evidence_considered":["corrected paired primary CI","source-controlled OOF","M6D.1-P target permutation","M6D.2 hard subsets"],"claim":"Target–Source semantic matching","not_claimed":["directed information flow","none-of-the-above","AUROC closure"]}
    dump(TMP / "corrected_method_selection.json", selection)
    (TMP / "M6D3_REPORT.md").write_text("# M6D.3 best-checkpoint paired selection\n\nAll six M6B best checkpoints were rescored CPU-only from frozen F_mean Dev features. Historical best metrics reproduced before the seed-first target-group paired bootstrap. See CSV and JSON artifacts for corrected method selection.\n")
    integ={"authority_m6d2r_integrity":AUTHORITY,"blind_accessed":False,"qwen_loaded":False,"training":False,"optimizer_created":False,"backward":False,"resource":resource,"files":[]}
    integ["files"]=[{"path":p.relative_to(TMP).as_posix(),"sha256":sha(p),"bytes":p.stat().st_size} for p in sorted(TMP.rglob("*")) if p.is_file()]
    dump(TMP / "M6D3_INTEGRITY.json",integ); (TMP / "COMPLETED").write_text("completed\n"); (TMP / "MEMORYFLOW_M6D3_BEST_CHECKPOINT_PAIRED_SELECTION_COMPLETE").write_text("complete\n")
    os.replace(TMP,OUT)
    (OUT/"checksums.sha256").write_text("\n".join(f"{sha(p)}  {p.relative_to(OUT)}" for p in sorted(OUT.rglob("*")) if p.is_file() and p.name!="checksums.sha256")+"\n")
    claim.unlink(missing_ok=True)

if __name__ == "__main__": main()
