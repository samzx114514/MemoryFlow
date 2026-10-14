#!/usr/bin/env python3
"""LC-Sent-15-Q2 frozen 3-head x 3-loss x 3-seed comparison."""
from __future__ import annotations
import argparse, hashlib, json, os, random, subprocess, sys, time
from pathlib import Path
import numpy as np
import torch
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'src'),str(ROOT/'scripts')]
from memoryflow.lc_sent15_q2 import HEADS, LOSSES, EXPECTED_PARAMETERS, grouped_loss, make_head, validate_heads
from run_lc_sent15_q1_rsym_transfer import (BM25,DATA,EXPECTED_CACHES,GROUP_BATCH,LR,Q0,SEEDS,WEIGHT_DECAY,aggregate,bootstrap_seed_first,listwise_eval_loss,load_split,model_logits,scores_and_targets,sha,tensors,unpack_features,validate_inputs)
Q1C=ROOT/'results/lc_sent15_v1_q1c_rsym_convergence_v1'; OUT=ROOT/'results/lc_sent15_v1_q2_head_loss_v1'; PATIENCE=5; EPOCHS=100; CLIP=1.; BOOT_SEED=20260815; REPS=10000

def dump(p,x):
 p.parent.mkdir(parents=True,exist_ok=True);t=p.with_suffix(p.suffix+'.tmp');t.write_text(json.dumps(x,ensure_ascii=False,indent=2,sort_keys=True,allow_nan=False)+'\n');os.replace(t,p)
def jsonl(p,rows):
 t=p.with_suffix(p.suffix+'.tmp');
 with t.open('w',encoding='utf8') as f:
  for r in rows:f.write(json.dumps(r,ensure_ascii=False,sort_keys=True,allow_nan=False)+'\n')
 os.replace(t,p)
def seed_all(s): random.seed(s);np.random.seed(s);torch.manual_seed(s);torch.cuda.manual_seed_all(s)
def key(m,e):return (-m['overall']['hit_at_1'],-m['overall']['mrr'],-m['overall']['ndcg_at_5'],m['ranking_loss'],e)
def device():
 lines=subprocess.check_output(['nvidia-smi','--query-gpu=index,memory.free','--format=csv,noheader,nounits'],text=True).splitlines();safe=[(int(a.strip()),int(b.strip())) for a,b in (x.split(',') for x in lines) if int(b.strip())>=8192]
 if not safe: raise RuntimeError('NO_SAFE_GPU')
 return torch.device(f"cuda:{max(safe,key=lambda x:(x[1],-x[0]))[0]}")
def run_dir(h,l,s):return OUT/'runs'/h/l/f'seed_{s}'
def files_ok(d):
 if not (d/'COMPLETED').is_file() or not (d/'integrity.json').is_file():return False
 i=json.loads((d/'integrity.json').read_text());return all(sha(d/n)==v for n,v in i['files'].items())
def prepare():
 if OUT.exists():
  allowed={'q2_frozen_config.json','input_manifest.json','runs','logs','metrics_by_run.json','predictions_dev.jsonl','bootstrap_main.json','Q2_REPORT.md','Q2_INTEGRITY.json','checksums.sha256','COMPLETED'}
  extra={x.name for x in OUT.iterdir()}-allowed
  if extra:raise RuntimeError('CONFLICT '+str(sorted(extra)))
 else:OUT.mkdir(parents=True)
 validate_inputs();validate_heads()
 if sha(Q1C/'Q1C_INTEGRITY.json')!='dd0070676c296df85cf50142cf2b5522b4afc876a8ff6a140edb57d24698252b':raise RuntimeError('Q1C integrity SHA mismatch')
 cfg={'checkpoint':'LC-Sent-15-Q2','before_metrics':True,'heads':{'H1_LINEAR_FULL':{'input':'[t;s;t*s;abs(t-s);cosine]','params':14338},'H2_R_SYM_128':{'input':'[t*s;abs(t-s);cosine]','params':917889},'H3_D_FULL_64':{'input':'[t;s;t*s;abs(t-s);cosine]','params':917697}},'losses':{'L1_LISTWISE_CE':'-log_softmax(score_group)[positive]','L2_PAIRWISE_SOFTPLUS':'mean_neg softplus(negative-positive)','L3_BALANCED_POINTWISE_BCE':'0.5*softplus(-positive)+0.5*mean_neg softplus(negative)'},'seeds':list(SEEDS),'optimizer':'AdamW','lr':LR,'weight_decay':WEIGHT_DECAY,'groups_per_batch':GROUP_BATCH,'max_epoch':EPOCHS,'patience':PATIENCE,'gradient_clip_norm':CLIP,'selection':'Dev Hit@1 desc, MRR desc, nDCG@5 desc, cell loss asc, earlier epoch','bootstrap':{'seed':BOOT_SEED,'reps':REPS,'unit':'target','seed_first_metrics':True},'prohibitions':{'qwen':True,'blind':True,'reserve':True,'multi_positive':True,'mixed_catalog':True,'bm25_input':True,'new_hyperparameters':True}}
 inp=validate_inputs()|{'q1c_integrity':sha(Q1C/'Q1C_INTEGRITY.json'),'feature_caches':EXPECTED_CACHES}
 for n,x in [('q2_frozen_config.json',cfg),('input_manifest.json',inp)]:
  p=OUT/n
  if p.exists() and json.loads(p.read_text())!=x:raise RuntimeError('CONFLICT '+n)
  if not p.exists():dump(p,x)
def run_one(head,loss,seed,dev):
 d=run_dir(head,loss,seed)
 if files_ok(d):return
 if d.exists():raise RuntimeError('incomplete run conflict '+str(d))
 # Preserve the failed first-attempt staging directory for audit; never reuse it.
 work=d.with_name('.'+d.name+'.tmp-retry1');work.mkdir(parents=True)
 train,tc,tp=load_split('train');dv,dc,dp=load_split('dev');ttm,tsm=unpack_features(train,tc,tp);dtm,dsm=unpack_features(dv,dc,dp);tt,ts,ty,tg=tensors(train,ttm,tsm,dev);dt,ds,_,_=tensors(dv,dtm,dsm,dev)
 seed_all(seed);m=make_head(head).to(dev).float();opt=torch.optim.AdamW(m.parameters(),lr=LR,weight_decay=WEIGHT_DECAY);best=None;bad=0;hist=[];started=time.time()
 for epoch in range(1,EPOCHS+1):
  m.train();losses=[];order=np.random.default_rng(seed+1000+epoch).permutation(len(train))
  for start in range(0,len(train),GROUP_BATCH):
   take=order[start:start+GROUP_BATCH];mask=torch.zeros(len(ty),dtype=torch.bool,device=dev)
   for g in take:mask|=tg==int(g)
   opt.zero_grad(set_to_none=True);v=grouped_loss(loss,m(tt[mask],ts[mask]),ty[mask].bool(),tg[mask]);
   if not torch.isfinite(v):raise RuntimeError('nonfinite loss')
   v.backward();grad=float(torch.nn.utils.clip_grad_norm_(m.parameters(),CLIP));opt.step();losses.append(float(v.detach().cpu()))
  m.eval()
  with torch.inference_mode():a=m(tt,ts).cpu().numpy();b=m(dt,ds).cpu().numpy()
  if not(np.isfinite(a).all() and np.isfinite(b).all()):raise RuntimeError('nonfinite logits')
  _,tr=scores_and_targets(train,a,'train',seed);_,dr=scores_and_targets(dv,b,'dev',seed);tm,dm=aggregate(tr),aggregate(dr);tm['ranking_loss']=listwise_eval_loss(a,train);dm['ranking_loss']=listwise_eval_loss(b,dv)
  # The stored loss must be the cell's own objective, not listwise loss.
  with torch.inference_mode(): dm['cell_loss']=float(grouped_loss(loss,torch.from_numpy(b),torch.from_numpy(np.asarray([c['label'] for e in dv for c in e['candidates']],np.float32)).bool(),torch.arange(len(dv)).repeat_interleave(15)))
  k=key({**dm,'ranking_loss':dm['cell_loss']},epoch);im=best is None or k<tuple(best['key']);bad=0 if im else bad+1
  hist.append({'epoch':epoch,'train_loss':float(np.mean(losses)),'grad_norm_preclip':grad,'train':tm,'dev':dm,'improved':im,'bad_count':bad})
  if im:best={'epoch':epoch,'key':list(k),'state':{n:x.detach().cpu() for n,x in m.state_dict().items()},'train':tm,'dev':dm}
  if bad>=PATIENCE:break
 assert best is not None
 torch.save(best.pop('state'),work/'best.pt');torch.save(opt.state_dict(),work/'terminal_optimizer.pt');torch.save({'torch_cpu':torch.get_rng_state().cpu(),'torch_cuda':torch.cuda.get_rng_state(dev).cpu()},work/'terminal_rng.pt')
 restored=make_head(head).to(dev).float();restored.load_state_dict(torch.load(work/'best.pt',map_location=dev,weights_only=True));restored.eval()
 with torch.inference_mode():a=restored(tt,ts).cpu().numpy();b=restored(dt,ds).cpu().numpy()
 trp,tr=scores_and_targets(train,a,'train',seed);dvp,dr=scores_and_targets(dv,b,'dev',seed);tm,dm=aggregate(tr),aggregate(dr);tm['ranking_loss']=listwise_eval_loss(a,train);dm['ranking_loss']=listwise_eval_loss(b,dv)
 cfg={'head':head,'loss':loss,'seed':seed,'params':EXPECTED_PARAMETERS[head],'lr':LR,'weight_decay':WEIGHT_DECAY,'groups_per_batch':GROUP_BATCH,'max_epoch':EPOCHS,'patience':PATIENCE,'selection':'Hit@1/MRR/nDCG@5/cell-loss/earlier','device':str(dev),'no_qwen':True,'no_blind':True,'no_bm25_input':True}
 best.update({'best_checkpoint_metrics_after_reload':{'train':tm,'dev':dm},'terminal_epoch':hist[-1]['epoch'],'post_peak_bad_count':bad,'terminal_reason':'patience_5' if bad>=PATIENCE else 'CENSORED_AT_100','runtime_seconds':time.time()-started,'peak_gpu_bytes':int(torch.cuda.max_memory_allocated(dev))})
 dump(work/'config.json',cfg);dump(work/'history.json',hist);dump(work/'best.json',best);jsonl(work/'train_predictions.jsonl',trp);jsonl(work/'dev_predictions.jsonl',dvp);dump(work/'train_targets.json',tr);dump(work/'dev_targets.json',dr)
 fs={p.name:sha(p) for p in work.iterdir() if p.is_file()};dump(work/'integrity.json',{'files':fs,'input_manifest_sha256':sha(OUT/'input_manifest.json'),'frozen_config_sha256':sha(OUT/'q2_frozen_config.json')});(work/'COMPLETED').write_text('completed\n');os.replace(work,d)
def pair_boot(a,b,indices):
 # seed x target ranks, exactly seed-first scalar metrics.
 out={}
 for name,fun in {'hit_at_1':lambda x:x==1,'mrr':lambda x:1/x,'ndcg_at_5':lambda x:np.where(x<=5,1/np.log2(x+1),0)}.items():
  av,bv=fun(a.astype(float)),fun(b.astype(float));d=av[:,indices].mean(2).mean(0)-bv[:,indices].mean(2).mean(0);out[name]={'delta':float(av.mean(1).mean()-bv.mean(1).mean()),'ci95':[float(np.quantile(d,.025)),float(np.quantile(d,.975))]}
 return out
def finalise():
 if (OUT/'COMPLETED').exists():return
 allruns=[];bycell={}
 for h in HEADS:
  for l in LOSSES:
   rows=[]
   for s in SEEDS:
    d=run_dir(h,l,s)
    if not files_ok(d):raise RuntimeError('incomplete '+str(d))
    b=json.loads((d/'best.json').read_text());rows.append({'head':h,'loss':l,'seed':s,'best_epoch':b['epoch'],'terminal_epoch':b['terminal_epoch'],'terminal_reason':b['terminal_reason'],'params':EXPECTED_PARAMETERS[h],'runtime_seconds':b['runtime_seconds'],'peak_gpu_bytes':b['peak_gpu_bytes'],'train':b['best_checkpoint_metrics_after_reload']['train'],'dev':b['best_checkpoint_metrics_after_reload']['dev'],'checkpoint_sha256':sha(d/'best.pt')})
   bycell[(h,l)]=rows;allruns+=rows
 means=[]
 for (h,l),rows in bycell.items():
  devm={m:float(np.mean([r['dev']['overall'][m] for r in rows])) for m in ('hit_at_1','mrr','ndcg_at_5','mean_gold_rank')};means.append({'head':h,'loss':l,'params':EXPECTED_PARAMETERS[h],'dev':devm})
 winner=sorted(means,key=lambda r:(-r['dev']['hit_at_1'],-r['dev']['mrr'],-r['dev']['ndcg_at_5'],r['params'],r['head']+'_'+r['loss']))[0]
 idx=np.load(Q0/'bootstrap_indices.npy');rank={}
 for c in bycell:
  rank[c]=np.asarray([[x['gold_rank'] for x in json.loads((run_dir(*c,s)/'dev_targets.json').read_text())] for s in SEEDS],dtype=np.int64)
 primary={}
 for name,a,b in [('H3L1_minus_H2L1',('H3_D_FULL_64','L1_LISTWISE_CE'),('H2_R_SYM_128','L1_LISTWISE_CE')),('H1L1_minus_H2L1',('H1_LINEAR_FULL','L1_LISTWISE_CE'),('H2_R_SYM_128','L1_LISTWISE_CE')),('H2L2_minus_H2L1',('H2_R_SYM_128','L2_PAIRWISE_SOFTPLUS'),('H2_R_SYM_128','L1_LISTWISE_CE')),('H2L3_minus_H2L1',('H2_R_SYM_128','L3_BALANCED_POINTWISE_BCE'),('H2_R_SYM_128','L1_LISTWISE_CE'))]:primary[name]=pair_boot(rank[a],rank[b],idx)
 q1=np.asarray([[x['gold_rank'] for x in json.loads((Q1C/f'runs/seed_{s}/best_dev_targets.json').read_text())] for s in SEEDS],dtype=np.int64);bm={x['example_id']:x for x in [json.loads(z) for z in (BM25/'bm25_legacy_dev_predictions.jsonl').read_text().splitlines() if z]};ids=[x['example_id'] for x in json.loads((run_dir(winner['head'],winner['loss'],0)/'dev_targets.json').read_text())];bmr=np.asarray([bm[x]['gold_rank'] for x in ids],dtype=np.int64)
 cand=rank[(winner['head'],winner['loss'])];compare={'candidate_minus_q1c':pair_boot(cand,q1,idx),'candidate_minus_bm25':bootstrap_seed_first(cand,bmr,idx)}
 gate=compare['candidate_minus_q1c']['hit_at_1'];status='Q2_DEV_IMPROVEMENT_PASS' if gate['delta']>0 and gate['ci95'][0]>0 and compare['candidate_minus_q1c']['mrr']['ci95'][0]>=0 and compare['candidate_minus_q1c']['ndcg_at_5']['ci95'][0]>=0 else 'Q2_DEV_IMPROVEMENT_CONDITIONAL' if gate['delta']>0 else 'Q2_DEV_NO_IMPROVEMENT'
 ninety='INTERPRETABLE_90_TARGET_REACHED' if winner['dev']['hit_at_1']>=.9 else 'INTERPRETABLE_90_TARGET_NOT_REACHED'
 dump(OUT/'metrics_by_run.json',{'runs':allruns,'cell_means':means,'winner':winner,'q2_status':status,'ninety_target':ninety});dump(OUT/'bootstrap_main.json',{'primary_contrasts':primary,'winner_comparisons':compare,'seed':BOOT_SEED,'reps':REPS,'indices_sha256':sha(Q0/'bootstrap_indices.npy')})
 jsonl(OUT/'predictions_dev.jsonl',[r for (h,l) in bycell for s in SEEDS for r in [json.loads(z) for z in (run_dir(h,l,s)/'dev_predictions.jsonl').read_text().splitlines() if z]])
 report=['# LC-Sent-15-Q2 Head x Loss','',f"Winner: `{winner['head']} x {winner['loss']}`.",f"Q2 Dev decision: `{status}`. 90%: `{ninety}`.",'', 'All 9 cells x 3 seeds ran under the frozen Q2 protocol. No Qwen, Blind, Reserve, multi-positive, mixed catalog, or BM25 training feature was used.']
 (OUT/'Q2_REPORT.md').write_text('\n'.join(report)+'\n')
 fs={str(p.relative_to(OUT)):sha(p) for p in OUT.rglob('*') if p.is_file() and p.name not in {'checksums.sha256','Q2_INTEGRITY.json','COMPLETED'}};(OUT/'checksums.sha256').write_text(''.join(f'{v}  {k}\n' for k,v in sorted(fs.items())))
 dump(OUT/'Q2_INTEGRITY.json',{'status':'PASS','files':fs,'frozen_config_sha256':sha(OUT/'q2_frozen_config.json'),'input_manifest_sha256':sha(OUT/'input_manifest.json'),'no_qwen':True,'no_blind':True,'no_reserve':True,'no_multi_positive':True,'no_mixed_catalog':True,'winner':winner,'decision':status});(OUT/'COMPLETED').write_text('MEMORYFLOW_LC_SENT15_Q2_HEAD_LOSS_COMPLETE\n')
def main():
 p=argparse.ArgumentParser();p.add_argument('mode',choices=('prepare','run','finalize'));a=p.parse_args();prepare()
 if a.mode=='prepare':return
 if a.mode=='run':
  d=device()
  for h in HEADS:
   for l in LOSSES:
    for s in SEEDS:run_one(h,l,s,d)
 else:finalise()
if __name__=='__main__':main()
