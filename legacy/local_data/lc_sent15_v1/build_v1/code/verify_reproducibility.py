"""Compare deterministic LC-Sent-15-v1 payloads from two complete builds."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


PAYLOADS = (
    "split_assignments.jsonl",
    "train/single_positive_15.jsonl",
    "train/multi_positive_sidecar.jsonl",
    "train/source_catalog.jsonl",
    "dev/single_positive_15.jsonl",
    "dev/multi_positive_sidecar.jsonl",
    "dev/source_catalog.jsonl",
    "sealed_reserve/single_positive_15.jsonl",
    "sealed_reserve/source_catalog.jsonl",
    "sealed_reserve/RESERVE_MANIFEST.json",
    "samples/train_examples_3.jsonl",
    "samples/dev_examples_3.jsonl",
)


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--primary", required=True)
    parser.add_argument("--rebuild", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    primary = Path(args.primary)
    rebuild = Path(args.rebuild)
    files = []
    for relative in PAYLOADS:
        left = digest(primary / relative)
        right = digest(rebuild / relative)
        files.append({"path": relative, "primary_sha256": left, "rebuild_sha256": right, "match": left == right})
    primary_metrics = json.loads((primary / "build_metrics.json").read_text(encoding="utf-8"))
    rebuild_metrics = json.loads((rebuild / "build_metrics.json").read_text(encoding="utf-8"))
    primary_metrics.pop("elapsed_seconds", None)
    rebuild_metrics.pop("elapsed_seconds", None)
    metrics_match = primary_metrics == rebuild_metrics
    report = {
        "schema_version": "lc-sent-15-v1-reproducibility-v1",
        "full_rebuild_completed": True,
        "payload_file_count": len(files),
        "payload_matches": sum(item["match"] for item in files),
        "all_payload_sha256_match": all(item["match"] for item in files),
        "timing_excluded_metrics_match": metrics_match,
        "files": files,
        "status": "pass" if all(item["match"] for item in files) and metrics_match else "fail",
    }
    Path(args.output).write_text(json.dumps(report, indent=2), encoding="utf-8", newline="\n")
    print("LC_SENT15_REPRODUCIBILITY_PASS" if report["status"] == "pass" else "LC_SENT15_REPRODUCIBILITY_FAIL")
    return 0 if report["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
