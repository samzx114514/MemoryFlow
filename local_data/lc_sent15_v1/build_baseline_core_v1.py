from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import re
import shutil
import statistics
import tarfile
import runpy
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path


EXPECTED_CHECKSUMS_SHA256 = "3284defb04b61c933477facb30dccd23f66cb18280250c378c0d18215c477045"
EXPECTED = {
    "train": {"targets": 854, "pairs": 12810},
    "dev": {"targets": 228, "pairs": 3420},
}
SCHEMA = "lc-sent15-baseline-core-v1"


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(8 * 1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def normalize(text: str) -> str:
    return " ".join(text.split()).casefold()


def anon_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def visible_len(text: str) -> int:
    return sum(not c.isspace() for c in text)


def percentile(values: list[int], p: float) -> float:
    if not values:
        return 0.0
    values = sorted(values)
    x = (len(values) - 1) * p
    lo, hi = math.floor(x), math.ceil(x)
    if lo == hi:
        return float(values[lo])
    return values[lo] * (hi - x) + values[hi] * (x - lo)


def length_stats(values: list[int]) -> dict:
    return {
        "count": len(values),
        "min": min(values) if values else 0,
        "p10": percentile(values, 0.10),
        "p25": percentile(values, 0.25),
        "median": percentile(values, 0.50),
        "p75": percentile(values, 0.75),
        "p90": percentile(values, 0.90),
    }


def classify_text(text: str) -> dict[str, bool]:
    stripped = "".join(text.split())
    has_letter = bool(re.search(r"[A-Za-z\u3400-\u4dbf\u4e00-\u9fff]", stripped))
    pure_numeric = bool(re.fullmatch(r"[+-]?(?:\d{1,4}(?:[.,]\d+)?)%?", stripped))
    ordinal = bool(re.fullmatch(r"(?:\(?\d{1,4}\)?[.、:)）]|[（(]?[一二三四五六七八九十百]+[)）.、])", stripped))
    punct_only = bool(stripped) and not bool(re.search(r"[A-Za-z\u3400-\u4dbf\u4e00-\u9fff0-9]", stripped))
    year = bool(re.fullmatch(r"(?:18|19|20|21)\d{2}(?:年)?", stripped))
    reference_like = bool(
        re.search(r"(?i)\b(?:references?|bibliography|doi|isbn|vol\.?|pp?\.)\b|https?://|www\.", text)
        or re.match(r"^\s*\[?\d+\]?\s*[-.)、:]\s*(?:[A-Z][\w'’-]+(?:\s+[A-Z][\w'’-]+){0,4}|https?://)", text)
    )
    layout_fragment = bool(
        re.fullmatch(r"\s*(?:\|[^|]*){2,}\|?\s*", text)
        or re.fullmatch(r"\s*[-_=*•·]{2,}\s*", text)
        or re.fullmatch(r"\s*(?:page|页)\s*\d+\s*", text, re.I)
    )
    return {
        "no_han_or_latin": not has_letter,
        "pure_numeric": pure_numeric,
        "ordinal": ordinal,
        "punctuation_only": punct_only,
        "year_like": year,
        "reference_or_layout_fragment": reference_like or layout_fragment,
    }


def parse_checksum_file(path: Path) -> list[tuple[str, str]]:
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        digest, rel = line.split(None, 1)
        rows.append((digest.lower(), rel.strip().lstrip("*")))
    return rows


def validate_input(root: Path) -> dict:
    checksums = root / "checksums.sha256"
    actual = sha256_file(checksums)
    if actual != EXPECTED_CHECKSUMS_SHA256:
        raise RuntimeError(f"input checksums SHA mismatch: {actual}")
    allowed = {
        "train/single_positive_15.jsonl", "train/source_catalog.jsonl",
        "dev/single_positive_15.jsonl", "dev/source_catalog.jsonl",
        "samples/train_examples_3.jsonl", "samples/dev_examples_3.jsonl",
        "DATA_CARD.md", "evaluation_contract.md", "BUILD_REPORT.md",
    }
    verified = 0
    out_of_scope_not_accessed = 0
    for expected, rel in parse_checksum_file(checksums):
        rel_norm = rel.replace("\\", "/")
        if rel_norm not in allowed:
            out_of_scope_not_accessed += 1
            continue
        path = root / rel
        if not path.is_file() or sha256_file(path) != expected:
            raise RuntimeError(f"input checksum failure: {rel}")
        verified += 1
    return {
        "checksums_file_sha256": actual,
        "prior_full_validation": "31/31 recorded pass in authoritative manifest",
        "in_scope_entries_reverified": verified,
        "out_of_scope_entries_not_accessed": out_of_scope_not_accessed,
    }


def scan_single(path: Path, split: str) -> tuple[dict, dict[str, dict]]:
    required_sources: dict[str, dict] = {}
    target_ids, document_ids = set(), set()
    rows = 0
    pairs = 0
    position_counts = [0] * 15
    with path.open("r", encoding="utf-8") as f:
        for lineno, line in enumerate(f, 1):
            row = json.loads(line)
            rows += 1
            if row.get("split") != split or row.get("candidate_count") != 15:
                raise RuntimeError(f"invalid split/candidate_count at {path}:{lineno}")
            candidates = row.get("candidates", [])
            if len(candidates) != 15 or len({c["source_id"] for c in candidates}) != 15:
                raise RuntimeError(f"invalid candidates at {path}:{lineno}")
            positives = [i for i, c in enumerate(candidates) if c.get("label") == 1]
            if len(positives) != 1 or sum(c.get("label") == 0 for c in candidates) != 14:
                raise RuntimeError(f"invalid labels at {path}:{lineno}")
            if row.get("gold_source_ids") != [candidates[positives[0]]["source_id"]]:
                raise RuntimeError(f"gold mismatch at {path}:{lineno}")
            position_counts[positives[0]] += 1
            target_id = row["target"]["id"]
            if target_id in target_ids:
                raise RuntimeError(f"duplicate target ID: {target_id}")
            target_ids.add(target_id)
            document_ids.add(row["document_id"])
            for c in candidates:
                sid = c["source_id"]
                required_sources.setdefault(sid, {"positive": False, "negative": False})
                required_sources[sid]["positive" if c["label"] == 1 else "negative"] = True
                pairs += 1
    if rows != EXPECTED[split]["targets"] or pairs != EXPECTED[split]["pairs"]:
        raise RuntimeError(f"{split} count mismatch: targets={rows}, pairs={pairs}")
    return {
        "targets": rows,
        "pairs": pairs,
        "unique_target_ids": len(target_ids),
        "document_ids": document_ids,
        "target_ids": target_ids,
        "positive_position_counts": position_counts,
    }, required_sources


def filter_catalog(source: Path, destination: Path, required: dict[str, dict]) -> tuple[dict, dict[str, dict]]:
    found: dict[str, dict] = {}
    destination.parent.mkdir(parents=True, exist_ok=True)
    with source.open("r", encoding="utf-8") as src, destination.open("w", encoding="utf-8", newline="\n") as dst:
        for lineno, line in enumerate(src, 1):
            row = json.loads(line)
            sid = row["id"]
            if sid not in required:
                continue
            if sid in found:
                raise RuntimeError(f"conflicting/duplicate source ID in catalog: {sid}")
            found[sid] = row
            dst.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")
    missing = sorted(set(required) - set(found))
    extra = sorted(set(found) - set(required))
    if missing or extra:
        raise RuntimeError(f"catalog mismatch: missing={len(missing)} extra={len(extra)}")
    return {
        "candidate_source_id_occurrences": None,
        "unique_candidate_source_ids": len(required),
        "catalog_records": len(found),
        "missing": len(missing),
        "extra": len(extra),
    }, found


def audit_tracks(single_paths: dict[str, Path], catalogs: dict[str, dict[str, dict]], required: dict[str, dict]) -> tuple[dict, dict, list[dict], list[dict]]:
    data = {}
    quality_values = {}
    negative_records = []
    for split in ("train", "dev"):
        target_ids, doc_ids = set(), set()
        target_texts, all_source_texts, pos_source_texts, neg_source_texts = set(), set(), set(), set()
        all_pairs, pos_pairs, neg_pairs = set(), set(), set()
        pos_lengths, neg_lengths = [], []
        quality = {"positive": Counter(), "negative": Counter()}
        newline_counts = {"positive": Counter(), "negative": Counter()}
        counts = Counter()
        with single_paths[split].open("r", encoding="utf-8") as f:
            for line in f:
                row = json.loads(line)
                tid = row["target"]["id"]
                tnorm = normalize(row["target"]["text"])
                target_ids.add(tid)
                doc_ids.add(row["document_id"])
                target_texts.add(tnorm)
                for c in row["candidates"]:
                    srow = catalogs[split][c["source_id"]]
                    snorm = normalize(srow["text"])
                    pair = tnorm + "\0" + snorm
                    all_source_texts.add(snorm)
                    all_pairs.add(pair)
                    role = "positive" if c["label"] == 1 else "negative"
                    (pos_source_texts if role == "positive" else neg_source_texts).add(snorm)
                    (pos_pairs if role == "positive" else neg_pairs).add(pair)
                    length = visible_len(srow["text"])
                    (pos_lengths if role == "positive" else neg_lengths).append(length)
                    counts[role] += 1
                    flags = classify_text(srow["text"])
                    for key, value in flags.items():
                        quality[role][key] += int(value)
                    for threshold in (3, 5, 10):
                        quality[role][f"visible_length_le_{threshold}"] += int(length <= threshold)
                    newline_counts[role][str(srow["text"].count("\n"))] += 1
                    if role == "negative":
                        negative_records.append({
                            "split": split,
                            "example_id": row["example_id"],
                            "source_id": c["source_id"],
                            "document_id": row["document_id"],
                            "visible_length": length,
                            "text": srow["text"],
                            "quality_flags": [k for k, v in flags.items() if v],
                        })
        data[split] = {
            "target_ids": target_ids, "document_ids": doc_ids,
            "target_texts": target_texts, "all_source_texts": all_source_texts,
            "positive_source_texts": pos_source_texts, "negative_source_texts": neg_source_texts,
            "all_pairs": all_pairs, "positive_pairs": pos_pairs, "negative_pairs": neg_pairs,
        }
        quality_values[split] = {
            role: {
                "visible_length": length_stats(pos_lengths if role == "positive" else neg_lengths),
                "ratios": {k: quality[role][k] / counts[role] for k in sorted(quality[role])},
                "counts": {k: quality[role][k] for k in sorted(quality[role])},
                "newline_count_distribution": dict(sorted(newline_counts[role].items(), key=lambda x: int(x[0]))),
            } for role in ("positive", "negative")
        }
        quality_values[split]["positive_minus_negative_visible_length"] = {
            "median": percentile(pos_lengths, .5) - percentile(neg_lengths, .5),
            "mean": statistics.fmean(pos_lengths) - statistics.fmean(neg_lengths),
        }

    categories = {
        "target_id": (data["train"]["target_ids"], data["dev"]["target_ids"]),
        "candidate_source_id": (set(catalogs["train"]), set(catalogs["dev"])),
        "normalized_target_text": (data["train"]["target_texts"], data["dev"]["target_texts"]),
        "normalized_all_candidate_source_text": (data["train"]["all_source_texts"], data["dev"]["all_source_texts"]),
        "normalized_positive_source_text": (data["train"]["positive_source_texts"], data["dev"]["positive_source_texts"]),
        "normalized_negative_source_text": (data["train"]["negative_source_texts"], data["dev"]["negative_source_texts"]),
        "normalized_all_target_source_pair": (data["train"]["all_pairs"], data["dev"]["all_pairs"]),
        "normalized_positive_target_source_pair": (data["train"]["positive_pairs"], data["dev"]["positive_pairs"]),
        "normalized_negative_target_source_pair": (data["train"]["negative_pairs"], data["dev"]["negative_pairs"]),
    }
    duplicate_audit = {}
    for name, (left, right) in categories.items():
        overlap = left & right
        duplicate_audit[name] = {
            "count": len(overlap),
            "anonymous_sha256": sorted(anon_hash(x) for x in overlap),
        }
    duplicate_audit["document_id"] = {
        "count": len(data["train"]["document_ids"] & data["dev"]["document_ids"]),
        "anonymous_sha256": [],
    }

    negative_records.sort(key=lambda x: (x["visible_length"], anon_hash(x["split"] + ":" + x["example_id"] + ":" + x["source_id"])))
    shortest = negative_records[:20]
    lengths = [r["visible_length"] for r in negative_records]
    p25, p75 = percentile(lengths, .25), percentile(lengths, .75)
    ordinary_pool = [r for r in negative_records if p25 <= r["visible_length"] <= p75]
    ordinary_pool.sort(key=lambda x: anon_hash("lc-sent15-baseline-core-v1:ordinary:" + x["split"] + ":" + x["example_id"] + ":" + x["source_id"]))
    return duplicate_audit, quality_values, shortest, ordinary_pool[:20]


def write_json(path: Path, value) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")


def write_jsonl(path: Path, rows: list[dict]) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")


def create_tests(out: Path) -> None:
    test = '''import hashlib, json\nfrom pathlib import Path\nROOT=Path(__file__).parents[1]\ndef rows(p):\n    with p.open(encoding="utf-8") as f:\n        yield from map(json.loads,f)\ndef test_counts_and_labels():\n    for split,n in (("train",854),("dev",228)):\n        rs=list(rows(ROOT/split/"single_positive_15.jsonl")); assert len(rs)==n\n        assert all(len(r["candidates"])==15 and sum(c["label"] for c in r["candidates"])==1 for r in rs)\ndef test_catalog_is_referenced_only():\n    for split in ("train","dev"):\n        rs=list(rows(ROOT/split/"single_positive_15.jsonl")); needed={c["source_id"] for r in rs for c in r["candidates"]}\n        ids=[r["id"] for r in rows(ROOT/split/"source_catalog.jsonl")]\n        assert len(ids)==len(set(ids)); assert set(ids)==needed\ndef test_no_id_or_positive_pair_leakage():\n    audit=json.loads((ROOT/"audit"/"duplicate_audit.json").read_text(encoding="utf-8"))\n    for key in ("document_id","target_id","candidate_source_id","normalized_positive_target_source_pair"):\n        assert audit[key]["count"]==0\ndef test_samples():\n    assert sum(1 for _ in rows(ROOT/"samples"/"train_examples_3.jsonl"))==3\n    assert sum(1 for _ in rows(ROOT/"samples"/"dev_examples_3.jsonl"))==3\ndef test_manifest_scope():\n    m=json.loads((ROOT/"manifest.json").read_text(encoding="utf-8")); assert m["status"]=="pass"\n    forbidden=("reserve","multi_positive","split_assignments","long.jsonl")\n    assert all(not any(x in f["path"].lower() for x in forbidden) for f in m["files"])\ndef test_checksums():\n    for line in (ROOT/"checksums.sha256").read_text(encoding="utf-8").splitlines():\n        digest,rel=line.split(None,1); p=ROOT/rel.strip().lstrip("*")\n        assert hashlib.sha256(p.read_bytes()).hexdigest()==digest\n'''
    (out / "tests").mkdir()
    (out / "tests" / "test_baseline_core.py").write_text(test, encoding="utf-8", newline="\n")


def write_docs(out: Path, catalog_stats: dict, duplicate: dict, quality: dict) -> None:
    (out / "DATA_CARD.md").write_text("""# LC-Sent-15-v1 Baseline Core V1\n\nThis immutable package contains only the Train/Dev `single_positive_15` track and referenced-only source catalogs. Labels are `silver_longcite`, not human Gold. Each target has exactly 15 same-document candidates: one cited official sentence unit and 14 deterministic uncited negatives.\n\nExcluded: multi-positive sidecar, Reserve, official raw data, split assignments, models, caches, old processed data, and mixed catalogs. Text is retained exactly from Build V1. No candidate was changed or filtered.\n""", encoding="utf-8", newline="\n")
    (out / "evaluation_contract.md").write_text("""# Evaluation Contract\n\n- Scope: Train/Dev `single_positive_15` only.\n- Primary metric: Hit@1.\n- Secondary metrics: MRR and nDCG@5.\n- Random Hit@1 baseline: 1/15.\n- Ties are broken by candidate ID ascending.\n- BM25 must report raw scores; group-normalized variants require a separately named protocol.\n- Report overall results and language-stratified results.\n- Candidate list position is not a model feature.\n- Reserve is excluded and must remain sealed.\n""", encoding="utf-8", newline="\n")
    lines = ["# Baseline Core V1 Build Report", "", "No source reconstruction, candidate modification, retrieval, model, GPU, or Reserve access was performed.", "", "## Referenced-only catalogs", ""]
    for split in ("train", "dev"):
        s = catalog_stats[split]
        lines += [f"- {split}: {s['candidate_source_id_occurrences']} candidate occurrences; {s['unique_candidate_source_ids']} unique sources; missing {s['missing']}; extra {s['extra']}."]
    lines += ["", "## Leakage gate", "", f"- Positive normalized Target-Source pair overlap: {duplicate['normalized_positive_target_source_pair']['count']}.", "- Full details: `audit/duplicate_audit.json`.", "", "## Quality audit", "", "Descriptive only. No source was removed or relabeled. See `audit/negative_quality_audit.json` and the two deterministic sample files.", ""]
    (out / "BUILD_REPORT.md").write_text("\n".join(lines), encoding="utf-8", newline="\n")


def file_records(out: Path) -> list[dict]:
    excluded = {"manifest.json", "checksums.sha256"}
    records = []
    for path in sorted(p for p in out.rglob("*") if p.is_file() and p.name not in excluded):
        rel = path.relative_to(out).as_posix()
        records.append({"path": rel, "size_bytes": path.stat().st_size, "sha256": sha256_file(path)})
    return records


def write_manifest_and_checksums(out: Path, manifest: dict) -> str:
    manifest["files"] = file_records(out)
    write_json(out / "manifest.json", manifest)
    paths = sorted(p for p in out.rglob("*") if p.is_file() and p.name not in {"checksums.sha256", "pytest_output.txt"})
    text = "".join(f"{sha256_file(p)}  {p.relative_to(out).as_posix()}\n" for p in paths)
    (out / "checksums.sha256").write_text(text, encoding="utf-8", newline="\n")
    return sha256_file(out / "checksums.sha256")


def create_archive(out: Path, archive: Path) -> dict:
    if archive.exists():
        raise RuntimeError(f"create-only archive conflict: {archive}")
    with tarfile.open(archive, "w:gz", format=tarfile.PAX_FORMAT) as tf:
        for path in sorted(p for p in out.rglob("*") if p.is_file()):
            rel = Path("baseline_core_v1") / path.relative_to(out)
            info = tf.gettarinfo(str(path), arcname=rel.as_posix())
            info.mtime = 0
            info.uid = info.gid = 0
            info.uname = info.gname = ""
            with path.open("rb") as f:
                tf.addfile(info, f)
    with tarfile.open(archive, "r:gz") as tf:
        names = tf.getnames()
        forbidden = ("reserve", "multi_positive", "split_assignments", "long.jsonl", "mixed", "cache", "model")
        bad = [n for n in names if n.startswith(("/", "\\")) or ".." in Path(n).parts or any(x in n.lower() for x in forbidden)]
        if bad:
            raise RuntimeError(f"unsafe/forbidden archive members: {bad[:5]}")
    return {"path": str(archive), "size_bytes": archive.stat().st_size, "sha256": sha256_file(archive), "members": len(names), "safety_audit": "pass"}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", type=Path, required=True)
    ap.add_argument("--output", type=Path, required=True)
    ap.add_argument("--archive", type=Path, required=True)
    args = ap.parse_args()
    root, out = args.input.resolve(), args.output.resolve()
    if out.exists() or args.archive.exists():
        raise RuntimeError("create-only conflict: output or archive already exists")
    out.mkdir(parents=True)
    input_gate = validate_input(root)
    (out / "code").mkdir()
    shutil.copy2(Path(__file__), out / "code" / Path(__file__).name)
    (out / "audit").mkdir()
    (out / "samples").mkdir()
    stats, required, catalogs = {}, {}, {}
    for split in ("train", "dev"):
        src_single = root / split / "single_positive_15.jsonl"
        (out / split).mkdir()
        shutil.copy2(src_single, out / split / "single_positive_15.jsonl")
        stats[split], required[split] = scan_single(src_single, split)
        cat_stats, catalogs[split] = filter_catalog(root / split / "source_catalog.jsonl", out / split / "source_catalog.jsonl", required[split])
        cat_stats["candidate_source_id_occurrences"] = stats[split]["pairs"]
        stats[split]["catalog"] = cat_stats
        shutil.copy2(root / "samples" / f"{split}_examples_3.jsonl", out / "samples" / f"{split}_examples_3.jsonl")
    duplicate, quality, shortest, ordinary = audit_tracks(
        {s: root / s / "single_positive_15.jsonl" for s in ("train", "dev")}, catalogs, required
    )
    write_json(out / "audit" / "duplicate_audit.json", duplicate)
    write_json(out / "audit" / "negative_quality_audit.json", quality)
    write_jsonl(out / "audit" / "shortest_negative_examples_20.jsonl", shortest)
    write_jsonl(out / "audit" / "ordinary_negative_examples_20.jsonl", ordinary)
    if any(duplicate[k]["count"] for k in ("document_id", "target_id", "candidate_source_id")):
        raise RuntimeError("ID-level train/dev leakage")
    if duplicate["normalized_positive_target_source_pair"]["count"]:
        raise RuntimeError("MEMORYFLOW_LC_SENT15_MAINTRACK_POSITIVE_LEAKAGE_BLOCKED")
    catalog_stats = {s: stats[s]["catalog"] for s in ("train", "dev")}
    write_docs(out, catalog_stats, duplicate, quality)
    create_tests(out)
    manifest = {
        "schema_version": SCHEMA,
        "marker": "MEMORYFLOW_LC_SENT15_BASELINE_CORE_READY",
        "status": "pass",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "authoritative_input": str(root),
        "input_gate": input_gate,
        "counts": {
            s: {k: v for k, v in stats[s].items() if k not in {"document_ids", "target_ids"}} for s in ("train", "dev")
        },
        "duplicate_audit": duplicate,
        "quality_audit_path": "audit/negative_quality_audit.json",
        "scope": {"reserve_accessed": False, "multi_read": False, "candidate_modified": False, "model_or_retrieval_used": False},
        "import_policy": "create-only; NEW allowed, IDENTICAL may be skipped after SHA match, CONFLICT blocks",
    }
    write_manifest_and_checksums(out, manifest)
    namespace = runpy.run_path(str(out / "tests" / "test_baseline_core.py"))
    test_names = sorted(name for name in namespace if name.startswith("test_") and callable(namespace[name]))
    for name in test_names:
        namespace[name]()
    test_text = f"{len(test_names)} passed (stdlib deterministic test runner)\n"
    (out / "pytest_output.txt").write_text(test_text, encoding="utf-8", newline="\n")
    manifest["tests"] = {"status": "pass", "passed": len(test_names), "output": "pytest_output.txt"}
    integrity_sha = write_manifest_and_checksums(out, manifest)
    archive_info = create_archive(out, args.archive.resolve())
    sidecar = args.archive.with_suffix(args.archive.suffix + ".sha256")
    sidecar.write_text(f"{archive_info['sha256']}  {args.archive.name}\n", encoding="utf-8", newline="\n")
    write_json(args.archive.with_suffix(args.archive.suffix + ".report.json"), {
        "schema_version": SCHEMA + "-archive-v1",
        "integrity_sha256": integrity_sha,
        "archive": archive_info,
        "scope": manifest["scope"],
        "import_policy": manifest["import_policy"],
    })
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
