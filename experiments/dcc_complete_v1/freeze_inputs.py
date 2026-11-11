"""Freeze 30 source-bearing DCC inputs before generating the evaluated answers."""
import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path

from transformers import AutoTokenizer

from pipeline import author_functions, render, write


def freeze(root):
    developer=json.loads((root/"development.json").read_text())
    excluded={item["source"] for item in developer}
    earlier=Path("/data1/songzhengxing_intern_dccv2/mf_yf_batch12_20261109")
    pools={"nba":[],"clause":[],"finauditing":[]}
    for task in json.loads((earlier/"frozen.json").read_text())["jobs"]:
        if task["job"] in {"nba-03","clause-02"}:
            continue
        for path in sorted((earlier/"jobs"/task["job"]/"wire").glob("*.request.json")):
            pools[task["family"]].append((path,task["task_id"]))
    for path in sorted((root/"fin-wire").glob("*.request.json")):
        pools["finauditing"].append((path,"finauditing-files-development-collection"))
    tokenizer=AutoTokenizer.from_pretrained("/data/Qwen3.8-27B-FP8",local_files_only=True)
    functions=author_functions(tokenizer)
    selected=[]
    for benchmark,pool in pools.items():
        candidates=[]
        seen=set()
        for path,task_id in pool:
            if str(path) in excluded or not path.with_name(path.name.replace(".request.json",".response.json")).is_file():
                continue
            original=json.loads(path.read_text())
            request=original["request"]
            if not any(m["role"]=="tool" and len(m.get("content") or "")>=500 for m in request["messages"]):
                continue
            prompt={"messages":request["messages"],"tools":request.get("tools")}
            digest=hashlib.sha256(json.dumps(prompt,sort_keys=True).encode()).hexdigest()
            if digest in seen:
                continue
            seen.add(digest)
            candidates.append((hashlib.sha256(("mf11-formal:"+digest).encode()).hexdigest(),path,task_id,prompt,digest))
        for _,path,task_id,prompt,digest in sorted(candidates):
            try:
                ids,sources=render(tokenizer,prompt,functions)
            except (ValueError,AssertionError):
                continue
            if not 1000<=len(ids)<=20000 or len(sources)<4:
                continue
            selected.append({"id":f"{benchmark}-{sum(r['benchmark']==benchmark for r in selected)+1:02d}",
                             "benchmark":benchmark,"task_id":task_id,"source":str(path),
                             "source_file_sha256":hashlib.sha256(path.read_bytes()).hexdigest(),
                             "input_sha256":digest,"prompt_tokens_27b":len(ids),"request":prompt})
            if sum(r["benchmark"]==benchmark for r in selected)==10:
                break
    count=Counter(r["benchmark"] for r in selected)
    if count!={"nba":10,"clause":10,"finauditing":10}:
        raise SystemExit(f"Input collection pending: {dict(count)}")
    destination=root/"formal_inputs.json"
    if destination.exists():
        raise FileExistsError(destination)
    write(destination,selected)
    write(root/"formal_lock.json",{
        "sha256":hashlib.sha256(destination.read_bytes()).hexdigest(),"distribution":dict(count),
        "dcc_commit":"1fa314da6ac6e5997d2f464d80120fd9540c102e","outputs_per_call":1,"max_tokens":1024,
        "selection":"seeded SHA order among source-bearing calls, 1000..20000 Qwen3.8 prompt tokens",
        "pilot_tasks_excluded":["rulearena-nba-comp0-028","nli_omission_bc25415a4a1d63a7"],
    })
    print(dict(count),flush=True)


if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("root",type=Path)
    args=p.parse_args()
    freeze(args.root)
