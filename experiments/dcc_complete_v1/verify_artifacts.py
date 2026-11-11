"""Bind complete-row coverage and paired artifacts to the frozen inputs."""
import hashlib
import json
from pathlib import Path

import numpy as np

from pipeline import write


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def verify(root, output):
    lock = json.loads((root / "formal_lock.json").read_text())
    if digest(root / "formal_inputs.json") != lock["sha256"]:
        raise ValueError("Frozen inputs changed")
    expected = {job["id"]: job["input_sha256"] for job in json.loads((root / "formal_inputs.json").read_text())}
    rows = []
    for name in ("formal_1_5b", "formal_7b", "formal_27b"):
        run = root / name
        jobs = json.loads((run / "inputs.json").read_text())
        if {job["id"]: job["input_sha256"] for job in jobs} != expected:
            raise ValueError("Models did not use identical frozen requests")
        if not (run / "completed.json").is_file():
            raise ValueError("Run did not finish")
        for job in jobs:
            receipt = run / job["id"] / "yf" / "response.json"
            generated = json.loads(receipt.read_text())["choices"][0]["token_ids"]
            for source in job["sources"]:
                a, b = source["span"]
                original = job["request"]["messages"][source["message_index"]]["content"]
                if original[a:b] != source["text"]:
                    raise ValueError("Candidate is not an exact recorded-input span")
            record = {"run": name, "id": job["id"], "benchmark": job["benchmark"],
                      "prompt_tokens": len(job["prompt_ids"]), "output_tokens": len(generated),
                      "candidate_count": len(job["sources"]), "files": {}}
            for method in ("yf", "mf"):
                matrix_path = run / job["id"] / f"{method}.npy"
                matrix = np.load(matrix_path, mmap_mode="r", allow_pickle=False)
                header_path = run / job["id"] / method / "capture" / "qk.json"
                header = json.loads(header_path.read_text())
                if matrix.shape != (len(generated), len(job["sources"])) or not np.isfinite(matrix).all():
                    raise ValueError("Invalid full-call matrix")
                if header["rows"] < len(job["prompt_ids"])+len(generated)-1:
                    raise ValueError("Missing prediction rows")
                record[method] = {"shape": list(matrix.shape), "qk_rows": header["rows"], "head": header["config"]}
                for path in (matrix_path, header_path, header_path.with_name("qk.safetensors"),
                             run / job["id"] / method / "request.json", run / job["id"] / method / "response.json"):
                    record["files"][str(path.relative_to(root))] = digest(path)
            rows.append(record)
    write(output, {"frozen_inputs_sha256": lock["sha256"], "calls_per_model": 30,
                   "paired_calls": len(rows), "matrices": 2*len(rows), "coverage": "all output token rows",
                   "runs": rows})


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    verify(args.root, args.output)
