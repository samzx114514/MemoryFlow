"""Complete the approved native-context batch, retaining the fixed compatible core."""
import hashlib
import json
import re
import time
from collections import Counter
from pathlib import Path

from transformers import AutoTokenizer

from analysis_inputs import MODELS, ROOT, classify, scan
from pipeline import model_context_limit, render, write


def prepare(output):
    output.mkdir(exist_ok=True)
    core=ROOT/"compatibility_native32_13/formal_inputs.json"
    core_items=json.loads(core.read_text())
    accepted={x["input_sha256"]:x for x in core_items}
    core_hashes=set(accepted)
    if (output/"accepted_calls.json").exists():
        accepted.update({x["input_sha256"]:x for x in json.loads((output/"accepted_calls.json").read_text())})
    tokenizers={model.name:AutoTokenizer.from_pretrained(model,local_files_only=True) for model in MODELS}
    limits={model.name:min(65536,model_context_limit(json.loads((model/"config.json").read_text()))) for model in MODELS}
    write(output/"selection_lock.json",{"core_sha256":hashlib.sha256(core.read_bytes()).hexdigest(),
          "context_limits":limits,"max_tokens":2048,"temperature":0,"seed":0,
          "selection":"domain-result or material-complete analysis input; at most three calls per source task; no attribution scores"})
    cache={}
    material=json.loads((ROOT/"clause_material_ready_candidates.json").read_text())
    preferred={x["input_sha256"] for x in json.loads((ROOT/"experiment1_analysis_v1/eligible_calls.json").read_text())}
    preferred.update(p.stem for p in (ROOT/"stage_manual_reviews").glob("*.json"))
    while True:
        pool=scan(ROOT)
        for entry in material:
            source=Path(entry["source"])
            if hashlib.sha256(source.read_bytes()).hexdigest()!=entry["source_sha256"]:
                raise ValueError("Material-ready source changed")
            record=json.loads(source.read_text())
            request={"messages":record["request"]["messages"],"tools":record["request"].get("tools")}
            key=hashlib.sha256(json.dumps(request,sort_keys=True).encode()).hexdigest()
            task=json.loads((source.parents[2]/"command.json").read_text())["task"]["id"]
            pool[key]={"input_sha256":key,"benchmark":"clause","task_id":task,"source":str(source),
                       "source_sha256":entry["source_sha256"],"request":request,"full_materials":entry["full_materials"]}
        counts=Counter(x["benchmark"] for x in accepted.values())
        per_task=Counter(x["task_id"] for x in accepted.values())
        ordered=sorted(pool.values(),key=lambda x:(not (x["input_sha256"] in preferred or x.get("full_materials") or x.get("input_stage_review")),
                       hashlib.sha256(("mf11-native32:"+x["input_sha256"]).encode()).hexdigest()))
        for item in ordered:
            key=item["input_sha256"];bench=item["benchmark"]
            if key in accepted or counts[bench]>=10 or per_task[item["task_id"]]>=3 or cache.get(key) is False:
                continue
            if bench=="nba" and key not in preferred and not item.get("input_stage_review"):
                body=item.get("public_output","").split("\nTOOL CALLS:")[0].removeprefix("CONTENT:\n").strip()
                report=any(mark in item.get("public_output","") for mark in ('"name": "write','"name": "sp_finish','<function=sp_finish>'))
                if not report and (body.startswith("<tool_call>") or not re.search(r"\$\s*\d|Answer:|Operation\s+[A-Z]|Player\s+[A-Z]|COMPLIANT|VIOLATION|^(True|False)$",body)):
                    cache[key]=False
                    continue
            if key not in cache:
                short=MODELS[1].name
                lengths={short:len(render(tokenizers[short],item["request"],None,only_ids=True)[0])}
                if lengths[short]+2048>limits[short]:
                    cache[key]=False
                    continue
                lengths.update({name:len(render(tok,item["request"],None,only_ids=True)[0])
                                for name,tok in tokenizers.items() if name!=short})
                if any(lengths[name]+2048>limits[name] for name in lengths):
                    cache[key]=False
                    continue
                if item.get("input_stage_review"):
                    decision=item["input_stage_review"]
                elif item.get("full_materials"):
                    decision={"is_analysis_result":True,"reason":"Complete document is already present in the actual coder analysis input",
                              "full_materials":item["full_materials"],"source_sha256":item["source_sha256"]}
                else:
                    try:
                        print("stage",bench,item["source"],flush=True)
                        decision=classify(item,output,"http://127.0.0.1:8770","/data/Qwen3.8-27B")
                    except (ValueError,KeyError) as error:
                        write(output/"stage_errors"/(key+".json"),{"error":str(error)})
                        cache[key]=False
                        continue
                if not decision["is_analysis_result"]:
                    cache[key]=False
                    continue
                cache[key]={**item,"prompt_tokens":lengths,"stage_review":decision}
            item=cache[key]
            accepted[key]=item;counts[bench]+=1;per_task[item["task_id"]]+=1
            write(output/"accepted_calls.json",list(accepted.values()))
            print("accepted",dict(counts),flush=True)
        if all(counts[bench]==10 for bench in ("nba","clause","finauditing")):
            break
        write(output/"selection_status.json",{"accepted":dict(counts),"waiting_for":"native-context analysis calls"})
        time.sleep(10)
    items=list(accepted.values())
    for bench in ("nba","clause","finauditing"):
        used={x["id"] for x in core_items if x["benchmark"]==bench}
        available=iter(f"{bench}-{n:02d}" for n in range(1,11) if f"{bench}-{n:02d}" not in used)
        for item in items:
            if item["benchmark"]==bench and item["input_sha256"] not in core_hashes:item["id"]=next(available)
    items=[{k:v for k,v in x.items() if k!="public_output"} for x in items]
    items.sort(key=lambda x:x["id"])
    write(output/"formal_inputs.json",items)
    write(output/"added17_inputs.json",[x for x in items if x["input_sha256"] not in core_hashes])
    write(output/"formal_lock.json",{"sha256":hashlib.sha256((output/"formal_inputs.json").read_bytes()).hexdigest(),
          "distribution":dict(Counter(x["benchmark"] for x in items)),"context_limits":limits,"max_tokens":2048,
          "temperature":0,"seed":0,"reused_core_calls":13,"added_calls":17,
          "source_tasks":dict(Counter(x["task_id"] for x in items))})
    print("frozen native-compatible 30",flush=True)


if __name__=="__main__":
    import argparse
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output",type=Path)
    prepare(parser.parse_args().output)
