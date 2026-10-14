#!/usr/bin/env python3
"""Create-only LC-Sent-15-v1 import and frozen CPU-only BM25 gate."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from pathlib import Path
import random
import shutil
import statistics
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from memoryflow.lc_sent15_bm25 import rank_by_score_then_source_id, score_group

SEED = 20260815
BOOTSTRAP_REPS = 10_000
IMPLEMENTATIONS = ("BM25_LEGACY", "BM25_MIXED_V1")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def read_jsonl(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def dump_json(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def write_jsonl(path: Path, rows: list[dict]) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, allow_nan=False, sort_keys=True) + "\n")


def source_map(path: Path) -> dict[str, dict]:
    rows = read_jsonl(path)
    result = {row["id"]: row for row in rows}
    if len(result) != len(rows):
        raise ValueError(f"duplicate catalog id in {path}")
    return result


def target_metric(rows: list[dict]) -> dict[str, float | int]:
    ranks = [int(row["gold_rank"]) for row in rows]
    return {
        "target_count": len(rows),
        "hit_at_1": sum(rank == 1 for rank in ranks) / len(ranks),
        "mrr": sum(1.0 / rank for rank in ranks) / len(ranks),
        "ndcg_at_5": sum((1.0 / math.log2(rank + 1)) if rank <= 5 else 0.0 for rank in ranks) / len(ranks),
        "mean_gold_rank": statistics.fmean(ranks),
        "top1_failures": sum(rank != 1 for rank in ranks),
    }


def bootstrap(rows: list[dict]) -> dict[str, object]:
    rng = random.Random(SEED)
    values = {key: [] for key in ("hit_at_1", "mrr", "ndcg_at_5")}
    ranks = [int(row["gold_rank"]) for row in rows]
    for _ in range(BOOTSTRAP_REPS):
        sample = [ranks[rng.randrange(len(ranks))] for _ in ranks]
        values["hit_at_1"].append(sum(rank == 1 for rank in sample) / len(sample))
        values["mrr"].append(sum(1.0 / rank for rank in sample) / len(sample))
        values["ndcg_at_5"].append(sum((1.0 / math.log2(rank + 1)) if rank <= 5 else 0.0 for rank in sample) / len(sample))
    return {key: {"lower_95": sorted(draws)[249], "upper_95": sorted(draws)[9749]} for key, draws in values.items()}


def evaluate(split_rows: list[dict], catalog: dict[str, dict], implementation: str) -> list[dict]:
    records: list[dict] = []
    for example in split_rows:
        candidates = example["candidates"]
        ids = [candidate["source_id"] for candidate in candidates]
        documents = {source_id: catalog[source_id]["text"] for source_id in ids}
        scores = score_group(example["target"]["text"], documents, implementation=implementation)
        ranking = rank_by_score_then_source_id(scores)
        gold = next(candidate["source_id"] for candidate in candidates if int(candidate["label"]) == 1)
        rank = ranking.index(gold) + 1
        records.append({
            "implementation": implementation,
            "split": example["split"],
            "example_id": example["example_id"],
            "language": example["language"],
            "gold_source_id": gold,
            "gold_rank": rank,
            "top1_source_id": ranking[0],
            "candidate_ids": ids,
            "ranking": ranking,
            "scores": {source_id: scores[source_id] for source_id in ids},
        })
    return records


def summary(records: list[dict], *, include_bootstrap: bool) -> dict[str, object]:
    groups = {"overall": records}
    for language in ("zh", "en"):
        groups[language] = [row for row in records if row["language"] == language]
    result = {name: target_metric(rows) for name, rows in groups.items()}
    if include_bootstrap:
        result["overall_bootstrap_10000"] = bootstrap(records)
    return result


def random_baseline() -> dict[str, float]:
    return {
        "hit_at_1": 1.0 / 15,
        "mrr": sum(1.0 / rank for rank in range(1, 16)) / 15,
        "ndcg_at_5": sum(1.0 / math.log2(rank + 1) for rank in range(1, 6)) / 15,
    }


def copy_create_only(source: Path, target: Path) -> list[dict]:
    operations=[]
    for path in sorted(source.rglob("*")):
        if not path.is_file():
            continue
        rel=path.relative_to(source); out=target/rel
        digest=sha256(path)
        if out.exists():
            if out.is_file() and sha256(out)==digest:
                operations.append({"path":rel.as_posix(),"operation":"SKIP_IDENTICAL","sha256":digest})
                continue
            raise RuntimeError(f"CONFLICT {out}")
        out.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, out)
        if sha256(out)!=digest:
            raise RuntimeError(f"copy checksum mismatch {out}")
        operations.append({"path":rel.as_posix(),"operation":"CREATE_ONLY","sha256":digest})
    return operations


def main() -> int:
    ap=argparse.ArgumentParser()
    ap.add_argument("--data", type=Path, default=ROOT/"data/lc_sent15_v1")
    ap.add_argument("--out", type=Path, default=ROOT/"results/lc_sent15_v1_bm25_gate_v1")
    ap.add_argument("--staged", type=Path)
    args=ap.parse_args()
    data=args.data.resolve(); out=args.out.resolve()
    if out.exists(): raise RuntimeError(f"result output already exists: {out}")
    if args.staged:
        copy_create_only(args.staged.resolve(), data)
    for forbidden in ("blind", "reserve", "multi_positive"):
        if forbidden in str(data).lower() or forbidden in str(out).lower(): raise RuntimeError("forbidden path")
    start=time.monotonic(); tmp=out.with_name("."+out.name+".tmp")
    if tmp.exists(): raise RuntimeError(f"temporary output exists: {tmp}")
    tmp.mkdir(parents=True)
    try:
        contract=json.loads((data/"manifest.json").read_text(encoding="utf-8"))
        results={"config":{"bootstrap_seed":SEED,"bootstrap_reps":BOOTSTRAP_REPS,"ranking_tie_break":"score_desc_then_source_id_asc","query":"target statement only","candidate_position_feature":False,"legacy_lineage":{"code":"workspace/src/memoryflow/ranking_baselines.py","tokenizer":"mixed_tokenize","formula":"BM25Index k1=1.2 b=0.75 corpus restricted to each fixed candidate group"}},"random_baseline":random_baseline(),"implementations":{}}
        all_errors=[]
        for implementation in IMPLEMENTATIONS:
            impl={}
            for split in ("train","dev"):
                examples=read_jsonl(data/split/"single_positive_15.jsonl")
                catalog=source_map(data/split/"source_catalog.jsonl")
                records=evaluate(examples,catalog,implementation)
                write_jsonl(tmp/f"{implementation.lower()}_{split}_predictions.jsonl",records)
                impl[split]=summary(records,include_bootstrap=(split=="dev"))
                if split=="dev" and implementation=="BM25_MIXED_V1": all_errors=records
            results["implementations"][implementation]=impl
        dump_json(tmp/"metrics.json",results)
        write_jsonl(tmp/"dev_top1_failures.jsonl",[row for row in all_errors if row["gold_rank"] != 1])
        readable=[]
        for row in [row for row in all_errors if row["gold_rank"] != 1][:20]:
            readable.append({key:row[key] for key in ("example_id","language","gold_source_id","top1_source_id","gold_rank","scores")})
        dump_json(tmp/"dev_error_examples_max20.json",readable)
        strongest=max(IMPLEMENTATIONS,key=lambda name:results["implementations"][name]["dev"]["overall"]["hit_at_1"])
        marker="MEMORYFLOW_LC_SENT15_BM25_EASY_GATE" if results["implementations"][strongest]["dev"]["overall"]["hit_at_1"] >= .90 else "MEMORYFLOW_LC_SENT15_BM25_HEADROOM_PASS"
        difference=abs(results["implementations"][strongest]["dev"]["zh"]["hit_at_1"]-results["implementations"][strongest]["dev"]["en"]["hit_at_1"])
        if difference > .10: marker += "\nLANGUAGE_STRATIFICATION_REQUIRED"
        report=["# LC-Sent-15-v1 BM25 Gate", "", f"Marker: `{marker.replace(chr(10), '`, `')}`", "", f"Strongest frozen BM25: `{strongest}`.", "", "## Contract", "- Query: target statement only.", "- Documents: the fixed 15 candidate source texts per target.", "- Ranking: score descending, then source_id ascending.", "- No Qwen, GPU, embedding, training, Reserve, multi-positive, or Blind access.", "", "## Metrics"]
        for name in IMPLEMENTATIONS:
            dev=results['implementations'][name]['dev']; overall=dev['overall']; zh=dev['zh']; en=dev['en']
            report.extend([f"### {name}", f"- Dev overall: Hit@1={overall['hit_at_1']:.6f}, MRR={overall['mrr']:.6f}, nDCG@5={overall['ndcg_at_5']:.6f}.", f"- Dev zh ({zh['target_count']}): Hit@1={zh['hit_at_1']:.6f}; en ({en['target_count']}): Hit@1={en['hit_at_1']:.6f}."])
        (tmp/"BM25_GATE_REPORT.md").write_text("\n".join(report)+"\n",encoding="utf-8")
        integrity={"marker":marker.splitlines(),"data_manifest_sha256":sha256(data/"manifest.json"),"package_checksums_sha256":sha256(data/"checksums.sha256"),"runtime_seconds":time.monotonic()-start,"no_blind":True,"no_qwen":True,"no_gpu":True,"no_training":True,"files":{}}
        for path in sorted(p for p in tmp.rglob("*") if p.is_file()): integrity['files'][path.relative_to(tmp).as_posix()]=sha256(path)
        dump_json(tmp/"integrity_report.json",integrity)
        with (tmp/"checksums.sha256").open("w",encoding="utf-8") as handle:
            for path in sorted(p for p in tmp.rglob("*") if p.is_file() and p.name != "checksums.sha256"):
                handle.write(f"{sha256(path)}  {path.relative_to(tmp).as_posix()}\n")
        (tmp/"COMPLETED").write_text(marker+"\n",encoding="utf-8")
        tmp.rename(out)
    except BaseException:
        raise
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
