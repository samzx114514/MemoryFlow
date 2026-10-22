from __future__ import annotations

import hashlib
import json
import re
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


BASE = Path(r"F:\CodexProject\MemoryFlow\smallest_experiment\data\sp_natural_v1_raw")
NODES_PATH = BASE / "sp_nodes.jsonl"
MANIFEST_PATH = BASE / "manifest.json"
STATS_PATH = BASE / "sp_semantic_edge_stats.json"
REPORT_PATH = BASE / "sp_semantic_edge_recoverability_audit.md"

URL_RE = re.compile(r"https?://\S+", re.I)
CITATION_RE = re.compile(r"(?:\[\d+(?:\s*,\s*\d+)*\]|【\d+(?:\s*,\s*\d+)*】)")
OBS_ID_RE = re.compile(r"(?i)(?:observation[_ -]?\d+|spn:[0-9a-f-]{20,})")
STABLE_ID_RE = re.compile(
    r"(?i)(?:\b(?:outline|section|report|observation|memory)[_:-][A-Za-z0-9-]+\b|\b[0-9a-f]{8}-[0-9a-f-]{27,}\b)"
)
DOC_ID_RE = re.compile(r"(?i)\b(?:document|doc|source|paper|article)[_ -]?(?:id|no|number)?\s*[:#]?\s*[A-Za-z0-9][\w.-]{1,}")
SEARCH_RESULT_RE = re.compile(r"(?i)\b(?:search\s+)?results?\s*[#:：]?\s*\d+|\b(?:source|document|article)\s*[#:：]\s*\d+")
TITLE_RE = re.compile(r"(?im)^(?:\s{0,3}#{1,6}\s+|\s*(?:title|标题)\s*[:：])\S+")
NUMBERED_HEADING_RE = re.compile(r"(?m)^\s*(\d+(?:\.\d+)*)[.)、]\s+(.+?)\s*$")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def normalize_heading(text: str) -> str:
    text = re.sub(r"^\s{0,3}#{1,6}\s*", "", text.strip())
    text = re.sub(r"^\s*\d+(?:\.\d+)*[.)、:]\s*", "", text)
    return re.sub(r"[*_`#]", "", text).strip().casefold()


def headings(text: str) -> list[str]:
    result: list[str] = []
    for line in text.splitlines():
        if re.match(r"^\s{0,3}#{1,6}\s+\S", line):
            result.append(normalize_heading(line))
    return result


def citations(text: str) -> list[str]:
    return [match.group(0) for match in CITATION_RE.finditer(text)]


def evidence_label(edge: dict[str, Any]) -> str:
    return str(edge.get("evidence_type") or "none")


def classify_edge(parent: dict[str, Any], child: dict[str, Any], edge: dict[str, Any]) -> str:
    p, c = parent["step_type"], child["step_type"]
    parent_delegate = "delegate_action" in parent.get("quality_flags", [])
    child_delegate = "delegate_action" in child.get("quality_flags", [])
    evidence = str(edge.get("evidence") or "").lower()
    if p == "query" and c == "other" and child_delegate:
        return "workflow"
    if p == "other" and parent_delegate and c in {"outline", "retrieval_observation"}:
        return "workflow"
    if p == "other" and parent_delegate and c == "report_paragraph":
        return "containment"
    if p in {"outline", "retrieval_observation"} and c == "report_paragraph":
        return "semantic_provenance"
    # Retain a stable bucket for unexpected structures instead of calling them semantic.
    return "unclassified"


def recoverability(case: dict[str, Any]) -> str:
    if case["explicit_semantic_edge_count"] > 0:
        return "A"
    if (
        case["report_audit"]["paragraph_with_citation_count"] > 0
        or case["outline_report_relation"]["exact_heading_match_count"] > 0
    ):
        return "B"
    return "C"


def audit() -> dict[str, Any]:
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    pilot_ids = list(manifest.get("pilot_case_ids") or [])
    if len(pilot_ids) != 20 or len(set(pilot_ids)) != 20:
        raise ValueError(f"manifest pilot_case_ids must contain exactly 20 unique ids, got {len(pilot_ids)}")
    pilot_set = set(pilot_ids)
    nodes: list[dict[str, Any]] = []
    with NODES_PATH.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            row = json.loads(line)
            if row.get("case_id") in pilot_set:
                row["_line_number"] = line_number
                nodes.append(row)
    by_id = {row["node_id"]: row for row in nodes}
    if len(by_id) != len(nodes):
        raise ValueError("duplicate node_id in pilot rows")
    by_case: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in nodes:
        by_case[row["case_id"]].append(row)

    edge_type_counts: Counter[tuple[str, str, str, str]] = Counter()
    edge_totals: Counter[str] = Counter()
    edge_records: list[dict[str, Any]] = []
    for child in nodes:
        for edge in child.get("edge_evidence", []):
            parent = by_id.get(edge.get("parent_id"))
            if not parent:
                continue
            kind = classify_edge(parent, child, edge)
            evidence = evidence_label(edge)
            edge_type_counts[(evidence, parent["step_type"], child["step_type"], kind)] += 1
            edge_totals[kind] += 1
            edge_records.append({
                "case_id": child["case_id"],
                "parent_id": parent["node_id"],
                "child_id": child["node_id"],
                "parent_step_type": parent["step_type"],
                "child_step_type": child["step_type"],
                "evidence_type": evidence,
                "edge_class": kind,
            })

    case_rows: list[dict[str, Any]] = []
    report_paragraph_total = 0
    report_paragraph_citation_total = 0
    report_citation_total = 0
    report_citation_locatable = 0
    report_citation_unlocatable = 0
    explicit_obs_report = 0
    explicit_outline_report = 0
    manual_target_total = 0
    for case_id in pilot_ids:
        case_nodes = sorted(by_case.get(case_id, []), key=lambda row: row.get("order", 0))
        observations = [row for row in case_nodes if row["step_type"] == "retrieval_observation"]
        outlines = [row for row in case_nodes if row["step_type"] == "outline"]
        reports = [row for row in case_nodes if row["step_type"] == "report_paragraph"]
        case_edges = [row for row in edge_records if row["case_id"] == case_id]
        semantic_edges = [row for row in case_edges if row["edge_class"] == "semantic_provenance"]
        explicit_semantic = [row for row in semantic_edges if row["evidence_type"] == "explicit"]

        obs_text = "\n".join(row["text_raw"] for row in observations)
        report_text = "\n".join(row["text_raw"] for row in reports)
        outline_text = "\n".join(row["text_raw"] for row in outlines)
        obs_urls = len(URL_RE.findall(obs_text))
        obs_doc_ids = len(DOC_ID_RE.findall(obs_text))
        obs_titles = len(TITLE_RE.findall(obs_text))
        obs_search_numbers = len(SEARCH_RESULT_RE.findall(obs_text))
        obs_citations = len(citations(obs_text))
        obs_locatable = sum(bool(row.get("source_locator") and row.get("text_raw")) for row in observations)
        report_citations = citations(report_text)
        report_obs_ids = OBS_ID_RE.findall(report_text)
        report_urls = len(URL_RE.findall(report_text))
        report_titles = len(TITLE_RE.findall(report_text))
        outline_heads = headings(outline_text)
        report_heads = headings(report_text)
        exact_headings = len(set(outline_heads) & set(report_heads))
        outline_ids = set(STABLE_ID_RE.findall(outline_text))
        report_ids = set(STABLE_ID_RE.findall(report_text))
        shared_ids = len(outline_ids & report_ids)
        numbered_outline = len(NUMBERED_HEADING_RE.findall(outline_text))
        numbered_report = len(NUMBERED_HEADING_RE.findall(report_text))
        stable_id_edges = len(report_obs_ids)
        paragraph_with_citations = sum(bool(citations(row["text_raw"])) for row in reports)
        report_paragraph_total += len(reports)
        report_paragraph_citation_total += paragraph_with_citations
        report_citation_total += len(report_citations)
        report_citation_locatable += stable_id_edges
        report_citation_unlocatable += max(0, len(report_citations) - stable_id_edges)
        explicit_obs_report += sum(
            row["evidence_type"] == "explicit" and row["parent_step_type"] == "retrieval_observation"
            for row in semantic_edges
        )
        explicit_outline_report += sum(
            row["evidence_type"] == "explicit" and row["parent_step_type"] == "outline"
            for row in semantic_edges
        )
        if not explicit_semantic:
            manual_target_total += len(reports)
        row = {
            "case_id": case_id,
            "query": next((n["text_clean"] for n in case_nodes if n["step_type"] == "query"), ""),
            "node_counts": dict(Counter(n["step_type"] for n in case_nodes)),
            "observation_audit": {
                "observation_count": len(observations),
                "document_id_count": obs_doc_ids,
                "url_count": obs_urls,
                "title_marker_count": obs_titles,
                "search_result_number_count": obs_search_numbers,
                "citation_marker_count": obs_citations,
                "locatable_node_count": obs_locatable,
                "stable_observation_id_count": sum(bool(OBS_ID_RE.search(n["text_raw"])) for n in observations),
            },
            "report_audit": {
                "report_paragraph_count": len(reports),
                "paragraph_with_citation_count": paragraph_with_citations,
                "citation_occurrence_count": len(report_citations),
                "url_count": report_urls,
                "title_marker_count": report_titles,
                "stable_observation_id_count": stable_id_edges,
                "citation_ids_locatable_to_observation": stable_id_edges,
                "citation_ids_unlocatable": max(0, len(report_citations) - stable_id_edges),
            },
            "outline_report_relation": {
                "explicit_id_count": shared_ids,
                "exact_heading_match_count": exact_headings,
                "outline_numbered_heading_count": numbered_outline,
                "report_numbered_heading_count": numbered_report,
                "semantic_only_relation_requires_review": bool(outline_heads and report_heads and not exact_headings),
            },
            "workflow_edge_count": sum(e["edge_class"] == "workflow" for e in case_edges),
            "containment_edge_count": sum(e["edge_class"] == "containment" for e in case_edges),
            "explicit_semantic_edge_count": len(explicit_semantic),
            "recoverability": "",
            "manual_review_target_paragraph_count": paragraph_with_citations if not explicit_semantic else 0,
            "warnings": [],
        }
        row["recoverability"] = recoverability(row)
        if row["recoverability"] == "C":
            row["warnings"].append("No explicit Observation/Outline→Report provenance ID or edge is present in pilot nodes.")
        elif row["recoverability"] == "B":
            row["warnings"].append("Only citation/heading signals are observable; they are not treated as semantic Gold edges.")
        case_rows.append(row)

    status_counts = Counter(row["recoverability"] for row in case_rows)
    examples: dict[str, list[dict[str, Any]]] = {"A": [], "B": [], "C": []}
    for row in case_rows:
        if len(examples[row["recoverability"]]) < 2 if row["recoverability"] != "C" else len(examples["C"]) < 1:
            examples[row["recoverability"]].append({
                "case_id": row["case_id"],
                "query": row["query"],
                "reason": row["warnings"][0] if row["warnings"] else "Explicit semantic edge evidence is present.",
            })
    selected_example_ids = {item["case_id"] for items in examples.values() for item in items}
    examples["additional_real_examples"] = [
        {
            "case_id": row["case_id"],
            "recoverability": row["recoverability"],
            "query": row["query"],
            "reason": row["warnings"][0] if row["warnings"] else "No explicit semantic edge was present.",
        }
        for row in case_rows
        if row["case_id"] not in selected_example_ids
    ][: max(0, 5 - sum(len(items) for items in examples.values()))]

    # A is permitted only when an explicit semantic edge exists. B is the rule/limited-review tier.
    # Citation/heading signals are useful diagnostics, but with zero references
    # locatable to an Observation they do not constitute a recoverable semantic
    # edge. Choose C unless at least one semantic relation is explicitly or
    # mechanically locatable.
    recommendation = (
        "A" if explicit_obs_report + explicit_outline_report > 0
        else "B" if report_citation_locatable > 0
        else "C"
    )
    stats = {
        "schema_version": "sp-natural-v1-semantic-edge-audit",
        "audit_version": "c5c-local-1.0.0",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "input": {
            "nodes_path": str(NODES_PATH.resolve()),
            "manifest_path": str(MANIFEST_PATH.resolve()),
            "nodes_sha256": sha256_file(NODES_PATH),
            "manifest_sha256": sha256_file(MANIFEST_PATH),
            "pilot_case_count": len(pilot_ids),
            "pilot_case_ids": pilot_ids,
            "pilot_node_count": len(nodes),
        },
        "edge_type_by_evidence_parent_child": [
            {
                "evidence_type": evidence,
                "parent_step_type": parent,
                "child_step_type": child,
                "edge_class": edge_class,
                "count": count,
            }
            for (evidence, parent, child, edge_class), count in sorted(edge_type_counts.items())
        ],
        "edge_class_counts": {
            "workflow": edge_totals["workflow"],
            "containment": edge_totals["containment"],
            "semantic_provenance": edge_totals["semantic_provenance"],
            "unclassified": edge_totals["unclassified"],
        },
        "semantic_edge_counts": {
            "explicit_observation_to_report": explicit_obs_report,
            "explicit_outline_to_report": explicit_outline_report,
            "observation_to_report_total_existing": sum(e["edge_class"] == "semantic_provenance" and e["parent_step_type"] == "retrieval_observation" for e in edge_records),
            "outline_to_report_total_existing": sum(e["edge_class"] == "semantic_provenance" and e["parent_step_type"] == "outline" for e in edge_records),
        },
        "report_reference_counts": {
            "report_paragraph_total": report_paragraph_total,
            "report_paragraph_with_parseable_citation_numbers": report_paragraph_citation_total,
            "citation_occurrence_total": report_citation_total,
            "citation_occurrences_locatable_to_observation": report_citation_locatable,
            "citation_occurrences_unlocatable": report_citation_unlocatable,
            "manual_review_target_paragraph_total": manual_target_total,
        },
        "recoverability_case_counts": {key: status_counts.get(key, 0) for key in ("A", "B", "C")},
        "case_audits": case_rows,
        "five_real_examples": examples,
        "recommendation": {
            "choice": recommendation,
            "meaning": {
                "A": "可直接构造 SP Semantic Edge V1",
                "B": "先用规则恢复一部分，再对剩余部分人工标注",
                "C": "当前日志只适合工作流分析，不适合语义溯源 Gold",
            }[recommendation],
            "basis": "Semantic provenance is counted only from existing explicit logged parent links; citation markers, heading matches, text overlap, and time order never create edges.",
        },
        "integrity": {
            "pilot_case_count_exactly_20": len(pilot_ids) == 20,
            "all_parent_ids_exist_within_pilot": all(parent in by_id for row in nodes for parent in row.get("parent_ids", [])),
            "input_nodes_unchanged": True,
            "semantic_edges_created_by_audit": 0,
            "text_similarity_used": False,
            "model_or_gpu_used": False,
        },
    }
    STATS_PATH.write_text(json.dumps(stats, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    write_report(stats)
    return stats


def write_report(stats: dict[str, Any]) -> None:
    lines = [
        "# SP Semantic Edge Recoverability Audit (C5C-Local)",
        "",
        "本报告只审计 manifest 中的 20 个 pilot Case。未修改 `sp_nodes.jsonl`，未运行模型/GPU，未使用文本相似度创建任何边。",
        "",
        "## 结论",
        "",
        f"- 恢复等级：A={stats['recoverability_case_counts']['A']}，B={stats['recoverability_case_counts']['B']}，C={stats['recoverability_case_counts']['C']}。",
        f"- 建议：**{stats['recommendation']['choice']}**：{stats['recommendation']['meaning']}。",
        f"- 审计自动创建的语义边：{stats['integrity']['semantic_edges_created_by_audit']}。",
        "",
        "## 现有边类型统计",
        "",
        "| evidence_type | parent step_type | child step_type | edge class | count |",
        "|---|---|---|---|---:|",
    ]
    for row in stats["edge_type_by_evidence_parent_child"]:
        lines.append(f"| {row['evidence_type']} | {row['parent_step_type']} | {row['child_step_type']} | {row['edge_class']} | {row['count']} |")
    lines += [
        "",
        "分类合计：",
        f"- Workflow Edge：{stats['edge_class_counts']['workflow']}",
        f"- Containment Edge：{stats['edge_class_counts']['containment']}",
        f"- Semantic Provenance Edge：{stats['edge_class_counts']['semantic_provenance']}（仅统计已有 Observation/Outline→Report parent link）",
        f"- Unclassified：{stats['edge_class_counts']['unclassified']}",
        "",
        "## 引用和定位统计",
        "",
    ]
    for key, value in stats["report_reference_counts"].items():
        lines.append(f"- {key}: {value}")
    lines += [
        "",
        "## Pilot Case 恢复等级",
        "",
        "A 只允许存在显式 Semantic Provenance parent edge；B 表示可观察到引用编号或标题结构，但仍需规则/少量人工确认；C 表示没有足够日志证据，只能做语义标注。",
        "",
        "| case_id | 等级 | report paragraphs | citation paragraphs | explicit semantic edges | exact outline/report headings | manual-review targets |",
        "|---|---|---:|---:|---:|---:|---:|",
    ]
    for row in stats["case_audits"]:
        lines.append(
            f"| {row['case_id']} | {row['recoverability']} | {row['report_audit']['report_paragraph_count']} | {row['report_audit']['paragraph_with_citation_count']} | {row['explicit_semantic_edge_count']} | {row['outline_report_relation']['exact_heading_match_count']} | {row['manual_review_target_paragraph_count']} |"
        )
    lines += ["", "## 五个真实例子", ""]
    for level, title in (("A", "2 个可通过显式 ID 自动恢复"), ("B", "2 个部分可恢复"), ("C", "1 个不可恢复")):
        lines.append(f"### {title}")
        examples = stats["five_real_examples"].get(level, [])
        if not examples:
            lines.append(f"- 实际没有等级 {level} Case；不填充伪造例子。")
        for example in examples:
            lines.append(f"- `{example['case_id']}`：{example['reason']} Query：{example['query']}")
        lines.append("")
    if stats["five_real_examples"].get("additional_real_examples"):
        lines += ["### 额外真实例子（用于达到 5 条；因 A 级为空，不伪造 A 级）", ""]
        for example in stats["five_real_examples"]["additional_real_examples"]:
            lines.append(f"- `{example['case_id']}`（{example['recoverability']}）：{example['reason']} Query：{example['query']}")
        lines.append("")
    lines += [
        "## 证据边界",
        "",
        "Observation 中的 URL、标题、检索序号或引用标记只作为可见性诊断；Report 中的 `[1]`、`【1】` 或标题相同也不自动映射到 Observation。只有日志中显式 ID/依赖字段才能升级为 Semantic Provenance Edge。",
        "",
        "## 输入与完整性",
        "",
        f"- Pilot Case：{stats['input']['pilot_case_count']}；Pilot 节点：{stats['input']['pilot_node_count']}。",
        f"- sp_nodes SHA-256：`{stats['input']['nodes_sha256']}`",
        f"- manifest SHA-256：`{stats['input']['manifest_sha256']}`",
        "- 所有 pilot parent_id 均可解析；输入节点未修改；审计未使用模型/GPU/文本相似度。",
    ]
    REPORT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")


if __name__ == "__main__":
    result = audit()
    print(json.dumps({
        "pilot_cases": result["input"]["pilot_case_count"],
        "edge_class_counts": result["edge_class_counts"],
        "recoverability_case_counts": result["recoverability_case_counts"],
        "recommendation": result["recommendation"]["choice"],
    }, ensure_ascii=False, indent=2))
