"""Check replay isolation against serial and altered-neighbour executions."""
import asyncio
import json
import time
from pathlib import Path

import numpy as np

from pipeline import reduce, send, send_batch, write


async def check(run, output):
    jobs=json.loads((run/"inputs.json").read_text())
    assert len(jobs)==2
    requests=[]
    for job in jobs:
        receipt=json.loads((run/job["id"]/"yf/response.json").read_text())
        generated=receipt["choices"][0]["token_ids"]
        requests.append({"prompt":job["prompt_ids"]+generated[:-1],"max_tokens":1,"temperature":0,"seed":0})
    results={}
    output.mkdir()
    for i,request in enumerate(requests):
        await asyncio.to_thread(send,request,output/f"serial{i}")
    await asyncio.to_thread(send_batch,requests,[output/f"packed{i}" for i in range(2)])
    altered={**requests[1],"prompt":requests[1]["prompt"][:16]+requests[1]["prompt"][16:][::-1]}
    await asyncio.to_thread(send_batch,[requests[0],altered],[output/"altered0",output/"altered1"])
    for i,job in enumerate(jobs):
        original=json.loads((run/job["id"]/"yf/response.json").read_text())
        count=len(original["choices"][0]["token_ids"])
        p=len(job["prompt_ids"])
        serial,_=reduce(output/f"serial{i}/capture",p,count,job["sources"])
        packed,header=reduce(output/f"packed{i}/capture",p,count,job["sources"])
        result={"max_abs_difference":float(np.max(np.abs(serial-packed))),
                "mean_abs_difference":float(np.mean(np.abs(serial-packed))),
                "packed_max_batch_size":max(x["batch_size"] for x in header["schedule"])}
        if i==0:
            changed,_=reduce(output/"altered0/capture",p,count,job["sources"])
            result["altered_neighbour_max_abs_difference"]=float(np.max(np.abs(serial-changed)))
            result["altered_neighbour_mean_abs_difference"]=float(np.mean(np.abs(serial-changed)))
        results[job["id"]]=result
    write(output/"result.json",results)
    print(json.dumps(results),flush=True)


if __name__=="__main__":
    import argparse
    p=argparse.ArgumentParser()
    p.add_argument("run",type=Path)
    p.add_argument("output",type=Path)
    a=p.parse_args()
    asyncio.run(check(a.run,a.output))
