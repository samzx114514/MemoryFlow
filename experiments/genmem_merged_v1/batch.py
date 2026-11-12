"""Build full replay tables per trajectory; retain failures without truncation."""
import argparse
import json
import time
from collections import defaultdict
from pathlib import Path
from types import SimpleNamespace

from replay import run


def main(args):
    groups = defaultdict(list)
    for target in json.loads((args.dataset/"targets.json").read_text()):
        groups[target["sample_id"]].append(target["legacy_id"])
    args.output.mkdir()
    records = []
    for sample_id, targets in sorted(groups.items()):
        output = args.output/sample_id
        started = time.time()
        try:
            run(SimpleNamespace(dataset=args.dataset, output=output, model=args.model,
                                targets=targets, matrices_only=True))
            record = {"sample_id": sample_id, "status": "matrices_ready",
                      **json.loads((output/"completed.json").read_text())}
        except Exception as error:
            record = {"sample_id": sample_id, "status": "failed", "legacy_ids": targets,
                      "error_type": type(error).__name__, "error": str(error)}
        record["seconds"] = time.time()-started
        records.append(record)
        (args.output/"progress.json").write_text(json.dumps(records, ensure_ascii=False, indent=2)+"\n")
        print(json.dumps(record, ensure_ascii=False), flush=True)
    (args.output/"completed.json").write_text(json.dumps({"trajectories": len(records),
         "matrices_ready": sum(r["status"] == "matrices_ready" for r in records),
         "failed": sum(r["status"] == "failed" for r in records), "queries": 0,
         "note": "Engineering reconstruction; chain and common-candidate labels not yet frozen."}, indent=2)+"\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dataset", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--model", required=True)
    main(parser.parse_args())
