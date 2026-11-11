"""Freeze real analysis-call inputs, without reading attribution scores."""
import hashlib
import json
import time
from collections import Counter, defaultdict
from pathlib import Path
from urllib.request import Request, urlopen

from transformers import AutoTokenizer
from pipeline import author_functions, render, write


ROOT = Path("/data1/songzhengxing_intern_dccv2/mf_complete_20261111")
MODELS = [Path("/data/Qwen3.8-27B-FP8"),
          Path("/data2/pkuiti/songzhengxing_intern/model/Qwen2.5-7B-Instruct"),
          Path("/data2/pkuiti/songzhengxing_intern/model/Qwen2.5-1.5B-Instruct")]
INSTRUCTION = """Classify the stage of an actual DCC model output. No attribution scores
are supplied. Decide only whether it reports a domain analysis result, not whether it is
correct. Domain results concern the NBA operation, contract, or financial documents.
Include factual observations before further tools and results inside write/finish tool
arguments. A categorical answer or an empty issue-report array is a result in its task.
Exclude file-reading instructions, searches, delegated future tasks, memory/user-profile
updates, summaries of session goals, and statements that work is incomplete. Do not
classify generic runtime observations as domain results. Return JSON only:
{"is_analysis_result":true,"facts":["exact substring from the supplied output"],
"reason":"at most 20 words"}. List up to three actual assertions. Do not invent or
correct assertions. For categorical/structured outputs quote the actual value. If there
is no result return false and facts:[]."""


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def candidate(request, response, benchmark, task_id, source):
    if not response.get("choices"):
        return None
    message = response["choices"][0]["message"]
    content = message.get("content") or ""
    tools = message.get("tool_calls") or []
    names = [tool["function"]["name"] for tool in tools]
    report = any(any(word in name.lower() for word in ("write", "finish", "deliver")) for name in names)
    if not content.strip() and not report:
        return None
    public_output = "CONTENT:\n"+content+"\nTOOL CALLS:\n"+json.dumps(tools, ensure_ascii=False, indent=2)
    # Include a decoded argument view to make JSON string values readable.
    for tool in tools:
        args = tool["function"].get("arguments", "")
        if any(word in tool["function"]["name"].lower() for word in ("write", "finish", "deliver")):
            public_output += "\nREPORT ARGUMENTS:\n"+args
            try:
                decoded = json.loads(args)
            except json.JSONDecodeError:
                continue
            for value in decoded.values():
                if isinstance(value, str):
                    public_output += "\nDECODED STRING VALUE:\n"+value
    prompt = {"messages": request["messages"], "tools": request.get("tools")}
    identity = hashlib.sha256(json.dumps(prompt, sort_keys=True).encode()).hexdigest()
    return {"input_sha256": identity, "benchmark": benchmark, "task_id": task_id,
            "source": str(source), "source_sha256": sha(source), "request": prompt, "public_output": public_output}


def scan(root):
    earlier = Path("/data1/songzhengxing_intern_dccv2/mf_yf_batch12_20261109")
    result = {}
    excluded = {row["input_sha256"] for row in json.loads((root / "formal_inputs.json").read_text())}
    for task in json.loads((earlier / "frozen.json").read_text())["jobs"]:
        if task["family"] != "nba" or task["job"] == "nba-03":
            continue
        for source in (earlier / "jobs" / task["job"] / "wire").glob("*.response.json"):
            response = json.loads(source.read_text())
            if response.get("status") != 200:
                continue
            request = json.loads(source.with_name(source.name.replace(".response.json", ".request.json")).read_text())["request"]
            item = candidate(request, response["response"], "nba", task["task_id"], source)
            if item and item["input_sha256"] not in excluded:
                result[item["input_sha256"]] = item
    for benchmark, folder in (("clause", "sources_clause_v2"), ("clause", "sources_clause_v3"), ("finauditing", "sources_fin_v2")):
        for case in (root / folder).glob("*"):
            command = case / "command.json"
            if not command.exists():
                continue
            task_id = json.loads(command.read_text())["task"]["id"]
            for source in (case / "capture/wire").glob("*.json"):
                try:
                    record = json.loads(source.read_text())
                except json.JSONDecodeError:
                    continue
                if record.get("status") != 200:
                    continue
                item = candidate(record["request"], record["response"], benchmark, task_id, source)
                if item and item["input_sha256"] not in excluded:
                    result[item["input_sha256"]] = item
    return result


def classify(item, output):
    manual = ROOT / "stage_manual_reviews" / (item["input_sha256"]+".json")
    if manual.exists():
        decision = json.loads(manual.read_text())
        if decision["source_sha256"] != item["source_sha256"]:
            raise ValueError("Manually reviewed source changed")
        return decision
    folder = output / "stage_reviews" / item["input_sha256"]
    record_path = folder / "decision.json"
    previous = ROOT / "experiment1_v2/stage_reviews" / item["input_sha256"] / "decision.json"
    if not record_path.exists() and previous.exists():
        record_path = previous
    if record_path.exists():
        decision = json.loads(record_path.read_text())
        if decision["source_sha256"] != item["source_sha256"]:
            raise ValueError("Reviewed source file changed")
        return decision
    payload = {"model": "mf-model", "messages": [{"role": "system", "content": INSTRUCTION},
               {"role": "user", "content": json.dumps({"benchmark": item["benchmark"], "output": item["public_output"]}, ensure_ascii=False)}],
               "temperature": 0, "seed": 0, "max_tokens": 512, "response_format": {"type": "json_object"},
               "chat_template_kwargs": {"enable_thinking": False}}
    write(folder / "request.json", payload)
    request = Request("http://127.0.0.1:8781/v1/chat/completions", json.dumps(payload).encode(),
                      headers={"Content-Type": "application/json"})
    with urlopen(request, timeout=300) as response:
        raw = json.load(response)
    write(folder / "response.json", raw)
    decision = json.loads(raw["choices"][0]["message"]["content"])
    if not isinstance(decision.get("is_analysis_result"), bool) or not isinstance(decision.get("facts"), list):
        raise ValueError("Malformed stage decision")
    if decision["is_analysis_result"] and not decision["facts"]:
        raise ValueError("Positive stage decision needs an actual output assertion")
    if any(not fact or fact not in item["public_output"] for fact in decision["facts"]):
        raise ValueError("Stage decision invented an output assertion")
    decision["source_sha256"] = item["source_sha256"]
    write(record_path, decision)
    return decision


def sources_finished(root):
    for benchmark, version in (("clause", "v2"), ("clause", "v3"), ("fin", "v2")):
        path = root / f"source_tasks_{benchmark}_{version}.json"
        if not path.exists():
            continue
        tasks = json.loads(path.read_text())
        for index, task in enumerate(tasks):
            case = root / f"sources_{benchmark}_{version}" / f"{index:02d}-{task['id']}"
            if not (case / "result.json").exists() and not (case / "collector_error.json").exists():
                return False
    return True


def freeze(root, output):
    output.mkdir(exist_ok=True)
    identity={"instruction_sha256":hashlib.sha256(INSTRUCTION.encode()).hexdigest(),
              "clause_sources_sha256":sha(root/"source_tasks_clause_v2.json"),
              "fin_sources_sha256":sha(root/"source_tasks_fin_v2.json"),"context_limit":65536,"max_tokens":2048}
    extra=root/"source_tasks_clause_v3.json"
    if extra.exists():
        identity["additional_clause_sources_sha256"]=sha(extra)
    identity_path=output/"selection_identity.json"
    if identity_path.exists() and json.loads(identity_path.read_text()) != identity:
        raise ValueError("Selection protocol changed; use a new output directory")
    write(identity_path,identity)
    tokenizers = {model.name: AutoTokenizer.from_pretrained(model, local_files_only=True) for model in MODELS}
    functions = {name: author_functions(tok) for name, tok in tokenizers.items()}
    eligible_path=output/"eligible_calls.json"
    prior=root/"experiment1_v2/eligible_calls.json"
    initial=eligible_path if eligible_path.exists() else prior
    accepted={row["input_sha256"]:row for row in json.loads(initial.read_text())} if initial.exists() else {}
    rejected=set()
    while True:
        pool = scan(root)
        counts = Counter((item["benchmark"], item["task_id"]) for item in accepted.values())
        ordered = sorted(pool.values(), key=lambda item: hashlib.sha256(("mf11-result:"+item["input_sha256"]).encode()).hexdigest())
        for item in ordered:
            identity = item["input_sha256"]
            if identity in accepted or identity in rejected or counts[item["benchmark"], item["task_id"]] >= 3:
                continue
            try:
                decision = classify(item, output)
                if not decision["is_analysis_result"]:
                    rejected.add(identity)
                    continue
                lengths = {}
                for name, tok in tokenizers.items():
                    ids, _ = render(tok, item["request"], functions[name])
                    lengths[name] = len(ids)
                if max(lengths.values()) > 61440:
                    rejected.add(identity)
                    write(output / "over_context" / f"{identity}.json", lengths)
                    continue
                accepted[identity] = {**item, "prompt_tokens": lengths, "stage_review": decision}
                counts[item["benchmark"], item["task_id"]] += 1
                write(output / "eligible_calls.json", list(accepted.values()))
                print("eligible", dict(Counter(row["benchmark"] for row in accepted.values())), flush=True)
            except (ValueError, KeyError) as error:
                rejected.add(identity)
                write(output / "stage_errors" / f"{identity}.json", {"error": str(error)})
        if sources_finished(root):
            break
        time.sleep(10)
    selected = []
    for benchmark in ("nba", "clause", "finauditing"):
        groups = defaultdict(list)
        for item in accepted.values():
            if item["benchmark"] == benchmark:
                groups[item["task_id"]].append(item)
        for group in groups.values():
            group.sort(key=lambda item: hashlib.sha256(("mf11-final:"+item["input_sha256"]).encode()).hexdigest())
        tasks = sorted(groups, key=lambda task: hashlib.sha256(("mf11-task:"+task).encode()).hexdigest())
        chosen = []
        for round_index in range(3):
            for task in tasks:
                if len(groups[task]) > round_index:
                    chosen.append(groups[task][round_index])
                if len(chosen) == 10:
                    break
            if len(chosen) == 10:
                break
        if len(chosen) != 10:
            write(output / "insufficient.json", {"counts": dict(Counter(item["benchmark"] for item in accepted.values())), "benchmark": benchmark})
            raise ValueError(f"Only {len(chosen)} eligible {benchmark} calls")
        for index, item in enumerate(chosen):
            selected.append({key: value for key, value in {**item, "id": f"{benchmark}-{index+1:02d}"}.items() if key != "public_output"})
    write(output / "formal_inputs.json", selected)
    write(output / "formal_lock.json", {"sha256": sha(output / "formal_inputs.json"), "distribution": {"nba": 10, "clause": 10, "finauditing": 10},
                                "max_tokens": 2048, "context_limit": 65536, "temperature": 0, "seed": 0,
                                "rope_scaling": "unchanged model configuration", "selection": "domain-result stage; source-task round robin, at most 3 calls per source task; no attribution scores read",
                                "source_tasks": dict(Counter(item["task_id"] for item in selected))})


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    freeze(ROOT, args.output)
