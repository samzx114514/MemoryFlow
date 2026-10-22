#!/usr/bin/env python3
"""Q3: train-only OOF alpha discovery, then one frozen Dev fusion evaluation."""
from __future__ import annotations
import argparse, hashlib, json, os, random, subprocess, sys, time
from pathlib import Path
import numpy as np
import torch

ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'src'),str(ROOT/'scripts')]
from memoryflow.lc_sent15_q2 import DirectionalFull64, grouped_loss
from memoryflow.lc_sent15_q3 import ALPHAS, choose_alpha, fold_for_document, group_z, metric_from_ranks, ranks
from run_lc_sent15_q1_rsym_transfer import (BM25,DATA,EXPECTED_CACHES,GROUP_BATCH,LR,Q0,SEEDS,WEIGHT_DECAY,aggregate,load_split,sha,tensors,unpack_features,validate_inputs)

Q1C=ROOT/'results/lc_sent15_v1_q1c_rsym_convergence_v1';Q2=ROOT/'results/lc_sent15_v1_q2_head_loss_v1';Q2C=ROOT/'results/lc_sent15_v1_q2c_dfull128_capacity_v1';OUT=ROOT/'results/lc_sent15_v1_q3_oof_fusion_v1'
PATIENCE,EPOCHS,CLIP,BOOT_SEED,REPS=5,100,1.,20260815,10000

def dump(p,x):
 p.parent.mkdir(parents=True,exist_ok=True);t=p.with_suffix(p.suffix+'.tmp');t.write_text(json.dumps(x,ensure_ascii=False,indent=2,sort_keys=True,allow_nan=False)+'\n');os.replace(t,p)
def jsonl(p,rows):
 t=p.with_suffix(p.suffix+'.tmp')
 with t.open('w',encoding='utf8') as f:
  for r in rows:f.write(json.dumps(r,ensure_ascii=False,sort_keys=True,allow_nan=False)+'\n')
 os.replace(t,p)
def read_jsonl(p): return [json.loads(x) for x in p.read_text(encoding='utf8').splitlines() if x]
def seed_all(s):random.seed(s);np.random.seed(s);torch.manual_seed(s);torch.cuda.manual_seed_all(s)
def key(m,e):return(-m['overall']['hit_at_1'],-m['overall']['mrr'],-m['overall']['ndcg_at_5'],m['ranking_loss'],e)
def choose_device():
 snap=[]
 for x in subprocess.check_output(['nvidia-smi','--query-gpu=index,memory.free,memory.total','--format=csv,noheader,nounits'],text=True).splitlines():
  a,b,c=[int(z.strip()) for z in x.split(',')];snap.append({'physical_gpu':a,'free_mib':b,'total_mib':c})
 safe=[x for x in snap if x['free_mib']>=8192]
 if not safe:raise RuntimeError('NO_SAFE_GPU')
 s=max(safe,key=lambda x:(x['free_mib'],-x['physical_gpu']));return torch.device(f"cuda:{s['physical_gpu']}"),snap
def run_dir(seed,fold):return OUT/'oof_runs'/f'seed_{seed}'/f'fold_{fold}'
def files_ok(d):
 if not (d/'COMPLETED').is_file() or not(d/'integrity.json').is_file():return False
 x=json.loads((d/'integrity.json').read_text());return all(sha(d/n)==v for n,v in x['files'].items())
def pred_targets(examples,logits,seed,fold):
 rows=[];summary=[]
 for ix,row in enumerate(examples):
  ids=[c['source_id'] for c in row['candidates']];v=logits[ix*15:(ix+1)*15];gold=row['gold_source_ids'][0];rank,gr=ranks(ids,v,gold)
  summary.append({'example_id':row['example_id'],'document_id':row['document_id'],'language':row['language'],'gold_source_id':gold,'gold_rank':gr,'top1_source_id':rank[0],'ranking':rank,'top1_margin':float(v[ids.index(rank[0])]-v[ids.index(rank[1])])})
  for pos,c in enumerate(row['candidates']):rows.append({'seed':seed,'fold':fold,'example_id':row['example_id'],'document_id':row['document_id'],'language':row['language'],'candidate_id':c['source_id'],'candidate_position':pos,'label':int(c['label']),'raw_logit':float(v[pos]),'ranking_score':float(v[pos]),'rank':rank.index(c['source_id'])+1})
 return rows,summary
def eval_loss(logits,examples):
 vs=[]
 for i,row in enumerate(examples):
  x=logits[i*15:(i+1)*15];g=next(j for j,c in enumerate(row['candidates']) if c['label']);z=x-x.max();vs.append(float(-(z[g]-np.log(np.exp(z).sum()))))
 return float(np.mean(vs))
def validate_core():
 validate_inputs()
 for p,e in [(Q2/'Q2_INTEGRITY.json','45eeca3adf1572ee924c363ed0146a030e4afe587b63253fa47bfd4479bb9824'),(Q2C/'Q2C_INTEGRITY.json','293dbd60b3607579e22a846f9f3e6b0d8390e989f619b8779a431b86630a0f96'),(Q1C/'Q1C_INTEGRITY.json','dd0070676c296df85cf50142cf2b5522b4afc876a8ff6a140edb57d24698252b')]:
  if sha(p)!=e:raise RuntimeError('integrity SHA mismatch '+str(p))
def prepare():
 if OUT.exists():
  allowed={'q3_frozen_config.json','input_manifest.json','fold_manifest.json','gpu_snapshot.json','q3_oof.log','oof_runs','alpha_frozen.json','oof_predictions.jsonl','dev_predictions.jsonl','metrics.json','bootstrap.json','Q3_REPORT.md','Q3_INTEGRITY.json','checksums.sha256','COMPLETED'};extra={p.name for p in OUT.iterdir()}-allowed
  if extra:raise RuntimeError('CONFLICT '+str(sorted(extra)))
 else:OUT.mkdir(parents=True)
 validate_core();tr,_,_=load_split('train');folds={str(i):[] for i in range(5)}
 for x in tr:folds[str(fold_for_document(x['document_id']))].append(x['example_id'])
 flat=[x for v in folds.values() for x in v]
 if len(flat)!=854 or len(set(flat))!=854:raise RuntimeError('invalid fold coverage')
 docs={}
 for x in tr:
  f=fold_for_document(x['document_id']);docs.setdefault(x['document_id'],f)
  if docs[x['document_id']]!=f:raise RuntimeError('document split violation')
 manifest={'formula':'int(SHA256("LC-Sent15-Q3-OOF:" + document_id)[:16],16) mod 5','folds':{k:{'target_ids':v,'target_count':len(v),'zh':sum(next(x for x in tr if x['example_id']==i)['language']=='zh' for i in v),'en':sum(next(x for x in tr if x['example_id']==i)['language']=='en' for i in v)} for k,v in folds.items()},'document_count':len(docs)}
 cfg={'checkpoint':'LC-Sent-15-Q3','neural_recipe':'Q2 H3_D_FULL_64 x L1_LISTWISE_CE','head':'Linear(14337,64)->GELU->Dropout(0.1)->Linear(64,1)','params':917697,'loss':'single-positive listwise CE','optimizer':'AdamW','lr':LR,'weight_decay':WEIGHT_DECAY,'groups_per_batch':GROUP_BATCH,'max_epoch':EPOCHS,'patience':PATIENCE,'selection':'Dev Hit@1 desc, MRR desc, nDCG@5 desc, cell loss asc, earlier epoch','seeds':list(SEEDS),'alphas':list(ALPHAS),'normalization':'per-target z, zero if std<=1e-12','prohibitions':{'qwen':True,'blind':True,'reserve':True,'multi_positive':True,'mixed_catalog':True,'dev_alpha_tuning':True}}
 inp=validate_inputs()|{'feature_caches':EXPECTED_CACHES,'q2_integrity':sha(Q2/'Q2_INTEGRITY.json'),'q1c_integrity':sha(Q1C/'Q1C_INTEGRITY.json'),'q2c_integrity':sha(Q2C/'Q2C_INTEGRITY.json')}
 for n,x in [('q3_frozen_config.json',cfg),('input_manifest.json',inp),('fold_manifest.json',manifest)]:
  p=OUT/n
  if p.exists() and json.loads(p.read_text())!=x:raise RuntimeError('CONFLICT '+n)
  if not p.exists():dump(p,x)
def train_fold(seed,fold,device):
 d=run_dir(seed,fold)
 if files_ok(d):return
 if d.exists():raise RuntimeError('incomplete run '+str(d))
 work=d.with_name('.'+d.name+'.tmp');work.mkdir(parents=True)
 alltrain,cat,packed=load_split('train');held=[x for x in alltrain if fold_for_document(x['document_id'])==fold];learn=[x for x in alltrain if fold_for_document(x['document_id'])!=fold]
 if len(held)+len(learn)!=854 or not held:raise RuntimeError('fold partition')
 tm,sm=unpack_features(alltrain,cat,packed);lt,ls,ly,lg=tensors(learn,tm,sm,device);ht,hs,_,_=tensors(held,tm,sm,device)
 seed_all(seed);m=DirectionalFull64().to(device).float();opt=torch.optim.AdamW(m.parameters(),lr=LR,weight_decay=WEIGHT_DECAY);best=None;bad=0;hist=[];started=time.time();torch.cuda.reset_peak_memory_stats(device)
 for epoch in range(1,EPOCHS+1):
  m.train();losses=[];order=np.random.default_rng(seed+1000+epoch).permutation(len(learn))
  for start in range(0,len(learn),GROUP_BATCH):
   take=order[start:start+GROUP_BATCH];mask=torch.zeros(len(ly),dtype=torch.bool,device=device)
   for g in take:mask|=lg==int(g)
   opt.zero_grad(set_to_none=True);v=grouped_loss('L1_LISTWISE_CE',m(lt[mask],ls[mask]),ly[mask].bool(),lg[mask]);
   if not torch.isfinite(v):raise RuntimeError('nonfinite loss')
   v.backward();grad=float(torch.nn.utils.clip_grad_norm_(m.parameters(),CLIP));opt.step();losses.append(float(v.detach().cpu()))
  m.eval()
  with torch.inference_mode():hlog=m(ht,hs).cpu().numpy()
  _,target=pred_targets(held,hlog,seed,fold);met=aggregate(target);met['ranking_loss']=eval_loss(hlog,held);met['cell_loss']=met['ranking_loss'];k=key(met,epoch);im=best is None or k<tuple(best['key']);bad=0 if im else bad+1
  hist.append({'epoch':epoch,'train_loss':float(np.mean(losses)),'grad_norm_preclip':grad,'heldout':met,'improved':im,'bad_count':bad})
  if im:best={'epoch':epoch,'key':list(k),'state':{n:x.detach().cpu() for n,x in m.state_dict().items()},'heldout':met}
  if bad>=PATIENCE:break
 assert best is not None;torch.save(best.pop('state'),work/'best.pt');torch.save(opt.state_dict(),work/'terminal_optimizer.pt');torch.save({'torch_cpu':torch.get_rng_state().cpu(),'torch_cuda':torch.cuda.get_rng_state(device).cpu()},work/'terminal_rng.pt')
 restore=DirectionalFull64().to(device).float();restore.load_state_dict(torch.load(work/'best.pt',map_location=device,weights_only=True));restore.eval()
 with torch.inference_mode():hlog=restore(ht,hs).cpu().numpy()
 preds,target=pred_targets(held,hlog,seed,fold);metric=aggregate(target);metric['ranking_loss']=eval_loss(hlog,held)
 best.update({'best_checkpoint_metrics_after_reload':metric,'terminal_epoch':hist[-1]['epoch'],'post_peak_bad_count':bad,'terminal_reason':'patience_5' if bad>=PATIENCE else 'CENSORED_AT_100','runtime_seconds':time.time()-started,'peak_gpu_bytes':int(torch.cuda.max_memory_allocated(device))})
 dump(work/'config.json',{'seed':seed,'fold':fold,'train_target_count':len(learn),'heldout_target_count':len(held),'params':917697,'lr':LR,'weight_decay':WEIGHT_DECAY,'no_dev_loaded':True});dump(work/'history.json',hist);dump(work/'best.json',best);jsonl(work/'oof_predictions.jsonl',preds);dump(work/'oof_targets.json',target)
 fs={p.name:sha(p) for p in work.iterdir() if p.is_file()};dump(work/'integrity.json',{'files':fs,'fold_manifest_sha256':sha(OUT/'fold_manifest.json'),'frozen_config_sha256':sha(OUT/'q3_frozen_config.json')});(work/'COMPLETED').write_text('completed\n');os.replace(work,d)
def oof():
 device,snap=choose_device();dump(OUT/'gpu_snapshot.json',{'selected_device':str(device),'cuda_visible_devices':'unchanged','logical_device':device.index,'snapshot':snap})
 for seed in SEEDS:
  for fold in range(5):train_fold(seed,fold,device)
def bm25_score_map(split):
 p=BM25/f'bm25_mixed_v1_{split}_predictions.jsonl';d={x['example_id']:x for x in read_jsonl(p)}
 expected={'train':854,'dev':228}[split]
 if len(d)!=expected:raise RuntimeError('BM25 target count')
 return d
def oof_records(seed):
 rows=[]
 for f in range(5):
  d=run_dir(seed,f)
  if not files_ok(d):raise RuntimeError('missing OOF '+str(d))
  rows+=read_jsonl(d/'oof_predictions.jsonl')
 if len(rows)!=854*15:return None
 return rows
def groups_from_preds(rows):
 ans={}
 for r in rows:ans.setdefault(r['example_id'],[]).append(r)
 for rs in ans.values():rs.sort(key=lambda x:x['candidate_position'])
 return ans
def metrics_for_scores(groups):
 targets=[]
 for eid,rs in groups.items():
  ids=[r['candidate_id'] for r in rs];vals=np.array([r['fused_score'] for r in rs]);gold=next(r['candidate_id'] for r in rs if r['label']);order,gr=ranks(ids,vals,gold);targets.append({'gold_rank':gr,'language':rs[0]['language'],'example_id':eid,'top1_source_id':order[0],'ranking':order})
 return aggregate(targets),targets
def freeze_alpha():
 if (OUT/'alpha_frozen.json').exists():return
 train=read_jsonl(DATA/'train/single_positive_15.jsonl');bm=bm25_score_map('train');bm_groups={}
 for e in train:
  z=bm[e['example_id']];bm_groups[e['example_id']]={c['source_id']:z['scores'][c['source_id']] for c in e['candidates']}
 # Verify frozen BM25 train metrics from raw scores under the exact source-ID tie rule.
 bm_fused=[]
 for e in train:
  rs=[]
  for c in e['candidates']:rs.append({'candidate_id':c['source_id'],'label':c['label'],'language':e['language'],'fused_score':bm_groups[e['example_id']][c['source_id']]})
  bm_fused.append((e['example_id'],rs))
 bm_metric,_=metrics_for_scores(dict(bm_fused));expected={'hit_at_1':.6814988290398126,'mrr':.7475097079605275,'ndcg_at_5':.7450402089342653}
 if any(abs(bm_metric['overall'][k]-v)>1e-12 for k,v in expected.items()):raise RuntimeError('BM25 train reproduction failed')
 out={a:[] for a in ALPHAS};allpred=[];model_sha={}
 for seed in SEEDS:
  rows=oof_records(seed)
  if rows is None:raise RuntimeError('OOF coverage')
  groups=groups_from_preds(rows)
  if set(groups)!={x['example_id'] for x in train} or any(len(v)!=15 for v in groups.values()):raise RuntimeError('OOF coverage/duplicates')
  for a in ALPHAS:
   fused={}
   for eid,rs in groups.items():
    d=group_z(np.array([r['raw_logit'] for r in rs]));b=group_z(np.array([bm_groups[eid][r['candidate_id']] for r in rs]));fused[eid]=[{**r,'bm25_raw_score':float(bm_groups[eid][r['candidate_id']]),'dfull_z':float(d[i]),'bm25_z':float(b[i]),'fused_score':float(a*d[i]+(1-a)*b[i])} for i,r in enumerate(rs)]
   m,_=metrics_for_scores(fused);out[a].append(m['overall'])
  allpred += rows
  for f in range(5):model_sha[f'seed_{seed}/fold_{f}']={'checkpoint_sha256':sha(run_dir(seed,f)/'best.pt'),'prediction_sha256':sha(run_dir(seed,f)/'oof_predictions.jsonl')}
 chosen=choose_alpha(out)
 alpha={'status':'TRAIN_OOF_ONLY_FROZEN','alphas':[{"alpha":a,"seed_metrics":out[a],"mean":{k:float(np.mean([x[k] for x in out[a]])) for k in ('hit_at_1','mrr','ndcg_at_5')}} for a in ALPHAS],'selected_alpha':chosen,'selection':'mean OOF Hit@1 desc, MRR desc, nDCG@5 desc, smaller alpha, numeric order','fold_manifest_sha256':sha(OUT/'fold_manifest.json'),'models_and_predictions':model_sha,'bm25_train_reproduction':bm_metric['overall'],'no_dev_read_before_commit':True}
 jsonl(OUT/'oof_predictions.jsonl',allpred);dump(OUT/'alpha_frozen.json',alpha)
def pair_boot(a,b,idx):
 if b.ndim==1:b=np.broadcast_to(b,a.shape)
 o={}
 for n,fn in {'hit_at_1':lambda x:x==1,'mrr':lambda x:1/x,'ndcg_at_5':lambda x:np.where(x<=5,1/np.log2(x+1),0)}.items():
  x,y=fn(a.astype(float)),fn(b.astype(float));d=x[:,idx].mean(2).mean(0)-y[:,idx].mean(2).mean(0);o[n]={'delta':float(x.mean(1).mean()-y.mean(1).mean()),'ci95':[float(np.quantile(d,.025)),float(np.quantile(d,.975))]}
 return o
def dev_finalise():
 if (OUT/'COMPLETED').exists():return
 if not(OUT/'alpha_frozen.json').is_file():raise RuntimeError('ALPHA_NOT_FROZEN')
 alpha=json.loads((OUT/'alpha_frozen.json').read_text());a=alpha['selected_alpha'];dev,_,_=load_split('dev');bm=bm25_score_map('dev');allseed=[];predout=[]
 for seed in SEEDS:
  raw=groups_from_preds(read_jsonl(Q2/f'runs/H3_D_FULL_64/L1_LISTWISE_CE/seed_{seed}/dev_predictions.jsonl'));fused={}
  for e in dev:
   eid=e['example_id'];rs=raw[eid]
   if [r['candidate_id'] for r in rs] != [c['source_id'] for c in e['candidates']]:raise RuntimeError('candidate order mismatch')
   d=group_z(np.array([r['raw_logit'] for r in rs]));b=group_z(np.array([bm[eid]['scores'][r['candidate_id']] for r in rs]));fused[eid]=[{**r,'bm25_raw_score':float(bm[eid]['scores'][r['candidate_id']]),'dfull_z':float(d[i]),'bm25_z':float(b[i]),'fused_score':float(a*d[i]+(1-a)*b[i])} for i,r in enumerate(rs)]
  metric,targets=metrics_for_scores(fused);allseed.append({'seed':seed,'metrics':metric,'targets':targets});predout += [x for v in fused.values() for x in v]
 jsonl(OUT/'dev_predictions.jsonl',predout)
 mean={k:float(np.mean([x['metrics']['overall'][k] for x in allseed])) for k in ('hit_at_1','mrr','ndcg_at_5','mean_gold_rank')}
 idx=np.load(Q0/'bootstrap_indices.npy');fr=np.asarray([[x['gold_rank'] for x in z['targets']] for z in allseed]);df=np.asarray([[x['gold_rank'] for x in json.loads((Q2/f'runs/H3_D_FULL_64/L1_LISTWISE_CE/seed_{s}/dev_targets.json').read_text())] for s in SEEDS]);q1=np.asarray([[x['gold_rank'] for x in json.loads((Q1C/f'runs/seed_{s}/best_dev_targets.json').read_text())] for s in SEEDS]);bmrank=np.asarray([bm[x['example_id']]['gold_rank'] for x in dev])
 boot={'fusion_minus_dfull64':pair_boot(fr,df,idx),'fusion_minus_bm25':pair_boot(fr,bmrank,idx),'fusion_minus_q1c':pair_boot(fr,q1,idx)}
 h=boot['fusion_minus_dfull64']['hit_at_1'];status='Q3_FUSION_PASS' if h['delta']>0 and h['ci95'][0]>0 and boot['fusion_minus_dfull64']['mrr']['ci95'][0]>=0 and boot['fusion_minus_dfull64']['ndcg_at_5']['ci95'][0]>=0 else 'Q3_FUSION_CONDITIONAL' if h['delta']>0 else 'Q3_FUSION_NO_GAIN'
 # fixed seed 1 descriptive complementarity; model selection already closed.
 f={x['example_id']:x for x in allseed[1]['targets']};d={x['example_id']:x for x in json.loads((Q2/'runs/H3_D_FULL_64/L1_LISTWISE_CE/seed_1/dev_targets.json').read_text())};b={x['example_id']:bm[x['example_id']] for x in dev};comp={}
 for base,source in [('dfull64',d),('bm25',b)]:
  comp[base]={}
  for lang in ('overall','zh','en'):
   ids=[x['example_id'] for x in dev if lang=='overall' or x['language']==lang];comp[base][lang]={'both_correct':sum(f[i]['gold_rank']==1 and source[i]['gold_rank']==1 for i in ids),'baseline_only':sum(f[i]['gold_rank']!=1 and source[i]['gold_rank']==1 for i in ids),'fusion_only':sum(f[i]['gold_rank']==1 and source[i]['gold_rank']!=1 for i in ids),'both_wrong':sum(f[i]['gold_rank']!=1 and source[i]['gold_rank']!=1 for i in ids)}
 oracle=float(np.mean([(d[x['example_id']]['gold_rank']==1 or bm[x['example_id']]['gold_rank']==1) for x in dev]))
 dump(OUT/'metrics.json',{'selected_alpha':a,'train_oof_selected_alpha_mean':next(x['mean'] for x in alpha['alphas'] if x['alpha']==a),'dev_seed_metrics':[{'seed':x['seed'],'metrics':x['metrics']} for x in allseed],'dev_mean':mean,'status':status,'ninety_target':'INTERPRETABLE_90_TARGET_REACHED' if mean['hit_at_1']>=.9 else 'INTERPRETABLE_90_TARGET_NOT_REACHED','complementarity_seed1':comp,'oracle_union_dfull64_bm25_seed1':oracle})
 dump(OUT/'bootstrap.json',{'seed':BOOT_SEED,'reps':REPS,'indices_sha256':sha(Q0/'bootstrap_indices.npy'),'comparisons':boot})
 (OUT/'Q3_REPORT.md').write_text(f'# LC-Sent-15-Q3 OOF Fusion\n\nSelected Train-only OOF alpha: `{a:.2f}`. Decision: `{status}`.\n\nDev was accessed only after `alpha_frozen.json` was atomically committed. No Qwen, Blind, Reserve, multi-positive, mixed catalog, or BM25 training feature was used.\n')
 fs={str(p.relative_to(OUT)):sha(p) for p in OUT.rglob('*') if p.is_file() and p.name not in {'checksums.sha256','Q3_INTEGRITY.json','COMPLETED'}};(OUT/'checksums.sha256').write_text(''.join(f'{v}  {k}\n' for k,v in sorted(fs.items())));dump(OUT/'Q3_INTEGRITY.json',{'status':'PASS','files':fs,'input_manifest_sha256':sha(OUT/'input_manifest.json'),'frozen_config_sha256':sha(OUT/'q3_frozen_config.json'),'alpha_frozen_sha256':sha(OUT/'alpha_frozen.json'),'no_qwen':True,'no_blind':True,'no_reserve':True,'no_multi_positive':True,'no_mixed_catalog':True,'decision':status});(OUT/'COMPLETED').write_text('MEMORYFLOW_LC_SENT15_Q3_OOF_FUSION_COMPLETE\n')
def main():
 p=argparse.ArgumentParser();p.add_argument('mode',choices=('prepare','oof','freeze-alpha','dev-finalize'));a=p.parse_args();prepare()
 if a.mode=='oof':oof()
 elif a.mode=='freeze-alpha':freeze_alpha()
 elif a.mode=='dev-finalize':dev_finalise()
if __name__=='__main__':main()
