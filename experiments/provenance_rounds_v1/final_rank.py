#!/usr/bin/env python3
"""Offline final-original ranking for the controlled two-round samples.

Reads the saved frozen inputs and matrices only (no model, no GPU).

Path scoring follows the prototype rule used for the CUAD chain:
  direct path          final sentence -> round-2 material: score = hop-1 mass
  indirect path        final sentence -> conclusion -> round-1 material:
                       score = hop-1(conclusion) * hop-2(material)
  same original text   paths are summed (``max`` is reported as a sensitivity check)
  final list           conclusion excluded, deduplicated by original text, global top-5
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import core

CONCLUSION = "conclusion:r1"
BUDGET = 5


def load(path: str) -> dict:
    return core.read_json(path)


def materials_by_unit(round_record: dict) -> dict[str, dict]:
    return {item["unit_id"]: item for item in round_record["materials"]}


def grouped_ranking(rows: list[dict], budget: int) -> list[dict]:
    ranked = sorted(rows, key=lambda row: (-row["score"], row.get("max", row["score"]), row["units"][0]))
    for index, row in enumerate(ranked, start=1):
        row["rank"] = index
    return ranked[:budget]


def merge_paths(frozen: dict, scores: dict) -> dict:
    m1 = {row["id"]: row for row in scores["matrices"]["m1"]["candidates"]}
    m2 = {row["id"]: row for row in scores["matrices"]["m2"]["candidates"]}
    s_c = m2[CONCLUSION]["score"]
    entries: dict[str, dict] = {}
    for round_index, materials in ((2, materials_by_unit(frozen["rounds"][1])), (1, materials_by_unit(frozen["rounds"][0]))):
        for unit, material in materials.items():
            key = core.normalise(material["text"])
            entry = entries.setdefault(key, {
                "key": key,
                "text": material["text"],
                "units": [],
                "roles": [],
                "direct": 0.0,
                "indirect": 0.0,
                "paths": [],
            })
            if unit not in entry["units"]:
                entry["units"].append(unit)
                entry["roles"].append(material["role"])
            if round_index == 2:
                value = m2[unit]["score"]
                entry["direct"] += value
                entry["paths"].append({"kind": "direct", "unit": unit, "score": value})
            else:
                value = m1[unit]["score"] * s_c
                entry["indirect"] += value
                entry["paths"].append({"kind": "indirect", "unit": unit, "score": value})
    rows = []
    for entry in entries.values():
        total = entry["direct"] + entry["indirect"]
        rows.append({
            "units": entry["units"],
            "roles": entry["roles"],
            "text": entry["text"],
            "direct": entry["direct"],
            "indirect": entry["indirect"],
            "score": total,
            "max": max(entry["direct"], entry["indirect"]),
            "paths": entry["paths"],
        })
    return {"s_c": s_c, "rows": rows}


def rank_of(rows: list[dict], unit_ids: list[str]) -> int | None:
    for row in rows:
        if set(row["units"]) & set(unit_ids):
            return row["rank"]
    return None


def top_table(rows: list[dict], limit: int = BUDGET) -> list[dict]:
    return [
        {
            "rank": row["rank"],
            "units": row["units"],
            "roles": row["roles"],
            "text": row["text"],
            "score": row["score"],
            "direct": row.get("direct"),
            "indirect": row.get("indirect"),
        }
        for row in rows[:limit]
    ]


def claim_hits(texts: list[str], phrases: list[tuple[str, ...]]) -> list[dict]:
    hits = []
    for text in texts:
        lowered = text.lower()
        for phrase in phrases:
            if all(token in lowered for token in phrase):
                hits.append({"text": text[:160], "phrase": " + ".join(phrase)})
                break
    return hits


def build_sample(sample: dict, subset: Path) -> dict:
    spec = load(sample["spec"])
    frozen = load(sample["frozen"])
    scores = load(sample["scores"])
    case = spec["source"]["case"]
    gt = json.loads((subset / f"contextual64_v4/{case}/ground_truth.json").read_text(encoding="utf-8"))
    entry = [row for row in gt if row["target_id"] == spec["source"]["target_id"]][0]

    A = [item["unit_id"] for item in frozen["evidence"]["A"]]
    B = [item["unit_id"] for item in frozen["evidence"]["B"]]
    r1 = materials_by_unit(frozen["rounds"][0])
    r2 = materials_by_unit(frozen["rounds"][1])
    roles = {}
    for material in list(r1.values()) + list(r2.values()):
        roles[material["unit_id"]] = material["role"]

    # group 1: last round only, raw originals (conclusion is not an original)
    g1_rows = [
        {"units": [row["id"]], "roles": [roles.get(row["id"], "material")], "text": row["text"],
         "score": row["score"], "max": row["score"]}
        for row in scores["matrices"]["m2"]["candidates"] if row["id"] != CONCLUSION
    ]
    g1_all = grouped_ranking(g1_rows, len(g1_rows))

    # group 2: flat pool of both rounds' raw originals
    g2_rows = [
        {"units": [row["id"]], "roles": [roles.get(row["id"], "material")], "text": row["text"],
         "score": row["score"], "max": row["score"]}
        for row in scores["matrices"]["mflat"]["candidates"]
    ]
    g2_all = grouped_ranking(g2_rows, len(g2_rows))

    # group 3: merged direct + indirect path scores, deduplicated by original text
    merged = merge_paths(frozen, scores)
    g3_all = grouped_ranking(merged["rows"], len(merged["rows"]))

    groups = {}
    for name, rows, pool in (("last_round", g1_all, len(g1_rows)), ("flat", g2_all, len(g2_rows)),
                             ("merged", g3_all, len(merged["rows"]))):
        rank_a = rank_of(rows, A)
        rank_b = rank_of(rows, B)
        groups[name] = {
            "pool": pool,
            "top5": top_table(rows),
            "a_rank": rank_a,
            "b_rank": rank_b,
            "found_a": rank_a is not None and rank_a <= BUDGET,
            "found_b": rank_b is not None and rank_b <= BUDGET,
            "found_all": (rank_a is not None and rank_a <= BUDGET
                          and rank_b is not None and rank_b <= BUDGET),
        }

    # sensitivity: rank by max(path) instead of sum (copy the order, do not mutate the rows)
    max_sorted = sorted(merged["rows"], key=lambda row: (-row["max"], row["units"][0]))
    max_top = [row["units"][0] for row in max_sorted[:BUDGET]]
    sum_top = [row["units"][0] for row in g3_all[:BUDGET]]

    # GT same-claim spans: other groups whose primary text equals A's text
    a_text = core.normalise(frozen["evidence"]["A"][0]["text"])
    same_claim_spans = []
    for group in entry["answer_groups"]:
        for row in group["all_of"]:
            primary = row["primary"]
            if core.normalise(primary["text"]) == a_text:
                same_claim_spans.append({
                    "artifact_id": primary["artifact_id"],
                    "start": primary["start"],
                    "end": primary["end"],
                    "candidate_ids": primary.get("candidate_ids"),
                })
    r2_units = {item["unit_id"] for item in frozen["rounds"][1]["materials"]}
    r2_texts = [item["text"] for item in frozen["rounds"][1]["materials"]]
    same_claim_in_r2 = [
        span for span in same_claim_spans
        if any(span["artifact_id"] == item["artifact_id"] and span["start"] == item["start"]
               and span["end"] == item["end"] for item in frozen["rounds"][1]["materials"])
    ]

    phrases = {
        "T03": [("fifth", "album"), ("5th", "album"), ("fifth", "studio")],
        "T09": [("fifth", "solo"), ("5th", "solo"), ("fifth", "album")],
        "T06": [("sidney", "symphonic"), ("zero zero (musical)",)],
    }[sample["short"]]
    hits = claim_hits(r2_texts, phrases)
    for hit in hits:
        hit["units"] = [item["unit_id"] for item in frozen["rounds"][1]["materials"] if item["text"] == hit["text"]]
    ordered_list_hits = []
    for item in frozen["rounds"][1]["materials"]:
        lowered = item["text"].lower()
        if "zero zero" in lowered and ("schizophonia" in lowered or "six days in berlin" in lowered):
            ordered_list_hits.append({"unit_id": item["unit_id"], "text": item["text"]})

    return {
        "sample": sample["short"],
        "target_id": frozen["source"]["target_id"],
        "round1_answer": frozen["rounds"][0]["answer"],
        "round2_answer": frozen["rounds"][1]["answer"],
        "questions": {
            "round1": frozen["rounds"][0]["question"],
            "round2": frozen["rounds"][1]["question"],
        },
        "inputs": {
            "round1": [
                {k: material[k] for k in ("unit_id", "artifact_id", "start", "end", "role", "text")}
                for material in frozen["rounds"][0]["materials"]
            ],
            "round2": [
                {k: material[k] for k in ("unit_id", "artifact_id", "start", "end", "role", "text")}
                for material in frozen["rounds"][1]["materials"]
            ],
        },
        "groups": groups,
        "merged_rows": g3_all,
        "s_c": merged["s_c"],
        "max_vs_sum_same_top5": sum_top == max_top,
        "checks": {
            "same_claim_spans": same_claim_spans,
            "same_claim_in_round2": same_claim_in_r2,
            "claim_phrase_hits_in_round2": hits,
            "ordered_list_hits_in_round2": ordered_list_hits,
            "round2_max_lcs_chars": spec["checks"]["round2_without_evidence_a"]["max_lcs_chars"],
            "round2_max_shared_shingles": spec["checks"]["round2_without_evidence_a"]["max_shared_shingles"],
        },
    }


def render_markdown(payload: dict) -> str:
    lines = [
        "# 受控两轮溯源：最终原文排名（离线复算）",
        "",
        "只读已保存的 frozen/spec/scores，不加载模型、不用 GPU。",
        "",
        "## 口径",
        "",
        "- 每跳前 5：`m2`（第二轮单元，含中间结论）与 `m1`（第一轮材料）各自的 top-5，保留在原始矩阵顺序里。",
        "- 路径计分沿用 CUAD 原型的乘积规则：直达 = hop-1 分数；经中间结论 = hop-1(结论) × hop-2(分数)。",
        "- 同一原文合并直达与间接路径：分数相加（`max` 作敏感性复核），按原文文本去重，排除中间结论，取全局前 5。",
        "- 参照：CUAD 案例 0.4872 = 0.7569 × 0.6437，直达 0.3563，合并 0.8435（sum）。",
        "",
        "## 三组最终原文排名",
        "",
        "| 样例 | 组 | 1 | 2 | 3 | 4 | 5 | A 名次 | B 名次 | A 齐 | B 齐 | 找齐 |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for sample in payload["samples"]:
        for name, label in (("last_round", "G1 最后一轮"), ("flat", "G2 平铺"), ("merged", "G3 多轮全局")):
            group = sample["groups"][name]
            cells = []
            for row in group["top5"]:
                unit = row["units"][0]
                short = unit.split(":")[-2] + ":" + unit.split(":")[-1]
                mark = ""
                if set(row["units"]) & set(payload["evidence"][sample["sample"]]["A"]):
                    mark = " **A**"
                elif set(row["units"]) & set(payload["evidence"][sample["sample"]]["B"]):
                    mark = " **B**"
                cells.append(f"`{short}`{mark}")
            while len(cells) < BUDGET:
                cells.append("—")
            lines.append(
                f"| {sample['sample']} | {label} | " + " | ".join(cells)
                + f" | {group['a_rank'] if group['a_rank'] is not None else '—'} | "
                + f"{group['b_rank'] if group['b_rank'] is not None else '—'} | "
                + ("是" if group["found_a"] else "否") + " | "
                + ("是" if group["found_b"] else "否") + " | "
                + ("是" if group["found_all"] else "否") + " |"
            )
    lines.append("")
    lines.append("## 主例 T09（`case_02:selected_09`）")
    lines.append("")
    t09 = next(sample for sample in payload["samples"] if sample["sample"] == "T09")
    lines.append("### 原文位置")
    lines.append("")
    lines.append("| 标签 | unit | artifact | span | event | text |")
    lines.append("|---|---|---|---|---|---|")
    for label in ("A", "B"):
        for item in payload["source_positions"]["T09"][label]:
            lines.append(
                f"| {label} | `{item['unit_id'].split(':')[-2]}:{item['unit_id'].split(':')[-1]}` | "
                f"`{item['artifact_id'].split(':')[-1]}` | [{item['start']},{item['end']}) | "
                f"{item['event_index']} | {item['text']} |"
            )
    lines.append("")
    lines.append("### 两轮输入")
    lines.append("")
    for round_key, label in (("round1", "第一轮"), ("round2", "第二轮")):
        lines.append(f"**{label}**（问题：{t09['questions'][round_key]}）")
        if round_key == "round2":
            lines.append("")
            lines.append(f"前一步结论逐字放入：{t09['round1_answer']}")
        lines.append("")
        lines.append("| # | unit | span | role | text |")
        lines.append("|---|---|---|---|---|")
        for index, item in enumerate(t09["inputs"][round_key], start=1):
            lines.append(
                f"| {index} | `{item['unit_id'].split(':')[-2]}:{item['unit_id'].split(':')[-1]}` | "
                f"[{item['start']},{item['end']}) | {item['role']} | {item['text'][:90]} |"
            )
        lines.append("")
    lines.append("### 每跳前 5")
    lines.append("")
    for label, rows in (("hop-1：最终句 → 第二轮单元（含中间结论）", payload["hops"]["T09"]["hop1"]),
                        ("hop-2：中间结论 → 第一轮材料", payload["hops"]["T09"]["hop2"])):
        lines.append(f"**{label}**")
        lines.append("")
        lines.append("| rank | unit | score |")
        lines.append("|---|---|---|")
        for row in rows:
            unit = row["unit"]
            lines.append(f"| {row['rank']} | `{unit.split(':')[-2]}:{unit.split(':')[-1]}` | {row['score']:.6f} |")
        lines.append("")
    lines.append("### 两组最终前 5")
    lines.append("")
    for name, label in (("flat", "G2 平铺"), ("merged", "G3 多轮全局（直达 + 经中间结论，合并后）")):
        group = t09["groups"][name]
        lines.append(f"**{label}**（池 {group['pool']}，A 第 {group['a_rank']}、B 第 {group['b_rank']}）")
        lines.append("")
        lines.append("| rank | unit | role | score | 直达 | 间接 | text |")
        lines.append("|---|---|---|---|---|---|---|")
        for row in group["top5"]:
            unit = row["units"][0]
            direct = "—" if row.get("direct") is None else f"{row['direct']:.6f}"
            indirect = "—" if row.get("indirect") is None else f"{row['indirect']:.6f}"
            lines.append(
                f"| {row['rank']} | `{unit.split(':')[-2]}:{unit.split(':')[-1]}` | {', '.join(row['roles'])} | "
                f"{row['score']:.6f} | {direct} | {indirect} | {row['text'][:80]} |"
            )
        lines.append("")
    lines.append("### 核对")
    lines.append("")
    lines.append(f"- 平铺 B 第 {t09['groups']['flat']['b_rank']}（池 {t09['groups']['flat']['pool']}）；"
                 f"多轮全局 A 第 {t09['groups']['merged']['a_rank']}、B 第 {t09['groups']['merged']['b_rank']}。")
    lines.append(f"- 平铺 A 第 {t09['groups']['flat']['a_rank']}；最后一轮 A "
                 f"{'不可见' if t09['groups']['last_round']['a_rank'] is None else t09['groups']['last_round']['a_rank']}。")
    hits = t09["checks"]["claim_phrase_hits_in_round2"]
    lists = t09["checks"]["ordered_list_hits_in_round2"]
    lines.append(f"- 第二轮同义断言扫描：{'命中 ' + str(len(hits)) if hits else '无显式 fifth/5th 断言'}。"
                 + ("" if not hits else " 命中：" + "；".join(f"`{h['text'][:90]}`" for h in hits)))
    if lists:
        lines.append("- 可计数影子证据：" + "；".join(
            f"`{item['unit_id'].split(':')[-2]}:{item['unit_id'].split(':')[-1]}`（{item['text'][:110]}）"
            for item in lists
        ) + "。清单里 Zero Zero 在去掉 Caravans 的计数下是第 5 项；它不是显式 fifth 断言，也不是 GT 的 A。")
    lines.append("")
    lines.append("## T06 对照：最终轮自身已有足够证据")
    lines.append("")
    t06 = next(sample for sample in payload["samples"] if sample["sample"] == "T06")
    lines.append("- 最终句只要求“专辑 + 发行年”；第二轮材料里题名（`a0279`、`a0282`）与年份 `a0284:u137-154` 都在，"
                 "最终轮 top-5 直接包含 B 与题名，因此不需要沿中间结论追到列表项 A。")
    lines.append(f"- 多轮全局 A 第 {t06['groups']['merged']['a_rank']}、B 第 {t06['groups']['merged']['b_rank']}："
                 "A 被最终轮的直接材料挤出前 5，这是“自足对照”的预期结果，不作为链失败。")
    lines.append("")
    lines.append("## 另两题的最终轮同义原文核对")
    lines.append("")
    for name in ("T03", "T09"):
        sample = next(sample for sample in payload["samples"] if sample["sample"] == name)
        check = sample["checks"]
        lines.append(f"- **{name}**：同文 A 支持位置 {len(check['same_claim_spans'])} 个，"
                     f"落入第二轮 {len(check['same_claim_in_round2'])} 个；"
                     f"第二轮显式断言命中 {len(check['claim_phrase_hits_in_round2'])} 个；"
                     f"可计数清单 {len(check['ordered_list_hits_in_round2'])} 个；"
                     f"最长公共子串 {check['round2_max_lcs_chars']} 字符、8-token shingle {check['round2_max_shared_shingles']}。")
    lines.append("")
    lines.append("## 不同主题的合格样例")
    lines.append("")
    lines.append("- `case_08` 两个开发目标各只有一段主证据（`a0030[108,222)`、`a0024[164,214)`），"
                 "无法满足“第二轮不含 A、同时含同组 B”的两轮构造；`case_02` 其余目标都属于同一 Katie Melua/Mike Batt 主题，"
                 "且多为单段或等价来源。结论：现有获准开发轨迹里没有不同主题的合格样例，本轮不新增。")
    lines.append("")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--subset", required=True, help="extracted contextual64_v4 root")
    parser.add_argument("--out-json", required=True)
    parser.add_argument("--out-md", required=True)
    args = parser.parse_args(argv)

    manifest = core.read_json(args.manifest)
    subset = Path(args.subset)
    samples = [build_sample(sample, subset) for sample in manifest["samples"]]

    evidence = {}
    source_positions = {}
    hops = {}
    for sample, sample_manifest in zip(samples, manifest["samples"]):
        frozen = load(sample_manifest["frozen"])
        spec = load(sample_manifest["spec"])
        evidence[sample["sample"]] = {
            "A": [item["unit_id"] for item in frozen["evidence"]["A"]],
            "B": [item["unit_id"] for item in frozen["evidence"]["B"]],
        }
        source_positions[sample["sample"]] = {
            label: [
                {k: item[k] for k in ("unit_id", "artifact_id", "start", "end", "event_index", "text")}
                for item in frozen["evidence"][label]
            ]
            for label in ("A", "B")
        }
        analysis = load(sample_manifest["analysis"])
        hops[sample["sample"]] = {
            "hop1": [
                {"rank": entry["rank"], "unit": analysis["candidate_units"].get(entry["candidate_id"],
                                                                              entry["candidate_id"]),
                 "score": entry["score"]}
                for entry in analysis["path"]["hops"][0]["candidates"]
            ],
            "hop2": [
                {"rank": entry["rank"], "unit": analysis["candidate_units"].get(entry["candidate_id"],
                                                                              entry["candidate_id"]),
                 "score": entry["score"]}
                for entry in analysis["path"]["hops"][1]["candidates"]
            ],
        }

    payload = {
        "schema": "provenance_rounds_v1.final_rank.v1",
        "budget": BUDGET,
        "rule": "direct=hop1; indirect=hop1(conclusion)*hop2; same text summed; conclusion excluded",
        "samples": samples,
        "evidence": evidence,
        "source_positions": source_positions,
        "hops": hops,
    }
    Path(args.out_json).write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                                   encoding="utf-8")
    markdown = render_markdown(payload)
    Path(args.out_md).write_text(markdown, encoding="utf-8")
    summary = {
        sample["sample"]: {
            name: {"a": group["a_rank"], "b": group["b_rank"], "found": group["found_all"]}
            for name, group in sample["groups"].items()
        }
        for sample in samples
    }
    print(json.dumps({"summary": summary, "out_json": args.out_json, "out_md": args.out_md},
                     ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
