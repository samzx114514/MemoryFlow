#!/usr/bin/env python3
"""Run the four methods over a batch of unified multi-turn cases and score them.

Before scoring, ``--write-lock`` freezes the inclusion set, candidate membership,
labels and matrix hashes. A normal run refuses to proceed if the lock is missing
or no longer matches, so method scores cannot be inspected before the labels and
candidate pool are fixed.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import cases
import methods
import metrics


def short(cid: str) -> str:
    if cid.startswith("transmission:"):
        return cid
    artifact, span = cid.rsplit("#", 1)
    return f"{artifact.split(':')[-1]}:{span}"


def lock_payload(directory: Path, manifest: dict) -> dict:
    entries = {}
    for row in manifest["cases"]:
        case_path = directory / row["case_path"]
        matrix_path = directory / row["matrix_path"]
        case = cases.read_json(case_path)
        entries[row["short"]] = {
            "case_id": case["case_id"],
            "case_sha256": cases.case_hash(case),
            "matrix_sha256": cases.sha256_file(matrix_path),
            "candidate_ids_sha256": cases.sha256_text(
                json.dumps(sorted(candidate["canonical_id"] for candidate in case["candidates"]))
            ),
            "labels_sha256": cases.sha256_text(json.dumps(case.get("labels") or {}, sort_keys=True)),
            "evidence_sha256": cases.sha256_text(json.dumps(case["evidence_groups"], sort_keys=True)),
        }
    return {
        "schema": "memoryflow.multiturn_batch.lock.v1",
        "created": "2026-11-06",
        "final_budget": cases.FINAL_BUDGET,
        "hop_budget": cases.HOP_BUDGET,
        "manifest_sha256": cases.sha256_file(directory / "manifest.json"),
        "cases": entries,
    }


def check_lock(directory: Path, lock: dict, manifest: dict) -> None:
    current = lock_payload(directory, manifest)
    problems = []
    for short_name, entry in current["cases"].items():
        frozen = lock["cases"].get(short_name)
        if frozen is None:
            problems.append(f"{short_name}: missing from lock")
            continue
        for key in ("case_sha256", "matrix_sha256", "candidate_ids_sha256", "labels_sha256", "evidence_sha256"):
            if frozen.get(key) != entry.get(key):
                problems.append(f"{short_name}: {key} changed")
    if current["manifest_sha256"] != lock.get("manifest_sha256"):
        problems.append("manifest changed")
    if problems:
        raise SystemExit("lock check failed:\n- " + "\n- ".join(problems))


def top_list(ranked: list[str], limit: int = 10) -> str:
    return "、".join(f"`{short(cid)}`" for cid in ranked[:limit]) if ranked else "—"


def render_markdown(results: dict) -> str:
    summary = results["summary"]
    lines = [
        "# 多轮批处理验收（统一入口 + 四方法）",
        "",
        "数据：`experiments/multiturn_batch_v1` 的三题开发验收；只读已保存矩阵与 CPU BM25，未重跑模型。",
        "",
        "## 口径",
        "",
        f"- 最终返回预算：top-{summary['final_budget']}；每跳展开预算：top-{results['hop_budget']}（另记）。"
        "\n- 多轮链每跳 5，合并去重后实际返回 8–9 条；其余方法返回 10 条。若要求所有方法恰好 10 条，把 hop 调到 10。",
        "- 方法：最后一轮（last_round）、全历史 BM25（bm25_history）、同头全历史直接回放（head_full_history）、MemoryFlow 多轮追踪（memoryflow）。",
        "- 覆盖规则沿用原评测：片段按同 artifact 的非空白字符覆盖，组内 all_of（含等价出现）全中，组间 OR；Hit@3 = 前 3 有任一证据片段；完整@5/@10 = 任一 full 组完整。",
        "- 同一证据按 (artifact, start, end) 归并；renamed 位置保留在 case JSON 的 occurrences 里。",
        "- T06 单列为“最终轮自身已有足够证据”的对照，主表宏平均不含它。",
        "",
        "## 逐题名次",
        "",
        "| 题 | 方法 | 返回 | Hit@3 | 完整@5 | 完整@10 | 首个证据名次 | 完整名次 | A 名次 | B 名次 |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for case_row in results["cases"]:
        for method in methods.METHODS:
            row = case_row["methods"][method]
            lines.append(
                f"| {case_row['case_id'].split(':')[-1] if ':' in case_row['case_id'] else case_row['case_id']}"
                f"{'（对照）' if case_row.get('control') else ''} | {method} | {len(row['ranked'])} | "
                f"{'是' if row['hit_at_3'] else '否'} | {'是' if row['complete_at_5'] else '否'} | "
                f"{'是' if row['complete_at_10'] else '否'} | "
                f"{row['hit_rank'] if row['hit_rank'] is not None else '—'} | "
                f"{row['complete_rank'] if row['complete_rank'] is not None else '—'} | "
                f"{row['label_ranks'].get('A') if row['label_ranks'].get('A') is not None else '—'} | "
                f"{row['label_ranks'].get('B') if row['label_ranks'].get('B') is not None else '—'} |"
            )
    lines.append("")
    lines.append("## 宏平均")
    lines.append("")
    for block, label in (("main", "主表（不含对照）"), ("control", "对照"), ("all", "全部")):
        aggregate = summary[block]
        if not aggregate.get("cases"):
            continue
        lines.append(f"**{label}**（n={aggregate['cases']}）")
        lines.append("")
        lines.append("| 方法 | Hit@3 | 完整@5 | 完整@10 | 平均完整名次 | 平均首个证据名次 |")
        lines.append("|---|---|---|---|---|---|")
        for method in methods.METHODS:
            row = aggregate["methods"][method]
            lines.append(
                f"| {method} | {row['hit_at_3']:.3f} ({row['hit_at_3_count']}/{aggregate['cases']}) | "
                f"{row['complete_at_5']:.3f} ({row['complete_at_5_count']}/{aggregate['cases']}) | "
                f"{row['complete_at_10']:.3f} ({row['complete_at_10_count']}/{aggregate['cases']}) | "
                f"{row['mean_complete_rank']:.2f} | {row['mean_hit_rank']:.2f} |"
            )
        lines.append("")
    lines.append("### T06 对照说明")
    lines.append("")
    lines.append(
        "T06 的 GT 组仍是原“第 6 张 + 年份”的 ordinal 组（6 个列表项 + `a0282` + `a0284`，共 8 项），"
        "但受控最终句只要求“专辑 + 发行年”，不再声明第 6。因此它的 Complete@5/@10 只作诊断，"
        "不进主表宏平均；对照检查是：最终轮 top-5 已含 B（年份）和专辑题名，最终句不需要沿链追到列表项 A。"
    )
    lines.append("")
    lines.append("## 配对胜平负（MemoryFlow 对基线）")
    lines.append("")
    lines.append("| 基线 | 完整名次 W/T/L | 首个证据名次 W/T/L |")
    lines.append("|---|---|---|")
    for baseline, value in summary["paired_main"].items():
        comp = value["complete_rank"]
        hit = value["hit_rank"]
        lines.append(
            f"| {baseline} | {comp['win']}/{comp['tie']}/{comp['loss']} | {hit['win']}/{hit['tie']}/{hit['loss']} |"
        )
    lines.append("")
    lines.append("## 每跳展开（另记）")
    lines.append("")
    for case_row in results["cases"]:
        memory = case_row["methods"]["memoryflow"]
        lines.append(f"**{case_row['case_id']}**（hop budget {case_row['hop_budget']}）")
        lines.append("")
        lines.append("| hop | factor | top-k |")
        lines.append("|---|---|---|")
        for hop in memory.get("hops") or []:
            top = "、".join(f"`{short(item['canonical_id'])}`" for item in hop.get("top") or [])
            lines.append(f"| {hop.get('round')} | {hop.get('factor')} | {top or hop.get('stop', '—')} |")
        lines.append("")
    lines.append("## 最终返回（最多 10 条）")
    lines.append("")
    for case_row in results["cases"]:
        lines.append(f"- **{case_row['case_id']}**")
        for method in methods.METHODS:
            lines.append(f"  - {method}: {top_list(case_row['methods'][method]['ranked'])}")
    lines.append("")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dir", required=True, help="batch directory with manifest.json")
    parser.add_argument("--out", required=True, help="results JSON")
    parser.add_argument("--md", required=True, help="results markdown")
    parser.add_argument("--write-lock", action="store_true", help="freeze and exit before scoring")
    args = parser.parse_args(argv)

    directory = Path(args.dir).resolve()
    manifest = cases.read_json(directory / "manifest.json")
    if args.write_lock:
        lock = lock_payload(directory, manifest)
        cases.write_json(directory / "lock.json", lock)
        print(json.dumps({"lock": str(directory / "lock.json"), "cases": list(lock["cases"])}, ensure_ascii=False))
        return 0
    lock_path = directory / "lock.json"
    if not lock_path.exists():
        raise SystemExit("lock.json is missing; run --write-lock before scoring")
    check_lock(directory, cases.read_json(lock_path), manifest)

    results = {"schema": "memoryflow.multiturn_batch.results.v1", "final_budget": cases.FINAL_BUDGET,
               "hop_budget": cases.HOP_BUDGET, "cases": []}
    for row in manifest["cases"]:
        case = cases.read_json(directory / row["case_path"])
        matrix = cases.read_json(directory / row["matrix_path"])
        method_output = methods.run(case, matrix, cases.FINAL_BUDGET, cases.HOP_BUDGET)
        results["cases"].append(metrics.evaluate_case(case, method_output))
    results["summary"] = metrics.summarize(results["cases"], cases.FINAL_BUDGET)
    cases.write_json(args.out, results)
    Path(args.md).write_text(render_markdown(results), encoding="utf-8")
    print(json.dumps({
        "cases": [row["case_id"] for row in results["cases"]],
        "main": results["summary"]["main_case_ids"],
        "control": results["summary"]["control_case_ids"],
        "out": args.out,
    }, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

