#!/usr/bin/env python3
"""Freeze one controlled two-round sample from the GenMem batch10 v3 archive."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import core


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, help="batch10 v3 zip, or an extracted directory")
    parser.add_argument("--recipe", required=True, help="recipe json")
    parser.add_argument("--out", required=True, help="frozen spec json")
    args = parser.parse_args(argv)

    source = Path(args.source)
    recipe = core.read_json(args.recipe)
    spec = core.build_spec(source, recipe)

    if source.is_file():
        spec["source"]["archive_path"] = str(source)
        spec["source"]["archive_sha256"] = core.sha256_file(source)
    for name in (
        f"contextual64_v4/{spec['source']['case']}/ground_truth.json",
        f"contextual64_v4/{spec['source']['case']}/source_units.jsonl",
    ):
        data = core.open_member(source, name)
        spec["source"][Path(name).name + "_sha256"] = core.sha256_bytes(data)

    spec["spec_sha256"] = core.sha256_text(core.canonical({k: v for k, v in spec.items() if k != "spec_sha256"}))
    core.write_json(args.out, spec)

    summary = {
        "sample": spec["source"]["target_id"],
        "round1_materials": len(spec["rounds"][0]["materials"]),
        "round2_materials": len(spec["rounds"][1]["materials"]),
        "merged_raw_units": len(spec["checks"]["merged_raw_units"]),
        "round2_without_A_passed": spec["checks"]["round2_without_evidence_a"]["passed"],
        "max_shared_shingles": spec["checks"]["round2_without_evidence_a"]["max_shared_shingles"],
        "max_lcs_chars": spec["checks"]["round2_without_evidence_a"]["max_lcs_chars"],
        "spec_sha256": spec["spec_sha256"],
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
