#!/usr/bin/env python3
"""Compute fixed-head matrices for unified multi-turn cases (GPU).

For every case in a batch directory:
  r1    round-1 output        vs round-1 raw materials
  r2    final round output    vs [transmitted previous output] + round-2 raw materials
  flat  final output          vs the full original candidate pool

The scoring implementation is the same frozen one used for the 47-target table
(``experiments/genmem_quality_v2/predict.py``: Qwen2.5-7B-Instruct, BF16, eager,
fixed layer 19 / head 15, the fixed query, ``\\n\\n``-joined candidates).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import cases

EXPERIMENT_ROOT = Path(__file__).resolve().parents[2]
GENMEM_QUALITY = EXPERIMENT_ROOT / "experiments/genmem_quality_v2"
YIFENG = EXPERIMENT_ROOT / "artifacts/third_party/yifeng_20261016/AAAI27_supplementary_material"


def matrix_rows(case: dict, flat_pool: str = "all") -> dict[str, dict]:
    rounds = case["rounds"]
    rows = {}
    for round_record in rounds:
        key = f"r{round_record['round']}"
        candidates = [
            {"canonical_id": material["canonical_id"], "text": material["text"]}
            if "canonical_id" in material
            else {
                "canonical_id": cases.canonical_id(material["artifact_id"], material["start"], material["end"]),
                "text": material["text"],
            }
            for material in round_record["inputs"]
        ]
        if round_record["round"] > 1:
            previous = rounds[round_record["round"] - 2]["output"]["text"]
            candidates.insert(0, {"canonical_id": f"transmission:r{round_record['round'] - 1}", "text": previous})
        rows[key] = {"target": round_record["output"]["text"], "candidates": candidates}
    if flat_pool == "union":
        seen = set()
        flat_candidates = []
        for round_record in rounds:
            for material in round_record["inputs"]:
                cid = cases.canonical_id(material["artifact_id"], material["start"], material["end"])
                if cid in seen:
                    continue
                seen.add(cid)
                flat_candidates.append({"canonical_id": cid, "text": material["text"]})
    else:
        flat_candidates = [
            {"canonical_id": candidate["canonical_id"], "text": candidate["text"]}
            for candidate in case["candidates"]
        ]
    rows["flat"] = {"target": case["target"]["text"], "candidates": flat_candidates}
    return rows


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dir", required=True, help="batch directory with manifest.json")
    parser.add_argument("--root", required=True, help="memoryflow root on the server")
    parser.add_argument("--physical-gpu", type=int, required=True)
    parser.add_argument("--memory-cap-gib", type=float, default=24.0)
    parser.add_argument("--repeat", type=int, default=1)
    parser.add_argument("--flat-pool", choices=["all", "union"], default=None,
                        help="flat candidate pool; default uses case.analysis_pool")
    args = parser.parse_args(argv)

    directory = Path(args.dir).resolve()
    manifest = cases.read_json(directory / "manifest.json")
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"
    os.environ["CUDA_VISIBLE_DEVICES"] = str(args.physical_gpu)
    os.environ.setdefault("PYTORCH_CUDA_ALLOC_CONF", "expandable_segments:True")

    sys.path.insert(0, str(GENMEM_QUALITY))
    sys.path.insert(0, str(YIFENG))
    import numpy as np
    import predict as gq

    paths = gq.Paths(Path(args.root).resolve())
    runtime = gq.configure_runtime(args.physical_gpu, args.memory_cap_gib)
    tokenizer, model = gq.load_model(paths)
    engine = gq.Engine(model, tokenizer, [gq.FIXED_LAYER])

    for row in manifest["cases"]:
        case = cases.read_json(directory / row["case_path"])
        plans = matrix_rows(case, args.flat_pool or case.get("analysis_pool", "all"))
        results = {}
        for matrix_id, plan in plans.items():
            scoring_row = {
                "id": matrix_id,
                "case": case["case_id"],
                "query": "Identify earlier text relevant to the supplied statement.",
                "target": {"text": plan["target"]},
                "candidates": [{"id": item["canonical_id"], "text": item["text"]} for item in plan["candidates"]],
            }
            built = gq.build_case(tokenizer, scoring_row, "")
            cache = engine.prefill(built["prompt_ids"][:-1])
            block = [built["prompt_ids"][-1]] + built["target_ids"][:-1]
            rows_to_read = gq.read_rows(0, built["target_length"])
            repeats = []
            started = time.monotonic()
            for _ in range(max(1, args.repeat)):
                captured = engine.block(cache, block, rows_to_read, built["ranges"])
                gq.crop_cache(cache, len(built["prompt_ids"]) - 1)
                repeats.append(np.asarray(captured[gq.FIXED_LAYER][gq.FIXED_HEAD], dtype=np.float64))
            scores = repeats[0]
            max_repeat = 0.0
            for other in repeats[1:]:
                max_repeat = max(max_repeat, float(np.max(np.abs(repeats[0] - other))))
            results[matrix_id] = {
                "target": plan["target"],
                "candidates": [
                    {"canonical_id": item["canonical_id"], "text": item["text"], "score": float(scores[index])}
                    for index, item in enumerate(plan["candidates"])
                ],
                "prompt_tokens": built["prompt_length"],
                "target_tokens": built["target_length"],
                "total_tokens": built["prompt_length"] + built["target_length"],
                "max_repeat_difference": max_repeat,
                "seconds": round(time.monotonic() - started, 3),
            }
            print(json.dumps({"case": case["case_id"], "matrix": matrix_id,
                              "prompt": built["prompt_length"], "target": built["target_length"]},
                             ensure_ascii=False), flush=True)
            del cache
        payload = {
            "schema": cases.MATRIX_SCHEMA,
            "case_id": case["case_id"],
            "final_round": f"r{len(case['rounds'])}",
            "hop_budget": cases.HOP_BUDGET,
            "final_budget": cases.FINAL_BUDGET,
            "matrices": results,
            "source": {
                "model": "Qwen2.5-7B-Instruct",
                "layer": gq.FIXED_LAYER,
                "head": gq.FIXED_HEAD,
                "runtime": runtime,
                "scored_at": "2026-11-06",
            },
        }
        output_path = directory / row["matrix_path"]
        cases.write_json(output_path, payload)
        print(json.dumps({"wrote": str(output_path), "case": case["case_id"]}, ensure_ascii=False), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
