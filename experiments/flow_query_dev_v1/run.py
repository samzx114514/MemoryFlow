"""CPU-only query development on a frozen, trajectory-level GenMem subset."""
import argparse
from collections import defaultdict
import hashlib
import signal
from statistics import mean, median
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from flow_query_dev_v1.cohort import freeze, read, required, sha, write
from genmem_merged_v1.metrics import evaluate
from provenance_v2.compact_query import CompactQuery
from provenance_v2.full_query import FullQuery


def rank(scores):
    return sorted(scores, key=lambda cid: (-scores[cid], hashlib.sha256(cid.encode()).hexdigest()))


def original_scores(result, key):
    roots = {r["root_id"]: r for r in result["roots"]}
    values = defaultdict(float)
    for path in result["paths"]:
        if path["stop"] == "material_input":
            values[key(roots[path["root_id"]])] += path["path_score"]
    return dict(values)


def measured(case, ranking, budget):
    row = evaluate(case, ranking[:budget])
    return {"precision": row["citation_precision"], "recall": row["evidence_recall"], "f1": row["f1"],
            "complete": row["complete_at_10"], "returned": row["returned_fragments"],
            "fixed_budget_precision": row["citation_precision"]*row["returned_fragments"]/budget}


def run(args):
    from transformers import AutoTokenizer
    from pipeline import AUTHOR, author_functions

    protocol = read(args.protocol)
    config = protocol["config"]
    if sha(args.common/"cases.json") != protocol["cases_sha256"] or sha(args.common/"inputs/records.json") != protocol["records_sha256"]:
        raise ValueError("Fixed candidates or labels changed")
    wanted = set(protocol["development_target_ids"])
    if args.preflight:
        wanted = {"genmem_177236211632d6b8:selected_03"}
    cases = [c for c in read(args.common/"cases.json") if c["case_id"] in wanted]
    if len(cases) != len(wanted) or not all(c["sample_id"] in protocol["development_samples"] for c in cases):
        raise ValueError("Query escaped the fixed development cohort")
    old = {r["id"]: r for r in read(args.original_rankings) if r["id"] in wanted}
    tokenizer = AutoTokenizer.from_pretrained(args.model, local_files_only=True)
    functions = author_functions(tokenizer)

    def select(masses, eligible):
        if not eligible:
            return []
        available = masses[eligible]
        normalized = available/available.sum() if available.sum() else available
        record = functions["select_citations"](["target"], normalized[None, :], [str(i) for i in eligible])[0]
        return [eligible[e["sentence_index"]] for e in record["citations"]]

    methods = ["original", "cached_author", *[f"wide{k}" for k in config["widths"]]]
    args.output.mkdir(parents=True)
    write(args.output/"identity.json", {"protocol_sha256": sha(args.protocol), "cases_sha256": protocol["cases_sha256"],
          "original_rankings_sha256": sha(args.original_rankings), "author_source_sha256": sha(AUTHOR),
          "model_tokenizer": args.model, "depth": config["depth"], "methods": methods,
          "preflight": args.preflight, "config": config,
          "matrix_manifest_sha256": {s: sha(args.replay/s/"episode/matrices/manifest.json") for s in {c["sample_id"] for c in cases}},
          "code_sha256": {str(p):sha(p) for p in [Path(__file__),Path(__file__).with_name("cohort.py"),
             Path(__file__).resolve().parents[1]/"provenance_v2/compact_query.py",Path(__file__).resolve().parents[1]/"provenance_v2/full_query.py"]}})
    all_rows, equivalence = [], []
    def timed_out(signum, frame):
        raise TimeoutError("wall_seconds exceeded")
    previous_handler = signal.signal(signal.SIGALRM, timed_out)
    try:
        for number, case in enumerate(cases):
            episode = args.replay/case["sample_id"]/"episode"
            aliases = {(o["event"], *o["span"]):c["canonical_id"] for c in case["candidates"] for o in c["occurrences"]}
            def key(root):
                value = aliases.get((root["message_index"], *root["message_char_span"]))
                if value is None:
                    raise ValueError("Query returned material outside fixed candidates")
                return value
            runs = {m: [] for m in methods}
            for repeat in range(config["repeats"]):
                order = methods[repeat % len(methods):]+methods[:repeat % len(methods)]
                for method in order:
                    if runs[method] and runs[method][-1]["status"] != "complete":
                        continue
                    began, cpu = time.perf_counter(), time.process_time()
                    signal.setitimer(signal.ITIMER_REAL, config["limits"]["wall_seconds"])
                    engine = None
                    try:
                        cls = FullQuery if method == "original" else CompactQuery
                        width = int(method[4:]) if method.startswith("wide") else 3
                        engine = cls(episode/"forest.json", episode/"matrices", width, config["depth"],
                                     None if method.startswith("wide") else select)
                        span = (case["target"]["start"], case["target"]["end"])
                        result = (engine.walk(case["call_id"], span) if method == "original" else
                                  engine.walk(case["call_id"], span, root_key=key, limits=config["limits"]))
                        result.setdefault("status", "complete")
                        scores = original_scores(result, key) if method == "original" else result["root_scores"]
                        ranking = rank(scores)
                    except (TimeoutError, ValueError) as error:
                        result = {"status": "unfinished", "reason": str(error)}
                        scores, ranking = {}, []
                    finally:
                        signal.setitimer(signal.ITIMER_REAL, 0)
                    wall, cpu_seconds = time.perf_counter()-began, time.process_time()-cpu
                    trial = {"status": result["status"], "reason": result.get("reason"), "wall_seconds": wall,
                             "cpu_seconds": cpu_seconds, "scores": scores, "ranking": ranking,
                             "expanded_spans": result.get("expanded_spans"),
                             "path_count": len(result["paths"]) if method == "original" and "paths" in result else result.get("path_count"),
                             "states": result.get("states"), "stats": result.get("stats")}
                    runs[method].append(trial)
                    if repeat == 0:
                        write(args.output/f"target{number:03d}"/f"{method}.json", result)
                    if engine is not None:
                        engine.matrices.clear()
                    del result
                # Check arithmetic before continuing to further targets or choosing a width.
                baseline, cached = runs["original"][0], runs["cached_author"][0]
                if baseline["status"] == cached["status"] == "complete":
                    if set(baseline["scores"]) != set(cached["scores"]):
                        raise ValueError("Caching changed the reachable material set")
                    error = max((abs(v-cached["scores"][k]) for k,v in baseline["scores"].items()), default=0)
                    if error > 1e-10 or baseline["path_count"] != cached["path_count"] or baseline["ranking"][:10] != cached["ranking"][:10]:
                        raise ValueError(f"Caching changed path-score semantics: {case['case_id']}, error={error}")
            baseline = runs["original"][0]
            if baseline["status"] == "complete" and baseline["ranking"] != old[case["case_id"]]["ranking"]:
                raise ValueError("Original method no longer reproduces frozen v1 ranking")
            equivalence.append({"id":case["case_id"], "original_reproduced":baseline["status"] == "complete",
                                "cache_complete":runs["cached_author"][0]["status"] == "complete",
                                "max_score_difference":max((abs(v-runs['cached_author'][0]['scores'].get(k,0)) for k,v in baseline['scores'].items()), default=0)})
            for method, trials in runs.items():
                successful = all(t["status"] == "complete" for t in trials)
                first = trials[0]
                if successful and any(t["ranking"] != first["ranking"] for t in trials):
                    raise ValueError("Non-deterministic repeated CPU ranking")
                ranking = first["ranking"] if successful else []
                row = {"id":case["case_id"], "sample_id":case["sample_id"], "method":method,
                       "support_items":required(case), "status":"complete" if successful else "unfinished",
                       "ranking":ranking, "metrics":{str(b):measured(case, ranking, b) for b in config["return_budgets"]},
                       "cpu_wall_median":median(t["wall_seconds"] for t in trials),
                       "cpu_process_median":median(t["cpu_seconds"] for t in trials), "trials":trials,
                       "expanded_spans":first["expanded_spans"], "path_count":first["path_count"],
                       "states":first["states"], "stats":first["stats"]}
                all_rows.append(row)
            write(args.output/"progress.json", {"targets":number+1, "total":len(cases), "last":case["case_id"]})
            print(f"target {number+1}/{len(cases)} {case['case_id']}", flush=True)
    finally:
        signal.signal(signal.SIGALRM, previous_handler)
    table = []
    for method in methods:
        rows = [r for r in all_rows if r["method"] == method]
        for budget in config["return_budgets"]:
            table.append({"method":method, "budget":budget, "targets":len(rows),
                          "completed":sum(r['status']=='complete' for r in rows),
                          **{k:mean(r['metrics'][str(budget)][k] for r in rows) for k in rows[0]['metrics'][str(budget)]},
                          "cpu_wall_median":median(r['cpu_wall_median'] for r in rows),
                          "cpu_wall_max":max(r['cpu_wall_median'] for r in rows),
                          "expanded_spans_median":median(r['expanded_spans'] or 0 for r in rows),
                          "paths_median":median(r['path_count'] or 0 for r in rows)})
    write(args.output/"results.json", {"table":table, "per_target":all_rows, "equivalence":equivalence,
          "protocol_sha256":sha(args.protocol), "depth":config['depth'], "development_only":True,
          "path_counts":"All enumerated terminal routes, counted exactly via DAG; displayed paths are representatives.",
          "unfinished_policy":"Retained as empty return / zero quality; attempted time reported, remaining repeats not run."})


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["freeze","run"])
    parser.add_argument("--common",type=Path,required=True)
    parser.add_argument("--output",type=Path,required=True)
    parser.add_argument("--config",type=Path,default=Path(__file__).with_name('config.json'))
    parser.add_argument("--protocol",type=Path)
    parser.add_argument("--replay",type=Path)
    parser.add_argument("--model")
    parser.add_argument("--original-rankings",type=Path)
    parser.add_argument("--preflight",action="store_true")
    args=parser.parse_args()
    if args.command == "freeze":
        print(freeze(args.common,args.config,args.output))
    else:
        run(args)
