#!/usr/bin/env python3
"""Score frozen statements against frozen candidate pools with the fixed 7B head.

Reuses the frozen GenMem scoring implementation (``experiments/genmem_quality_v2/predict.py``):
Qwen2.5-7B-Instruct, BF16, eager attention, fixed zero-based head (19, 15), the fixed
query and ``\\n\\n``-joined candidates, target rows read from the appended statement.

Three matrices per sample:
  m2     final sentence  vs round-2 units (raw materials + transmitted conclusion)
  m1     round-1 answer  vs round-1 raw materials
  mflat  final sentence  vs the merged raw materials of both rounds
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import core

EXPERIMENT_ROOT = Path(__file__).resolve().parents[2]
GENMEM_QUALITY = EXPERIMENT_ROOT / "experiments/genmem_quality_v2"
YIFENG = EXPERIMENT_ROOT / "artifacts/third_party/yifeng_20261016/AAAI27_supplementary_material"


def candidate_pools(frozen: dict) -> dict[str, dict]:
    r1 = frozen["rounds"][0]["materials"]
    r2 = frozen["rounds"][1]["materials"]
    conclusion = {
        "id": "conclusion:r1",
        "text": frozen["rounds"][0]["answer"],
        "source": "assistant_transmission",
    }
    m1_candidates = [{"id": item["unit_id"], "text": item["text"]} for item in r1]
    m2_candidates = [{"id": conclusion["id"], "text": conclusion["text"]}] + [
        {"id": item["unit_id"], "text": item["text"]} for item in r2
    ]
    seen = {item["id"] for item in m1_candidates}
    flat_candidates = list(m1_candidates)
    for item in r2:
        if item["unit_id"] not in seen:
            flat_candidates.append({"id": item["unit_id"], "text": item["text"]})
            seen.add(item["unit_id"])
    return {
        "m1": {
            "target": frozen["rounds"][0]["answer"],
            "candidates": m1_candidates,
            "note": "round-1 statement against round-1 raw materials",
        },
        "m2": {
            "target": frozen["rounds"][1]["answer"],
            "candidates": m2_candidates,
            "note": "final statement against round-2 units (raw materials + transmitted conclusion)",
        },
        "mflat": {
            "target": frozen["rounds"][1]["answer"],
            "candidates": flat_candidates,
            "note": "final statement against the merged raw materials of both rounds",
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--frozen", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--root", required=True, help="memoryflow root on the server")
    parser.add_argument("--physical-gpu", type=int, required=True)
    parser.add_argument("--memory-cap-gib", type=float, default=22.0)
    parser.add_argument("--repeat", type=int, default=2)
    args = parser.parse_args(argv)

    frozen = core.read_json(args.frozen)
    pools = candidate_pools(frozen)
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

    results = {}
    for matrix_id, pool in pools.items():
        row = {
            "id": matrix_id,
            "case": frozen["source"]["case"],
            "query": core.FIXED_QUERY,
            "target": {"text": pool["target"]},
            "candidates": pool["candidates"],
        }
        case = gq.build_case(tokenizer, row, "")
        if len(case["prompt_ids"]) + len(case["target_ids"]) > gq.NATIVE_CONTEXT:
            raise core.SpecError(f"{matrix_id} exceeds the model context")
        cache = engine.prefill(case["prompt_ids"][:-1])
        prefix_length = len(case["prompt_ids"]) - 1
        block = [case["prompt_ids"][-1]] + case["target_ids"][:-1]
        rows_to_read = gq.read_rows(0, case["target_length"])
        repeats = []
        started = time.monotonic()
        for _ in range(max(1, args.repeat)):
            captured = engine.block(cache, block, rows_to_read, case["ranges"])
            crop = getattr(gq, "crop_cache", None)
            if crop is not None:
                crop(cache, prefix_length)
            repeats.append(np.asarray(captured[gq.FIXED_LAYER][gq.FIXED_HEAD], dtype=np.float64))
        elapsed = time.monotonic() - started
        scores = repeats[0]
        max_repeat = 0.0
        for other in repeats[1:]:
            max_repeat = max(max_repeat, float(np.max(np.abs(repeats[0] - other))))
        total = float(scores.sum())
        order = np.argsort(-scores)
        rank_of = {int(index): rank for rank, index in enumerate(order, start=1)}
        entries = []
        for index, candidate in enumerate(pool["candidates"]):
            entries.append(
                {
                    "id": candidate["id"],
                    "text": candidate["text"],
                    "score": float(scores[index]),
                    "share": float(scores[index] / total) if total else None,
                    "rank": rank_of[index],
                }
            )
        results[matrix_id] = {
            "matrix_id": matrix_id,
            "target": pool["target"],
            "note": pool["note"],
            "prompt_tokens": case["prompt_length"],
            "target_tokens": case["target_length"],
            "total_tokens": case["prompt_length"] + case["target_length"],
            "candidates": entries,
            "candidate_mass_sum": total,
            "max_repeat_difference": max_repeat,
            "seconds": round(elapsed, 3),
        }
        print(json.dumps({"matrix": matrix_id, "prompt_tokens": case["prompt_length"],
                          "target_tokens": case["target_length"],
                          "repeat_diff": max_repeat}, ensure_ascii=False), flush=True)
        del cache

    payload = {
        "schema": "provenance_rounds_v1.scores.v1",
        "sample": frozen["source"]["target_id"],
        "frozen_sha256": frozen["frozen_sha256"],
        "runtime": runtime,
        "head": {"model": "Qwen2.5-7B-Instruct", "layer": gq.FIXED_LAYER, "head": gq.FIXED_HEAD,
                 "query": core.FIXED_QUERY},
        "matrices": results,
    }
    core.write_json(args.out, payload)
    print(json.dumps({"scores_out": args.out,
                      "matrices": {k: len(v["candidates"]) for k, v in results.items()}},
                     ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
