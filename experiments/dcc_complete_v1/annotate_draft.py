"""Draft evidence labels from raw review packs only, for subsequent review."""
import concurrent.futures
import json
import time
from pathlib import Path
from urllib.request import Request, urlopen

from pipeline import write


INSTRUCTION = """Annotate provenance using only the supplied raw output and input sources.
No method scores or rankings are provided. Select the first 2–3 distinct atomic factual
assertions in output order, when present. Split a composite answer into atomic assertions
where appropriate. Exclude headings, plans, tool syntax, and requested future actions.
A factual assertion embedded in a tool argument is eligible. A categorical answer or
structured field value also expresses an assertion in its task context. An empty issue
report array asserts that no covered issue was found; it is not an absence of claims.
Record the exact raw substring and add a claim field explaining its task meaning.
Distinguish actual stated facts in forwarded text from instructions and format examples.
Keep each rationale under 30 words. Never invent a claim to
reach a quota. Use exact output substrings, including its original escaping.
For each assertion examine ALL input sources, and list every reasonable supporting
source ID, including partial evidence and valid alternative sources. A complete support
set is a minimal combination of IDs that together fully supports the assertion. Include
alternative complete sets. Use no external knowledge. A numerical calculation can be
supported by its actual premises and rule. Do not label task instructions as factual
evidence merely because they mention the topic. Unsupported assertions have empty lists.
Return JSON only: {"targets":[{"text":"exact substring","occurrence":1,
"supporting_sources":["source ID"],"complete_support_sets":[["source ID"]],
"rationale":"explain support and missing premises"}],"no_claim_reason":null}.
When no factual assertion exists return targets:[] and a concrete no_claim_reason.
These are draft annotations that will be reviewed before scoring."""


def annotate(call, folder, endpoint, model):
    if (folder / "validated.json").exists():
        return
    source = {"output": call["output"], "sources": [{"source_id": item["source_id"], "role": item["role"], "text": item["text"]}
                                                   for item in call["sources"]]}
    payload = {"model": model, "messages": [{"role": "system", "content": INSTRUCTION},
                                              {"role": "user", "content": json.dumps(source, ensure_ascii=False)}],
               "temperature": 0, "seed": 0, "max_tokens": 3072,
               "chat_template_kwargs": {"enable_thinking": False}, "response_format": {"type": "json_object"}}
    write(folder / "request.json", payload)
    started = time.time()
    request = Request(endpoint + "/v1/chat/completions", json.dumps(payload).encode(), headers={"Content-Type": "application/json"})
    with urlopen(request, timeout=900) as response:
        result = json.load(response)
    write(folder / "response.json", result)
    draft = json.loads(result["choices"][0]["message"]["content"])
    valid = {source["source_id"] for source in call["sources"]}
    for target in draft["targets"]:
        text, occurrence = target["text"], target.get("occurrence", 1)
        start = -1
        for _ in range(occurrence):
            start = call["output"].find(text, start+1)
            if start < 0 or not text:
                raise ValueError("Draft claim is not an exact substring")
        target["span"] = [start, start+len(text)]
        if not set(target["supporting_sources"]) <= valid:
            raise ValueError("Draft contains an unknown evidence source")
        if any(not group or not set(group) <= set(target["supporting_sources"]) for group in target["complete_support_sets"]):
            raise ValueError("Malformed complete evidence combination")
    if not draft["targets"] and not draft.get("no_claim_reason"):
        raise ValueError("Empty draft has no reason")
    write(folder / "validated.json", {**draft, "review_complete": False, "seconds": time.time()-started})


def run(review_packs, output, endpoint, model):
    output.mkdir(exist_ok=True)
    pending = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        for review in review_packs:
            pack = json.loads(review.read_text())
            for call in pack["calls"]:
                folder = output / review.stem / call["id"]
                pending.append((folder, pool.submit(annotate, call, folder, endpoint, model)))
        for folder, future in pending:
            try:
                future.result()
                print("draft", str(folder), flush=True)
            except Exception as error:
                write(folder / "error.json", {"type": type(error).__name__, "detail": str(error)})
                print("draft_error", str(folder), type(error).__name__, flush=True)
    write(output / "complete.json", {"calls": len(pending),
                                     "validated_drafts": len(list(output.glob("*/*/validated.json"))),
                                     "note": "Drafts only. No method score was read; semantic review remains required."})


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument("reviews", nargs="+", type=Path)
    parser.add_argument("--endpoint", default="http://127.0.0.1:8770")
    parser.add_argument("--model", default="/data/Qwen3.8-27B")
    args = parser.parse_args()
    run(args.reviews, args.output, args.endpoint, args.model)
