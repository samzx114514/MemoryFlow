"""Query saved full-call matrices and rank canonical original material."""
import argparse
import hashlib
import json
from collections import defaultdict
from pathlib import Path

from intake import digest, read, write


def run(args):
    from transformers import AutoTokenizer
    from forest_bridge import query
    cases = read(args.common/"cases.json")
    tokenizer = AutoTokenizer.from_pretrained(args.model, local_files_only=True)
    args.output.mkdir()
    rows = []
    for number, case in enumerate(cases):
        episode = args.replay/case["sample_id"]/"episode"
        path = args.output/f"query{number:03d}.json"
        query(episode, case["call_id"], [case["target"]["start"], case["target"]["end"]], tokenizer, path)
        result = read(path)
        aliases = {(o["event"], *o["span"]): c["canonical_id"] for c in case["candidates"] for o in c["occurrences"]}
        roots = {r["root_id"]: r for r in result["roots"]}
        scores, missing = defaultdict(float), []
        for route in result["paths"]:
            if route.get("stop") != "material_input":
                continue
            root = roots[route["root_id"]]
            cid = aliases.get((root["message_index"], *root["message_char_span"]))
            if cid is None:
                cid = "unmapped:"+route["root_id"]
                missing.append(root)
            scores[cid] += route["path_score"]
        ranking = sorted(scores, key=lambda cid: (-scores[cid], hashlib.sha256(cid.encode()).hexdigest()))
        rows.append({"id": case["case_id"], "ranking": ranking, "scores": dict(scores),
                     "expanded_spans": result["expanded_spans"], "paths": len(result["paths"]),
                     "max_local_steps": max((len(p["steps"]) for p in result["paths"]), default=0),
                     "unmapped_roots": missing, "query_seconds": result["query_seconds"],
                     "query_file": path.name})
        (args.output/"progress.json").write_text(json.dumps({"targets": len(rows), "last": case["case_id"]})+"\n")
    write(args.output/"rankings.json", rows)
    write(args.output/"identity.json", {"common_records_sha256": digest(args.common/"inputs/records.json"),
          "common_cases_sha256": digest(args.common/"cases.json"), "model": args.model,
          "targets": len(rows), "ranking_sha256": digest(args.output/"rankings.json"),
          "rule": "Unchanged author multisource at each hop; product along each path, sum across paths per canonical material; return cap 10 at evaluation.",
          "input_kind": "Recorded-event-prefix reconstruction; original requests were not saved."})


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ("common", "replay", "output"):
        parser.add_argument("--"+key, type=Path, required=True)
    parser.add_argument("--model", required=True)
    run(parser.parse_args())
