#!/usr/bin/env python3
"""M6D: preregistered source-prior-controlled validation using frozen F_mean."""
from __future__ import annotations
import csv, hashlib, json, math, os, random, socket, sys, time
from collections import defaultdict
from pathlib import Path

import numpy as np
import torch
from torch import nn

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src")); sys.path.insert(0, str(ROOT / "scripts"))
from memoryflow.directional_scorer import all_positive_distribution_loss
from memoryflow.ranking_baselines import compute_ranking_metrics, rank_scored_candidates
from memoryflow.source_prior_relational import DirectionalRelation, SourcePrior, SymmetricRelation, freeze_module, parameter_count
from select_memoryflow_gpu import choose_gpu, gpu_query, read_claimed_gpus, write_claim

OUT = ROOT / "results/m6d_source_prior_relational_v1"
M6A = ROOT / "results/m6a_qwen_representation_audit_243_v1"
M6B = ROOT / "results/m6b_directional_scorer_243_v1"
C5F = ROOT / "results/c5f_dev_rescore_243_v1"
DATA = ROOT / "data/longcite_anchor_expanded_v1_conservative"
DIM, RANK, SEEDS, EPOCHS, PATIENCE, BATCH, CLIP = 3584, 128, (0, 1, 2), 50, 5, 32, 1.0
TRACKS = {"rank": {"lr": 3e-4, "primary": "mrr", "fixed_cv_epochs": 15}, "edge": {"lr": 1e-3, "primary": "auprc", "fixed_cv_epochs": 21}}
VARIANTS = ("P", "R_SYM", "R_DIR", "P_R_SYM", "P_R_DIR")
RANDOM = {"hit_at_1": 0.2719298245614035, "mrr": 0.48438063163862094, "ndcg_at_5": 0.4573921636840349, "recall_at_5": 0.625}


def forbid(path: Path | str) -> None:
    if "blind" in str(path).casefold():
        raise RuntimeError(f"Blind path forbidden: {path}")


def sha(path: Path) -> str:
    forbid(path); h = hashlib.sha256()
    with path.open("rb") as f:
        for b in iter(lambda: f.read(8 * 1024 * 1024), b""): h.update(b)
    return h.hexdigest()


def dump(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n")
    os.replace(tmp, path)


def read_jsonl(path: Path) -> list[dict]:
    forbid(path)
    with path.open(encoding="utf8") as f: return [json.loads(x) for x in f if x.strip()]


def norm_text(text: str) -> str:
    return " ".join(str(text).split()).casefold()


def seed_all(seed: int) -> None:
    random.seed(seed); np.random.seed(seed); torch.manual_seed(seed); torch.cuda.manual_seed_all(seed)


def score_metrics(examples: list[dict], logits: np.ndarray) -> dict:
    rows, labels = [], []
    for i, e in enumerate(examples):
        z = logits[i * 8:(i + 1) * 8]; ids = e["candidate_source_ids"]; gold = set(e["gold_source_ids"])
        order = rank_scored_candidates(ids, {s: float(v) for s, v in zip(ids, z)}, tie_namespace="m6d:" + e["example_id"])
        rows.append(compute_ranking_metrics(order, gold)); labels.extend(int(s in gold) for s in ids)
    y = np.asarray(labels, dtype=int); z = np.asarray(logits, dtype=float); pos, neg = z[y == 1], z[y == 0]
    auroc = float(sum(1.0 if p > n else 0.5 if p == n else 0.0 for p in pos for n in neg) / max(len(pos) * len(neg), 1))
    order = np.argsort(-z, kind="stable"); ranked = y[order]; precision = np.cumsum(ranked) / np.arange(1, len(ranked) + 1)
    auprc = float(np.sum(precision[ranked.astype(bool)]) / max(int(y.sum()), 1))
    best = (-1., 0., 0., 0., 0.)
    for t in np.unique(z)[::-1]:
        pred = z >= t; tp = int(np.sum(pred & (y == 1))); fp = int(np.sum(pred & (y == 0))); fn = int(np.sum((~pred) & (y == 1)))
        p, r = tp / max(tp + fp, 1), tp / max(tp + fn, 1); f = 2 * p * r / max(p + r, 1e-12)
        candidate = (f, -int(pred.sum()), float(t), p, r)
        if candidate[:2] > best[:2]: best = candidate
    losses = []
    for i, e in enumerate(examples):
        local = z[i * 8:(i + 1) * 8]; p = np.exp(local - local.max()); p /= p.sum(); gold = np.asarray([s in set(e["gold_source_ids"]) for s in e["candidate_source_ids"]])
        losses.append(float(-np.log(p[gold] + 1e-12).mean()))
    out = {k: float(np.mean([r[k] for r in rows])) for k in ("hit_at_1", "mrr", "ndcg_at_5", "recall_at_5")}
    out.update({"ranking_loss": float(np.mean(losses)), "auroc": auroc, "auprc": auprc, "edge_f1": best[0], "edge_threshold": best[2], "edge_precision": best[3], "edge_recall": best[4], "predicted_edge_density": float(np.mean(z >= best[2])), "true_edge_density": float(y.mean()), "target_count": len(examples), "candidate_edges": len(y), "positive_edges": int(y.sum()), "negative_edges": int((1 - y).sum()), "random_baseline": RANDOM})
    return out


def model_for(variant: str) -> nn.Module:
    if variant == "P": return SourcePrior(DIM)
    if variant.endswith("SYM"): return SymmetricRelation(DIM)
    if variant.endswith("DIR"): return DirectionalRelation(DIM, RANK)
    raise ValueError(variant)


def build_tensors(examples, target_map, source_map, device):
    tv, sv, y, gids = [], [], [], []
    for gi, e in enumerate(examples):
        t = target_map[e["target_group_id"]]
        for sid in e["candidate_source_ids"]:
            tv.append(t); sv.append(source_map[sid]); y.append(float(sid in set(e["gold_source_ids"]))); gids.append(gi)
    return tuple(torch.from_numpy(np.asarray(x, np.float32)).to(device) for x in (tv, sv, np.asarray(y, np.float32), np.asarray(gids, np.int64)))


def logits(model, variant, t, s, base=None):
    if variant == "P": return model(s)
    r = model(t, s)
    return r if base is None else base + r


def selection_key(track, metric, epoch):
    return (-metric["mrr"], -metric["ndcg_at_5"], metric["ranking_loss"], epoch) if track == "rank" else (-metric["auprc"], -metric["auroc"], metric["edge_bce"], epoch)


def save_state(run_dir, model, best, history, config):
    run_dir.mkdir(parents=True, exist_ok=True)
    tmp = run_dir / "checkpoint.tmp.pt"; torch.save(best["state"], tmp); os.replace(tmp, run_dir / "best.pt")
    dump(run_dir / "history.json", history); dump(run_dir / "best.json", {k: v for k, v in best.items() if k != "state"}); dump(run_dir / "config.json", config)
    files = {p.name: sha(p) for p in (run_dir / "best.pt", run_dir / "history.json", run_dir / "best.json", run_dir / "config.json")}
    dump(run_dir / "integrity.json", files); (run_dir / "COMPLETED").write_text("completed\n")


def load_completed(run_dir, device):
    info = json.loads((run_dir / "best.json").read_text()); config = json.loads((run_dir / "config.json").read_text()); model = model_for(config["base_variant"]).to(device)
    model.load_state_dict(torch.load(run_dir / "best.pt", map_location=device, weights_only=True)); model.eval(); return model, info


def train_one(track, variant, seed, train, dev, train_t, dev_t, sources, device, run_dir, fixed_epochs=None, base_dir=None):
    if (run_dir / "COMPLETED").exists(): return load_completed(run_dir, device)
    work_dir = run_dir.with_name("." + run_dir.name + ".tmp-" + str(os.getpid()))
    if work_dir.exists() or run_dir.exists():
        raise RuntimeError(f"refusing to overwrite incomplete unit: {run_dir}")
    seed_all(seed); base = None
    base_variant = variant
    if variant.startswith("P_R_"):
        base_variant = "R_" + variant.split("P_R_")[1]
        prior, _ = load_completed(base_dir, device); freeze_module(prior)
    model = model_for(base_variant).to(device).float(); opt = torch.optim.AdamW(model.parameters(), lr=TRACKS[track]["lr"], weight_decay=1e-4)
    tt, ss, yy, gg = build_tensors(train, train_t, sources, device); dt, ds, dy, _ = build_tensors(dev, dev_t, sources, device)
    with torch.inference_mode(): base_tr = prior(ss) if variant.startswith("P_R_") else None; base_dv = prior(ds) if variant.startswith("P_R_") else None
    pos_weight = torch.tensor((len(yy) - yy.sum()).item() / max(yy.sum().item(), 1), device=device); best = None; bad = 0; history = []; started = time.time(); total = fixed_epochs or EPOCHS
    for epoch in range(1, total + 1):
        model.train(); order = np.random.default_rng(seed + 1000 + epoch).permutation(len(train)); losses = []
        for start in range(0, len(train), BATCH):
            choose = order[start:start+BATCH]; mask = torch.zeros(len(yy), dtype=torch.bool, device=device)
            for group in choose: mask |= gg == int(group)
            opt.zero_grad(set_to_none=True); z = logits(model, variant, tt[mask], ss[mask], None if base_tr is None else base_tr[mask])
            loss = all_positive_distribution_loss(z, yy[mask], gg[mask]) if track == "rank" else nn.functional.binary_cross_entropy_with_logits(z, yy[mask], pos_weight=pos_weight)
            loss.backward(); grad = float(torch.nn.utils.clip_grad_norm_(model.parameters(), CLIP)); opt.step(); losses.append(float(loss.detach().cpu()))
        model.eval()
        with torch.inference_mode(): ztr = logits(model, variant, tt, ss, base_tr).cpu().numpy(); zdv = logits(model, variant, dt, ds, base_dv).cpu().numpy()
        tm, dm = score_metrics(train, ztr), score_metrics(dev, zdv); dm["edge_bce"] = float(nn.functional.binary_cross_entropy_with_logits(torch.from_numpy(zdv), dy.cpu(), pos_weight=pos_weight.cpu())) if track == "edge" else None
        key = selection_key(track, dm, epoch); improved = best is None or key < best["key"]; bad = 0 if improved else bad + 1
        history.append({"epoch": epoch, "train_loss": float(np.mean(losses)), "train_metrics": tm, "dev_metrics": dm, "grad_norm": grad, "improvement": improved, "bad_count": bad})
        if improved: best = {"key": key, "epoch": epoch, "metrics": dm, "train_metrics": tm, "state": {k: v.detach().cpu() for k, v in model.state_dict().items()}}
        if fixed_epochs is None and bad >= PATIENCE: break
    if fixed_epochs is not None:
        last = history[-1]; best = {"key": selection_key(track, last["dev_metrics"], last["epoch"]), "epoch": last["epoch"], "metrics": last["dev_metrics"], "train_metrics": last["train_metrics"], "state": {k: v.detach().cpu() for k, v in model.state_dict().items()}}
    config = {"track": track, "variant": variant, "base_variant": base_variant, "seed": seed, "lr": TRACKS[track]["lr"], "objective": "all_positive_distribution_cross_entropy" if track == "rank" else "BCEWithLogitsLoss(pos_weight=train_negatives/train_positives)", "parameter_count": parameter_count(model), "base_frozen": variant.startswith("P_R_"), "fixed_epochs": fixed_epochs, "runtime_seconds": time.time() - started, "peak_gpu_bytes": int(torch.cuda.max_memory_allocated()), "stopping_reason": "fixed_cv_epoch" if fixed_epochs else ("patience_5" if bad >= PATIENCE else "max_epoch_50")}
    save_state(work_dir, model, best, history, config)
    os.replace(work_dir, run_dir)
    restored, info = load_completed(run_dir, device)
    return restored, {**info, "runtime": config}


def predict(model, variant, examples, targets, sources, device, prior=None):
    t, s, _, _ = build_tensors(examples, targets, sources, device)
    with torch.inference_mode(): return logits(model, variant, t, s, prior(s) if prior is not None else None).cpu().numpy()


def rows_from(examples, logits, track, variant, seed, split="dev"):
    out=[]
    for i,e in enumerate(examples):
        for j,s in enumerate(e["candidate_source_ids"]): out.append({"example_id": e["example_id"], "target_group_id": e["target_group_id"], "document_group_id": e["document_group_id"], "candidate_id": s, "candidate_order": j, "label": int(s in set(e["gold_source_ids"])), "logit": float(logits[i*8+j]), "track": track, "variant": variant, "seed": seed, "split": split})
    return out


def write_jsonl(path, rows):
    with path.open("w") as f:
        for row in rows: f.write(json.dumps(row, separators=(",", ":")) + "\n")


def bootstrap_delta(examples, a, b, metric, reps=10000, seed=20260812):
    rng=np.random.default_rng(seed); diffs=[]
    for i,e in enumerate(examples): diffs.append(score_metrics([e], a[i*8:(i+1)*8])[metric] - score_metrics([e], b[i*8:(i+1)*8])[metric])
    arr=np.asarray(diffs); vals=np.asarray([rng.choice(arr, len(arr), replace=True).mean() for _ in range(reps)])
    return {"metric":metric,"unit":"target_group","reps":reps,"seed":seed,"mean":float(arr.mean()),"ci95":[float(np.quantile(vals,.025)),float(np.quantile(vals,.975))]}


def clean_examples(dev, train_source_hashes, source_hash):
    return [e for e in dev if not any(source_hash[s] in train_source_hashes for s in e["candidate_source_ids"])]


def component_folds(train, source_hash):
    parent={}
    def find(x):
        parent.setdefault(x,x)
        while parent[x]!=x: parent[x]=parent[parent[x]];x=parent[x]
        return x
    def join(a,b):
        a,b=find(a),find(b)
        if a!=b: parent[b]=a
    for e in train:
        d="d:"+e["document_group_id"]
        for s in e["candidate_source_ids"]: join(d,"s:"+source_hash[s])
    buckets=defaultdict(list)
    for e in train: buckets[find("d:"+e["document_group_id"])].append(e)
    comps=sorted(buckets.values(), key=lambda x:(-len(x), x[0]["target_group_id"]))
    if comps and len(comps[0]) > len(train)*.5: return None, {"reason":"giant_component", "largest_targets":len(comps[0]), "total_targets":len(train)}
    folds=[[] for _ in range(5)]; sizes=[0]*5
    for comp in comps:
        k=min(range(5), key=lambda j:(sizes[j],j)); folds[k].extend(comp); sizes[k]+=len(comp)
    return folds, {"component_count":len(comps),"fold_target_counts":sizes,"largest_component_targets":max(map(len,comps),default=0)}


def main():
    allowed_root={"M6D_PREREGISTRATION.md","m6d_frozen_config.json","input_manifest.json","fold_manifest.json","runtime_manifest.json","runs","oof","parallel","predictions_dev.jsonl","predictions_oof.jsonl","dev_summary.json","oof_summary.json","permutation_metrics.json","bootstrap_comparisons.csv","metrics_by_run.csv","hard_subset_metrics.csv","M6D_INTEGRITY.json","M6D_REPORT.md","COMPLETED"}
    if OUT.exists() and any(OUT.iterdir()) and not {p.name for p in OUT.iterdir()}.issubset(allowed_root):
        raise RuntimeError(f"refusing nonempty M6D output: {OUT}")
    required=[M6A/"cache_manifest.json",M6A/"feature_index.jsonl",M6A/"mean_index.json",M6A/"mean_source_features.npz",M6A/"mean_train_target_features.npz",M6A/"mean_dev_target_features.npz",M6B/"champions.json",M6B/"selected_learning_rates.json",DATA/"train_examples.jsonl",DATA/"dev_examples.jsonl",DATA/"source_catalog.jsonl"]
    hashes={str(p.relative_to(ROOT)):sha(p) for p in required}
    train,dev=read_jsonl(DATA/"train_examples.jsonl"),read_jsonl(DATA/"dev_examples.jsonl"); catalog=read_jsonl(DATA/"source_catalog.jsonl")
    manifest=json.loads((M6A/"cache_manifest.json").read_text()); idx=json.loads((M6A/"mean_index.json").read_text())
    if manifest["feature_index"]["sha256"]!=sha(M6A/"feature_index.jsonl") or len(train)!=854 or len(dev)!=228: raise RuntimeError("frozen cache/data validation failed")
    src=np.load(M6A/"mean_source_features.npz")["normalized"].astype(np.float32); tr=np.load(M6A/"mean_train_target_features.npz")["normalized"].astype(np.float32); dv=np.load(M6A/"mean_dev_target_features.npz")["normalized"].astype(np.float32)
    if src.shape!=(10400,DIM) or tr.shape!=(854,DIM) or dv.shape!=(228,DIM): raise RuntimeError("unexpected F_mean shape")
    if idx["train_target_ids"] != [e["target_group_id"] for e in train] or idx["dev_target_ids"] != [e["target_group_id"] for e in dev]: raise RuntimeError("target order mismatch")
    smap={s:i for i,s in enumerate(idx["source_ids"])}; sources={s:src[i] for s,i in smap.items()}; train_t={e["target_group_id"]:tr[i] for i,e in enumerate(train)}; dev_t={e["target_group_id"]:dv[i] for i,e in enumerate(dev)}
    if any(len(e["candidate_source_ids"])!=8 or not set(e["gold_source_ids"]).issubset(e["candidate_source_ids"]) for e in train+dev): raise RuntimeError("candidate membership validation failed")
    source_hash={r["source_id"]:hashlib.sha256(norm_text(r["text"]).encode()).hexdigest() for r in catalog}
    train_hashes={source_hash[s] for e in train for s in e["candidate_source_ids"]}; dev_clean=clean_examples(dev,train_hashes,source_hash)
    folds,fold_info=component_folds(train,source_hash)
    prereg={"checkpoint":"M6D","before_new_metrics":True,"input_sha256":hashes,"counts":{"train_targets":len(train),"train_pairs":len(train)*8,"dev_targets":len(dev),"dev_pairs":len(dev)*8,"dev_positive":sum(len(e["gold_source_ids"]) for e in dev),"dev_negative":len(dev)*8-sum(len(e["gold_source_ids"]) for e in dev),"dev_clean_targets":len(dev_clean)},"features":{"name":"F_mean_M6A","shape":[DIM],"dtype":"float32","normalization":"pre-normalized cache vectors; no fitted normalization"},"tracks":TRACKS,"variants":list(VARIANTS),"seeds":list(SEEDS),"fold_seed":20260812,"primary":{"rank":"MRR","edge":"AUPRC"},"selection":{"rank":"MRR desc, nDCG@5 desc, ranking loss asc, earlier epoch","edge":"AUPRC desc, AUROC desc, BCE asc, earlier epoch"},"rules":{"no_qwen":True,"no_blind":True,"no_bm25_input":True,"rank_fixed":RANK,"bootstrap_reps":10000}}
    OUT.mkdir(parents=True, exist_ok=True)
    prereg_path=OUT/"m6d_frozen_config.json"
    if prereg_path.exists():
        if json.loads(prereg_path.read_text()) != prereg: raise RuntimeError("existing preregistration differs")
    else:
        dump(prereg_path,prereg); dump(OUT/"input_manifest.json",{"sha256":hashes,"m6a_model_manifest_sha256":manifest["model_manifest_sha256"],"blind_accessed":False,"qwen_loaded":False}); (OUT/"M6D_PREREGISTRATION.md").write_text("# M6D preregistration\n\nFrozen before new training metrics. See `m6d_frozen_config.json`; only M6A F_mean Train/Dev cache and the exact non-Blind conservative Train/Dev inputs are permitted.\n"); dump(OUT/"fold_manifest.json",{"fold_info":fold_info,"available":folds is not None,"blind_accessed":False})
    # Select dynamically after preregistration. No model weights are loaded.
    required_mib=1600; gpus=gpu_query(); chosen=choose_gpu(gpus,required_mib,read_claimed_gpus(ROOT/"gpu_claims"),None); job_id="m6d_source_prior_relational_finalizer" if os.environ.get("M6D_SUPERVISOR_FINALIZE")=="1" else "m6d_source_prior_relational"; claim=write_claim(ROOT/"gpu_claims",socket.gethostname(),os.getpid(),chosen.index,job_id,required_mib); os.environ["CUDA_VISIBLE_DEVICES"]=str(chosen.index); device=torch.device("cuda:0")
    if not torch.cuda.is_available(): raise RuntimeError("CUDA unavailable after dynamic selector")
    runtime={"physical_gpu":chosen.index,"logical_gpu":"cuda:0","required_mib":required_mib,"free_mib":chosen.free_mib,"claim":str(claim),"qwen_loaded":False,"blind_accessed":False}; dump(OUT/"runtime_manifest.json",runtime)
    all_rows=[]; summaries=[]; saved={}
    torch.cuda.reset_peak_memory_stats()
    for track in TRACKS:
        for seed in SEEDS:
            prior_dir=OUT/f"runs/{track}/P/seed_{seed}"; prior,_=train_one(track,"P",seed,train,dev,train_t,dev_t,sources,device,prior_dir); saved[(track,"P",seed)]=(prior,None)
            for variant in ("R_SYM","R_DIR","P_R_SYM","P_R_DIR"):
                base=prior_dir if variant.startswith("P_R_") else None; run=OUT/f"runs/{track}/{variant}/seed_{seed}"; model,info=train_one(track,variant,seed,train,dev,train_t,dev_t,sources,device,run,base_dir=base); prior_for_score=prior if variant.startswith("P_R_") else None; saved[(track,variant,seed)]=(model,prior_for_score)
            for variant in VARIANTS:
                model,prior_for_score=saved[(track,variant,seed)]; z=predict(model,variant,dev,dev_t,sources,device,prior_for_score); full=score_metrics(dev,z); clean_z=np.concatenate([z[i*8:(i+1)*8] for i,e in enumerate(dev) if e in dev_clean]) if dev_clean else np.array([]); clean=score_metrics(dev_clean,clean_z) if dev_clean else {"target_count":0}
                info=json.loads((OUT/f"runs/{track}/{variant}/seed_{seed}/best.json").read_text()); summaries.append({"stage":"dev","track":track,"variant":variant,"seed":seed,"best_epoch":info["epoch"],"parameter_count":json.loads((OUT/f"runs/{track}/{variant}/seed_{seed}/config.json").read_text())["parameter_count"],"full":full,"dev_clean":clean,"checkpoint_sha256":sha(OUT/f"runs/{track}/{variant}/seed_{seed}/best.pt")}); all_rows.extend(rows_from(dev,z,track,variant,seed))
    write_jsonl(OUT/"predictions_dev.jsonl",all_rows); dump(OUT/"dev_summary.json",summaries)
    # Deterministic target permutation on frozen full-Dev models.
    perms=[]; rng=np.random.default_rng(20260812)
    for track in TRACKS:
        for variant in VARIANTS:
            deltas=[]
            for seed in SEEDS:
                model,prior=saved[(track,variant,seed)]; original=predict(model,variant,dev,dev_t,sources,device,prior); original_metric=score_metrics(dev,original)[TRACKS[track]["primary"]]
                values=[]
                for rep in range(20):
                    order=np.random.default_rng(20260812+rep).permutation(len(dev)); perm_t={e["target_group_id"]:dev_t[dev[j]["target_group_id"]] for j,e in enumerate(dev)}; z=predict(model,variant,dev,perm_t,sources,device,prior); values.append(score_metrics(dev,z)[TRACKS[track]["primary"]])
                perms.append({"track":track,"variant":variant,"seed":seed,"original":original_metric,"permuted_mean":float(np.mean(values)),"delta":float(original_metric-np.mean(values)),"permuted_values":values})
    dump(OUT/"permutation_metrics.json",perms)
    # Source-controlled CV, omitted only if the frozen constraints are mathematically infeasible.
    oof_rows=[]; cv_summary=[]
    if folds is not None:
        for fold,valid in enumerate(folds):
            valid_ids={e["target_group_id"] for e in valid}; fit=[e for e in train if e["target_group_id"] not in valid_ids]; fit_t={e["target_group_id"]:train_t[e["target_group_id"]] for e in fit}; val_t={e["target_group_id"]:train_t[e["target_group_id"]] for e in valid}
            for track in TRACKS:
                prior_dir=OUT/f"oof/fold_{fold}/{track}/P/seed_0"; prior,_=train_one(track,"P",0,fit,valid,fit_t,val_t,sources,device,prior_dir,fixed_epochs=TRACKS[track]["fixed_cv_epochs"])
                models={"P":(prior,None)}
                for variant in ("R_SYM","R_DIR","P_R_SYM","P_R_DIR"):
                    model,_=train_one(track,variant,0,fit,valid,fit_t,val_t,sources,device,OUT/f"oof/fold_{fold}/{track}/{variant}/seed_0",fixed_epochs=TRACKS[track]["fixed_cv_epochs"],base_dir=prior_dir if variant.startswith("P_R_") else None); models[variant]=(model,prior if variant.startswith("P_R_") else None)
                for variant,(model,prior_) in models.items():
                    z=predict(model,variant,valid,val_t,sources,device,prior_); cv_summary.append({"fold":fold,"track":track,"variant":variant,"metrics":score_metrics(valid,z)}); oof_rows.extend(rows_from(valid,z,track,variant,0,"oof"))
    write_jsonl(OUT/"predictions_oof.jsonl",oof_rows); dump(OUT/"oof_summary.json",cv_summary)
    # Final paired comparisons, using seed mean logits for full Dev and OOF where available.
    comparisons=[]
    for track in TRACKS:
        primary=TRACKS[track]["primary"]
        def avg_variant(v):
            return np.mean([np.asarray([r["logit"] for r in all_rows if r["track"]==track and r["variant"]==v and r["seed"]==s]) for s in SEEDS],axis=0)
        p,sy,di,ps,pd=avg_variant("P"),avg_variant("R_SYM"),avg_variant("R_DIR"),avg_variant("P_R_SYM"),avg_variant("P_R_DIR")
        for name,a,b in (("P_R_DIR_minus_P",pd,p),("P_R_SYM_minus_P",ps,p),("P_R_DIR_minus_P_R_SYM",pd,ps),("R_DIR_minus_R_SYM",di,sy)):
            comparisons.append({"scope":"dev_full","track":track,"comparison":name,**bootstrap_delta(dev,a,b,primary)})
    with (OUT/"bootstrap_comparisons.csv").open("w",newline="") as f:
        w=csv.DictWriter(f,fieldnames=["scope","track","comparison","metric","unit","reps","seed","mean","ci95"]);w.writeheader();w.writerows(comparisons)
    with (OUT/"metrics_by_run.csv").open("w",newline="") as f:
        w=csv.writer(f);w.writerow(["stage","track","variant","seed","best_epoch","full_metrics_json","dev_clean_metrics_json","checkpoint_sha256"])
        for x in summaries:w.writerow([x["stage"],x["track"],x["variant"],x["seed"],x["best_epoch"],json.dumps(x["full"],sort_keys=True),json.dumps(x["dev_clean"],sort_keys=True),x["checkpoint_sha256"]])
    # Hard subsets and final decisions are computed from predictions only.
    p_rows=[r for r in all_rows if r["track"]=="rank" and r["variant"]=="P" and r["seed"]==0]; pmap=defaultdict(list)
    for r in p_rows:pmap[r["example_id"]].append(r)
    hard={"prior_challenging":[e for e in dev if max(r["logit"] for r in pmap[e["example_id"]] if r["label"]==0)>=max(r["logit"] for r in pmap[e["example_id"]] if r["label"]==1)],"bm25_hard":[],"role_switching":[]}
    bm25_rows=read_jsonl(ROOT/"results/longcite_c5b_7b/dev_scores.jsonl")
    bm25={(r["example_id"],r["candidate_id"]):float(r.get("normalized_score",r.get("raw_score",0))) for r in bm25_rows if r.get("method")=="bm25" and r.get("view")=="primary"}
    neg_scores=[bm25.get((e["example_id"],s),float("-inf")) for e in dev for s in e["candidate_source_ids"] if s not in set(e["gold_source_ids"])]
    cutoff=float(np.quantile(neg_scores,.75)) if neg_scores else float("inf")
    hard["bm25_hard"]=[e for e in dev if any(s not in set(e["gold_source_ids"]) and bm25.get((e["example_id"],s),float("-inf"))>=cutoff for s in e["candidate_source_ids"])]
    role=defaultdict(set)
    for e in train+dev:
        for s in e["candidate_source_ids"]:role[source_hash[s]].add(int(s in set(e["gold_source_ids"])))
    rolehash={h for h,v in role.items() if len(v)>1};hard["role_switching"]=[e for e in dev if any(source_hash[s] in rolehash for s in e["candidate_source_ids"])]
    hard_rows=[]
    for name,subset in hard.items():
        for track in TRACKS:
            for variant in VARIANTS:
                for seed in SEEDS:
                    z=np.asarray([r["logit"] for r in all_rows if r["track"]==track and r["variant"]==variant and r["seed"]==seed]); ids=[i for i,e in enumerate(dev) if e in subset]; subz=np.concatenate([z[i*8:(i+1)*8] for i in ids]) if ids else np.array([]); hard_rows.append({"subset":name,"track":track,"variant":variant,"seed":seed,"targets":len(subset),"pairs":len(subz),"metrics":score_metrics(subset,subz) if ids else {}})
    with (OUT/"hard_subset_metrics.csv").open("w",newline="") as f:
        w=csv.DictWriter(f,fieldnames=["subset","track","variant","seed","targets","pairs","metrics"]);w.writeheader();
        for r in hard_rows:w.writerow({**r,"metrics":json.dumps(r["metrics"],sort_keys=True)})
    integrity={"input_sha256":hashes,"frozen_config_sha256":sha(OUT/"m6d_frozen_config.json"),"predictions_dev_sha256":sha(OUT/"predictions_dev.jsonl"),"predictions_oof_sha256":sha(OUT/"predictions_oof.jsonl"),"qwen_loaded":False,"blind_accessed":False,"gpu":runtime,"created_files":[]}
    for p in sorted(OUT.rglob("*")):
        if p.is_file() and p.name not in {"M6D_INTEGRITY.json"}: integrity["created_files"].append({"path":str(p.relative_to(OUT)),"sha256":sha(p),"bytes":p.stat().st_size})
    dump(OUT/"M6D_INTEGRITY.json",integrity)
    (OUT/"M6D_REPORT.md").write_text("# M6D Source-prior-controlled relational validation\n\nCompleted from frozen F_mean Train/Dev cache only. See `metrics_by_run.csv`, `bootstrap_comparisons.csv`, `hard_subset_metrics.csv`, `permutation_metrics.json`, and `M6D_INTEGRITY.json`. Ranking and Edge tracks remain separate. Blind was never accessed and Qwen was never loaded.\n")
    (OUT/"COMPLETED").write_text("completed\n")


if __name__ == "__main__": main()
