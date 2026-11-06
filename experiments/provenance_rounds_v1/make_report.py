#!/usr/bin/env python3
"""Render the frozen-run report for the controlled two-round samples."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import core


def load(path: str) -> dict:
    return core.read_json(path)


def short(text: str, limit: int = 110) -> str:
    text = text.replace("\n", " ")
    return text if len(text) <= limit else text[: limit - 1] + "…"


def rank_cell(ranks: dict, pool: int | None, visible: bool = True) -> str:
    if not ranks:
        return "—（不可见）" if not visible else "—"
    best = min(ranks.values())
    return f"{best}/{pool}" if pool else str(best)


def pair_cell(ranks_a: dict, ranks_b: dict, pool: int | None, visible_a: bool = True) -> str:
    return f"A {rank_cell(ranks_a, pool, visible_a)} · B {rank_cell(ranks_b, pool)}"


def materials_table(round_record: dict) -> list[str]:
    lines = [
        "| # | unit | artifact | span | event | role | text |",
        "|---|---|---|---|---|---|---|",
    ]
    for index, material in enumerate(round_record["materials"], start=1):
        lines.append(
            "| {index} | `{unit}` | `{artifact}` | [{start},{end}) | {event} | {role} | {text} |".format(
                index=index,
                unit=material["unit_id"].split(":")[-2] + ":" + material["unit_id"].split(":")[-1],
                artifact=material["artifact_id"].split(":")[-1],
                start=material["start"],
                end=material["end"],
                event=material["event_index"],
                role=material["role"],
                text=short(material["text"]),
            )
        )
    return lines


def matrix_table(matrix: dict, limit: int = 6) -> list[str]:
    lines = [
        "| rank | candidate | score | share |",
        "|---|---|---|---|",
    ]
    for entry in sorted(matrix["candidates"], key=lambda row: row["rank"])[:limit]:
        share = entry["share"]
        lines.append(
            f"| {entry['rank']} | `{entry['id'].split(':')[-2]}:{entry['id'].split(':')[-1]}` | "
            f"{entry['score']:.6f} | {(share * 100 if share is not None else 0):.1f}% |"
        )
    return lines


def sample_section(sample: dict) -> list[str]:
    spec = load(sample["spec"])
    frozen = load(sample["frozen"])
    scores = load(sample["scores"])
    analysis = load(sample["analysis"])
    rounds = frozen["rounds"]
    groups = analysis["groups"]
    budget = analysis["return_budget"]
    source = spec["source"]
    lines = [f"## {sample['title']}", ""]
    lines.append(f"- 案例/目标：`{source['case']}` / `{source['target_id']}`（{sample['split_note']}）")
    lines.append(f"- 原始 GenMem 目标句：{source['target_text']}")
    lines.append(f"- 第一轮输出（中间结论）：{rounds[0]['answer']}")
    lines.append(f"- 第二轮输出（最终句，评分目标）：{rounds[1]['answer']}")
    lines.append(f"- 返回预算：top-{budget}")
    lines.append("")

    lines.append("### 第一轮输入")
    lines.append("")
    lines.append(f"- 问题：{rounds[0]['question']}")
    lines.append(f"- 指令：{rounds[0]['instruction']}")
    lines.append(f"- 材料数：{len(rounds[0]['materials'])}")
    lines.append("")
    lines.extend(materials_table(rounds[0]))
    lines.append("")
    lines.append("### 第二轮输入")
    lines.append("")
    lines.append(f"- 前一步结论（逐字放入提示）：{rounds[0]['answer']}")
    lines.append(f"- 问题：{rounds[1]['question']}")
    lines.append(f"- 指令：{rounds[1]['instruction']}")
    lines.append(f"- 材料数：{len(rounds[1]['materials'])}")
    lines.append("")
    lines.extend(materials_table(rounds[1]))
    lines.append("")

    lines.append("### 证据标签（看分数前固定）")
    lines.append("")
    lines.append("| 标签 | unit | artifact | span | event | text |")
    lines.append("|---|---|---|---|---|---|")
    for label in ("A", "B"):
        for item in frozen["evidence"][label]:
            lines.append(
                f"| {label} | `{item['unit_id'].split(':')[-2]}:{item['unit_id'].split(':')[-1]}` | "
                f"`{item['artifact_id'].split(':')[-1]}` | [{item['start']},{item['end']}) | "
                f"{item['event_index']} | {short(item['text'], 120)} |"
            )
    lines.append("")

    check = spec["checks"]["round2_without_evidence_a"]
    lines.append("### 第二轮无 A 检查")
    lines.append("")
    lines.append(
        f"- 精确包含命中：{len(check['exact_containment_hits'])}；"
        f"8-token shingle 最大共享：{check['max_shared_shingles']}；"
        f"最长公共子串：{check['max_lcs_chars']} 字符（阈值 < {check['lcs_limit_chars']}）；"
        f"通过：{check['passed']}"
    )
    lines.append(
        f"- 第二轮材料数：{spec['checks']['round2_material_units']}；第一轮材料数："
        f"{spec['checks']['round1_material_units']}；合并原始候选：{len(spec['checks']['merged_raw_units'])}"
    )
    conclusion_a_lcs = 0
    conclusion_a_shingles = 0
    for item in frozen["evidence"]["A"]:
        for answer in (rounds[0]["answer"], rounds[1]["answer"]):
            length, _ = core.longest_common_substring(core.normalise(item["text"]), core.normalise(answer))
            conclusion_a_lcs = max(conclusion_a_lcs, length)
            conclusion_a_shingles = max(
                conclusion_a_shingles,
                len(core.shingles(core.tokens(item["text"])) & core.shingles(core.tokens(answer))),
            )
    lines.append(
        f"- 中间结论/最终句与 A 的转述重叠：最长公共子串 {conclusion_a_lcs} 字符，"
        f"8-token shingle 共享 {conclusion_a_shingles}；这是模型转述，不当作 A 的原文片段。"
    )
    lines.append("")

    lines.append("### 三组名次")
    lines.append("")
    lines.append("| 组 | A 名次 | B 名次 | 中间结论名次 | 找齐 A | 找齐 B | 三组找齐 |")
    lines.append("|---|---|---|---|---|---|---|")
    last = groups["last_round_raw"]
    flat = groups["flat_pool"]
    chain = groups["memoryflow_chain"]
    lines.append(
        f"| 1 最后一轮原始材料 | {rank_cell(last['evidence_a_ranks'], last['pool_units'], last['evidence_a_visible'])} | "
        f"{rank_cell(last['evidence_b_ranks'], last['pool_units'])} | — | {last['found_a']} | {last['found_b']} | {last['found_all']} |"
    )
    lines.append(
        f"| 2 两轮平铺 | {rank_cell(flat['evidence_a_ranks'], flat['pool_units'])} | "
        f"{rank_cell(flat['evidence_b_ranks'], flat['pool_units'])} | — | {flat['found_a']} | {flat['found_b']} | {flat['found_all']} |"
    )
    m1_pool = len(scores["matrices"]["m1"]["candidates"])
    m2_pool = len(scores["matrices"]["m2"]["candidates"])
    lines.append(
        f"| 3 MemoryFlow 链 | {rank_cell(chain['evidence_a_ranks'], m1_pool)} | "
        f"{rank_cell(chain['evidence_b_ranks'], m2_pool)} | "
        f"{chain['transmitted_conclusion_rank']} | {chain['found_a']} | {chain['found_b']} | {chain['found_all']} |"
    )
    lines.append("")

    lines.append("### 逐跳结果")
    lines.append("")
    for hop in analysis["path"]["hops"]:
        lines.append(f"**{hop['unit']}**（矩阵 `{hop['matrix']}`）")
        lines.append("")
        lines.append("| rank | unit | score | transmission |")
        lines.append("|---|---|---|---|")
        for entry in hop["candidates"]:
            unit = analysis["candidate_units"].get(entry["candidate_id"], entry["candidate_id"])
            links = entry.get("transmission") or []
            link_text = "、".join(f"{link['kind']}→{link['to']}" for link in links) if links else "—"
            lines.append(
                f"| {entry['rank']} | `{unit.split(':')[-2]}:{unit.split(':')[-1]}` | "
                f"{entry['score']:.6f} | {link_text} |"
            )
        lines.append("")
    lines.append(f"- 停止原因：无（全部矩阵都有候选）")
    lines.append("")

    lines.append("### 矩阵（前三名）")
    lines.append("")
    for name, label in (("m2", "第二轮单元（含中间结论）"), ("m1", "第一轮原始材料"), ("mflat", "两轮平铺")):
        matrix = scores["matrices"][name]
        lines.append(f"**{name}：{label}**（prompt {matrix['prompt_tokens']} + target {matrix['target_tokens']} tokens）")
        lines.append("")
        lines.extend(matrix_table(matrix))
        lines.append("")
    lines.append(
        f"- 重复前向最大差："
        + "、".join(f"{name} {scores['matrices'][name]['max_repeat_difference']:.3e}" for name in ("m1", "m2", "mflat"))
    )
    lines.append(f"- spec `{spec['spec_sha256'][:16]}…`；frozen `{frozen['frozen_sha256'][:16]}…`；scores `{analysis['scores_sha256'][:16]}…`")
    lines.append("")
    return lines


def hop_pool(chain: dict, unit: str) -> list[dict]:
    for hop in chain["hops"]:
        if hop["unit"] == unit:
            return hop["candidates"]
    return []


def hop1_pool(chain: dict) -> list[dict]:
    return hop_pool(chain, "call_r2#target1")


def hop2_pool(chain: dict) -> list[dict]:
    return hop_pool(chain, "call_r1#target0")


def summary_table(samples: list[dict]) -> list[str]:
    lines = [
        "| 样例 | 第一轮结论 | 最终句 | G1 A/B | G2 A/B | G3 A/B（结论） | G1/G2/G3 找齐 |",
        "|---|---|---|---|---|---|---|",
    ]
    for sample in samples:
        frozen = load(sample["frozen"])
        scores = load(sample["scores"])
        analysis = load(sample["analysis"])
        g = analysis["groups"]
        last, flat, chain = g["last_round_raw"], g["flat_pool"], g["memoryflow_chain"]
        m1_pool = len(scores["matrices"]["m1"]["candidates"])
        m2_pool = len(scores["matrices"]["m2"]["candidates"])
        g1 = pair_cell(last["evidence_a_ranks"], last["evidence_b_ranks"], last["pool_units"], last["evidence_a_visible"])
        g2 = pair_cell(flat["evidence_a_ranks"], flat["evidence_b_ranks"], flat["pool_units"])
        g3 = (
            f"A {rank_cell(chain['evidence_a_ranks'], m1_pool)} · "
            f"B {rank_cell(chain['evidence_b_ranks'], m2_pool)}（结论 {chain['transmitted_conclusion_rank']}）"
        )
        flags = f"{last['found_all']}/{flat['found_all']}/{chain['found_all']}"
        lines.append(
            f"| {sample['short']} | {short(frozen['rounds'][0]['answer'], 55)} | {short(frozen['rounds'][1]['answer'], 55)} | "
            f"{g1} | {g2} | {g3} | {flags} |"
        )
    return lines


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--rejected", default=None)
    args = parser.parse_args(argv)

    manifest = core.read_json(args.manifest)
    samples = manifest["samples"]
    lines = [
        "# 基于 GenMem 材料的受控两轮溯源（第一轮执行记录）",
        "",
        "生成时间：2026-11-06。数据：243 `artifacts/raw/genmem_batch10_v3/genmem_batch10_selection_v1.zip`，"
        "只用原开发案例 `case_02`、`case_08`。",
        "",
        "## 结论摘要",
        "",
    ]
    lines.extend(summary_table(samples))
    lines.append("")
    lines.append(
        "口径：G1 只按最后一轮实际可见的原始材料排序（中间结论不算“原文”）；G2 把两轮原始材料合并后直接排序；"
        "G3 用 `experiments/provenance_v2` 的逐跳连接逻辑，从最终句沿中间结论追到 A。名次是 top-k 内的名次"
        "（分母为该组候选数）；“找齐”指 A、B 都在固定预算内被返回。"
    )
    lines.append("")
    lines.append(
        "为什么三条都来自 `case_02`：`case_08` 的两个开发目标各只有一段主证据"
        "（`a0030[108,222)`、`a0024[164,214)`），第二轮若要不含 A 就无法同时包含同组 B，"
        "因此没有构造两轮样例；这是数据约束，不是漏做。"
    )
    lines.append("")
    lines.append(
        "另核：三条样例的第二轮原始材料都不含同一目标的其它同文支持位置"
        "（T03 的 `a0296[259,341)`、`a0302[96,178)`；T09 的 `a0150`；T06 的同组列表项），"
        "A 的等价出现不是在 R2 里被找到的。"
    )
    lines.append("")
    for sample in samples:
        lines.extend(sample_section(sample))
    if args.rejected:
        rejected = core.read_json(args.rejected)
        lines.append("## 被弃用的构造（v1 T06）")
        lines.append("")
        lines.append(rejected["note"])
        lines.append("")
        for item in rejected["items"]:
            lines.append(f"- {item}")
        lines.append("")
    lines.append("## 数据与路径")
    lines.append("")
    lines.append("| 项 | 值 |")
    lines.append("|---|---|")
    first_spec = load(samples[0]["spec"])
    lines.append(f"| 归档 SHA256 | `{first_spec['source'].get('archive_sha256', '')}` |")
    lines.append(f"| 运行目录 | `{manifest['run_root']}` |")
    for sample in samples:
        frozen = load(sample["frozen"])
        lines.append(f"| {sample['short']} frozen | `{frozen['frozen_sha256']}` |")
    lines.append("")
    lines.append("## 边界")
    lines.append("")
    lines.append("- 这是基于 GenMem 材料的**受控多轮验证**，不是原始逐次请求恢复；`visibility=unverified`、`actual_use=unknown`。")
    lines.append("- 原 47 题结果继续单列，本表不并入。")
    lines.append("- 语义支持不等于实际使用或因果影响；A/B 只用于评分，不用来证明模型“用了”它。")
    lines.append("- 生成与评分共用 Qwen2.5-7B-Instruct；用 243 的 0 号卡（每次运行前记录：1/3/5/7 号卡当时 100% 利用，2/6 号卡显存不足 20 GiB；0 号卡空闲 >= 20 GiB，另有 lyx 的 sglang 常驻）。")
    lines.append("")
    Path(args.out).write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({"out": args.out, "samples": [s["short"] for s in samples]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


