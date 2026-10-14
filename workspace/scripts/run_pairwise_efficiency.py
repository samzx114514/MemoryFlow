#!/usr/bin/env python3
"""C4A Pairwise reference and Packed/Pairwise efficiency benchmark."""

from __future__ import annotations
import gc,json,os,statistics,sys,time
from pathlib import Path
import numpy as np
import torch
from safetensors.torch import load_file
from transformers import AutoModelForCausalLM,AutoTokenizer

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/"src"));sys.path.insert(0,str(ROOT/"scripts"))
from evaluate_anchor_scaling import CHECKPOINT,EXPECTED,MODEL,OUT,load_jsonl,load_view,packed_anchor,record  # noqa:E402
from memoryflow.anchor_attention import build_anchor_attention_mask,maximum_masked_attention  # noqa:E402
from memoryflow.expanded_anchor_training import file_sha256  # noqa:E402
from memoryflow.pairwise_efficiency import batched_pairwise_raw_scores,inject_batched_anchor,padded_pairwise_tensors  # noqa:E402
from memoryflow.ranking_baselines import METRIC_NAMES,compute_ranking_metrics  # noqa:E402
from memoryflow.scaling_candidates import kendall_tau_rankings  # noqa:E402
from memoryflow.expanded_longcite import stable_hex  # noqa:E402
from memoryflow.trainable_anchor import inject_shared_anchor  # noqa:E402
from train_anchor_vector_smoke import pack  # noqa:E402

DATA=ROOT/"data/longcite_anchor_scaling_primary_v1"

def pair_layout(tokenizer,e,sources,sid):
 row=dict(e);row["candidate_source_ids"]=[sid];return pack(tokenizer,row,sources,tokenizer.eos_token_id)
def batched_forward(model,layouts,anchor):
 ids,pos,mask=padded_pairwise_tensors(layouts,pad_token_id=model.config.eos_token_id,device="cuda")
 with torch.no_grad():base=model.get_input_embeddings()(ids).detach();embeds=inject_batched_anchor(base,layouts,anchor);out=model(inputs_embeds=embeds,position_ids=pos,attention_mask=mask,output_attentions=True,use_cache=False,return_dict=True,logits_to_keep=1)
 return out,mask
def aggregate(rows):
 return {k:statistics.fmean(r[k] for r in rows) for k in METRIC_NAMES}
def select_examples(examples):
 single=sorted((e for e in examples if len(e["gold_source_ids"])==1),key=lambda e:stable_hex("memoryflow-c4a-pairwise-v1",e["target_group_id"]))[:15]
 multi=sorted((e for e in examples if len(e["gold_source_ids"])>1),key=lambda e:stable_hex("memoryflow-c4a-pairwise-v1",e["target_group_id"]))[:15]
 if len(single)!=15 or len(multi)!=15:raise RuntimeError("pairwise stratum shortage")
 return single+multi
def score_pairwise(model,tokenizer,anchor,selected,sources,packed_rows):
 records=[];leak=0.;finite=True;taus=[];top1=top3=0;rank_diffs=[]
 for number,e in enumerate(selected,1):
  ids=e["candidate_source_ids"];layouts=[pair_layout(tokenizer,e,sources,sid) for sid in ids];out,mask=batched_forward(model,layouts,anchor);raw=batched_pairwise_raw_scores(out.attentions,layouts).cpu().tolist();finite &= bool(torch.isfinite(out.logits).all()) and all(bool(torch.isfinite(a).all()) for a in out.attentions)
  for i,layout in enumerate(layouts):
   local=build_anchor_attention_mask(layout,mode="anchor",dtype=torch.float32,device="cuda");blocked=local[0,0]!=0
   for layer in out.attentions:leak=max(leak,float(layer[i,:, :layout.sequence_length,:layout.sequence_length].float().masked_select(blocked.unsqueeze(0)).abs().max()))
  scores=dict(zip(ids,raw));ranking=sorted(ids,key=lambda sid:(-scores[sid],sid));gold=set(e["gold_source_ids"]);metric=compute_ranking_metrics(ranking,gold);records.append(record(e,32,"pairwise_trained_anchor_raw",scores,ranking,metric,raw=scores))
  packed=packed_rows[e["target_group_id"]];taus.append(kendall_tau_rankings(ranking,packed["ranking"]));top1+=ranking[0]==packed["ranking"][0];top3+=set(ranking[:3])==set(packed["ranking"][:3]);ppos={x:i+1 for i,x in enumerate(packed["ranking"])};rpos={x:i+1 for i,x in enumerate(ranking)};rank_diffs.append(np.mean([rpos[x]-ppos[x] for x in gold]))
  del out,mask
 return records,{"masked_attention_max_abs":leak,"all_finite":finite,"mean_kendall_tau":float(np.mean(taus)),"top1_consistency":top1/len(selected),"top3_set_consistency":top3/len(selected),"mean_positive_rank_difference_pairwise_minus_packed":float(np.mean(rank_diffs))}
def one_packed(model,layout,anchor):
 ids=torch.tensor([layout.input_ids],device="cuda");pos=torch.tensor([layout.position_ids],device="cuda");mask=build_anchor_attention_mask(layout,mode="anchor",dtype=torch.float32,device="cuda")
 with torch.no_grad():base=model.get_input_embeddings()(ids).detach();embeds=inject_shared_anchor(base,layout.source_anchor_positions+[layout.target_anchor_position],anchor);out=model(inputs_embeds=embeds,position_ids=pos,attention_mask=mask,output_attentions=True,use_cache=False,return_dict=True,logits_to_keep=1)
 return out
def benchmark_operation(operation,warmups=3,repeats=5):
 for _ in range(warmups):operation();torch.cuda.synchronize()
 times=[];alloc=[];reserved=[]
 for _ in range(repeats):
  torch.cuda.reset_peak_memory_stats();torch.cuda.synchronize();start_event=torch.cuda.Event(True);end_event=torch.cuda.Event(True);wall=time.perf_counter();start_event.record();operation();end_event.record();torch.cuda.synchronize();times.append(time.perf_counter()-wall);alloc.append(torch.cuda.max_memory_allocated());reserved.append(torch.cuda.max_memory_reserved())
 return {"wall_seconds_mean":float(np.mean(times)),"wall_seconds_std":float(np.std(times)),"cuda_seconds_mean":float(np.mean([x for x in times])),"peak_allocated_bytes_mean":float(np.mean(alloc)),"peak_reserved_bytes_mean":float(np.mean(reserved)),"repeats":repeats,"warmups":warmups}
def efficiency(model,tokenizer,anchor,selected,sources,by_size):
 result={}
 for n in (8,16,32):
  examples={e["target_group_id"]:e for e in by_size[n]};chosen=[examples[e["target_group_id"]] for e in selected];packed_layouts=[pack(tokenizer,e,sources,tokenizer.eos_token_id) for e in chosen];pair_groups=[[pair_layout(tokenizer,e,sources,sid) for sid in e["candidate_source_ids"]] for e in chosen]
  def packed_op():
   for layout in packed_layouts:del_output(one_packed(model,layout,anchor))
  def sequential_op():
   for group in pair_groups:
    for layout in group:del_output(one_packed(model,layout,anchor))
  def batched_op():
   for group in pair_groups:
    out,_=batched_forward(model,group,anchor);del out
  packed_tokens=sum(x.sequence_length for x in packed_layouts);sequential_tokens=sum(x.sequence_length for g in pair_groups for x in g);batched_tokens=sum(len(g)*max(x.sequence_length for x in g) for g in pair_groups)
  output_elements={"packed":sum(28*12*x.sequence_length**2 for x in packed_layouts),"pairwise_sequential":sum(28*12*x.sequence_length**2 for g in pair_groups for x in g),"pairwise_batched":sum(28*12*len(g)*max(x.sequence_length for x in g)**2 for g in pair_groups)}
  result[str(n)]={}
  for name,op,calls,tokens in (("packed",packed_op,30,packed_tokens),("pairwise_sequential",sequential_op,30*n,sequential_tokens),("pairwise_batched",batched_op,30,batched_tokens)):
   stats=benchmark_operation(op);stats.update({"forward_calls":calls,"processed_tokens":tokens,"targets":30,"seconds_per_target":stats["wall_seconds_mean"]/30,"tokens_per_second":tokens/stats["wall_seconds_mean"],"output_attention_elements":output_elements[name],"output_attention_bytes_fp32":output_elements[name]*4});result[str(n)][name]=stats
  base=result[str(n)]["packed"]["wall_seconds_mean"]
  for name in result[str(n)]:result[str(n)][name]["packed_speedup_vs_method"]=result[str(n)][name]["wall_seconds_mean"]/base
 return result
def del_output(out):del out
def main():
 if os.environ.get("CUDA_VISIBLE_DEVICES")!="4" or os.environ.get("HF_HUB_OFFLINE")!="1" or os.environ.get("TRANSFORMERS_OFFLINE")!="1":raise RuntimeError("offline GPU4 required")
 if file_sha256(CHECKPOINT)!=EXPECTED:raise RuntimeError("checkpoint mismatch")
 by_size,sources=load_view(DATA);selected=select_examples(by_size[32]);(OUT/"pairwise_selected_targets.json").write_text(json.dumps({"selection_seed":"memoryflow-c4a-pairwise-v1","single_positive":15,"multi_positive":15,"target_group_ids":[e["target_group_id"] for e in selected]},indent=2)+"\n")
 packed={r["target_group_id"]:r for r in load_jsonl(OUT/"per_example_primary.jsonl") if r["method"]=="trained_anchor_last8" and r["candidate_size"]==32 and r["target_group_id"] in {e["target_group_id"] for e in selected}}
 tokenizer=AutoTokenizer.from_pretrained(MODEL,local_files_only=True);model=AutoModelForCausalLM.from_pretrained(MODEL,local_files_only=True,dtype=torch.float32,attn_implementation="eager").to("cuda").eval().requires_grad_(False);anchor=load_file(CHECKPOINT)["trainable_anchor"].to("cuda");torch.cuda.reset_peak_memory_stats();started=time.perf_counter()
 pair,comparison=score_pairwise(model,tokenizer,anchor,selected,sources,packed);pair_metrics=aggregate([r["metrics"] for r in pair]);packed_metrics=aggregate([packed[e["target_group_id"]]["metrics"] for e in selected]);comparison.update({"target_count":30,"single_positive":15,"multi_positive":15,"pairwise_metrics":pair_metrics,"packed32_metrics":packed_metrics,"checkpoint_sha256":file_sha256(CHECKPOINT),"same_anchor":True})
 (OUT/"pairwise_comparison.json").write_text(json.dumps(comparison,indent=2)+"\n");(OUT/"pairwise_per_example.jsonl").write_text("".join(json.dumps(r,ensure_ascii=False,separators=(",",":"))+"\n" for r in pair))
 eff=efficiency(model,tokenizer,anchor,selected,sources,by_size);(OUT/"efficiency_results.json").write_text(json.dumps(eff,indent=2)+"\n");summary={"elapsed_seconds":time.perf_counter()-started,"peak_memory_bytes":torch.cuda.max_memory_allocated(),"checkpoint_unchanged":file_sha256(CHECKPOINT)==EXPECTED};(OUT/"pairwise_efficiency_integrity.json").write_text(json.dumps(summary,indent=2)+"\n");print(json.dumps({"comparison":comparison,"efficiency":eff,"summary":summary},indent=2))
 del model,anchor;gc.collect();torch.cuda.empty_cache()

if __name__=="__main__":main()
