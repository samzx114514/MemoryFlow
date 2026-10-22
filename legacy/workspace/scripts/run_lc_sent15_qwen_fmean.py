#!/usr/bin/env python3
"""Create-only frozen Qwen2.5-7B F_mean cosine baseline for LC-Sent-15."""

from __future__ import annotations

import csv
import hashlib
import json
import math
import os
from pathlib import Path
import random
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from memoryflow.lc_sent15_fmean import assert_allowed_path, rank_scores, single_positive_metrics

MODEL = Path('/data2/pkuiti/songzhengxing_intern/model/Qwen2.5-7B-Instruct')
MODEL_MANIFEST = ROOT / 'results/c5f_ranking_continuation_243_v1/model_manifest/model_sha256_manifest.json'
M6A_AUDIT = ROOT / 'results/m6a_qwen_representation_audit_243_v1/representation_audit.json'
DATA = ROOT / 'data/lc_sent15_v1'
BM25 = ROOT / 'results/lc_sent15_v1_bm25_gate_v1'
BM25_AUDIT = ROOT / 'results/lc_sent15_v1_bm25_gate_audit_closure_v2'
OUT = ROOT / 'results/lc_sent15_v1_qwen_fmean_cosine_v1'
MAX_LENGTH = 512
BATCH_SIZE = 8
BOOTSTRAP_SEED = 20260815
BOOTSTRAP_REPS = 10000


def sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def dump(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n', encoding='utf-8')


def read_jsonl(path: Path) -> list[dict]:
    with path.open(encoding='utf-8') as handle:
        return [json.loads(line) for line in handle if line.strip()]


def write_jsonl(path: Path, rows: list[dict]) -> None:
    with path.open('w', encoding='utf-8', newline='\n') as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True, allow_nan=False) + '\n')


def gpu_snapshot() -> list[dict]:
    command = ['nvidia-smi', '--query-gpu=index,name,memory.total,memory.used,memory.free', '--format=csv,noheader,nounits']
    lines = subprocess.check_output(command, text=True).splitlines()
    result=[]
    for line in lines:
        index, name, total, used, free = [part.strip() for part in line.split(',')]
        result.append({'physical_gpu':int(index),'name':name,'total_mib':int(total),'used_mib':int(used),'free_mib':int(free)})
    return result


def select_gpu(snapshot: list[dict]) -> dict:
    # M6A measured 28,968 MiB allocation; retain a 12 GiB safety margin.
    required = 42 * 1024
    safe = [entry for entry in snapshot if entry['free_mib'] >= required]
    if not safe:
        raise RuntimeError('NO_SAFE_GPU')
    return max(safe, key=lambda entry: (entry['free_mib'], -entry['physical_gpu']))


def verify_model_manifest() -> dict:
    manifest=json.loads(MODEL_MANIFEST.read_text(encoding='utf-8'))
    expected_m6a=json.loads(M6A_AUDIT.read_text(encoding='utf-8'))['model_manifest_sha256']
    if sha(MODEL_MANIFEST) != expected_m6a:
        raise RuntimeError('M6A model manifest SHA mismatch')
    checked=[]
    for entry in manifest['files']:
        path=MODEL/entry['name']
        if not path.is_file() or path.stat().st_size != entry['size_bytes'] or sha(path) != entry['sha256']:
            raise RuntimeError(f"model manifest mismatch: {entry['name']}")
        checked.append(entry['name'])
    return {'manifest_path':str(MODEL_MANIFEST),'manifest_file_sha256':sha(MODEL_MANIFEST),'internal_manifest_sha256':manifest['manifest_sha256'],'checked_files':checked,'model_path':str(MODEL)}


def load_split(split: str) -> tuple[list[dict], dict[str, dict]]:
    examples=read_jsonl(DATA/split/'single_positive_15.jsonl')
    catalog={row['id']:row for row in read_jsonl(DATA/split/'source_catalog.jsonl')}
    if len(examples) != {'train':854,'dev':228}[split] or any(len(row['candidates']) != 15 or sum(int(c['label']) for c in row['candidates']) != 1 for row in examples):
        raise RuntimeError(f'data contract mismatch: {split}')
    source_ids={candidate['source_id'] for row in examples for candidate in row['candidates']}
    if set(catalog) != source_ids:
        raise RuntimeError(f'catalog mismatch: {split}')
    return examples,catalog


def length_audit(tokenizer, splits: dict[str, tuple[list[dict], dict[str, dict]]]) -> tuple[dict, dict[str, list[str]], dict[str, dict[str, str]]]:
    texts={}; ids={}; lookup={}
    for split,(examples,catalog) in splits.items():
        target_ids=[row['example_id'] for row in examples]
        target_text={row['example_id']:row['target']['text'] for row in examples}
        source_ids=sorted(catalog); source_text={key:catalog[key]['text'] for key in source_ids}
        texts[f'{split}_target']=[target_text[key] for key in target_ids]; ids[f'{split}_target']=target_ids; lookup[f'{split}_target']=target_text
        texts[f'{split}_source']=[source_text[key] for key in source_ids]; ids[f'{split}_source']=source_ids; lookup[f'{split}_source']=source_text
    audit={}; context=32768
    for key, values in texts.items():
        lengths=[len(tokenizer(text, add_special_tokens=True, truncation=False)['input_ids']) for text in values]
        over_context=[ids[key][i] for i,n in enumerate(lengths) if n>context]
        audit[key]={'count':len(values),'min':min(lengths),'max':max(lengths),'over_m6a_max_length_512':sum(n>MAX_LENGTH for n in lengths),'over_model_context':len(over_context),'over_model_context_ids':over_context}
        if over_context: raise RuntimeError(f'MODEL_CONTEXT_EXCEEDED {key}')
    return audit,ids,lookup


def encode(tokenizer, model, ids: list[str], texts: dict[str,str], device: str, torch):
    import numpy as np
    rows=[]; raw_lengths=[]
    for start in range(0,len(ids),BATCH_SIZE):
        batch_ids=ids[start:start+BATCH_SIZE]; batch=[texts[key] for key in batch_ids]
        encoded=tokenizer(batch,padding=True,truncation=True,max_length=MAX_LENGTH,return_tensors='pt')
        raw_lengths.extend(len(tokenizer(text,add_special_tokens=True,truncation=False)['input_ids']) for text in batch)
        encoded={key:value.to(device) for key,value in encoded.items()}
        with torch.inference_mode(): hidden=model(**encoded,return_dict=True).last_hidden_state.float()
        mask=encoded['attention_mask'].unsqueeze(-1).to(hidden.dtype)
        vector=(hidden*mask).sum(1)/mask.sum(1).clamp_min(1.0)
        rows.append(vector.cpu().numpy().astype(np.float32,copy=False))
    features=np.concatenate(rows,axis=0)
    norms=np.linalg.norm(features,axis=1)
    if not np.isfinite(features).all() or not np.isfinite(norms).all() or (norms <= 0).any(): raise RuntimeError('non-finite feature')
    normalized=features/norms[:,None]
    return features,normalized,raw_lengths


def metric_rows(examples, target_vectors, source_vectors, *, split: str) -> tuple[list[dict], list[dict]]:
    rows=[]; targets=[]
    for example in examples:
        target_id=example['example_id']; ids=[x['source_id'] for x in example['candidates']]
        scores={source_id:float(target_vectors[target_id].dot(source_vectors[source_id])) for source_id in ids}
        ranking=rank_scores(scores); gold=next(x['source_id'] for x in example['candidates'] if int(x['label'])==1); rank=ranking.index(gold)+1
        targets.append({'example_id':target_id,'language':example['language'],'gold_rank':rank,'top1_source_id':ranking[0],'gold_source_id':gold,'ranking':ranking})
        for pos,candidate in enumerate(example['candidates']):
            source_id=candidate['source_id']; rows.append({'split':split,'example_id':target_id,'language':example['language'],'candidate_id':source_id,'candidate_position':pos,'label':int(candidate['label']),'raw_cosine_score':scores[source_id],'normalized_score':scores[source_id],'rank':ranking.index(source_id)+1})
    return rows,targets


def summarize(targets: list[dict]) -> dict:
    result={}
    for name,chosen in {'overall':targets,'zh':[x for x in targets if x['language']=='zh'],'en':[x for x in targets if x['language']=='en']}.items(): result[name]=single_positive_metrics([x['gold_rank'] for x in chosen])
    return result


def bootstrap(qwen: list[dict], bm25: list[dict], path: Path) -> dict:
    import numpy as np
    q={row['example_id']:row['gold_rank'] for row in qwen}; b={row['example_id']:row['gold_rank'] for row in bm25}; ids=sorted(q)
    if ids != sorted(b): raise RuntimeError('BM25/Qwen target mismatch')
    rng=random.Random(BOOTSTRAP_SEED); indices=np.asarray([[rng.randrange(len(ids)) for _ in ids] for _ in range(BOOTSTRAP_REPS)],dtype=np.int16); np.save(path,indices)
    qr=np.asarray([q[key] for key in ids],dtype=float); br=np.asarray([b[key] for key in ids],dtype=float)
    def vec(ranks, metric):
        values = (ranks==1) if metric=='hit_at_1' else 1/ranks if metric=='mrr' else np.where(ranks<=5,1/np.log2(ranks+1),0)
        return values[indices].mean(axis=1)
    answer={}
    for metric in ('hit_at_1','mrr','ndcg_at_5'):
        qdraw=vec(qr,metric); bdraw=vec(br,metric); delta=qdraw-bdraw
        answer[metric]={'qwen_ci95':[float(np.quantile(qdraw,.025)),float(np.quantile(qdraw,.975))],'qwen_minus_bm25_point':float(vec(qr,metric).mean()-vec(br,metric).mean()),'qwen_minus_bm25_ci95':[float(np.quantile(delta,.025)),float(np.quantile(delta,.975))]}
    return {'seed':BOOTSTRAP_SEED,'reps':BOOTSTRAP_REPS,'indices_file':path.name,'indices_sha256':sha(path),'metrics':answer}


def length_bucket_metrics(qwen: list[dict], bm25: list[dict], lengths: dict[str, int], *, field: str) -> list[dict]:
    values=sorted(lengths[row[field]] for row in qwen)
    cuts=[values[(len(values)-1)*index//4] for index in (1,2,3)]
    def bucket(value: int) -> int: return sum(value > cut for cut in cuts) + 1
    bmap={row['example_id']:row for row in bm25}; output=[]
    for value in range(1,5):
        selected=[row for row in qwen if bucket(lengths[row[field]])==value]
        q=single_positive_metrics([row['gold_rank'] for row in selected]); b=single_positive_metrics([bmap[row['example_id']]['gold_rank'] for row in selected])
        output.append({'field':field,'bucket':value,'target_count':len(selected),'qwen':q,'bm25':b})
    return output


def main() -> int:
    for path in (DATA,BM25,BM25_AUDIT,MODEL,MODEL_MANIFEST,M6A_AUDIT): assert_allowed_path(str(path))
    if OUT.exists(): raise RuntimeError(f'create-only result exists: {OUT}')
    if not (BM25/'COMPLETED').is_file() or not (BM25_AUDIT/'COMPLETED').is_file(): raise RuntimeError('BM25 prerequisite incomplete')
    verification=verify_model_manifest()
    os.environ['HF_HUB_OFFLINE']='1'; os.environ['TRANSFORMERS_OFFLINE']='1'
    from transformers import AutoTokenizer, AutoModel
    tokenizer=AutoTokenizer.from_pretrained(str(MODEL),local_files_only=True)
    m6a=json.loads(M6A_AUDIT.read_text(encoding='utf-8'))
    if tokenizer.eos_token_id != m6a['tokenizer']['eos_token_id']: raise RuntimeError('M6A tokenizer contract mismatch')
    splits={split:load_split(split) for split in ('train','dev')}
    lengths,ids,lookup=length_audit(tokenizer,splits)
    snapshot=gpu_snapshot()
    try: chosen=select_gpu(snapshot)
    except RuntimeError:
        raise
    os.environ['CUDA_VISIBLE_DEVICES']=str(chosen['physical_gpu'])
    import torch
    if not torch.cuda.is_available() or torch.cuda.device_count()!=1: raise RuntimeError('CUDA logical mapping failure')
    started=time.time(); tmp=OUT.with_name('.'+OUT.name+'.tmp')
    if tmp.exists(): raise RuntimeError(f'temporary output exists: {tmp}')
    tmp.mkdir(parents=True)
    try:
        model=AutoModel.from_pretrained(str(MODEL),local_files_only=True,dtype=torch.float32,attn_implementation='eager').to('cuda').eval(); model.requires_grad_(False)
        if any(param.requires_grad or param.grad is not None for param in model.parameters()): raise RuntimeError('model not frozen')
        torch.cuda.reset_peak_memory_stats()
        all_vectors={}; cache_meta={}; length_by_id={}
        for key in ('train_target','train_source','dev_target','dev_source'):
            raw,norm,raw_lengths=encode(tokenizer,model,ids[key],lookup[key],'cuda',torch)
            import numpy as np
            np.savez_compressed(tmp/f'{key}_fmean.npz',raw=raw,normalized=norm)
            text_hashes={item_id:hashlib.sha256(lookup[key][item_id].encode()).hexdigest() for item_id in ids[key]}
            all_vectors[key]=dict(zip(ids[key],norm)); cache_meta[key]={'count':len(ids[key]),'shape':list(raw.shape),'dtype':'float32','feature_file':f'{key}_fmean.npz','feature_sha256':sha(tmp/f'{key}_fmean.npz'),'text_sha256':text_hashes,'truncated_at_512':sum(n>MAX_LENGTH for n in raw_lengths)}
            length_by_id.update(dict(zip(ids[key],raw_lengths)))
        # Repeat/padding check uses a fixed target with a batchmate and a padded batch.
        probe=ids['dev_target'][0]; raw1,_,_=encode(tokenizer,model,[probe],{probe:lookup['dev_target'][probe]},'cuda',torch); raw2,_,_=encode(tokenizer,model,[probe,ids['dev_target'][1]],{probe:lookup['dev_target'][probe],ids['dev_target'][1]:lookup['dev_target'][ids['dev_target'][1]]},'cuda',torch)
        padding_diff=float(abs(raw1[0]-raw2[0]).max())
        if padding_diff != 0.0: raise RuntimeError(f'padding invariance failed {padding_diff}')
        score_outputs={}; summaries={}; target_outputs={}
        for split in ('train','dev'):
            rows,targets=metric_rows(splits[split][0],all_vectors[f'{split}_target'],all_vectors[f'{split}_source'],split=split)
            write_jsonl(tmp/f'{split}_qwen_predictions.jsonl',rows); write_jsonl(tmp/f'{split}_qwen_targets.jsonl',targets)
            score_outputs[split]=rows; target_outputs[split]=targets; summaries[split]=summarize(targets)
        bm25_targets=[]
        for row in read_jsonl(BM25/'bm25_legacy_dev_predictions.jsonl'):
            bm25_targets.append({'example_id':row['example_id'],'gold_rank':row['gold_rank'],'top1_source_id':row['top1_source_id'],'language':row['language'],'gold_source_id':row['gold_source_id'],'ranking':row['ranking']})
        boot=bootstrap(target_outputs['dev'],bm25_targets,tmp/'bootstrap_indices.npy')
        # Fixed four-way agreement plus text-bearing, Dev-only representative error examples.
        bmap={row['example_id']:row for row in bm25_targets}; qmap={row['example_id']:row for row in target_outputs['dev']}; contingency={key:0 for key in ('both_correct','bm25_only','qwen_only','both_wrong')}; failures=[]
        examples_by_id={row['example_id']:row for row in splits['dev'][0]}; catalog=splits['dev'][1]
        for example_id,qrow in qmap.items():
            brow=bmap[example_id]; key='both_correct' if qrow['gold_rank']==1 and brow['gold_rank']==1 else 'bm25_only' if brow['gold_rank']==1 else 'qwen_only' if qrow['gold_rank']==1 else 'both_wrong'; contingency[key]+=1
            if key!='both_correct':
                ex=examples_by_id[example_id]; failures.append({'category':key,'example_id':example_id,'language':qrow['language'],'target_text':ex['target']['text'],'gold_source_id':qrow['gold_source_id'],'gold_text':catalog[qrow['gold_source_id']]['text'],'qwen_top1_source_id':qrow['top1_source_id'],'qwen_top1_text':catalog[qrow['top1_source_id']]['text'],'bm25_top1_source_id':brow['top1_source_id'],'bm25_top1_text':catalog[brow['top1_source_id']]['text'],'qwen_gold_rank':qrow['gold_rank'],'bm25_gold_rank':brow['gold_rank']})
        selected=[]
        for lang in ('zh','en'):
            for category in ('bm25_only','qwen_only','both_wrong'):
                selected.extend([x for x in failures if x['language']==lang and x['category']==category][:4])
        seen=set(); selected=[x for x in selected if not (x['example_id'] in seen or seen.add(x['example_id']))]; selected.extend([x for x in failures if x['example_id'] not in seen][:max(0,20-len(selected))])
        by_language={}
        for language in ('zh','en'):
            counts={key:0 for key in contingency}
            for row in qmap.values():
                if row['language'] != language: continue
                bm_rank=bmap[row['example_id']]['gold_rank']
                key='both_correct' if row['gold_rank']==1 and bm_rank==1 else 'bm25_only' if bm_rank==1 else 'qwen_only' if row['gold_rank']==1 else 'both_wrong'
                counts[key]+=1
            by_language[language]=counts
        dump(tmp/'error_complementarity.json',{'overall':contingency,'by_language':by_language})
        dump(tmp/'representative_dev_failures_max20.json',selected[:20])
        for row in target_outputs['dev']:
            row['gold_source_id']=row['gold_source_id']
        dump(tmp/'length_bucket_metrics.json',{'target_length':length_bucket_metrics(target_outputs['dev'],bm25_targets,length_by_id,field='example_id'),'gold_source_length':length_bucket_metrics(target_outputs['dev'],bm25_targets,length_by_id,field='gold_source_id')})
        config={'contract':'M6A F_mean: raw chunk text, tokenizer default special-token behavior, final hidden state attention-mask mean, FP32 storage; L2 normalize then cosine','model':verification,'tokenizer_path':str(MODEL),'tokenizer_eos_id':tokenizer.eos_token_id,'special_tokens':tokenizer.special_tokens_map,'transformers_version':__import__('transformers').__version__,'torch_version':torch.__version__,'model_dtype':'float32','feature_dtype':'float32','attention_implementation':'eager','padding':True,'truncation':True,'max_length':MAX_LENGTH,'candidate_group_normalization':False,'tie_break':'score_desc_source_id_asc','blind_accessed':False,'reserve_accessed':False,'multi_positive_accessed':False,'mixed_catalog_accessed':False,'training':False,'gpu_snapshot_before':snapshot,'selected_gpu':chosen,'logical_gpu':0,'micro_batch_size':BATCH_SIZE,'length_audit':lengths}
        dump(tmp/'frozen_config.json',config); dump(tmp/'metrics.json',{'qwen':summaries,'random':{'hit_at_1':1/15,'mrr':sum(1/r for r in range(1,16))/15,'ndcg_at_5':sum(1/math.log2(r+1) for r in range(1,6))/15},'bm25':json.loads((BM25/'metrics.json').read_text(encoding='utf-8'))['implementations']['BM25_LEGACY'],'bootstrap':boot})
        runtime={'runtime_seconds':time.time()-started,'peak_memory_allocated_bytes':int(torch.cuda.max_memory_allocated()),'gpu_snapshot_after':gpu_snapshot(),'padding_invariance_max_abs':padding_diff,'model_parameters_frozen':True,'generate_calls':0,'backward_calls':0}
        dump(tmp/'runtime.json',runtime)
        report=['# LC-Sent-15-Q0 Frozen Qwen F_mean Cosine','', '`F_mean` is M6A-compatible final-layer attention-mask mean pooled FP32 hidden states of raw text, L2-normalized before cosine scoring.', '', f"GPU physical `{chosen['physical_gpu']}` mapped to logical `cuda:0`; no training, generation, or Blind access.", '', '## Dev', f"- Qwen Hit@1 {summaries['dev']['overall']['hit_at_1']:.6f}; MRR {summaries['dev']['overall']['mrr']:.6f}; nDCG@5 {summaries['dev']['overall']['ndcg_at_5']:.6f}.", f"- BM25 Hit@1 {json.loads((BM25/'metrics.json').read_text())['implementations']['BM25_LEGACY']['dev']['overall']['hit_at_1']:.6f}."]
        (tmp/'Q0_REPORT.md').write_text('\n'.join(report)+'\n',encoding='utf-8')
        integrity={'status':'PASS','inputs':{str(path.relative_to(ROOT)):sha(path) for path in (DATA/'manifest.json',DATA/'checksums.sha256',BM25/'integrity_report.json',BM25_AUDIT/'integrity_report.json',M6A_AUDIT,MODEL_MANIFEST)},'no_blind':True,'no_reserve':True,'no_multi_positive':True,'no_mixed_catalog':True,'no_training':True,'no_qwen_generation':True,'files':{}}
        for path in sorted(x for x in tmp.rglob('*') if x.is_file()): integrity['files'][path.relative_to(tmp).as_posix()]=sha(path)
        dump(tmp/'integrity_report.json',integrity)
        with (tmp/'checksums.sha256').open('w',encoding='utf-8') as handle:
            for path in sorted(x for x in tmp.rglob('*') if x.is_file() and x.name!='checksums.sha256'): handle.write(f'{sha(path)}  {path.relative_to(tmp).as_posix()}\n')
        (tmp/'COMPLETED').write_text('MEMORYFLOW_LC_SENT15_QWEN_FMEAN_COSINE_COMPLETE\nLANGUAGE_STRATIFICATION_REQUIRED\n',encoding='utf-8')
        tmp.rename(OUT)
    finally:
        if 'model' in locals(): del model
        if 'torch' in locals() and torch.cuda.is_available(): torch.cuda.empty_cache()
    return 0


if __name__=='__main__': raise SystemExit(main())
