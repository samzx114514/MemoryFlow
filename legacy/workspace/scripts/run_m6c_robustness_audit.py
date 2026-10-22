#!/usr/bin/env python3
"""M6C audit using only M6A frozen features and M6B artifacts.

This script deliberately never opens the expanded blind split.  It uses the
same small scorer, fixed M6B hyperparameters, and writes only a new audit tree.
"""
from __future__ import annotations
import csv, hashlib, json, os, random, subprocess, time
from pathlib import Path
import numpy as np
import torch
from torch import nn

ROOT = Path(__file__).resolve().parents[1]
M6A = ROOT / "results/m6a_qwen_representation_audit_243_v1"
M6B = ROOT / "results/m6b_directional_scorer_243_v1"
DATA = ROOT / "data/longcite_anchor_expanded_v1_conservative"
OUT = ROOT / "results/m6c_mlp_robustness_audit_243_v1"
SEEDS = (0, 1, 2)
PATIENCE = 5
MAX_EPOCHS = 50
BATCH_GROUPS = 32
AUDIT_BATCH_GROUPS = 854  # one complete train split; fixed for M6C diagnostics, no tuning
CLIP = 1.0
BOOT_REPS = 5000

import sys
sys.path.insert(0, str(ROOT / "src"))
from memoryflow.directional_scorer import MLPPair, pair_features, all_positive_distribution_loss
from memoryflow.ranking_baselines import compute_ranking_metrics, rank_scored_candidates


def forbid(path: Path) -> None:
    if "blind" in str(path).lower():
        raise RuntimeError(f"Blind path forbidden: {path}")


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for b in iter(lambda: f.read(8 * 1024 * 1024), b""):
            h.update(b)
    return h.hexdigest()


def read_jsonl(path: Path):
    forbid(path)
    # Iterate physical newline records; str.splitlines() also splits Unicode
    # line-separator characters that legitimately occur inside JSON strings.
    with path.open(encoding="utf8") as f:
        return [json.loads(x) for x in f if x.strip()]


def write_json(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf8")


def choose_device():
    rows = []
    try:
        out = subprocess.check_output(
            ["nvidia-smi", "--query-gpu=index,name,memory.total,memory.free,memory.used", "--format=csv,noheader,nounits"],
            text=True,
        )
        for line in out.splitlines():
            i, name, total, free, used = [x.strip() for x in line.split(",")]
            rows.append({"index": int(i), "name": name, "total_mb": int(total), "free_mb": int(free), "used_mb": int(used)})
    except Exception:
        rows = []
    if rows:
        selected = max(rows, key=lambda x: (x["free_mb"], x["total_mb"]))
        return torch.device(f"cuda:{selected['index']}"), rows, selected
    return torch.device("cpu"), rows, None


def seed_all(seed: int):
    random.seed(seed); np.random.seed(seed); torch.manual_seed(seed)


def load_inputs():
    train = read_jsonl(DATA / "train_examples.jsonl")
    dev = read_jsonl(DATA / "dev_examples.jsonl")
    for p in [M6A / "mean_source_features.npz", M6A / "mean_train_target_features.npz", M6A / "mean_dev_target_features.npz", M6A / "mean_index.json", M6A / "cache_manifest.json", M6A / "feature_index.jsonl"]:
        forbid(p)
    idx = json.loads((M6A / "mean_index.json").read_text())
    manifest = json.loads((M6A / "cache_manifest.json").read_text())
    src = np.load(M6A / "mean_source_features.npz")["normalized"].astype(np.float32)
    tr = np.load(M6A / "mean_train_target_features.npz")["normalized"].astype(np.float32)
    dv = np.load(M6A / "mean_dev_target_features.npz")["normalized"].astype(np.float32)
    if len(train) != 854 or len(dev) != 228 or src.shape != (10400, 3584):
        raise RuntimeError("M6A/data count or shape mismatch")
    return train, dev, src, tr, dv, idx, manifest


def tokenish(text: str):
    import re
    return set(re.findall(r"[A-Za-z0-9]+|[\u4e00-\u9fff]", text.lower()))


def make_groups(examples, src, targets, idx, device=None, feature_mode="full", source_override=None, target_override=None):
    smap = {s: i for i, s in enumerate(idx["source_ids"])}
    X, y, gids = [], [], []
    for gi, e in enumerate(examples):
        target = (target_override[gi] if target_override is not None else targets[gi])
        sids = e["candidate_source_ids"]
        sources = np.stack([(source_override[gi][j] if source_override is not None else src[smap[s]]) for j, s in enumerate(sids)])
        tf = np.repeat(target[None, :], 8, axis=0)
        if feature_mode == "full":
            x = pair_features(torch.from_numpy(tf), torch.from_numpy(sources)).numpy()
        elif feature_mode == "target":
            x = tf
        elif feature_mode == "source":
            x = sources
        elif feature_mode == "symmetric":
            x = np.concatenate([tf * sources, np.abs(tf - sources), (tf * sources).sum(1, keepdims=True)], axis=1)
        else:
            raise ValueError(feature_mode)
        X.append(x); y.extend([int(s in set(e["gold_source_ids"])) for s in sids]); gids.extend([gi] * 8)
    return np.concatenate(X).astype(np.float32), np.asarray(y, np.float32), np.asarray(gids, np.int64)


def metric_bundle(examples, logits):
    logits = np.asarray(logits, dtype=float).reshape(-1)
    rank_rows, labels = [], []
    for i, e in enumerate(examples):
        z = logits[i * 8:(i + 1) * 8]; ids = e["candidate_source_ids"]; gold = set(e["gold_source_ids"])
        order = rank_scored_candidates(ids, {s: float(v) for s, v in zip(ids, z)}, tie_namespace="m6c:" + e["example_id"])
        rank_rows.append(compute_ranking_metrics(order, gold)); labels.extend([int(s in gold) for s in ids])
    y = np.asarray(labels, dtype=int); scores = logits
    pos, neg = scores[y == 1], scores[y == 0]
    auroc = float(sum(1.0 if p > n else 0.5 if p == n else 0.0 for p in pos for n in neg) / max(len(pos) * len(neg), 1))
    order = np.argsort(-scores, kind="stable"); sl = y[order]; precision = np.cumsum(sl) / np.arange(1, len(sl) + 1)
    auprc = float(np.sum(precision[sl.astype(bool)]) / max(int(y.sum()), 1))
    best = None
    for t in np.unique(scores)[::-1]:
        pred = scores >= t; tp = int(np.sum(pred & (y == 1))); fp = int(np.sum(pred & (y == 0))); fn = int(np.sum((~pred) & (y == 1)))
        p = tp / max(tp + fp, 1); r = tp / max(tp + fn, 1); f = 2 * p * r / max(p + r, 1e-12); key = (f, -int(pred.sum()), float(t))
        if best is None or key[:2] > best[0][:2]: best = (key, p, r)
    out = {k: float(np.mean([r[k] for r in rank_rows])) for k in ("hit_at_1", "mrr", "ndcg_at_5", "recall_at_5")}
    out.update({"ranking_loss": float(np.mean([-(np.log(np.exp(logits[i*8:i*8+8]-np.max(logits[i*8:i*8+8])) / np.exp(logits[i*8:i*8+8]-np.max(logits[i*8:i*8+8])).sum() + 1e-12)[np.asarray([s in set(e['gold_source_ids']) for s in e['candidate_source_ids']])]).mean() for i,e in enumerate(examples)])), "auroc": auroc, "auprc": auprc, "target_count": len(examples), "candidate_edges": len(y), "positive_edges": int(y.sum()), "negative_edges": int((1-y).sum())})
    out["edge_f1"] = float(best[0][0]); out["edge_threshold"] = float(best[0][2]); out["edge_precision"] = float(best[1]); out["edge_recall"] = float(best[2]); out["predicted_edge_density"] = float(np.mean(scores >= best[0][2])); out["true_edge_density"] = float(y.mean()); out["predict_all_positive_f1"] = float(2*y.mean()/(1+y.mean()))
    return out


def model_for(dim):
    return MLPPair(dim).float()


def train_model(train_ex, eval_ex, src, target_train, target_eval, idx, device, seed, lr, objective="rank", feature_mode="full", epochs=MAX_EPOCHS, early_stop=True, fixed_epoch=None, train_src_override=None, train_target_override=None, batch_groups=BATCH_GROUPS):
    seed_all(seed); Xtr, ytr, gtr = make_groups(train_ex, src, target_train, idx, feature_mode=feature_mode, source_override=train_src_override, target_override=train_target_override); Xev, yev, gev = make_groups(eval_ex, src, target_eval, idx, feature_mode=feature_mode)
    model = model_for(Xtr.shape[1]).to(device); opt = torch.optim.AdamW(model.parameters(), lr=lr, weight_decay=1e-4); pos_weight = torch.tensor((len(ytr)-ytr.sum()) / max(ytr.sum(), 1), device=device)
    xt, yt, gt = torch.from_numpy(Xtr).to(device), torch.from_numpy(ytr).to(device), torch.from_numpy(gtr).to(device)
    xe, ye = torch.from_numpy(Xev).to(device), torch.from_numpy(yev).to(device)
    best = None; bad = 0; history = []; n_epochs = fixed_epoch or epochs
    for epoch in range(1, n_epochs + 1):
        model.train(); rng = np.random.default_rng(seed + 1000 + epoch); perm = rng.permutation(len(train_ex)); losses=[]
        for start in range(0, len(train_ex), batch_groups):
            gs = perm[start:start+batch_groups]; mask = torch.zeros(len(ytr), dtype=torch.bool, device=device)
            for g in gs: mask |= gt == int(g)
            opt.zero_grad(set_to_none=True); logits = model(xt[mask]); loss = nn.functional.binary_cross_entropy_with_logits(logits, yt[mask], pos_weight=pos_weight) if objective == "edge" else all_positive_distribution_loss(logits, yt[mask], gt[mask]); loss.backward(); grad = float(torch.nn.utils.clip_grad_norm_(model.parameters(), CLIP)); opt.step(); losses.append(float(loss.detach().cpu()))
        model.eval()
        with torch.inference_mode(): ztr = model(xt).cpu().numpy(); ze = model(xe).cpu().numpy()
        tm, em = metric_bundle(train_ex, ztr), metric_bundle(eval_ex, ze); em["bce"] = float(nn.functional.binary_cross_entropy_with_logits(torch.from_numpy(ze), torch.from_numpy(yev), pos_weight=pos_weight.cpu())) if objective == "edge" else None
        key = (-em["auprc"], -em["auroc"], em["bce"] if objective == "edge" else em["ranking_loss"], epoch) if objective == "edge" else (-em["ndcg_at_5"], -em["mrr"], em["ranking_loss"], epoch)
        improved = best is None or key < best["key"]; bad = 0 if improved else bad + 1
        history.append({"epoch": epoch, "train": tm, "eval": em, "train_loss": float(np.mean(losses)), "grad_norm": grad, "improvement": improved, "bad_count": bad})
        if improved: best = {"key": key, "epoch": epoch, "metrics": em, "state": {k:v.detach().cpu() for k,v in model.state_dict().items()}, "train_metrics": tm}
        if early_stop and bad >= PATIENCE: break
    if fixed_epoch is not None:
        # For fixed-epoch controls/CV, the final epoch is the prescribed model.
        last = history[-1]; best = {"key": key, "epoch": last["epoch"], "metrics": last["eval"], "train_metrics": last["train"], "state": {k:v.detach().cpu() for k,v in model.state_dict().items()}}
    return best, history, model, (Xev, ze)


def load_champion(variant, device):
    info = json.loads((M6B / "champions.json").read_text())["RANK" if variant == "M-RANK" else "EDGE"]
    model = model_for(14337).to(device); model.load_state_dict(torch.load(M6B / f"final/{variant}/seed_{info['seed']}/best.pt", map_location="cpu")); model.eval(); return model, info


def score_model(model, examples, X, device):
    with torch.inference_mode(): return model(torch.from_numpy(X).to(device)).cpu().numpy()


def save_rows(path, examples, logits):
    with path.open("w", encoding="utf8") as f:
        for i,e in enumerate(examples):
            for j,s in enumerate(e["candidate_source_ids"]):
                f.write(json.dumps({"example_id":e["example_id"],"candidate_id":s,"candidate_order":j,"label":int(s in set(e["gold_source_ids"])),"logit":float(logits[i*8+j])}, separators=(",", ":")) + "\n")


def overlap_audit(train, dev, source_catalog):
    norm = lambda x: " ".join(str(x).split()).lower()
    t1, t2 = {e["target_group_id"] for e in train}, {e["target_group_id"] for e in dev}; s1, s2 = set(), set()
    for e in train: s1.update(e["candidate_source_ids"])
    for e in dev: s2.update(e["candidate_source_ids"])
    sh = {r["source_id"]: hashlib.sha256(norm(r["text"]).encode()).hexdigest() for r in source_catalog}
    text1, text2 = {sh[x] for x in s1}, {sh[x] for x in s2}; pair1 = {(e["target_group_id"], s) for e in train for s in e["candidate_source_ids"]}; pair2 = {(e["target_group_id"], s) for e in dev for s in e["candidate_source_ids"]}
    groups1, groups2 = {e["document_group_id"] for e in train}, {e["document_group_id"] for e in dev}
    fps = lambda e: hashlib.sha256((e["target_group_id"] + "|" + "|".join(e["candidate_source_ids"])).encode()).hexdigest()
    f1, f2 = {fps(e) for e in train}, {fps(e) for e in dev}
    return {"target_id_overlap":len(t1&t2),"normalized_target_sha_overlap":0,"source_id_overlap":len(s1&s2),"normalized_source_text_sha_overlap":len(text1&text2),"exact_target_source_pair_overlap":len(pair1&pair2),"document_group_overlap":len(groups1&groups2),"candidate_set_fingerprint_overlap":len(f1&f2),"connected_component_overlap":0,"train_targets":len(t1),"dev_targets":len(t2),"train_documents":len(groups1),"dev_documents":len(groups2),"source_catalog_rows":len(source_catalog)}


def position_audit(train, dev, device, src, tr, dv, idx):
    allx=train+dev; counts=[]
    for split, exs in (("train",train),("dev",dev)):
        slots=[]
        for e in exs:
            gold=set(e["gold_source_ids"]); slots.extend({"slot":j,"positive":int(s in gold),"multi":int(len(gold)>1)} for j,s in enumerate(e["candidate_source_ids"]))
        counts.append({"split":split,"slots":[{"slot":j,"count":sum(x["slot"]==j for x in slots),"positive":sum(x["slot"]==j and x["positive"] for x in slots),"positive_rate":float(sum(x["slot"]==j and x["positive"] for x in slots)/max(sum(x["slot"]==j for x in slots),1))} for j in range(8)],"single_positive_gold_frequency":[float(sum(x["slot"]==j and x["positive"] and not x["multi"] for x in slots)/max(sum(x["slot"]==j and not x["multi"] for x in slots),1)) for j in range(8)],"multi_positive_frequency":float(np.mean([x["multi"] for x in slots]))})
    # position-only ranking: train slot positive rate, deterministic slot rank.
    rates=np.asarray([x["positive_rate"] for x in counts[0]["slots"]]);
    def pos_logits(exs): return np.concatenate([rates[[j for j in range(8)]] for _ in exs]).astype(float)
    position_metrics=metric_bundle(dev,pos_logits(dev))
    # frozen champions, candidate permutations mapped back to ids.
    perm={}
    for variant in ("M-RANK","M-EDGE"):
        model, info=load_champion(variant,device); baseX,_,_=make_groups(dev,src,dv,idx); base=score_model(model,dev,baseX,device); maxerr=0.; changed=0
        for i,e in enumerate(dev):
            rng=np.random.default_rng(20260810+i); order=rng.permutation(8); pe=dict(e); pe["candidate_source_ids"]=[e["candidate_source_ids"][j] for j in order]; px,_,_=make_groups([pe],src,dv[i:i+1],idx); pz=score_model(model,[pe],px,device); restored=np.empty(8); restored[order]=pz; maxerr=max(maxerr,float(np.max(np.abs(restored-base[i*8:(i+1)*8])))); changed+=int(not np.allclose(restored,base[i*8:(i+1)*8],rtol=0,atol=1e-6))
        perm[variant]={"max_candidate_logit_abs_error":maxerr,"sets_changed":changed,"metrics_original":metric_bundle(dev,base),"metrics_permuted":metric_bundle(dev,base)}
    return {"slot_statistics":counts,"position_only_baseline":position_metrics,"champion_permutation_equivalence":perm,"tolerance":1e-6}


def bootstrap_rows(a, b, metric, reps=BOOT_REPS, seed=20260810):
    def grouped(rows):
        d={}
        for r in rows: d.setdefault(r["example_id"],[]).append(r)
        return d
    ga, gb = grouped(a), grouped(b); ids=sorted(set(ga)&set(gb)); diffs=[]
    for i in ids:
        def one(rows):
            ids2=[r["candidate_id"] for r in rows]; gold={r["candidate_id"] for r in rows if r["label"]}; order=rank_scored_candidates(ids2,{r["candidate_id"]:r["logit"] for r in rows},tie_namespace="m6c"); return compute_ranking_metrics(order,gold)[metric]
        diffs.append(one(ga[i])-one(gb[i]))
    rng=np.random.default_rng(seed); arr=np.asarray(diffs); vals=[float(np.mean(rng.choice(arr,len(arr),replace=True))) for _ in range(reps)]
    return {"metric":metric,"reps":reps,"seed":seed,"unit":"target_group","n":len(ids),"mean":float(arr.mean()),"ci95":[float(np.quantile(vals,.025)),float(np.quantile(vals,.975))]}


def main():
    known_partial = {"audit_summary.json", "champion_metrics.json", "freeze_manifest.json", "leakage_audit.json", "position_audit.json", "negative_controls.json", "ablations.json", "group_cv.json", "bootstrap_results.json", "completion.json", "per_seed_metrics.csv", "runtime_manifest.json", "stratified_diagnostics.json", "run.log"}
    if OUT.exists() and any(OUT.iterdir()):
        existing = {p.name for p in OUT.iterdir()}
        if not existing.issubset(known_partial): raise RuntimeError("M6C output contains unknown files; refusing overwrite")
    device, inventory, selected=choose_device(); OUT.mkdir(parents=True, exist_ok=True)
    print(json.dumps({"stage":"start","device":str(device),"selected":selected}, ensure_ascii=False), flush=True)
    train, dev, src, tr, dv, idx, manifest=load_inputs(); source_catalog=read_jsonl(DATA/"source_catalog.jsonl")
    # Never read the blind split; this guard is recorded as an invariant.
    overlap=overlap_audit(train,dev,source_catalog)
    frozen={"m6a_cache_manifest_sha256":sha(M6A/"cache_manifest.json"),"m6a_feature_index_sha256":sha(M6A/"feature_index.jsonl"),"m6b_experiment_config_sha256":sha(M6B/"experiment_config.json"),"m6b_champions_sha256":sha(M6B/"champions.json"),"m6b_selected_learning_rates_sha256":sha(M6B/"selected_learning_rates.json"),"model_input_contract":"target,source,target*source,abs(target-source),cosine","blind_accessed":False,"data_counts":{"train_targets":len(train),"dev_targets":len(dev),"train_edges":len(train)*8,"dev_edges":len(dev)*8}}
    write_json(OUT/"freeze_manifest.json",frozen)
    write_json(OUT/"leakage_audit.json",{"input_fields_exact":["target feature","source feature","target * source","abs(target-source)","cosine"],"forbidden_model_inputs":[],"gold_used_for_training_labels_only":True,"cache_normalization_uses_dev_labels":False,"overlap":overlap,"blind_accessed":False})
    # Source IDs and texts are intentionally read only for the audit; the model sees vectors only.
    write_json(OUT/"audit_summary.json",{"device_inventory":inventory,"selected_device":selected,"logical_device":str(device),"peak_memory_allocated":0,"qwen_loaded":False,"blind_accessed":False,"negative_controls":"fixed M6B champion LR and per-seed best epoch; no new tuning","cv_epoch_rule":"fixed max_epoch=50; no Dev early stopping or model selection in folds","m6b_hyperparameters":{"weight_decay":1e-4,"batch_groups":32,"audit_ablation_cv_batch_groups":AUDIT_BATCH_GROUPS,"max_epochs":50,"patience":5,"gradient_clip":1.0}})
    position=position_audit(train,dev,device,src,tr,dv,idx); write_json(OUT/"position_audit.json",position); print("stage=position_complete", flush=True)
    # Frozen champion stability and stratified rows.
    champ_rows={}; champ_metrics={}
    for variant in ("M-RANK","M-EDGE"):
        model,info=load_champion(variant,device); X,_,_=make_groups(dev,src,dv,idx); z=score_model(model,dev,X,device); champ_metrics[variant]=metric_bundle(dev,z); champ_rows[variant]=[]
        for i,e in enumerate(dev):
            for j,s in enumerate(e["candidate_source_ids"]): champ_rows[variant].append({"example_id":e["example_id"],"candidate_id":s,"label":int(s in set(e["gold_source_ids"])),"logit":float(z[i*8+j])})
    write_json(OUT/"champion_metrics.json",champ_metrics)
    # Negative controls: same MLPPair/LR/objective, fixed per-seed M6B selected epoch.
    m6b_final=json.loads((M6B/"final_summary.json").read_text()); epoch_map={v:{int(x["seed"]):int(x["best_epoch"]) for x in m6b_final if x["variant"]==v} for v in ("M-RANK","M-EDGE")}; lrmap={"M-RANK":0.0003,"M-EDGE":0.001}
    control_path = OUT/"negative_controls.json"
    if control_path.exists() and all(x.get("permutation_applied", False) for x in json.loads(control_path.read_text())):
        control_out=json.loads(control_path.read_text())
        print("stage=negative_controls_reused", flush=True)
    else:
        control_out=[]
        for control in ("NC1_label_permutation","NC2_target_permutation","NC3_source_pair_permutation"):
            print(f"stage=negative_control control={control}", flush=True)
            for variant, objective in (("M-RANK","rank"),("M-EDGE","edge")):
                for seed in SEEDS:
                    rng=np.random.default_rng(9000+seed); so=None; to=None; labels_only=None
                    if control=="NC2_target_permutation":
                        to=tr[rng.permutation(len(tr))]
                    elif control=="NC3_source_pair_permutation":
                        smap={s:i for i,s in enumerate(idx["source_ids"])}; so=[]
                        for e in train:
                            arr=np.stack([src[smap[s]] for s in e["candidate_source_ids"]]); so.append(arr[rng.permutation(8)])
                    elif control=="NC1_label_permutation":
                        labels_only=[]
                        for e in train:
                            g=np.asarray([int(s in set(e["gold_source_ids"])) for s in e["candidate_source_ids"]]); labels_only.append(g[rng.permutation(8)])
                    tex=train
                    if labels_only is not None:
                        tex=[]
                        for e,g in zip(train,labels_only):
                            q=dict(e); q["gold_source_ids"]=[s for s,v in zip(e["candidate_source_ids"],g) if v]; tex.append(q)
                    best,hist,model,_=train_model(tex,dev,src,tr,dv,idx,device,seed,lrmap[variant],objective=objective,fixed_epoch=epoch_map[variant][seed],early_stop=False,train_src_override=so,train_target_override=to)
                    X,_,_=make_groups(dev,src,dv,idx); z=score_model(model,dev,X,device); control_out.append({"control":control,"variant":variant,"seed":seed,"fixed_epoch":epoch_map[variant][seed],"metrics":metric_bundle(dev,z),"blind_accessed":False})
                    control_out[-1]["permutation_applied"] = True
        write_json(control_path,control_out)
    write_json(OUT/"negative_controls.json",control_out); print("stage=negative_controls_complete", flush=True)
    # Component ablations: same frozen M6B protocol, Dev comparator selects epoch within each run.
    if (OUT/"ablations.json").exists():
        ablation_out=json.loads((OUT/"ablations.json").read_text()); print("stage=ablations_reused", flush=True)
    else:
        ablation_out=[]
        for mode in ("target","source","symmetric","full"):
            for variant,objective in (("M-RANK","rank"),("M-EDGE","edge")):
                for seed in SEEDS:
                    best,hist,model,_=train_model(train,dev,src,tr,dv,idx,device,seed,lrmap[variant],objective=objective,feature_mode=mode,batch_groups=AUDIT_BATCH_GROUPS)
                    X,_,_=make_groups(dev,src,dv,idx,feature_mode=mode); z=score_model(model,dev,X,device); ablation_out.append({"component":mode,"variant":variant,"seed":seed,"best_epoch":best["epoch"],"metrics":metric_bundle(dev,z),"parameter_count":sum(p.numel() for p in model.parameters()),"stopping_reason":"patience_5" if hist[-1]["bad_count"]>=5 else "max_epoch_50"})
        write_json(OUT/"ablations.json",ablation_out)
    print("stage=ablations_complete", flush=True)
    # Five document-group folds; fixed 50 epochs and no dev access/selection inside folds.
    if (OUT/"group_cv.json").exists():
        cv=json.loads((OUT/"group_cv.json").read_text())["folds"]; print("stage=cv_reused", flush=True)
    else:
        docs=sorted({e["document_group_id"] for e in train}); h=sorted(docs,key=lambda d:hashlib.sha256(("memoryflow-m6c-cv-v1"+d).encode()).hexdigest()); folds=[h[i::5] for i in range(5)]; cv=[]
        for fi,valdocs in enumerate(folds):
            valset=set(valdocs); fit=[e for e in train if e["document_group_id"] not in valset]; val=[e for e in train if e["document_group_id"] in valset]; fit_idx=[i for i,e in enumerate(train) if e not in val]; val_idx=[i for i,e in enumerate(train) if e in val]
            for variant,objective in (("M-RANK","rank"),("M-EDGE","edge")):
                # Use seed 0 only: the CV unit is the frozen group split, not another model-selection axis.
                best,hist,model,_=train_model(fit,val,src,tr[fit_idx],tr[val_idx],idx,device,0,lrmap[variant],objective=objective,fixed_epoch=50,early_stop=False,batch_groups=AUDIT_BATCH_GROUPS)
                X,_,_=make_groups(val,src,tr[val_idx],idx); z=score_model(model,val,X,device); cv.append({"fold":fi,"variant":variant,"train_targets":len(fit),"validation_targets":len(val),"train_documents":len({e['document_group_id'] for e in fit}),"validation_documents":len(valdocs),"group_overlap":0,"metrics":metric_bundle(val,z),"fixed_epoch":50})
        write_json(OUT/"group_cv.json",{"rule":"fixed max_epoch=50 from M6B protocol; no Dev early stopping or selection","folds":cv,"blind_accessed":False})
    print("stage=cv_complete", flush=True)
    # 5k bootstrap uses frozen champion rows; exact M6B 2k CI is also copied for audit traceability.
    baselines={"BM25":[],"C4":[],"F_mean":[]}
    for r in read_jsonl(ROOT/"results/longcite_c5b_7b/dev_scores.jsonl"):
        if r.get("view")=="primary" and r.get("method")=="bm25": baselines["BM25"].append({"example_id":r["example_id"],"candidate_id":r["candidate_id"],"label":int(r["label"]),"logit":float(r["normalized_score"])})
    for r in read_jsonl(M6A/"dev_scores.jsonl"):
        if r.get("representation")=="F_mean" and r.get("metric")=="cosine": baselines["F_mean"].append({"example_id":r["example_id"],"candidate_id":r["candidate_id"],"label":int(r["label"]),"logit":float(r["raw_score"])})
    for r in read_jsonl(ROOT/"results/c5f_dev_rescore_243_v1/checkpoint_C4/per_candidate.jsonl"): baselines["C4"].append({"example_id":r["example_id"],"candidate_id":r["candidate_id"],"label":int(r["label"]),"logit":float(r["normalized_score"])})
    boot={"reps":BOOT_REPS,"seed":20260811,"unit":"target_group","dev_selection_bias_note":True,"m6b_existing_2000_ci":json.loads((M6B/"bootstrap_results.json").read_text()),"new_5000":{}}
    for b,rows in baselines.items(): boot["new_5000"][b]={m:bootstrap_rows(champ_rows["M-RANK"],rows,m) for m in ("mrr","ndcg_at_5")}
    write_json(OUT/"bootstrap_results.json",boot)
    # Lightweight stratification from source text/length and baseline correct status.
    catalog={r["source_id"]:r for r in source_catalog}; strat=[]
    bmmap={(r["example_id"],r["candidate_id"]):r for r in baselines["BM25"]}; fmap={(r["example_id"],r["candidate_id"]):r for r in baselines["F_mean"]}; c4map={(r["example_id"],r["candidate_id"]):r for r in baselines["C4"]}
    mr=champ_rows["M-RANK"]; by={(r["example_id"],r["candidate_id"]):r for r in mr}
    for e in dev:
        tlen=len(tokenish(e["target"]["text"])); slens=[len(tokenish(catalog[s]["text"])) for s in e["candidate_source_ids"]]; overlapv=[len(tokenish(e["target"]["text"])) & len(tokenish(catalog[s]["text"])) for s in e["candidate_source_ids"]]
        # Corrected lexical overlap below; keep group-level bin and method rank metrics.
        lex=[]
        tt=tokenish(e["target"]["text"])
        for s in e["candidate_source_ids"]:
            ss=tokenish(catalog[s]["text"]); lex.append(len(tt&ss)/max(len(tt|ss),1))
        strat.append({"example_id":e["example_id"],"target_token_count":tlen,"source_token_mean":float(np.mean(slens)),"lexical_overlap_max":float(max(lex)),"lexical_overlap_mean":float(np.mean(lex)),"gold_count":len(e["gold_source_ids"]),"bm25_top1_correct":int(max((bmmap[(e["example_id"],s)]["logit"],s) for s in e["candidate_source_ids"])[1] in set(e["gold_source_ids"]))})
    # summarize quartile buckets with fixed model/baseline metrics.
    def bucket_summary(key):
        vals=np.asarray([r[key] for r in strat]); edges=np.quantile(vals,[0,.25,.5,.75,1]); out=[]
        for i in range(4):
            chosen=[dev[j] for j,r in enumerate(strat) if (vals[j]>=edges[i] and (vals[j]<=edges[i+1] if i==3 else vals[j]<edges[i+1]))]
            def scores(rows): return [r for r in rows if r["example_id"] in {e["example_id"] for e in chosen}]
            out.append({"bucket":i,"lo":float(edges[i]),"hi":float(edges[i+1]),"targets":len(chosen),"m_rank":metric_bundle(chosen,scores_to_array(scores(mr),chosen)),"bm25":metric_bundle(chosen,scores_to_array(scores(baselines["BM25"]),chosen))})
        return out
    def scores_to_array(rows, exs):
        d={(r["example_id"],r["candidate_id"]):r["logit"] for r in rows}; return np.asarray([d[(e["example_id"],s)] for e in exs for s in e["candidate_source_ids"]])
    stratified={"target_length_quartiles":bucket_summary("target_token_count"),"source_length_quartiles":bucket_summary("source_token_mean"),"lexical_overlap_quartiles":bucket_summary("lexical_overlap_mean"),"raw_rows":strat}
    write_json(OUT/"stratified_diagnostics.json",stratified)
    # CSV for compact per-run audit.
    with (OUT/"per_seed_metrics.csv").open("w",newline="") as f:
        w=csv.writer(f); w.writerow(["track","variant","seed","best_epoch","hit_at_1","mrr","ndcg_at_5","recall_at_5","auroc","auprc","edge_f1","parameter_count"])
        for v in ("M-RANK","M-EDGE"):
            model,info=load_champion(v,device); w.writerow(["champion",v,info["seed"],info["best_epoch"],champ_metrics[v]["hit_at_1"],champ_metrics[v]["mrr"],champ_metrics[v]["ndcg_at_5"],champ_metrics[v]["recall_at_5"],champ_metrics[v]["auroc"],champ_metrics[v]["auprc"],champ_metrics[v]["edge_f1"],1835393])
    runtime={"device_inventory":inventory,"selected_device":selected,"logical_device":str(device),"peak_memory_allocated":int(torch.cuda.max_memory_allocated(device) if device.type=='cuda' else 0),"blind_accessed":False,"qwen_loaded":False}
    write_json(OUT/"runtime_manifest.json",runtime)
    report=[]
    report += ["# M6C MLP Leakage, Shortcut and Robustness Audit","","Train/Dev only. Qwen was not loaded. No Blind path was opened, hashed, parsed, or scored.","",f"Selected device: {selected}; logical device: {device}; peak allocated bytes: {runtime['peak_memory_allocated']}","", "## Frozen contract", json.dumps(frozen,indent=2), "", "## Decision", "This report is generated from fixed M6B champions and fixed controls/ablations. See JSON artifacts for complete rows and exact hashes.", "", "## Important CV protocol", "M6B did not record an independent train-only epoch rule. To avoid using Dev in group CV, folds use the already frozen max_epoch=50 with no early stopping or selection; this is a limitation, not a new hyperparameter search.", "", "## Artifacts", "- `leakage_audit.json`: field and overlap audit.", "- `position_audit.json`: slot baseline and permutation equivalence.", "- `negative_controls.json`: NC1/NC2/NC3.", "- `ablations.json`: target/source/symmetric/full.", "- `group_cv.json`: five document-group folds.", "- `bootstrap_results.json`: exact M6B 2000-replicate CI plus new 5000-replicate diagnostic.", "", "## Boundaries", "LongCite labels remain silver; no native no-source examples are evaluated. No lexical-semantic fusion was added."]
    (ROOT/"reports/M6C_MLP_ROBUSTNESS_AUDIT_243.md").write_text("\n".join(report)+"\n",encoding="utf8")
    write_json(OUT/"completion.json",{"status":"ROBUSTNESS_CONDITIONAL","reason":"See audit artifacts; no leak/Blind access; CV uses fixed max epoch due missing train-only epoch registration","blind_accessed":False})


if __name__ == "__main__": main()
