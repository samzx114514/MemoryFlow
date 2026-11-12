"""Replay recorded GenMem outputs against the complete recorded event prefix.

The event-prefix request and tool-call serialization are explicit reconstructions.
Original model input tokens, tool schemas and hidden prompts were not recorded.
"""
import argparse
import hashlib
import json
from pathlib import Path


def tool_calls(event):
    result = []
    for tool in event.get("tool_calls") or []:
        if "function" in tool:
            fn = tool["function"]
        else:
            fn = {"name": tool["name"], "arguments": tool.get("args", {})}
        result.append({"id": tool.get("id"), "type": "function", "function": fn})
    return result


def message(event):
    result = {"role": {"agent": "assistant", "tool": "tool", "user": "user"}[event["action"]],
              "content": event.get("content") or ""}
    if event["action"] == "agent" and event.get("tool_calls"):
        result["tool_calls"] = tool_calls(event)
    if event["action"] == "tool" and event.get("tool_call_id"):
        result["tool_call_id"] = event["tool_call_id"]
    return result


def output_text(event):
    text = event.get("content") or ""
    for tool in tool_calls(event):
        text += "\n<tool_call>\n"+json.dumps(tool["function"], ensure_ascii=False)+"\n</tool_call>"
    return text


def recorded_calls(log, last):
    history, calls = [], []
    for event_index, event in enumerate(log[:last+1]):
        if event["action"] == "agent":
            text = output_text(event)
            if text:
                calls.append({"event": event_index, "request": {"messages": list(history)},
                              "output": text, "tool_calls": tool_calls(event)})
        history.append(message(event))
    return calls


def run(args):
    import numpy as np
    from transformers import AutoTokenizer
    from pipeline import author_functions, check_budget, model_context_limit, offsets, reduce, render, send, send_batch, validate_model, write
    from rich_sources import full_sources
    from forest_bridge import export_episode, query
    validate_model(args.model)
    all_targets = json.loads((args.dataset/"targets.json").read_text())
    targets = [r for r in all_targets if r["legacy_id"] in args.targets]
    if len(targets) != len(args.targets) or len({r["sample_id"] for r in targets}) != 1:
        raise ValueError("Choose distinct frozen targets from one recorded trajectory")
    trace_path = args.dataset/"traces"/(targets[0]["sample_id"]+".json")
    trace = json.loads(trace_path.read_text())
    calls = recorded_calls(trace["memory_stack_log"], max(t["target"]["event"] for t in targets))
    tokenizer = AutoTokenizer.from_pretrained(args.model, local_files_only=True)
    functions = author_functions(tokenizer)
    limit = model_context_limit(json.loads((Path(args.model)/"config.json").read_text()))
    jobs, lengths = [], []
    for index, call in enumerate(calls):
        prompt, sources = render(tokenizer, call["request"], functions)
        generated = tokenizer.encode(call["output"], add_special_tokens=False)
        if offsets(tokenizer, generated)[0] != call["output"]:
            raise ValueError("Recorded output does not round-trip through replay tokenizer")
        call_id = f"call{index:02d}"
        check_budget(call_id, len(prompt), len(generated), limit)
        sources = full_sources(tokenizer, call["request"], prompt, sources, generated)
        jobs.append({"id": call_id, "event": call["event"], "request": call["request"],
                     "tool_calls": [{"id": t["id"], "name": t["function"]["name"], "args": t["function"]["arguments"]} for t in call["tool_calls"]],
                     "prompt_ids": prompt, "sources": sources, "output_receipt": "observed/response.json"})
        lengths.append({"call": call_id, "event": call["event"], "prompt_tokens": len(prompt), "output_tokens": len(generated)})
    args.output.mkdir()
    write(args.output/"identity.json", {"dataset_targets_sha256": hashlib.sha256((args.dataset/"targets.json").read_bytes()).hexdigest(),
          "trace_sha256": hashlib.sha256(trace_path.read_bytes()).hexdigest(), "targets": args.targets,
          "model": args.model, "lengths": lengths, "engineering_preflight": True,
          "input_assembly": "all recorded prior events retained; no invented intermediate content",
          "missing_original_fields": ["full_model_requests", "prompt_tokens", "tool_schemas"],
          "output_assembly": "recorded content followed by JSON serialization of recorded tool calls"})
    write(args.output/"inputs.json", jobs)
    for job, call in zip(jobs, calls):
        write(args.output/job["id"]/"observed/response.json", {"choices": [{"token_ids": tokenizer.encode(call["output"], add_special_tokens=False)}]})
    for start in range(0, len(jobs), 2):
        group = jobs[start:start+2]
        generated = [json.loads((args.output/j["id"]/"observed/response.json").read_text())["choices"][0]["token_ids"] for j in group]
        payloads = [{"prompt": j["prompt_ids"]+g[:-1], "max_tokens": 1, "temperature": 0, "seed": 0} for j, g in zip(group, generated)]
        destinations = [args.output/j["id"]/"mf" for j in group]
        if len(group) == 1:
            send(payloads[0], destinations[0])
        else:
            send_batch(payloads, destinations)
        for job, gen, destination in zip(group, generated, destinations):
            matrix, _ = reduce(destination/"capture", len(job["prompt_ids"]), len(gen), job["sources"])
            np.save(args.output/job["id"]/"mf.npy", matrix, allow_pickle=False)
    export_episode(args.output, args.output/"episode", [j["id"] for j in jobs], tokenizer)
    by_event = {j["event"]: j["id"] for j in jobs}
    if not args.matrices_only:
        for index, target in enumerate(targets):
            t = target["target"]
            query(args.output/"episode", by_event[t["event"]], [t["start"], t["end"]], tokenizer, args.output/f"target{index}.json")
    write(args.output/"completed.json", {"calls": len(jobs), "queries": 0 if args.matrices_only else len(targets),
          "legacy_ids": [t["legacy_id"] for t in targets], "matrices_only": args.matrices_only})


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dataset", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--model", required=True)
    parser.add_argument("--targets", nargs="+", required=True)
    parser.add_argument("--matrices-only", action="store_true", help="Build reusable matrices without target queries while labels are reviewed")
    run(parser.parse_args())
