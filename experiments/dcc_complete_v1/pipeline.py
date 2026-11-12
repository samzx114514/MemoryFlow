"""Exact-token DCC generation, full-call replay and shared author citations."""
import ast
import asyncio
import bisect
import hashlib
import json
import os
import shutil
import csv
import subprocess
import sys
import threading
import time
import uuid
from pathlib import Path
from urllib.request import Request, urlopen

import numpy as np
from safetensors.torch import load_file
from transformers import AutoTokenizer
from transformers.models.gpt2.tokenization_gpt2 import bytes_to_unicode

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from provenance_v2.span_views import views

AUTHOR = Path("/data1/songzhengxing_intern_dccv2/yf_driver/client_frozen.py")
URL = os.environ.get("MF_URL", "http://127.0.0.1:8781/v1/completions")
HEADS = {"Qwen3.8-27B-FP8": (51, 20), "Qwen2.5-7B-Instruct": (19, 15),
         "Qwen2.5-1.5B-Instruct": (16, 2)}


def validate_model(model, endpoint=URL):
    with urlopen(endpoint.rsplit("/v1/", 1)[0]+"/v1/models", timeout=10) as response:
        info = json.load(response)
    if not any(Path(item["root"]).resolve() == Path(model).resolve() for item in info["data"]):
        raise ValueError("Serving weights do not match the requested replay model")
    return info


def check_budget(call_id, prompt_tokens, output_tokens, context_limit):
    if prompt_tokens+output_tokens>context_limit:
        raise ValueError(f"{call_id}: {prompt_tokens} prompt + {output_tokens} output tokens exceed the configured model limit {context_limit}")


def model_context_limit(config):
    return config.get("text_config",config)["max_position_embeddings"]


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def author_functions(tokenizer):
    import re
    from nltk.tokenize import PunktSentenceTokenizer
    tree = ast.parse(AUTHOR.read_text())
    names = {"detect_language", "split_text_into_sentences", "_merge_short_segments"}
    definitions = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in names]
    build = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "build_citations")
    start = next(i for i, n in enumerate(build.body)
                 if isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "citations" for t in n.targets))
    select = ast.FunctionDef(name="select_citations",
        args=ast.arguments(posonlyargs=[], args=[ast.arg(arg="response_clauses"), ast.arg(arg="clause_matrix"), ast.arg(arg="input_sentences")],
                           kwonlyargs=[], kw_defaults=[], defaults=[]),
        body=build.body[start:], decorator_list=[])
    namespace = {"np": np, "re": re, "PunktSentenceTokenizer": PunktSentenceTokenizer, "tokenizer": tokenizer}
    module = ast.fix_missing_locations(ast.Module(body=definitions + [select], type_ignores=[]))
    exec(compile(module, str(AUTHOR), "exec"), namespace)
    return namespace


def spans(text, functions):
    language = functions["detect_language"](text)
    sentences = functions["split_text_into_sentences"](text, language)
    cursor = 0
    ranges = []
    for sentence in sentences:
        left = text.find(sentence, cursor)
        if left < 0:
            raise ValueError("Author sentence cannot be mapped to the original text")
        ranges.append((left, left + len(sentence)))
        cursor = ranges[-1][1]
    _, merged = functions["_merge_short_segments"](sentences, ranges, language)
    return merged


def offsets(tokenizer, ids):
    text = tokenizer.decode(ids, clean_up_tokenization_spaces=False)
    encoded = tokenizer(text, add_special_tokens=False, return_offsets_mapping=True)
    if encoded.input_ids == ids:
        return text, encoded.offset_mapping
    decoder = {v:k for k,v in bytes_to_unicode().items()}
    chunks = [token.encode() if token_id in tokenizer.all_special_ids else bytes(decoder[c] for c in token)
              for token_id, token in zip(ids, tokenizer.convert_ids_to_tokens(ids), strict=True)]
    assert b"".join(chunks).decode() == text
    boundaries = [0]
    for char in text:
        boundaries.append(boundaries[-1] + len(char.encode()))
    total = 0
    result = []
    for chunk in chunks:
        result.append((bisect.bisect_right(boundaries,total)-1,
                       bisect.bisect_left(boundaries,total+len(chunk))))
        total += len(chunk)
    return text, result


def token_span(offsets_, left, right):
    positions = [i for i,(a,b) in enumerate(offsets_) if b > left and a < right]
    if not positions:
        return None
    return [positions[0],positions[-1]+1]


def render(tokenizer, request, functions, only_ids=False):
    messages = []
    for raw in request["messages"]:
        msg = {**raw, "content":raw.get("content") or ""}
        if msg.get("tool_calls"):
            tools=[]
            for tool in msg["tool_calls"]:
                fn=dict(tool.get("function") or {"name":tool["name"],"arguments":tool.get("args",{})})
                if isinstance(fn.get("arguments"),str):
                    fn["arguments"]=json.loads(fn["arguments"])
                tools.append({**tool,"function":fn})
            msg["tool_calls"]=tools
        messages.append(msg)
    kwargs={"tokenize":False,"add_generation_prompt":True,"tools":request.get("tools") or None,
            "enable_thinking":False}
    prompt=tokenizer.apply_chat_template(messages,**kwargs)
    ids=tokenizer(prompt,add_special_tokens=False).input_ids
    if only_ids:
        return ids,[]
    _, prompt_offsets=offsets(tokenizer,ids)
    marked=[]
    markers={}
    for i,msg in enumerate(messages):
        m=dict(msg)
        if msg["content"]:
            prefix,suffix=f"MF11Open{i}v983q",f"MF11Close{i}v983q"
            body=msg["content"]
            begin=len(body)-len(body.lstrip())
            end=len(body.rstrip())
            m["content"]=body[:begin]+prefix+body[begin:end]+suffix+body[end:]
            markers[i]=(prefix,suffix)
        marked.append(m)
    probe=tokenizer.apply_chat_template(marked,**kwargs)
    sources=[]
    for i,(prefix,suffix) in markers.items():
        left=probe.index(prefix)
        end=probe.index(suffix)
        body=probe[left+len(prefix):end]
        assert body == messages[i]["content"].strip()
        probe=probe[:left]+body+probe[end+len(suffix):]
        if messages[i]["role"]=="system":
            continue
        structured=body.lstrip().startswith(("{","[")) or "<sp-subagent-task>" in body
        for view in views(body,structured=structured):
            for a,b in spans(view.text,functions):
                raw_a,raw_b=view.span(a,b)
                interval=token_span(prompt_offsets,left+raw_a,left+raw_b)
                if interval:
                    leading=len(messages[i]["content"])-len(messages[i]["content"].lstrip())
                    sources.append({"source_id":f"m{i}:{raw_a}:{raw_b}","message_index":i,"role":messages[i]["role"],
                                    "span":[leading+raw_a,leading+raw_b],"prompt_span":[left+raw_a,left+raw_b],"token_span":interval,
                                    "text":body[raw_a:raw_b],"match_text":view.text[a:b],
                                    "match_offsets":[left+value for value in view.offsets[a:b+1]] if view.offsets is not None else None})
    assert probe == prompt
    return ids,sources


def send(payload, destination):
    run_id="mf11-"+uuid.uuid4().hex
    payload={**payload,"model":"mf-model","return_token_ids":True,
             "vllm_xargs":{"output_qk":"true","save_to_disk":"1","run_id":run_id,
                           "mf_phase":"replay" if destination.name=="mf" else "generation"}}
    start=time.time()
    req=Request(URL,json.dumps(payload).encode(),headers={"Content-Type":"application/json"})
    with urlopen(req,timeout=900) as response:
        result=json.load(response)
    artifact=Path("/dev/shm/vllm_hook")/run_id/"tp_rank_0"
    shutil.copytree(artifact,destination/"capture")
    write(destination/"request.json",payload)
    write(destination/"response.json",result)
    write(destination/"timing.json",{"start":start,"end":time.time(),"run_id":run_id})
    return result



def send_batch(payloads, destinations):
    run_id="mf11-batch-"+uuid.uuid4().hex
    assert len(payloads)==len(destinations)>=2
    payload={**payloads[0],"prompt":[p["prompt"] for p in payloads],"model":"mf-model",
             "return_token_ids":True,
             "vllm_xargs":{"output_qk":"true","save_to_disk":"1","run_id":run_id,
                           "mf_phase":"replay","mf_batch":1,"mf_batch_size":len(payloads)}}
    started=time.time()
    req=Request(URL,json.dumps(payload).encode(),headers={"Content-Type":"application/json"})
    with urlopen(req,timeout=900) as response:
        result=json.load(response)
    assert len(result["choices"])==len(payloads)
    artifacts=Path("/dev/shm/vllm_hook")/run_id/"tp_rank_0"
    for i,destination in enumerate(destinations):
        matches=[path for path in artifacts.iterdir()
                 if path.is_dir() and json.loads((path/"qk.json").read_text())["external_request_id"].endswith("-"+str(i))]
        if len(matches)!=1:
            raise ValueError(f"Cannot locate packed request {i}: {list(artifacts.iterdir())}")
        shutil.copytree(matches[0],destination/"capture")
        write(destination/"request.json",{**payload,"prompt":payloads[i]["prompt"],"batch_index":i})
        write(destination/"response.json",{**result,"choices":[result["choices"][i]]})
        write(destination/"timing.json",{"start":started,"end":time.time(),"run_id":run_id,"batch_index":i})
    return result

def reduce(artifact, p, t, sources):
    header=json.loads((artifact/"qk.json").read_text())
    data=load_file(artifact/"qk.safetensors")
    layer=header.get("layer_order",[{}])[0]
    q=data[layer.get("key_q","q")].float().numpy()
    k=data[layer.get("key_k","k")].float().numpy()
    q_start=header.get("query_position_start",p-1 if header.get("hookq_mode")=="last_token" else 0)
    first=p-1-q_start
    if first<0 or first+t>len(q) or len(k)<p+t-1:
        raise ValueError("Q/K does not cover every output prediction row")
    q=q[first:first+t]
    keys=np.arange(p+t-1)
    k=k[:p+t-1]
    ranges=[s["token_span"] for s in sources]
    left,right=np.array(ranges).T
    left=np.minimum(left,len(keys))
    right=np.minimum(right,len(keys))
    values=np.zeros((t,len(sources)),dtype=np.float32)
    for start in range(0,t,64):
        stop=min(t,start+64)
        logits=q[start:stop] @ k.T * header["config"]["attention_multiplier"]
        logits[keys[None,:] > p-1+np.arange(start,stop)[:,None]]=-np.inf
        weights=np.exp(logits-logits.max(axis=1,keepdims=True))
        weights/=weights.sum(axis=1,keepdims=True)
        prefix=np.pad(weights.cumsum(axis=1,dtype=np.float64),((0,0),(1,0)))
        values[start:stop]=prefix[:,right]-prefix[:,left]
    return values,header


def cite(matrix, clauses, functions, sources):
    scores=np.array([matrix[a:b].mean(axis=0,dtype=np.float64) for a,b in clauses])
    total=scores.sum(axis=1,keepdims=True)
    scores=np.divide(scores,total,out=np.zeros_like(scores),where=total>0)
    return functions["select_citations"]([str(i) for i in range(len(clauses))],scores,[source.get("match_text",source["text"]) for source in sources])


async def run_work(inputs, out, model, max_tokens):
    server_info=validate_model(model)
    tok=AutoTokenizer.from_pretrained(model,local_files_only=True)
    functions=author_functions(tok)
    entries=json.loads(inputs.read_text())
    model_limit=model_context_limit(json.loads((model/"config.json").read_text()))
    context_limit=min(model_limit,server_info["data"][0]["max_model_len"])
    jobs=[]
    for item in entries:
        ids,sources=render(tok,item["request"],functions)
        check_budget(item["id"],len(ids),max_tokens,context_limit)
        jobs.append({**item,"prompt_ids":ids,"sources":sources})
    out.mkdir()
    write(out/"inputs.json",jobs)
    write(out/"identity.json",{"model":str(model),"config_sha256":hashlib.sha256((model/"config.json").read_bytes()).hexdigest(),
                             "author_sha256":hashlib.sha256(AUTHOR.read_bytes()).hexdigest(),
                             "pipeline_sha256":hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                             "server_models":server_info,"context_limit":context_limit})
    queue=asyncio.Queue()
    async def replay_worker():
        while True:
            first=await queue.get()
            if first is None:
                return
            batch=[first]
            second=await queue.get()
            if second is None:
                queue.put_nowait(None)
            else:
                batch.append(second)
            async def replay_one(record):
                job,generated=record
                dest=out/job["id"]/"mf"
                tokens=job["prompt_ids"]+generated[:-1]
                return await asyncio.to_thread(send,{"prompt":tokens,"max_tokens":1,"temperature":0,"seed":0},dest)
            begin=time.time()
            if len(batch)>1:
                payloads=[{"prompt":job["prompt_ids"]+generated[:-1],"max_tokens":1,"temperature":0,"seed":0}
                          for job,generated in batch]
                await asyncio.to_thread(send_batch,payloads,[out/job["id"]/"mf" for job,_ in batch])
            else:
                await replay_one(batch[0])
            await asyncio.gather(*(asyncio.to_thread(process_job,out,tok,functions,job) for job,_ in batch))
            with (out/"pipeline.jsonl").open("a") as f:
                f.write(json.dumps({"calls":[j[0]["id"] for j in batch],"start":begin,"end":time.time()})+"\n")
    worker=asyncio.create_task(replay_worker())
    for index in range(0,len(jobs),2):
        async def generate(job):
            destination=out/job["id"]/"yf"
            result=await asyncio.to_thread(send,{"prompt":job["prompt_ids"],"max_tokens":max_tokens,
                                                "temperature":0,"seed":0},destination)
            generated=result["choices"][0]["token_ids"]
            queue.put_nowait((job,generated))
            return generated
        await asyncio.gather(*(generate(j) for j in jobs[index:index+2]))
    await queue.put(None)
    await worker
    finish(out,tok,functions,jobs)


def process_job(out,tok,functions,job):
    started=time.time()
    folder=out/job["id"]
    receipt=json.loads((folder/"yf/response.json").read_text())
    generated=receipt["choices"][0]["token_ids"]
    text,output_offsets=offsets(tok,generated)
    statements=spans(text,functions)
    clauses=[token_span(output_offsets,a,b) for a,b in statements]
    assert all(clauses)
    result={"id":job["id"],"benchmark":job["benchmark"],"output":text,
            "statements":[{"text":text[a:b],"span":[a,b],"tokens":c}
                          for (a,b),c in zip(statements,clauses,strict=True)],"methods":{}}
    for method in ("yf","mf"):
        matrix,header=reduce(folder/method/"capture",len(job["prompt_ids"]),len(generated),job["sources"])
        expected=HEADS[tok.name_or_path.rstrip("/").rsplit("/",1)[-1]]
        if (header["config"]["target_layer"],header["config"]["target_query_head"]) != expected:
            raise ValueError("Captured head differs from the frozen model configuration")
        np.save(folder/f"{method}.npy",matrix)
        result["methods"][method]={"citations":cite(matrix,clauses,functions,job["sources"]),
                                  "max_batch_size":max(x["batch_size"] for x in header["schedule"])}
    write(folder/"citations.json",result)
    print(job["id"],len(generated),len(statements),flush=True)
    write(folder/"reduction_timing.json",{"start":started,"end":time.time()})


def finish(out,tok,functions,jobs,force=False):
    for job in jobs:
        if force or not (out/job["id"]/"citations.json").exists():
            process_job(out,tok,functions,job)
    write(out/"completed.json",{"calls":len(jobs),"time":time.time()})


async def run(inputs, out, model, max_tokens):
    done=threading.Event()
    physical_gpu=int(os.environ.get("MF_GPU", "6"))
    memory_file=out.parent/(out.name+".memory.jsonl")
    def sample():
        with memory_file.open("x",buffering=1) as stream:
            while not done.is_set():
                command=["nvidia-smi","-i",str(physical_gpu),"--query-compute-apps=pid,used_gpu_memory",
                         "--format=csv,noheader,nounits"]
                data=subprocess.check_output(command,text=True)
                processes={pid.strip():int(mib.strip()) for pid,mib in csv.reader(data.splitlines())
                           if pid.strip().isdigit() and mib.strip().isdigit()}
                stream.write(json.dumps({"time":time.time(),"gpu":physical_gpu,"processes_mib":processes})+"\n")
                done.wait(.5)
    sampler=threading.Thread(target=sample)
    sampler.start()
    try:
        await run_work(inputs,out,model,max_tokens)
    finally:
        done.set()
        sampler.join()


if __name__=="__main__":
    import argparse
    p=argparse.ArgumentParser()
    for name in ("inputs","out","model"):
        p.add_argument(name,type=Path)
    p.add_argument("--max-tokens",type=int,default=512)
    p.add_argument("--reprocess",action="store_true")
    args=p.parse_args()
    if args.reprocess:
        tokenizer=AutoTokenizer.from_pretrained(args.model,local_files_only=True)
        finish(args.out,tokenizer,author_functions(tokenizer),json.loads((args.out/"inputs.json").read_text()),force=True)
    else:
        asyncio.run(run(args.inputs,args.out,args.model,args.max_tokens))
