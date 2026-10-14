#!/usr/bin/env python3
"""CPU-only, seed-first M6D.2 primary method-selection closure.

It consumes only frozen M6D/M6B Dev predictions and the immutable M6D.1-P
bootstrap draw stream.  In particular, it never averages model scores across
seeds: every metric is evaluated per seed and only scalar deltas are reduced.
"""
from __future__ import annotations

import csv
import hashlib
import json
import os
import sys
import time
from collections import defaultdict
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from memoryflow.m6d1_vectorized import ranking_group_metrics
from memoryflow.m6d2_seedfirst import average_precision, ap_seed_delta, projected_counts, rank_seed_delta, seed_first_delta, summary
from memoryflow.source_prior_relational import prior_challenging_ids

OUT = ROOT / "results/m6d2_primary_method_selection_v3"
# Preserve a failed preparation directory for audit; this retry owns a new
# temporary path and is the only path eligible for atomic publication.
TMP = OUT.with_name("." + OUT.name + ".tmp-attempt2")
M6D = ROOT / "results/m6d_source_prior_relational_v1"
ATTEMPT = M6D / "finalization_attempt_3"
M6B = ROOT / "results/m6b_directional_scorer_243_v1"
M6D1P = ROOT / "results/m6d1_primary_permutation_closure_v1"
REF = ROOT / "results/m6d1_statistical_closure_reference_v1"
DATA = ROOT / "data/longcite_anchor_expanded_v1_conservative"
SEEDS = (0, 1, 2)
VARS = ("P", "R_SYM", "P_R_SYM", "R_DIR", "P_R_DIR")
KNOWN_P_INTEGRITY = "e7d3489151d328291d2b16b76abadbdb3ad807ef4e7b73fdbd0461a281f4cb36"
KNOWN_P_CSV = "cbcd91b91d01ea8cde9c9c7ef5822cb9229cd108b3b629fcf84dff1699efc0de"
KNOWN_ATTEMPT = "68c635cfe62d8748af49ff0716c71fe4ba8f7cc7cda3397374f0781f528dec22"


def forbid(path: Path | str) -> None:
    if "blind" in str(path).casefold():
        raise RuntimeError(f"Blind path forbidden: {path}")


def sha(path: Path) -> str:
    forbid(path)
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def read_json(path: Path):
    forbid(path)
    return json.loads(path.read_text())


def read_jsonl(path: Path) -> list[dict]:
    forbid(path)
    with path.open() as handle:
        return [json.loads(line) for line in handle if line.strip()]


def dump(path: Path, value: object) -> None:
    encoded = json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + "\n"
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(encoded)
    os.replace(temp, path)


def write_csv(path: Path, rows: list[dict]) -> None:
    fields = sorted({key for row in rows for key in row}) if rows else ["status"]
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: json.dumps(value, sort_keys=True) if isinstance(value, (list, dict)) else value for key, value in row.items()})


def norm_text(text: str) -> str:
    return " ".join(str(text).split()).casefold()


def build_labels(dev: list[dict]) -> np.ndarray:
    labels = np.asarray([[int(source in set(example["gold_source_ids"])) for source in example["candidate_source_ids"]] for example in dev], dtype=np.int8)
    if labels.shape != (228, 8) or int(labels.sum()) != 496:
        raise RuntimeError("frozen Dev labels/counts mismatch")
    return labels


def score_index(rows: list[dict], track: str, variant: str, seed: int) -> np.ndarray:
    filtered = [r for r in rows if r["track"] == track and r["variant"] == variant and int(r["seed"]) == seed]
    if len(filtered) != 1824:
        raise RuntimeError(f"prediction count mismatch: {track}/{variant}/seed{seed}")
    return np.asarray([r["logit"] for r in filtered], dtype=np.float64).reshape(228, 8)


def source_hashes(train: list[dict], dev: list[dict], catalog: list[dict]) -> tuple[dict[str, str], set[str]]:
    table = {item["source_id"]: hashlib.sha256(norm_text(item["text"]).encode()).hexdigest() for item in catalog}
    train_seen = {table[source] for example in train for source in example["candidate_source_ids"]}
    if len(table) != 10400:
        raise RuntimeError("source catalog count mismatch")
    return table, train_seen


def frozen_subsets(dev: list[dict], train: list[dict], catalog: list[dict], p_scores: np.ndarray) -> tuple[dict[str, list[int]], dict]:
    hashes, _ = source_hashes(train, dev, catalog)
    rows = defaultdict(list)
    for index, example in enumerate(dev):
        for pos, label in enumerate(build_labels(dev)[index]):
            rows[example["example_id"]].append({"label": int(label), "logit": float(p_scores[index, pos])})
    prior_ids, audit = prior_challenging_ids(rows)
    # The migrated project preserves C5B under its historical longcite prefix.
    bm25 = read_jsonl(ROOT / "results/longcite_c5b_7b/dev_scores.jsonl")
    score = {(r["example_id"], r["candidate_id"]): float(r.get("normalized_score", r.get("raw_score", 0.0))) for r in bm25 if r.get("method") == "bm25" and r.get("view") == "primary"}
    negative = [score.get((example["example_id"], candidate), -np.inf) for example in dev for candidate in example["candidate_source_ids"] if candidate not in set(example["gold_source_ids"])]
    threshold = float(np.quantile(negative, .75))
    roles = defaultdict(set)
    for example in train + dev:
        gold = set(example["gold_source_ids"])
        for candidate in example["candidate_source_ids"]:
            roles[hashes[candidate]].add(int(candidate in gold))
    switching = {key for key, value in roles.items() if len(value) > 1}
    subsets = {
        "prior_challenging": [i for i, example in enumerate(dev) if example["example_id"] in prior_ids],
        "BM25_hard": [i for i, example in enumerate(dev) if any(candidate not in set(example["gold_source_ids"]) and score.get((example["example_id"], candidate), -np.inf) >= threshold for candidate in example["candidate_source_ids"])],
        "role_switching": [i for i, example in enumerate(dev) if any(hashes[candidate] in switching for candidate in example["candidate_source_ids"])],
    }
    expected = {"prior_challenging": 139, "BM25_hard": 130, "role_switching": 110}
    if {key: len(value) for key, value in subsets.items()} != expected or audit != {"eligible": 225, "excluded_no_positive": 0, "excluded_no_negative": 3}:
        raise RuntimeError("frozen hard-subset definition mismatch")
    return subsets, {"prior_challenging_audit": audit, "bm25_negative_q75": threshold, "subset_target_counts": expected}


def identity_metrics(labels: np.ndarray, scores: np.ndarray) -> dict[str, float | None]:
    rank = ranking_group_metrics(labels, scores)
    return {"mrr": float(rank["mrr"].mean()), "hit_at_1": float(rank["hit_at_1"].mean()), "ndcg_at_5": float(rank["ndcg_at_5"].mean()), "auprc": average_precision(labels, scores)}


def bootstrap_comparison(labels: np.ndarray, left: list[np.ndarray], right: list[np.ndarray], counts: np.ndarray, track: str) -> dict:
    if len(left) != 3 or len(right) != 3:
        raise RuntimeError("three independently scored seeds required")
    if track == "rank":
        deltas = {metric: seed_first_delta([rank_seed_delta(labels, a, b, counts)[metric] for a, b in zip(left, right)]) for metric in ("mrr", "hit_at_1", "ndcg_at_5")}
        primary = "mrr"
    elif track == "edge":
        deltas = {"auprc": seed_first_delta([ap_seed_delta(labels, a, b, counts) for a, b in zip(left, right)])}
        primary = "auprc"
    else:
        raise ValueError(track)
    per_seed_left = [identity_metrics(labels, score)[primary] for score in left]
    per_seed_right = [identity_metrics(labels, score)[primary] for score in right]
    result = {"primary_metric": primary, "left_seed_mean": float(np.mean(per_seed_left)), "left_seed_std": float(np.std(per_seed_left)), "right_seed_mean": float(np.mean(per_seed_right)), "right_seed_std": float(np.std(per_seed_right)), "primary": summary(deltas[primary])}
    result.update({metric: summary(values) for metric, values in deltas.items() if metric != primary})
    return result


def existing_m6b_scores(track: str, m6d_rows: list[dict]) -> list[np.ndarray]:
    name = "M-RANK" if track == "rank" else "M-EDGE"
    observed = []
    for seed in SEEDS:
        path = M6B / "final" / name / f"seed_{seed}" / "dev_scores.jsonl"
        values = read_jsonl(path)
        ref = [r for r in m6d_rows if r["track"] == track and r["variant"] == "R_SYM" and int(r["seed"]) == seed]
        actual_key = [(r["example_id"], r["candidate_id"], int(r["candidate_order"]), int(r["label"])) for r in values]
        reference_key = [(r["example_id"], r["candidate_id"], int(r["candidate_order"]), int(r["label"])) for r in ref]
        if actual_key != reference_key or len(values) != 1824:
            raise RuntimeError(f"PAIRING_UNAVAILABLE: M6B alignment failed {track}/seed{seed}")
        observed.append(np.asarray([r["logit"] for r in values], dtype=np.float64).reshape(228, 8))
    return observed


def main() -> None:
    if OUT.exists() or TMP.exists():
        raise RuntimeError(f"refusing to overwrite existing output: {OUT}")
    # Preconditions: exact, immutable M6D.1-P scientific input.
    required_marker = M6D1P / "MEMORYFLOW_M6D1_PRIMARY_PERMUTATION_CLOSURE_COMPLETE"
    p_final = M6D1P / "finalization_attempt_1"
    if not required_marker.is_file() or read_json(M6D1P / "FINALIZATION_INDEX.json") != {"primary_gate_status": "PERMUTATION_GATE_PASS", "valid_attempt": "finalization_attempt_1"}:
        raise RuntimeError("M6D.1-P marker/index mismatch")
    if sha(p_final / "M6D1P_INTEGRITY.json") != KNOWN_P_INTEGRITY or sha(p_final / "primary_permutation_bootstrap.csv") != KNOWN_P_CSV:
        raise RuntimeError("M6D.1-P checksum mismatch")
    equivalence = read_json(M6D1P / "equivalence_gate.json")
    if equivalence["status"] != "PASS" or max(float(x["max_abs_difference"]) for x in equivalence["checks"]) > 2.43e-14:
        raise RuntimeError("M6D.1-P equivalence gate mismatch")
    if sha(ATTEMPT / "M6D_INTEGRITY.json") != KNOWN_ATTEMPT or read_json(M6D / "FINALIZATION_INDEX.json")["valid_attempt"] != "finalization_attempt_3":
        raise RuntimeError("M6D attempt-3 integrity mismatch")
    for path in (M6D / "M6D_PREREGISTRATION.md", M6D / "m6d_frozen_config.json", M6D / "input_manifest.json", M6D / "fold_manifest.json"):
        forbid(path)
    arrays = np.load(REF / "compact_predictions.npz")
    labels, full_indices = arrays["labels"], arrays["indices"]
    if labels.shape != (228, 8) or full_indices.shape != (10000, 228):
        raise RuntimeError("immutable bootstrap arrays mismatch")
    dev, train, catalog = read_jsonl(DATA / "dev_examples.jsonl"), read_jsonl(DATA / "train_examples.jsonl"), read_jsonl(DATA / "source_catalog.jsonl")
    if len(dev) != 228 or len(train) != 854 or len(catalog) != 10400 or not np.array_equal(labels, build_labels(dev)):
        raise RuntimeError("frozen Train/Dev/cache protocol mismatch")
    m6d_rows = read_jsonl(ATTEMPT / "predictions_dev.jsonl")
    if len(m6d_rows) != 2 * 5 * 3 * 1824:
        raise RuntimeError("M6D prediction row count mismatch")
    by_track_variant = {(track, variant): [score_index(m6d_rows, track, variant, seed) for seed in SEEDS] for track in ("rank", "edge") for variant in VARS}
    subsets, subset_audit = frozen_subsets(dev, train, catalog, by_track_variant[("rank", "P")][0])
    TMP.mkdir(parents=True)
    input_files = [
        M6D1P / "M6D1P_PROTOCOL.md", M6D1P / "equivalence_gate.json", p_final / "M6D1P_INTEGRITY.json", p_final / "primary_permutation_bootstrap.csv",
        ATTEMPT / "M6D_INTEGRITY.json", ATTEMPT / "predictions_dev.jsonl", ATTEMPT / "dev_summary.json", ATTEMPT / "oof_summary.json", ATTEMPT / "bootstrap_comparisons.csv",
        M6D / "M6D_PREREGISTRATION.md", M6D / "m6d_frozen_config.json", M6D / "input_manifest.json", M6D / "fold_manifest.json",
        DATA / "train_examples.jsonl", DATA / "dev_examples.jsonl", DATA / "source_catalog.jsonl", REF / "compact_predictions.npz",
    ]
    for track, name in (("rank", "M-RANK"), ("edge", "M-EDGE")):
        for seed in SEEDS:
            input_files.extend((M6B / "final" / name / f"seed_{seed}" / "dev_scores.jsonl", M6B / "final" / name / f"seed_{seed}" / "best.json", M6B / "final" / name / f"seed_{seed}" / "best.pt", M6D / "runs" / track / "R_SYM" / f"seed_{seed}" / "config.json", M6D / "runs" / track / "R_SYM" / f"seed_{seed}" / "best.pt"))
    input_files.append(M6B / "runtime_summary.json")
    integrity = {"inputs": {str(path.relative_to(ROOT)): sha(path) for path in input_files}, "m6d1p_integrity_expected": KNOWN_P_INTEGRITY, "m6d1p_bootstrap_expected": KNOWN_P_CSV, "blind_accessed": False, "qwen_loaded": False, "gpu_requested": False, "training": False, "rejected_mean_seed_logits_execution_used": False}
    dump(TMP / "input_integrity.json", integrity)
    protocol = """# M6D.2 primary method-selection closure\n\nThis CPU-only closure consumes frozen M6D/M6B Dev logits and M6D.1-P fixed bootstrap draws. The rejected `metric(mean_seed(logits))` execution is excluded. Each seed computes MRR or AUPRC separately; the reducer averages only the three seed-level scalar deltas. Ranking primary is MRR; Edge primary is AUPRC. AUROC is explicitly deferred.\n\nHard-subset resampling projects the immutable 10,000 full-Dev target-group draw stream (`seed=20260813`) onto each frozen subset; no bootstrap indices are regenerated.\n"""
    (TMP / "M6D2_PROTOCOL.md").write_text(protocol)

    hard_rows = []
    for subset_name, ids in subsets.items():
        sub_labels = labels[ids]
        counts = projected_counts(full_indices, ids, 228)
        positives, negatives = int(sub_labels.sum()), int(sub_labels.size - sub_labels.sum())
        status = "OK" if len(ids) and positives and negatives else "INSUFFICIENT"
        for track in ("rank", "edge"):
            for variant in ("P", "R_SYM", "P_R_SYM"):
                values = [score[ids] for score in by_track_variant[(track, variant)]]
                metric = "mrr" if track == "rank" else "auprc"
                per_seed = [identity_metrics(sub_labels, value)[metric] for value in values]
                hard_rows.append({"subset": subset_name, "track": track, "variant": variant, "metric": metric, "status": status, "target_count": len(ids), "pair_count": int(sub_labels.size), "positive_edges": positives, "negative_edges": negatives, "excluded_no_negative": subset_audit["prior_challenging_audit"]["excluded_no_negative"] if subset_name == "prior_challenging" else 0, "construction": "frozen M6D preregistration", "seed_metrics": per_seed, "seed_mean": float(np.mean(per_seed)) if all(v is not None for v in per_seed) else None, "seed_std": float(np.std(per_seed)) if all(v is not None for v in per_seed) else None})
            for left_variant, right_variant in (("R_SYM", "P"), ("P_R_SYM", "P")):
                comparison = bootstrap_comparison(sub_labels, [x[ids] for x in by_track_variant[(track, left_variant)]], [x[ids] for x in by_track_variant[(track, right_variant)]], counts, track)
                hard_rows.append({"subset": subset_name, "track": track, "variant": f"{left_variant}_minus_{right_variant}", "metric": comparison["primary_metric"], "status": status, "target_count": len(ids), "pair_count": int(sub_labels.size), "positive_edges": positives, "negative_edges": negatives, "excluded_no_negative": subset_audit["prior_challenging_audit"]["excluded_no_negative"] if subset_name == "prior_challenging" else 0, "construction": "frozen M6D preregistration; fixed full-Dev bootstrap projection", **comparison})
    write_csv(TMP / "hard_subset_closure.csv", hard_rows)

    paired_rows = []
    complexity = []
    for track in ("rank", "edge"):
        m6b_name = "M-RANK" if track == "rank" else "M-EDGE"
        m6b = existing_m6b_scores(track, m6d_rows)
        r_sym = by_track_variant[(track, "R_SYM")]
        counts = projected_counts(full_indices, range(228), 228)
        comparison = bootstrap_comparison(labels, r_sym, m6b, counts, track)
        paired_rows.append({"track": track, "comparison": f"R_SYM_minus_{m6b_name}", "target_count": 228, "pair_count": 1824, "positive_edges": 496, "negative_edges": 1328, "pairing_verified": True, "score_direction": "higher_is_better", "checkpoint_alignment": "exact Target/candidate/order/label equality for each seed", **comparison})
        m6b_bests = [read_json(M6B / "final" / m6b_name / f"seed_{seed}" / "best.json") for seed in SEEDS]
        m6d_configs = [read_json(M6D / "runs" / track / "R_SYM" / f"seed_{seed}" / "config.json") for seed in SEEDS]
        runtime = read_json(M6B / "runtime_summary.json")["runs"]
        m6b_runtime = [float(next(item["runtime_seconds"] for item in runtime if item["variant"] == m6b_name and int(item["seed"]) == seed)) for seed in SEEDS]
        complexity.extend([
            {"track": track, "model": m6b_name, "parameter_count": [int(x["parameter_count"]) for x in m6b_bests], "parameter_count_exact": int(m6b_bests[0]["parameter_count"]), "checkpoint_sha256": [sha(M6B / "final" / m6b_name / f"seed_{seed}" / "best.pt") for seed in SEEDS], "config_sha256": [sha(M6B / "final" / m6b_name / f"seed_{seed}" / "best.json") for seed in SEEDS], "checkpoint_bytes": [int((M6B / "final" / m6b_name / f"seed_{seed}" / "best.pt").stat().st_size) for seed in SEEDS], "runtime_seconds": m6b_runtime, "peak_gpu_bytes": 559393280, "input_features": "ordered target, source, product, abs difference, cosine", "raw_target_source_paths": True, "source_controlled_oof": False, "permutation_evidence": "not source-prior-controlled"},
            {"track": track, "model": "R_SYM", "parameter_count": [int(x["parameter_count"]) for x in m6d_configs], "parameter_count_exact": int(m6d_configs[0]["parameter_count"]), "checkpoint_sha256": [sha(M6D / "runs" / track / "R_SYM" / f"seed_{seed}" / "best.pt") for seed in SEEDS], "config_sha256": [sha(M6D / "runs" / track / "R_SYM" / f"seed_{seed}" / "config.json") for seed in SEEDS], "checkpoint_bytes": [int((M6D / "runs" / track / "R_SYM" / f"seed_{seed}" / "best.pt").stat().st_size) for seed in SEEDS], "runtime_seconds": [float(x["runtime_seconds"]) for x in m6d_configs], "peak_gpu_bytes": max(int(x["peak_gpu_bytes"]) for x in m6d_configs), "input_features": "target*source, abs(target-source), cosine", "raw_target_source_paths": False, "source_controlled_oof": True, "permutation_evidence": "M6D.1-P seed-first PASS"},
        ])
    write_csv(TMP / "m6b_rsym_paired_bootstrap.csv", paired_rows)
    write_csv(TMP / "model_complexity.csv", complexity)

    existing_boot = list(csv.DictReader((ATTEMPT / "bootstrap_comparisons.csv").open()))
    oof = read_json(ATTEMPT / "oof_summary.json")["runs"]
    relational = {}
    for track, metric in (("rank", "mrr"), ("edge", "auprc")):
        clean = next(row for row in existing_boot if row["scope"] == "dev_clean" and row["track"] == track and row["comparison"] == "P_R_SYM_minus_P")
        clean_ci = json.loads(clean["ci95"])
        oof_p = np.mean([row["metrics"][metric] for row in oof if row["track"] == track and row["variant"] == "P"])
        oof_combo = np.mean([row["metrics"][metric] for row in oof if row["track"] == track and row["variant"] == "P_R_SYM"])
        hard = next(row for row in hard_rows if row["subset"] == "prior_challenging" and row["track"] == track and row["variant"] == "R_SYM_minus_P")
        perm_rows = list(csv.DictReader((p_final / "primary_permutation_bootstrap.csv").open()))
        perm = next(row for row in perm_rows if row["track"] == track and row["variant"] == "R_SYM" and row["metric"] == metric)
        perm_ci = json.loads(perm["ci95"])
        passed = clean_ci[0] > 0 and oof_combo > oof_p and perm_ci[0] > 0 and hard["status"] == "OK" and hard["primary"]["ci95"][0] > 0
        relational[track] = {"verdict": "RELATIONAL_PASS" if passed else "RELATIONAL_CONDITIONAL", "primary_metric": metric, "dev_clean_ci95": clean_ci, "oof_delta": float(oof_combo - oof_p), "permutation_ci95": perm_ci, "prior_challenging_ci95": hard["primary"]["ci95"], "prior_challenging_delta": hard["primary"]["delta"], "directional_pass": False, "claim": "Target–Source semantic matching; no directed information-flow claim"}
    dump(TMP / "relational_decision.json", relational)

    selection = {}
    for row in paired_rows:
        ci = row["primary"]["ci95"]
        if ci[0] > 0:
            chosen = "SELECT_R_SYM"
        elif ci[1] < 0:
            chosen = "SELECT_M6B_FULL"
        else:
            chosen = "STATISTICALLY_TIED_PREFER_SIMPLER"
        selection[row["track"]] = {"selection": chosen, "primary_metric": row["primary_metric"], "paired_ci95": ci, "paired_delta_r_sym_minus_m6b": row["primary"]["delta"], "reason": "strict seed-first target-group paired bootstrap; tie rule prefers smaller R-SYM with source-controlled OOF/permutation evidence"}
    # A tie is explicitly resolved toward the simpler R-SYM, so both tracks
    # operationally retain it here (Edge wins outright; Ranking is tied).
    rank_uses_r_sym = selection["rank"]["selection"] in ("SELECT_R_SYM", "STATISTICALLY_TIED_PREFER_SIMPLER")
    edge_uses_r_sym = selection["edge"]["selection"] in ("SELECT_R_SYM", "STATISTICALLY_TIED_PREFER_SIMPLER")
    selection["paper_recommendation"] = {"unified_model": "R_SYM" if rank_uses_r_sym and edge_uses_r_sym else "track-specific results; do not claim a universal champion", "claim": "Target–Source semantic matching", "not_claimed": ["directed information flow", "none-of-the-above resolution", "AUROC secondary closure"]}
    dump(TMP / "method_selection.json", selection)

    report = "# M6D.2 primary method-selection closure\n\nM6D.2 uses only frozen Train/Dev-derived predictions. It excludes the rejected mean-seed-logits execution. The primary statistical protocol is `mean_seed(metric(logits_seed))`. MRR and AUPRC are closed; AUROC remains an explicitly deferred secondary metric.\n\nSee CSV/JSON artifacts for the seed-first hard-subset and M6B pairing evidence.\n"
    (TMP / "M6D2_REPORT.md").write_text(report)
    integrity["subset_audit"] = subset_audit
    integrity["files"] = [{"path": path.name, "sha256": sha(path), "bytes": path.stat().st_size} for path in sorted(TMP.iterdir()) if path.is_file()]
    integrity["created_at"] = time.time()
    dump(TMP / "M6D2_INTEGRITY.json", integrity)
    (TMP / "COMPLETED").write_text("completed\n")
    (TMP / "MEMORYFLOW_M6D2_PRIMARY_METHOD_SELECTION_COMPLETE").write_text("complete\n")
    os.replace(TMP, OUT)
    checks = [f"{sha(path)}  {path.relative_to(OUT)}" for path in sorted(OUT.rglob("*")) if path.is_file() and path.name != "checksums.sha256"]
    (OUT / "checksums.sha256").write_text("\n".join(checks) + "\n")


if __name__ == "__main__":
    main()
