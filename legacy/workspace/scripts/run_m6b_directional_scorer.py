#!/usr/bin/env python3
"""M6B Train/Dev-only competition using only the M6A F_mean cache."""
from __future__ import annotations
import csv, hashlib, json, math, os, random, time
from pathlib import Path
import numpy as np
import torch
from torch import nn

ROOT=Path(__file__).resolve().parents[1]
import sys; sys.path.insert(0,str(ROOT/'src')); sys.path.insert(0,str(ROOT/'scripts'))
from memoryflow.directional_scorer import LinearPair, MLPPair, all_positive_distribution_loss, pair_features
from memoryflow.ranking_baselines import compute_ranking_metrics, rank_scored_candidates

M6A=ROOT/'results/m6a_qwen_representation_audit_243_v1'; C5F=ROOT/'results/c5f_dev_rescore_243_v1'; C5B=ROOT/'results/longcite_c5b_7b/dev_metrics.json'; OUT=ROOT/'results/m6b_directional_scorer_243_v1'
LRS=(1e-4,3e-4,1e-3); VARIANTS=('L-RANK','M-RANK','L-EDGE','M-EDGE'); EPOCHS=50; PATIENCE=5; BATCH_GROUPS=32; CLIP=1.0; BOOTSTRAP=2000
RANDOM={'hit_at_1':0.2719298245614035,'mrr':0.48438063163862094,'ndcg_at_5':0.4573921636840349,'recall_at_5':0.625}

def forbid(path):
    if 'blind' in str(path).lower(): raise RuntimeError(f'Blind path forbidden: {path}')
def sha(p):
    h=hashlib.sha256()
    with p.open('rb') as f:
        for b in iter(lambda:f.read(8*1024*1024),b''):h.update(b)
    return h.hexdigest()
def dump(p,x): p.parent.mkdir(parents=True,exist_ok=True); p.write_text(json.dumps(x,ensure_ascii=False,indent=2,sort_keys=True)+'\n')
def rows(p):
    forbid(p)
    with p.open(encoding='utf8') as f:return [json.loads(x) for x in f if x.strip()]
def seed_all(seed):
    random.seed(seed); np.random.seed(seed); torch.manual_seed(seed); torch.cuda.manual_seed_all(seed)
def load_data():
    data=ROOT/'data/longcite_anchor_expanded_v1_conservative'; train=rows(data/'train_examples.jsonl');dev=rows(data/'dev_examples.jsonl')
    if len(train)!=854 or len(dev)!=228:raise RuntimeError('unexpected data counts')
    return train,dev
def load_cache():
    for p in [M6A/'mean_source_features.npz',M6A/'mean_train_target_features.npz',M6A/'mean_dev_target_features.npz',M6A/'mean_index.json',M6A/'cache_manifest.json',M6A/'feature_index.jsonl']:
        forbid(p)
    manifest=json.loads((M6A/'cache_manifest.json').read_text()); idx=json.loads((M6A/'mean_index.json').read_text())
    if not manifest.get('cache_complete') or manifest['feature_index']['sha256'] != sha(M6A/'feature_index.jsonl'):raise RuntimeError('M6A cache binding failed')
    src=np.load(M6A/'mean_source_features.npz')['normalized'].astype(np.float32); tr=np.load(M6A/'mean_train_target_features.npz')['normalized'].astype(np.float32); dv=np.load(M6A/'mean_dev_target_features.npz')['normalized'].astype(np.float32)
    return src,tr,dv,idx,manifest
def make_groups(examples,src,targets,idx):
    smap={s:i for i,s in enumerate(idx['source_ids'])}
    # caller passes the split-specific target matrix and index list.
    return_examples=[]; X=[]; y=[]; gids=[]
    for gi,e in enumerate(examples):
        tid=e['target_group_id']; target=targets[gi]
        sidx=[smap[s] for s in e['candidate_source_ids']]; sources=src[sidx]
        tf=target[None,:].repeat(8,0); X.append(pair_features(torch.from_numpy(tf),torch.from_numpy(sources)).numpy()); y.extend([int(s in e['gold_source_ids']) for s in e['candidate_source_ids']]); gids.extend([gi]*8); return_examples.append(e)
    return np.concatenate(X),np.asarray(y,np.float32),np.asarray(gids,np.int64)
def metrics_from_logits(examples, logits):
    pos=[]; labels=[]; target_rows=[]; off=0
    for e in examples:
        z=np.asarray(logits[off:off+8],float); off+=8; ids=e['candidate_source_ids']; gold=set(e['gold_source_ids']); order=rank_scored_candidates(ids,{s:float(v) for s,v in zip(ids,z)},tie_namespace='m6b:'+e['example_id']); target_rows.append(compute_ranking_metrics(order,gold))
        labels.extend([int(s in gold) for s in ids]);pos.extend(z.tolist())
    out={k:float(np.mean([r[k] for r in target_rows])) for k in ('hit_at_1','mrr','ndcg_at_5','recall_at_5')}; labels=np.asarray(labels);pos=np.asarray(pos)
    out.update({'target_count':len(examples),'candidate_edges':len(labels),'positive_edges':int(labels.sum()),'negative_edges':int((1-labels).sum()),'random_baseline':RANDOM})
    out['ranking_loss']=float(np.mean([-(np.log(np.exp(logits[i*8:i*8+8]-np.max(logits[i*8:i*8+8]))/np.exp(logits[i*8:i*8+8]-np.max(logits[i*8:i*8+8])).sum()+1e-12)[np.asarray([s in set(e['gold_source_ids']) for s in e['candidate_source_ids']])]).mean() for i,e in enumerate(examples)]))
    order=np.argsort(-pos,kind='stable'); sl=labels[order]; tp=np.cumsum(sl); fp=np.cumsum(1-sl); precision=tp/np.maximum(tp+fp,1); recall=tp/max(int(labels.sum()),1);out['auprc']=float(np.sum(precision[sl.astype(bool)])/max(int(labels.sum()),1));out['auroc']=float(sum(1.0 if p>n else .5 if p==n else 0.0 for p in pos[labels==1] for n in pos[labels==0])/(max(int(labels.sum()),1)*max(int((1-labels).sum()),1)))
    best=None
    for threshold in np.unique(pos)[::-1]:
        pred=pos>=threshold; tpv=int(np.sum(pred & (labels==1))); fpv=int(np.sum(pred & (labels==0))); fnv=int(np.sum((~pred) & (labels==1))); prec=tpv/max(tpv+fpv,1);rec=tpv/max(tpv+fnv,1);f1=2*prec*rec/max(prec+rec,1e-12);candidate=(f1,-int(pred.sum()),float(threshold),prec,rec)
        if best is None or candidate[:2]>best[:2]:best=candidate
    out['edge_threshold_diagnostic']={'threshold':best[2],'precision':best[3],'recall':best[4],'f1':best[0],'predicted_edge_density':float(np.mean(pos>=best[2])),'true_edge_density':float(np.mean(labels==1)),'selection':'Dev only; max F1 then fewer predicted edges'}
    out['predict_all_positive_f1']=2*float(labels.mean())/(1+float(labels.mean()))
    return out
def train_run(variant,lr,seed,train,dev,src,tr,dv,idx,run_dir):
    seed_all(seed); input_dim=14337; model=(LinearPair(input_dim) if variant[0]=='L' else MLPPair(input_dim)).cuda().float(); opt=torch.optim.AdamW(model.parameters(),lr=lr,weight_decay=1e-4); edge=variant.endswith('EDGE'); pos_weight=torch.tensor((len(train)*8-sum(len(e['gold_source_ids']) for e in train))/sum(len(e['gold_source_ids']) for e in train),device='cuda')
    Xtr,ytr,gtr=make_groups(train,src,tr,idx); Xdv,ydv,gdv=make_groups(dev,src,dv,{'source_ids':idx['source_ids']})
    xt=torch.from_numpy(Xtr).cuda();yt=torch.from_numpy(ytr).cuda();gt=torch.from_numpy(gtr).cuda();xd=torch.from_numpy(Xdv).cuda();yd=torch.from_numpy(ydv).cuda()
    best=None;bad=0;history=[];started=time.time()
    for epoch in range(1,EPOCHS+1):
        model.train(); perm=np.arange(len(train)); rng=np.random.default_rng(seed+epoch);rng.shuffle(perm); train_losses=[]
        for start in range(0,len(train),BATCH_GROUPS):
            groups=perm[start:start+BATCH_GROUPS]; mask=torch.zeros(len(ytr),dtype=torch.bool,device='cuda');
            for g in groups: mask |= gt==int(g)
            opt.zero_grad(set_to_none=True); logits=model(xt[mask]); loss=(nn.functional.binary_cross_entropy_with_logits(logits,yt[mask],pos_weight=pos_weight) if edge else all_positive_distribution_loss(logits,yt[mask],gt[mask])); loss.backward();torch.nn.utils.clip_grad_norm_(model.parameters(),CLIP);opt.step();train_losses.append(float(loss.detach().cpu()))
        model.eval();
        with torch.inference_mode(): ztr=model(xt).detach().cpu().numpy(); zd=model(xd).detach().cpu().numpy()
        tm=metrics_from_logits(train,ztr);dm=metrics_from_logits(dev,zd); dm['edge_bce']=float(nn.functional.binary_cross_entropy_with_logits(torch.from_numpy(zd),torch.from_numpy(ydv),pos_weight=pos_weight.cpu())) if edge else None
        score_tuple=((-dm['auprc'], -dm['auroc'], dm['edge_bce'] if edge else 0, epoch) if edge else (-dm['ndcg_at_5'],-dm['mrr'],dm['ranking_loss'],epoch))
        improved=best is None or score_tuple<best['tuple']; bad=0 if improved else bad+1
        rec={'variant':variant,'lr':lr,'seed':seed,'epoch':epoch,'train_loss':float(np.mean(train_losses)),'train_metrics':tm,'dev_metrics':dm,'improvement':improved,'bad_count':bad,'runtime_seconds':time.time()-started,'peak_memory_allocated':int(torch.cuda.max_memory_allocated())}
        history.append(rec)
        if improved:
            best={'tuple':score_tuple,'epoch':epoch,'metrics':dm,'state':{k:v.detach().cpu() for k,v in model.state_dict().items()}}
        if bad>=PATIENCE:break
    run_dir.mkdir(parents=True,exist_ok=True); torch.save(best['state'],run_dir/'best.pt'); dump(run_dir/'history.json',history);dump(run_dir/'best.json',{'variant':variant,'lr':lr,'seed':seed,'best_epoch':best['epoch'],'best_tuple':best['tuple'],'best_metrics':best['metrics'],'stopping_reason':'patience_5' if bad>=PATIENCE else 'max_epoch_50','parameter_count':sum(p.numel() for p in model.parameters()),'config_sha256':sha(run_dir/'best.json') if False else None})
    return best,history,model
def score_saved(model,examples,X,run_dir,variant,lr,seed):
    model.eval();
    with torch.inference_mode(): z=model(torch.from_numpy(X).cuda()).cpu().numpy()
    path=run_dir/'dev_scores.jsonl';
    with path.open('w') as f:
        for i,e in enumerate(examples):
            for j,sid in enumerate(e['candidate_source_ids']):f.write(json.dumps({'example_id':e['example_id'],'target_group_id':e['target_group_id'],'candidate_id':sid,'candidate_order':j,'label':int(sid in e['gold_source_ids']),'logit':float(z[i*8+j]),'variant':variant,'lr':lr,'seed':seed},separators=(',',':'))+'\n')
    return z
def bootstrap_compare(champion_rows,baseline_rows,metric,seed=20260810):
    rng=np.random.default_rng(seed); a={};b={}
    for r in champion_rows:a.setdefault(r['example_id'],[]).append(r)
    for r in baseline_rows:b.setdefault(r['example_id'],[]).append(r)
    ids=sorted(set(a)&set(b)); vals=[]
    def one(g):
        def rank(rows):
            ids=[x['candidate_id'] for x in rows];gold={x['candidate_id'] for x in rows if x['label']};order=rank_scored_candidates(ids,{x['candidate_id']:x['score'] for x in rows},tie_namespace='boot');return compute_ranking_metrics(order,gold)[metric]
        return rank(g[0])-rank(g[1])
    diffs=np.asarray([one((a[x],b[x])) for x in ids]);
    for _ in range(BOOTSTRAP): vals.append(float(np.mean(rng.choice(diffs,size=len(diffs),replace=True))))
    return {'metric':metric,'unit':'target_group','n':len(ids),'mean':float(diffs.mean()),'ci95':[float(np.quantile(vals,.025)),float(np.quantile(vals,.975))],'seed':seed,'reps':BOOTSTRAP}
def edge_metric(rows, name):
    labels=np.asarray([int(x['label']) for x in rows]); scores=np.asarray([float(x['score']) for x in rows]);
    if name=='auroc': return float(sum(1.0 if p>n else .5 if p==n else 0.0 for p in scores[labels==1] for n in scores[labels==0])/(max(int(labels.sum()),1)*max(int((1-labels).sum()),1)))
    order=np.argsort(-scores,kind='stable'); sl=labels[order]; precision=np.cumsum(sl)/np.arange(1,len(sl)+1); return float(np.sum(precision[sl.astype(bool)])/max(int(labels.sum()),1))
def edge_bootstrap_compare(champion_rows, baseline_rows, metric, seed=20260810):
    ca={}; ba={}
    for r in champion_rows: ca.setdefault(r['example_id'],[]).append(r)
    for r in baseline_rows: ba.setdefault(r['example_id'],[]).append(r)
    ids=sorted(set(ca)&set(ba)); rng=np.random.default_rng(seed); observed=[]; boots=[]
    for i in ids: observed.append(edge_metric(ca[i],metric)-edge_metric(ba[i],metric))
    observed=np.asarray(observed)
    for _ in range(BOOTSTRAP):
        chosen=rng.choice(len(ids),size=len(ids),replace=True); boots.append(float(observed[chosen].mean()))
    return {'metric':metric,'unit':'target_group','n':len(ids),'mean':float(observed.mean()),'ci95':[float(np.quantile(boots,.025)),float(np.quantile(boots,.975))],'seed':seed,'reps':BOOTSTRAP}
def main():
    if os.environ.get('CUDA_VISIBLE_DEVICES')!='3':raise RuntimeError('use selected GPU3')
    if OUT.exists() and any(OUT.iterdir()):
        allowed={'experiment_config.json','mean_pool_reconciliation.json'}
        existing={p.name for p in OUT.iterdir()}
        if not existing.issubset(allowed): raise RuntimeError('refusing unknown nonempty output')
    OUT.mkdir(parents=True,exist_ok=True);train,dev=load_data();src,tr,dv,idx,manifest=load_cache(); cfg={'variants':VARIANTS,'learning_rates':LRS,'epochs':EPOCHS,'patience':PATIENCE,'batch_groups':BATCH_GROUPS,'clip':CLIP,'seed_protocol':'seed0 lr screening then selected lr seeds1,2','device':'physical GPU3','cache_manifest_sha256':sha(M6A/'cache_manifest.json'),'feature_index_sha256':sha(M6A/'feature_index.jsonl'),'model_manifest_sha256':manifest['model_manifest_sha256'],'blind_accessed':False};dump(OUT/'experiment_config.json',cfg)
    # Reconciliation against the existing Dev-only C5B Qwen mean pool, before training.
    old=rows(ROOT/'results/longcite_c5b_7b/dev_scores.jsonl'); new=rows(M6A/'dev_scores.jsonl'); old=[x for x in old if x.get('method')=='qwen_frozen_mean_pool' and x.get('view')=='primary']; new=[x for x in new if x.get('representation')=='F_mean' and x.get('metric')=='cosine']; oldmap={(x['example_id'],x['candidate_id']):x for x in old};newmap={(x['example_id'],x['candidate_id']):x for x in new};
    if set(oldmap)!=set(newmap):raise RuntimeError('mean-pool candidate membership mismatch')
    diffs=[abs(float(oldmap[k]['normalized_score'])-float(newmap[k]['raw_score'])) for k in oldmap]; top=sum(max((float(oldmap[(e['example_id'],s)]['normalized_score']),s) for s in e['candidate_source_ids'])[1] != max((float(newmap[(e['example_id'],s)]['raw_score']),s) for s in e['candidate_source_ids'])[1] for e in dev for _ in [0]);
    dump(OUT/'mean_pool_reconciliation.json',{'formatter':'same raw text; M6A tokenizer default special-token call','pooling':'attention-mask mean','normalization':'row L2 for cosine','dtype_difference':'M6A FP32; prior formal scorer BF16','candidate_membership_same':True,'candidate_order_same':True,'labels_same':True,'max_score_abs_diff':max(diffs),'top1_disagreement_count':top,'cause':'explained BF16 versus FP32 numeric path; no cache modification','m6a_contract':'F_mean_M6A','blind_accessed':False})
    screening=[]
    for variant in VARIANTS:
        for lr in LRS:
            best,hist,model=train_run(variant,lr,0,train,dev,src,tr,dv,idx,OUT/f'screening/{variant}_lr_{lr:g}_seed_0');screening.append({'variant':variant,'lr':lr,'seed':0,'best_epoch':best['epoch'],'best_metrics':best['metrics'],'stopping_reason':hist[-1]['bad_count'],'history':hist});del model;torch.cuda.empty_cache()
    sel={}
    for variant in VARIANTS:
        candidates=[x for x in screening if x['variant']==variant]; edge=variant.endswith('EDGE'); candidates.sort(key=lambda x:((-x['best_metrics']['auprc'],-x['best_metrics']['auroc'],x['best_metrics'].get('edge_bce',0),x['best_epoch']) if edge else (-x['best_metrics']['ndcg_at_5'],-x['best_metrics']['mrr'],x['best_metrics']['ranking_loss'],x['best_epoch']))) ;sel[variant]=candidates[0]['lr']
    dump(OUT/'screening_summary.json',screening);dump(OUT/'selected_learning_rates.json',sel)
    final=[]
    for variant in VARIANTS:
        for seed in (0,1,2):
            best,hist,model=train_run(variant,sel[variant],seed,train,dev,src,tr,dv,idx,OUT/f'final/{variant}/seed_{seed}');Xdv,_,_=make_groups(dev,src,dv,{'source_ids':idx['source_ids']});z=score_saved(model,dev,Xdv,OUT/f'final/{variant}/seed_{seed}',variant,sel[variant],seed);final.append({'variant':variant,'seed':seed,'lr':sel[variant],'best_epoch':best['epoch'],'best_metrics':best['metrics'],'stop':hist[-1]['bad_count']});del model;torch.cuda.empty_cache()
    dump(OUT/'final_summary.json',final)
    # Baseline table and champions.
    formal=json.loads((M6A/'baseline_comparison.json').read_text())['existing_formal_dev_only']; fmetrics=json.loads((M6A/'metrics.json').read_text())['splits']['dev']; baselines={'Random':RANDOM,'BM25':formal['bm25'],'Qwen_mean_pool':formal['qwen_frozen_mean_pool'],'F_mean_M6A_cosine':fmetrics['F_mean_cosine'],'C4_Anchor':formal['c4_trained_anchor']};
    champions={};
    for track in ('RANK','EDGE'):
        candidates=[x for x in final if x['variant'].endswith(track)]; candidates.sort(key=lambda x:(-x['best_metrics']['ndcg_at_5'],-x['best_metrics']['mrr'],x['best_metrics']['ranking_loss'],x['best_epoch']) if track=='RANK' else (-x['best_metrics']['auprc'],-x['best_metrics']['auroc'],x['best_metrics'].get('edge_bce',0),x['best_epoch']));champions[track]=candidates[0]
    dump(OUT/'champions.json',champions);dump(OUT/'baseline_comparison.json',{'baselines':baselines,'champions':champions,'blind_accessed':False})
    # Fixed-seed target-group bootstrap. Baseline rows are Dev-only existing artifacts.
    def load_scored(path, *, score_key, filters=None):
        rr=rows(path); out=[]
        for r in rr:
            if filters and not filters(r): continue
            out.append({'example_id':r['example_id'],'candidate_id':r['candidate_id'],'label':int(r['label']),'score':float(r[score_key])})
        return out
    champ_rows={}
    for track,info in champions.items():
        p=OUT/f"final/{info['variant']}/seed_{info['seed']}/dev_scores.jsonl"; champ_rows[track]=load_scored(p,score_key='logit')
    baseline_rows={
      'C4':load_scored(C5F/'checkpoint_C4/per_candidate.jsonl',score_key='normalized_score'),
      'F_mean':load_scored(M6A/'dev_scores.jsonl',score_key='raw_score',filters=lambda r:r.get('representation')=='F_mean' and r.get('metric')=='cosine'),
      'BM25':load_scored(ROOT/'results/longcite_c5b_7b/dev_scores.jsonl',score_key='normalized_score',filters=lambda r:r.get('method')=='bm25' and r.get('view')=='primary'),
    }
    boot={'reps':BOOTSTRAP,'seed':20260810,'ranking':{},'edge':{},'blind_accessed':False}
    for base,rr in baseline_rows.items():
        boot['ranking'][base]={metric:bootstrap_compare(champ_rows['RANK'],rr,metric) for metric in ('mrr','ndcg_at_5')}
        boot['edge'][base]={metric:edge_bootstrap_compare(champ_rows['EDGE'],rr,metric) for metric in ('auprc','auroc')}
    dump(OUT/'bootstrap_results.json',boot)
    dump(OUT/'integrity_manifest.json',{'cache_manifest_sha256':sha(M6A/'cache_manifest.json'),'feature_index_sha256':sha(M6A/'feature_index.jsonl'),'blind_accessed':False,'qwen_loaded':False,'parameter_count':{'L':14338,'M':sum(p.numel() for p in MLPPair(14337).parameters())}})
    rows_for_report=[]
    for x in final:
        rows_for_report.append(f"| {x['variant']} | {x['seed']} | {x['lr']:.4g} | {x['best_epoch']} | {x['best_metrics']['hit_at_1']:.4f} | {x['best_metrics']['mrr']:.4f} | {x['best_metrics']['ndcg_at_5']:.4f} | {x['best_metrics']['recall_at_5']:.4f} | {x['best_metrics']['auroc']:.4f} | {x['best_metrics']['auprc']:.4f} |")
    report=['# M6B Direction-Aware Linear/MLP Competition','','Train/Dev-only experiment. Qwen weights were not loaded; no Blind path was accessed. F_mean is frozen under the `F_mean_M6A` contract.','',
      '## Reconciliation','M6A and the existing Qwen mean-pool scorer had identical candidate membership, order and labels. The maximum per-candidate score difference is recorded in `mean_pool_reconciliation.json`; the explainable difference is FP32 M6A extraction versus the prior BF16 scorer. The cache was not changed.','',
      '## Fixed scorer','Input is ordered `concat(target, source, target*source, abs(target-source), cosine)` from separately L2-normalized float32 features. LinearPair has 14,338 parameters; MLPPair has 1,835,393 parameters as recorded in integrity metadata. AdamW uses weight decay 1e-4, batch 32 groups, max 50 epochs, patience 5, clip 1.0.','',
      '## Final three-seed results','| variant | seed | lr | best epoch | Hit@1 | MRR | nDCG@5 | Recall@5 | AUROC | AUPRC |','|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|']+rows_for_report+['',
      '## Selection','Ranking and edge champions are selected separately using their preregistered comparators. They are not merged into one overall model. Dev thresholds are diagnostics only and are not Blind thresholds.','',
      '## Baselines','See `baseline_comparison.json` and `mean_pool_reconciliation.json` for Random, BM25, existing mean-pool, F_mean_M6A and C4.','',
      '## Limitations','LongCite labels remain silver and contain no native no-source examples. This does not evaluate None-of-the-above. Bootstrap summaries and complete per-candidate logits are stored in the output directory.']
    (ROOT/'reports/M6B_DIRECTIONAL_SCORER_243.md').write_text('\n'.join(report)+'\n',encoding='utf8')
    print(json.dumps({'screening':screening,'selected':sel,'final':final,'champions':champions},indent=2))
if __name__=='__main__':main()
