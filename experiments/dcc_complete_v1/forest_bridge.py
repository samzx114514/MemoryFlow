"""Adapt exact-token matrices to the existing forest and span-query engine."""
import json
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from provenance_v2.full_batch import digest
from provenance_v2.full_forest import build_run
from provenance_v2.full_query import FullQuery
from pipeline import author_functions, offsets, write


def export_episode(run, output, ordered_ids, tokenizer, method="mf"):
    """ordered_ids must describe one real episode; unrelated inputs stay separate."""
    jobs = {job["id"]: job for job in json.loads((run / "inputs.json").read_text())}
    output.mkdir(parents=True)
    matrices = output / "matrices"
    matrices.mkdir()
    rows, entries = [], {}
    for index, job_id in enumerate(ordered_ids):
        job = jobs[job_id]
        call_id = f"call{index:02d}"
        receipt = json.loads((run / job_id / job.get("output_receipt", "yf/response.json")).read_text())
        generated = receipt["choices"][0]["token_ids"]
        text, output_offsets = offsets(tokenizer, generated)
        columns = [{"column": i, "message_index": source["message_index"], "section": source.get("section", "content"),
                    "role": source["role"], "text": source["text"], "match_text": source.get("match_text", source["text"]),
                    **{key: source[key] for key in ("match_offsets", "response_char_span") if source.get(key) is not None},
                    "message_char_span": source["span"], "prompt_char_span": source["prompt_span"],
                    "token_span": source["token_span"], "source_id": source["source_id"]}
                   for i, source in enumerate(job["sources"])]
        score_path = matrices / f"{call_id}.npy"
        source_path = run / job_id / f"{method}.npy"
        score_path.write_bytes(source_path.read_bytes())
        p = len(job["prompt_ids"])
        header = json.loads((run / job_id / method / "capture" / "qk.json").read_text())
        metadata = {"call_id": call_id, "original_id": job_id, "prompt_tokens": p,
                    "output_tokens": len(generated), "output": text,
                    "response_text_length": 0 if job.get("tool_calls") or text.lstrip().startswith("<tool_call>") else len(text),
                    "output_offsets": output_offsets, "prediction_rows": list(range(p-1, p+len(generated)-1)),
                    "columns": columns, "scores_sha256": digest(score_path), "config": header["config"]}
        meta_path = matrices / f"{call_id}.json"
        write(meta_path, metadata)
        entries[call_id] = {"metadata": meta_path.name, "metadata_sha256": digest(meta_path),
                            "scores": score_path.name, "scores_sha256": digest(score_path)}
        rows.append({"request": job["request"], "response": {"generations": [{"text": text, "tool_calls": job.get("tool_calls", [])}]}})
    calls = output / "calls.jsonl"
    calls.write_text("".join(json.dumps(row, ensure_ascii=False)+"\n" for row in rows), encoding="utf-8")
    write(matrices / "manifest.json", {"schema": "memoryflow.full_replay.v1", "user_id": None,
                                       "calls_sha256": digest(calls), "calls": entries})
    started = time.perf_counter()
    forest = build_run(output, matrices, output / "forest.json")
    write(output / "build.json", {"seconds": time.perf_counter()-started,
                                  "calls": len(entries), "content_links": len(forest["content_transfers"]),
                                  "ordered_ids": ordered_ids, "method": method})


def query(episode, call_id, span, tokenizer, output):
    functions = author_functions(tokenizer)
    def select(masses, eligible):
        if not eligible:
            return []
        available = masses[eligible]
        normalized = available / available.sum() if available.sum() else available
        record = functions["select_citations"](["target"], normalized[None, :],
                                               [str(i) for i in eligible])[0]
        return [eligible[entry["sentence_index"]] for entry in record["citations"]]
    started = time.perf_counter()
    engine = FullQuery(episode / "forest.json", episode / "matrices", 3, 16, candidate_selector=select)
    result = engine.walk(call_id, tuple(span))
    result["query_seconds"] = time.perf_counter()-started
    result["selection_rule"] = "original_author_multisource"
    write(output, result)


if __name__ == "__main__":
    import argparse
    from transformers import AutoTokenizer
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("export", "query"))
    parser.add_argument("run", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--model", required=True)
    parser.add_argument("--ids", nargs="+")
    parser.add_argument("--method", choices=("mf", "yf"), default="mf")
    parser.add_argument("--call", default="call00")
    parser.add_argument("--span", nargs=2, type=int)
    args = parser.parse_args()
    tokenizer = AutoTokenizer.from_pretrained(args.model, local_files_only=True)
    if args.command == "export":
        export_episode(args.run, args.output, args.ids, tokenizer, args.method)
    else:
        query(args.run, args.call, args.span, tokenizer, args.output)
