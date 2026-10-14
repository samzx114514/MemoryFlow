#!/usr/bin/env python3
from __future__ import annotations
import argparse, json, os, socket, subprocess, time
from dataclasses import dataclass, asdict
from pathlib import Path

@dataclass(frozen=True)
class GpuInfo:
    index: int
    total_mib: int
    used_mib: int
    free_mib: int
    name: str = ""

def parse_gpu_csv(text: str):
    rows=[]
    for line in text.splitlines():
        if not line.strip(): continue
        parts=[x.strip() for x in line.split(',')]
        if len(parts)>=5:
            idx,total,free,used=int(parts[0]),int(parts[2]),int(parts[3]),int(parts[4]); name=parts[1]
        elif len(parts)==4:
            idx,total,used,free=map(int,parts); name=""
        else: raise ValueError(f"invalid GPU CSV row: {line}")
        rows.append(GpuInfo(idx,total,used,free,name))
    return rows

def choose_gpu(gpus, required_mib, claimed, override=None):
    if override is not None:
        m=next((g for g in gpus if g.index==override),None)
        if m is None or m.index in claimed or m.free_mib<required_mib:
            free=None if m is None else m.free_mib
            raise RuntimeError(f"override GPU {override} has only {free} MiB free")
        return m
    candidates=[g for g in gpus if g.index not in claimed and g.free_mib>=required_mib]
    if not candidates: raise RuntimeError(f"no GPU has required {required_mib} MiB free")
    return sorted(candidates,key=lambda g:(-g.free_mib,g.index))[0]

def live_pid(pid):
    try: os.kill(int(pid),0); return True
    except OSError: return False

def read_claimed_gpus(claim_dir, hostname=None):
    hostname=hostname or socket.gethostname(); claimed=set(); claim_dir=Path(claim_dir)
    for p in claim_dir.glob('*.json') if claim_dir.exists() else ():
        try: d=json.loads(p.read_text())
        except Exception: continue
        if d.get('hostname')!=hostname: continue
        if live_pid(d.get('pid',-1)): claimed.add(int(d['physical_gpu']))
    return claimed

def write_claim(claim_dir, hostname, pid, physical_gpu, job_id, required_mib):
    claim_dir=Path(claim_dir); claim_dir.mkdir(parents=True,exist_ok=True)
    data={'hostname':hostname,'pid':int(pid),'physical_gpu':int(physical_gpu),'required_mib':int(required_mib),'job_id':job_id,'claimed_at':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime())}
    path=claim_dir/(job_id+'.json'); fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o644)
    with os.fdopen(fd,'w') as f: json.dump(data,f,sort_keys=True,indent=2); f.write('\n')
    return path

def gpu_query():
    q=['nvidia-smi','--query-gpu=index,name,memory.total,memory.free,memory.used','--format=csv,noheader,nounits']
    return parse_gpu_csv(subprocess.check_output(q,text=True))

def process_query():
    q=['nvidia-smi','--query-compute-apps=gpu_uuid,pid,process_name,used_memory','--format=csv,noheader,nounits']
    try:
        return [x.strip() for x in subprocess.check_output(q,text=True).splitlines() if x.strip()]
    except Exception:
        return []

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--measured-peak-mib',type=int,required=True); ap.add_argument('--safety-margin-mib',type=int,required=True); ap.add_argument('--claim-dir',default='workspace/gpu_claims'); ap.add_argument('--override',type=int); ap.add_argument('--job-id',default='memoryflow-job')
    a=ap.parse_args(); required=a.measured_peak_mib+a.safety_margin_mib; host=socket.gethostname(); claimed=read_claimed_gpus(a.claim_dir,host); first=gpu_query(); chosen=choose_gpu(first,required,claimed,a.override); second=gpu_query(); chosen=choose_gpu(second,required,claimed,a.override)
    claim=write_claim(a.claim_dir,host,os.getpid(),chosen.index,a.job_id,required)
    out={'physical_gpu':chosen.index,'logical_gpu':('cuda:0' if os.environ.get('CUDA_VISIBLE_DEVICES') else None),'free_mib':chosen.free_mib,'required_mib':required,'external_processes':process_query(),'selected_at':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),'claim_path':str(claim),'gpu_inventory':[asdict(x) for x in second]}
    print(json.dumps(out,sort_keys=True))
if __name__=='__main__': main()
