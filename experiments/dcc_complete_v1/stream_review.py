"""Prepare blind review records and drafts while the three-model batch is running."""
import concurrent.futures
import json
import time
from pathlib import Path

from transformers import AutoTokenizer

from annotate_draft import annotate
from evaluate import digest
from pipeline import offsets, write


def run(root, endpoint, model):
    output = root / "annotation_drafts_v2"
    runs = ("formal_27b", "formal_7b", "formal_1_5b")
    known, submitted, pending = {}, set(), {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        while True:
            for name in runs:
                run_dir = root / name
                if name not in known and (run_dir / "inputs.json").exists() and (run_dir / "identity.json").exists():
                    try:
                        jobs = json.loads((run_dir / "inputs.json").read_text())
                        identity = json.loads((run_dir / "identity.json").read_text())
                    except json.JSONDecodeError:
                        continue  # A concurrently written file will be retried next pass.
                    known[name] = (jobs, AutoTokenizer.from_pretrained(identity["model"], local_files_only=True))
                if name not in known:
                    continue
                jobs, tokenizer = known[name]
                for job in jobs:
                    key = name, job["id"]
                    response = run_dir / job["id"] / "yf/response.json"
                    if key in submitted or not response.exists():
                        continue
                    try:
                        receipt = json.loads(response.read_text())
                    except json.JSONDecodeError:
                        continue
                    text, _ = offsets(tokenizer, receipt["choices"][0]["token_ids"])
                    call = {"id": job["id"], "benchmark": job["benchmark"], "output": text,
                            "sources": job["sources"], "response_sha256": digest(response)}
                    folder = output / name / job["id"]
                    if (folder / "blind_record.json").exists():
                        if json.loads((folder / "blind_record.json").read_text()) != call:
                            raise ValueError("Existing blind review record belongs to a different call")
                    else:
                        write(folder / "blind_record.json", call)
                    future = pool.submit(annotate, call, folder, endpoint, model)
                    pending[future] = key, folder
                    submitted.add(key)
            for future in list(pending):
                if not future.done():
                    continue
                key, folder = pending.pop(future)
                try:
                    future.result()
                    print("draft", *key, flush=True)
                except Exception as error:
                    write(folder / "error.json", {"type": type(error).__name__, "detail": str(error)})
                    print("draft_error", *key, type(error).__name__, flush=True)
            if all((root / name / "completed.json").exists() for name in runs) and not pending:
                break
            time.sleep(2)
    write(output / "complete.json", {"calls": len(submitted),
                                     "validated_drafts": len(list(output.glob("*/*/validated.json"))),
                                     "review_complete": False})


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    parser.add_argument("--endpoint", default="http://127.0.0.1:8770")
    parser.add_argument("--model", default="/data/Qwen3.8-27B")
    args = parser.parse_args()
    run(args.root, args.endpoint, args.model)
