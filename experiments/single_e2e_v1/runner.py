"""Independent generation-to-citation measurements for the frozen E1 inputs."""
import argparse
import asyncio
from collections import defaultdict
import hashlib
import json
import os
from pathlib import Path
import statistics
import threading
import time


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def interval_union(intervals):
    merged=[]
    for start,end in sorted(intervals):
        if merged and start<=merged[-1][1]:
            merged[-1][1]=max(merged[-1][1],end)
        else:
            merged.append([start,end])
    return sum(end-start for start,end in merged)


def locate(text, reference, targets):
    found, missing = [], []
    for index, target in enumerate(targets):
        phrase = target["text"]
        a, b = target["span"]
        if reference[a:b] != phrase:
            raise ValueError("Frozen target span differs from original output")
        if text == reference:
            found.append({"index":index,"span":[a,b],"text":phrase})
            continue
        hits, start = [], 0
        while True:
            at = text.find(phrase, start)
            if at < 0:
                break
            hits.append(at)
            start = at+1
        if len(hits)==1:
            a = hits[0]
        elif hits and len(hits)==reference.count(phrase):
            occurrence = reference[:target["span"][0]].count(phrase)
            a = hits[occurrence]
        else:
            missing.append({"index":index,"reason":"absent" if not hits else "ambiguous_after_regeneration"})
            continue
        found.append({"index":index,"span":[a,a+len(phrase)],"text":phrase})
    return found, missing


class MemorySampler:
    """Count only the one shared model service and its descendants."""
    def __init__(self, gpu, server_pid, output):
        import psutil
        import pynvml as nv
        self.nv, self.psutil, self.pid = nv, psutil, server_pid
        nv.nvmlInit()
        self.handle = nv.nvmlDeviceGetHandleByIndex(gpu)
        name = nv.nvmlDeviceGetName(self.handle)
        uuid = nv.nvmlDeviceGetUUID(self.handle)
        self.identity = {"index":gpu,"name":str(name),"uuid":str(uuid),"server_pid":server_pid,
                         "cards":1,"method":"NVML unique process IDs in the model-server process tree"}
        self.file, self.done = output, threading.Event()
        self.rows, self.error, self.allowed = [], None, set()

    def sample(self):
        process = self.psutil.Process(self.pid)
        self.allowed.update([self.pid, *[p.pid for p in process.children(recursive=True)]])
        usage = {int(p.pid):int(p.usedGpuMemory) for p in self.nv.nvmlDeviceGetComputeRunningProcesses(self.handle)
                 if p.usedGpuMemory is not None and int(p.usedGpuMemory)<2**63}
        selected = {str(pid):value for pid,value in usage.items() if pid in self.allowed}
        row = {"time":time.time(),"process_bytes":selected,"total_bytes":sum(selected.values()),
               "excluded_process_bytes":{str(p):v for p,v in usage.items() if p not in self.allowed}}
        self.rows.append(row)
        return row

    def start(self):
        self.file.parent.mkdir(parents=True, exist_ok=True)
        self.stream = self.file.open("x",encoding="utf-8",buffering=1)
        self.stream.write(json.dumps(self.sample())+"\n")
        def loop():
            try:
                while not self.done.wait(.1):
                    self.stream.write(json.dumps(self.sample())+"\n")
            except Exception as error:
                self.error = str(error)
        self.thread = threading.Thread(target=loop,daemon=True)
        self.thread.start()

    def finish(self):
        self.done.set()
        self.thread.join()
        self.stream.write(json.dumps(self.sample())+"\n")
        self.stream.close()
        if self.error:
            raise RuntimeError(self.error)
        return {**self.identity,"peak_bytes":max(r["total_bytes"] for r in self.rows),
                "per_card_peak_bytes":{str(self.identity['index']):max(r['total_bytes'] for r in self.rows)},
                "sample_count":len(self.rows),"owned_process_ids":sorted(self.allowed),
                "sampling_interval_seconds":.1,"trace_sha256":sha(self.file)}


def paired(yf, mf):
    common = sorted(set(yf["located_target_ids"]) & set(mf["located_target_ids"]))
    count = len(common)
    return {"common_target_ids":common,"common_targets":count,
            "yf_seconds_per_common_target":yf["wall_seconds"]/count if count else None,
            "mf_seconds_per_common_target":mf["wall_seconds"]/count if count else None,
            "same_output_tokens_calls":sum(yf['output_tokens_by_call'][k]==mf['output_tokens_by_call'][k]
                                           for k in yf['output_tokens_by_call'] if k in mf['output_tokens_by_call']),
            "planned_targets":yf['planned_targets']}


async def route(jobs, model, tokenizer, functions, output, method, gpu, server_pid):
    import numpy as np
    from pipeline import HEADS, URL, cite, offsets, reduce, send, send_batch, token_span
    from measure_capture import plain
    output.mkdir()
    sampler = MemorySampler(gpu,server_pid,output/"memory.jsonl")
    slots, cpu_slots = asyncio.Semaphore(4), asyncio.Semaphore(2)
    queue, processing = asyncio.Queue(), []
    records, batches = {}, []
    def process(job, generated, signal):
        begin = time.time()
        folder = output/job['id']
        text, offset = offsets(tokenizer,generated)
        found, missing = locate(text,job['reference_text'],job['targets'])
        mapped = time.time()
        matrix, header = reduce(signal/'capture',len(job['prompt_ids']),len(generated),job['sources'])
        expected = HEADS[Path(model).name]
        if (header['config']['target_layer'],header['config']['target_query_head'])!=expected:
            raise ValueError("Head differs from frozen E1 configuration")
        reduced = time.time()
        np.save(folder/'matrix.npy',matrix,allow_pickle=False)
        intervals = [token_span(offset,*target['span']) for target in found]
        if any(r is None for r in intervals):
            raise ValueError("Located target lacks generated-token rows")
        citations = cite(matrix,intervals,functions,job['sources']) if found else []
        write(folder/'citations.json',{'targets':[{**t,'citation':c} for t,c in zip(found,citations,strict=True)],
                                     'missing_frozen_targets':missing,'output_tokens':len(generated)})
        ready = time.time()
        row = {'id':job['id'],'status':'complete','generation':records[job['id']]['generation'],
               'mapping_seconds':mapped-begin,'reduction_seconds':reduced-mapped,
               'storage_and_citation_seconds':ready-reduced,'processing_interval':[begin,ready],
               'citation_ready':ready,'located_target_ids':[f"{job['id']}:{t['index']}" for t in found],
               'missing_targets':missing,'input_tokens':len(job['prompt_ids']),'output_tokens':len(generated),
               'matches_frozen_tokens':generated==job['reference_ids'], 'output_tokens_sha256':hashlib.sha256(json.dumps(generated).encode()).hexdigest(),
               'head':header['config'],'actual_gpu_batches':header['gpu_batches']}
        write(folder/'stage_timing.json',row)
        records[job['id']]=row

    async def process_async(job, generated, signal):
        try:
            async with cpu_slots:
                await asyncio.to_thread(process,job,generated,signal)
        except Exception as error:
            records[job['id']].update(status='failed',error=type(error).__name__+': '+str(error))
            write(output/job['id']/'failure.json',records[job['id']])

    async def replay_worker():
        while True:
            first=await queue.get()
            if first is None:
                return
            second=await queue.get()
            batch=[first] if second is None else [first,second]
            payloads=[{'prompt':j['prompt_ids']+g[:-1],'max_tokens':1,'temperature':0,'seed':0} for j,g in batch]
            destinations=[output/j['id']/'mf' for j,g in batch]
            for _ in batch:
                await slots.acquire()
            begin=time.time()
            try:
                if len(batch)==2:
                    await asyncio.to_thread(send_batch,payloads,destinations)
                else:
                    await asyncio.to_thread(send,payloads[0],destinations[0])
                batches.append({'calls':[j['id'] for j,g in batch],'interval':[begin,time.time()]})
                processing.extend(asyncio.create_task(process_async(j,g,p)) for (j,g),p in zip(batch,destinations))
            except Exception as error:
                for job,_ in batch:
                    records[job['id']].update(status='failed',error=type(error).__name__+': '+str(error))
                    write(output/job['id']/'failure.json',records[job['id']])
            finally:
                for _ in batch:
                    slots.release()
            if second is None:
                return

    async def generate(job):
        dest=output/job['id']/('yf' if method=='yf' else 'gen')
        async with slots:
            begin=time.time()
            records[job['id']]={'id':job['id'],'status':'generating','generation':[begin,None]}
            try:
                if method=='yf':
                    receipt=await asyncio.to_thread(send,job['generation_params']|{'prompt':job['prompt_ids']},dest)
                else:
                    await asyncio.to_thread(plain,job['generation_params']|{'prompt':job['prompt_ids']},dest)
                    receipt=read(dest/'response.json')
                generated=receipt['choices'][0]['token_ids']
                if not generated:
                    raise ValueError("Generation returned no tokens")
                timing=read(dest/'timing.json')
                records[job['id']]['generation']=[timing['start'],timing['end']]
                records[job['id']].update(generated_output_tokens=len(generated),
                    output_tokens_sha256=hashlib.sha256(json.dumps(generated).encode()).hexdigest(),
                    matches_frozen_tokens=generated==job['reference_ids'])
                if method=='yf':
                    processing.append(asyncio.create_task(process_async(job,generated,dest)))
                else:
                    queue.put_nowait((job,generated))
            except Exception as error:
                records[job['id']].update(status='failed',error=type(error).__name__+': '+str(error),generation=[begin,time.time()])
                write(output/job['id']/'failure.json',records[job['id']])

    sampler.start()
    try:
        worker=asyncio.create_task(replay_worker()) if method=='mf' else None
        for start in range(0,len(jobs),2):
            await asyncio.gather(*(generate(job) for job in jobs[start:start+2]))
        if worker:
            queue.put_nowait(None)
            await worker
        await asyncio.gather(*processing)
        ended=time.time()
    finally:
        memory=sampler.finish()
    first=min(r['generation'][0] for r in records.values())
    ready=max((r.get('citation_ready',r['generation'][1]) for r in records.values()))
    complete=[r for r in records.values() if r['status']=='complete']
    if memory['peak_bytes']<2**30:
        raise ValueError("NVML did not identify the resident model worker")
    summary={'method':method,'first_generation_request':first,'all_references_ready':ready,
             'wall_seconds':ready-first,'controller_finished':ended,'calls':len(jobs),'completed_calls':len(complete),
             'planned_targets':sum(len(j['targets']) for j in jobs),
             'located_target_ids':[t for r in complete for t in r['located_target_ids']],
             'input_tokens':sum(len(j['prompt_ids']) for j in jobs),
             'generated_output_tokens':sum(r.get('generated_output_tokens',r.get('output_tokens',0)) for r in records.values()),
             'output_tokens_by_call':{r['id']:r['output_tokens_sha256'] for r in records.values() if 'output_tokens_sha256' in r},
             'matches_frozen_output_calls':sum(r['matches_frozen_tokens'] for r in complete),
             'failed_calls':[r for r in records.values() if r['status']!='complete'],
             'memory':memory,'replay_batches':batches,
             'cpu_component_sums':{k:sum(r[k] for r in complete) for k in ['mapping_seconds','reduction_seconds','storage_and_citation_seconds']},
             'component_interval_unions':{'generation':interval_union([r['generation'] for r in records.values()]),
                 'replay':interval_union([r['interval'] for r in batches]),
                 'cpu_processing':interval_union([r['processing_interval'] for r in complete])},
             'settings':{'cards':1,'shared_weight_service':True,'generation_concurrency':2,'replay_batch_size':2,
                         'total_request_budget':4,'cpu_processing_workers':2,'server_max_sequences':4},
             'timing_note':'Actual wall interval, not the sum of overlapping stage times; all 30 generations included even without frozen factual targets.'}
    write(output/'summary.json',summary)
    return summary


async def main(args):
    from transformers import AutoTokenizer
    from pipeline import author_functions, offsets, validate_model
    info=validate_model(args.model)
    original=Path(args.formal)
    gold=read(args.gold)
    if sha(original/'inputs.json')!=gold['inputs_sha256'] or sha(original/'identity.json')!=gold['identity_sha256']:
        raise ValueError("Frozen input or annotation identity changed")
    tok=AutoTokenizer.from_pretrained(args.model,local_files_only=True)
    functions=author_functions(tok)
    labels={c['id']:c for c in gold['calls']}
    jobs=[]
    for item in read(original/'inputs.json'):
        receipt=read(original/item['id']/'yf/response.json')
        ids=receipt['choices'][0]['token_ids']
        request=read(original/item['id']/'yf/request.json')
        parameters={k:v for k,v in request.items() if k not in ['prompt','vllm_xargs','model','return_token_ids']}
        if parameters.get('temperature')!=0 or parameters.get('seed')!=0 or parameters.get('max_tokens')!=2048:
            raise ValueError("Frozen generation settings differ from planned E1")
        jobs.append({**item,'targets':labels[item['id']]['targets'],'reference_ids':ids,
                     'reference_text':offsets(tok,ids)[0],'generation_params':parameters})
    args.output.mkdir(parents=True)
    write(args.output/'identity.json',{'formal_inputs_sha256':sha(original/'inputs.json'),'gold_sha256':sha(args.gold),
          'model':args.model,'server_models':info,'gpu':args.gpu,'server_pid':args.server_pid,
          'calls':len(jobs),'planned_targets':sum(len(j['targets']) for j in jobs),
          'code_sha256':sha(Path(__file__)),'end_to_end_endpoint':'generation request to persisted citations ready'})
    pilot=[j for j in jobs if j['id'] in ['finauditing-01','finauditing-02']]
    if len(pilot)!=2:
        raise ValueError("Preflight must use the two fixed FinAuditing inputs")
    warm={}
    for method in ['yf','mf']:
        warm[method]=await route(pilot,args.model,tok,functions,args.output/f'preflight_{method}',method,args.gpu,args.server_pid)
    check=paired(warm['yf'],warm['mf'])
    write(args.output/'preflight_pair.json',check)
    if any(v['completed_calls']!=2 for v in warm.values()) or not check['common_targets']:
        raise ValueError("Paired preflight did not produce locatable common targets")
    print('PREFLIGHT',json.dumps(check),flush=True)
    trials=[]
    for repeat in range(3):
        pair={}
        for method in (['yf','mf'] if repeat%2==0 else ['mf','yf']):
            pair[method]=await route(jobs,args.model,tok,functions,args.output/f'{repeat}_{method}',method,args.gpu,args.server_pid)
            print('ROUTE',repeat,method,pair[method]['wall_seconds'],len(pair[method]['located_target_ids']),flush=True)
        trials.append({'repeat':repeat,'pair':paired(pair['yf'],pair['mf']),'routes':pair})
        write(args.output/'progress.json',{'completed_pairs':len(trials),'last':trials[-1]})
    table=[]
    for method in ['yf','mf']:
        complete=[t for t in trials if t['routes'][method]['completed_calls']==len(jobs) and t['pair']['common_targets']]
        table.append({'method':method,'measured_repeats':3,'complete_repeats':len(complete),
                      'seconds_per_target':statistics.median(t['pair'][f'{method}_seconds_per_common_target'] for t in complete) if complete else None,
                      'batch_wall_seconds':statistics.median(t['routes'][method]['wall_seconds'] for t in complete) if complete else None,
                      'peak_gib':statistics.median(t['routes'][method]['memory']['peak_bytes']/2**30 for t in complete) if complete else None,
                      'cards':1,'calls':len(jobs),'planned_targets':sum(len(j['targets']) for j in jobs),
                      'paired_target_counts':[t['pair']['common_targets'] for t in trials]})
    write(args.output/'results.json',{'table':table,'trials':trials,'preflight':check,
          'denominator':'Exact frozen targets locatable in both routes of each repeat; absent/ambiguous targets retained as missing, never silently counted.'})


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ['formal','gold','output']:
        p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--model',required=True)
    p.add_argument('--gpu',type=int,required=True)
    p.add_argument('--server-pid',type=int,required=True)
    asyncio.run(main(p.parse_args()))
