"""Score frozen statement annotations without consulting scores during labeling."""
import hashlib
import json
from collections import defaultdict
from pathlib import Path


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def metrics(selected, target):
    selected = set(selected)
    supporting = set(target["supporting_sources"])
    complete = target["complete_support_sets"]
    if any(not sources for sources in complete):
        raise ValueError("A complete support set cannot be empty")
    if any(not set(sources) <= supporting for sources in complete):
        raise ValueError("Complete evidence must belong to supporting sources")
    precision = len(selected & supporting) / len(selected) if selected else 0.0
    recall = (1.0 if any(set(sources) <= selected for sources in complete)
              else 0.5 if selected & supporting else 0.0)
    return {"precision": precision, "recall": recall, "covered": float(bool(selected)),
            "correct_citations": len(selected & supporting), "returned_citations": len(selected)}


def answer_metrics(rows):
    returned = sum(row["returned_citations"] for row in rows)
    p = sum(row["correct_citations"] for row in rows)/returned if returned else 0.0
    r = sum(row["recall"] for row in rows) / len(rows)
    return {"precision": p, "recall": r, "f1": 2*p*r/(p+r) if p+r else 0.0,
            "coverage": sum(row["covered"] for row in rows)/len(rows), "targets": len(rows)}


def aggregate_answers(answers, jobs):
    """Average answers within each original task, then give tasks equal weight."""
    task_answers = defaultdict(list)
    for (method, benchmark, call_id), values in answers.items():
        task_id = jobs[call_id].get("task_id", call_id)
        task_answers[method, benchmark, task_id].append({"id": call_id, **answer_metrics(values)})
    by_benchmark, task_rows = defaultdict(list), []
    keys = ("precision", "recall", "f1", "coverage")
    for (method, benchmark, task_id), values in sorted(task_answers.items()):
        row = {"method": method, "benchmark": benchmark, "task_id": task_id,
               "call_ids": [v["id"] for v in values], "calls_with_claims": len(values),
               "targets": sum(v["targets"] for v in values),
               **{key: sum(v[key] for v in values)/len(values) for key in keys}}
        task_rows.append(row)
        by_benchmark[method, benchmark].append(row)
    tables = []
    for (method, benchmark), values in sorted(by_benchmark.items()):
        tables.append({"method": method, "benchmark": benchmark, "tasks_with_claims": len(values),
                       "calls_with_claims": sum(v["calls_with_claims"] for v in values),
                       "targets": sum(v["targets"] for v in values),
                       **{key: sum(v[key] for v in values)/len(values) for key in keys}})
    return tables, task_rows


def review_pack(run, output):
    """Expose raw outputs and candidate text only; never load method matrices."""
    jobs = json.loads((run / "inputs.json").read_text())
    from transformers import AutoTokenizer
    from pipeline import offsets, write
    identity = json.loads((run / "identity.json").read_text())
    tokenizer = AutoTokenizer.from_pretrained(identity["model"], local_files_only=True)
    pack = {"schema": "dcc.statement_review.v1", "run": str(run),
            "inputs_sha256": digest(run / "inputs.json"), "identity_sha256": digest(run / "identity.json"),
            "instructions": "Select 2–3 factual claims where present. Annotate all reasonable alternative evidence. Record no_claim if absent.",
            "calls": []}
    for job in jobs:
        response = run / job["id"] / "yf" / "response.json"
        receipt = json.loads(response.read_text())
        text, _ = offsets(tokenizer, receipt["choices"][0]["token_ids"])
        pack["calls"].append({"id": job["id"], "benchmark": job["benchmark"],
                              "response_sha256": digest(response), "output": text,
                              "sources": job["sources"], "targets": [], "no_claim_reason": None})
    write(output, pack)


def evaluation_jobs(jobs, calls, benchmark=None):
    selected = {job["id"]: job for job in jobs if benchmark is None or job["benchmark"] == benchmark}
    ids = [call["id"] for call in calls]
    if not selected or len(ids) != len(set(ids)) or set(selected) != set(ids):
        raise ValueError("Annotations must account for every frozen call in the requested benchmark")
    return selected


def evaluate(run, gold_path, output, benchmark=None):
    import numpy as np
    from transformers import AutoTokenizer
    from pipeline import author_functions, cite, offsets, token_span, write
    gold = json.loads(gold_path.read_text())
    if not gold.get("review_complete"):
        raise ValueError("Annotations must be reviewed and frozen before scoring")
    if digest(run / "inputs.json") != gold["inputs_sha256"] or digest(run / "identity.json") != gold["identity_sha256"]:
        raise ValueError("Annotation identity differs from the run")
    identity = json.loads((run / "identity.json").read_text())
    tok = AutoTokenizer.from_pretrained(identity["model"], local_files_only=True)
    functions = author_functions(tok)
    if gold.get("benchmark") != benchmark:
        raise ValueError("Annotation benchmark differs from the requested scope")
    jobs = evaluation_jobs(json.loads((run / "inputs.json").read_text()), gold["calls"], benchmark)
    rows, answers, empty = [], defaultdict(list), []
    for call in gold["calls"]:
        job = jobs[call["id"]]
        response = run / call["id"] / "yf" / "response.json"
        if digest(response) != call["response_sha256"]:
            raise ValueError("Annotated output has changed")
        text, output_offsets = offsets(tok, json.loads(response.read_text())["choices"][0]["token_ids"])
        valid = {source["source_id"] for source in job["sources"]}
        if not call["targets"]:
            if not call.get("no_claim_reason"):
                raise ValueError("Missing targets require an explicit no-claim reason")
            empty.append({"id": call["id"], "benchmark": job["benchmark"], "reason": call["no_claim_reason"]})
            continue
        for target in call["targets"]:
            a, b = target["span"]
            if text[a:b] != target["text"] or not set(target["supporting_sources"]) <= valid:
                raise ValueError("Target span or annotated source IDs do not match")
        for method in ("yf", "mf"):
            matrix = np.load(run / call["id"] / f"{method}.npy", allow_pickle=False)
            target_rows = [token_span(output_offsets, *target["span"]) for target in call["targets"]]
            citations = cite(matrix, target_rows, functions, job["sources"])
            # Preserve the author's multi-source output and its candidate indices.
            for target, citation in zip(call["targets"], citations, strict=True):
                indices = [entry["sentence_index"] for entry in citation["citations"]]
                selected = [job["sources"][index]["source_id"] for index in indices]
                row = {"id": call["id"], "benchmark": job["benchmark"], "method": method,
                       "target": target["text"], "span": target["span"], "selected_sources": selected,
                       **metrics(selected, target)}
                rows.append(row)
                answers[method, job["benchmark"], call["id"]].append(row)
    tables, task_rows = aggregate_answers(answers, jobs)
    write(output, {"gold_sha256": digest(gold_path), "benchmark": benchmark, "frozen_calls": len(jobs),
                   "aggregation": "answer_then_original_task_macro",
                   "rows": rows, "tasks": task_rows, "table": tables, "calls_without_claims": empty})


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("review", "score"))
    parser.add_argument("run", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--gold", type=Path)
    parser.add_argument("--benchmark", choices=("nba", "clause", "finauditing"))
    args = parser.parse_args()
    if args.command == "review":
        review_pack(args.run, args.output)
    else:
        evaluate(args.run, args.gold, args.output, args.benchmark)
