"""Offline-only DCC Stage 1 commands: validate, render-preview, report."""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import subprocess
import sys
import unittest
from collections import Counter
from pathlib import Path

from core import (
    MATCH_FIELDS, STATES, _closed_record, _fact_values, _span_text,
    classify_transition, decide_obligation, evaluate_object, render_input,
    render_public, tri_and, tri_not, tri_or, validate_case,
)

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parents[1]
DATA = ROOT / "data"
REPORTS = ROOT / "reports"
PREVIEW = ROOT / "preview"
CONFIG = ROOT / "config/stage1.json"


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def cases() -> list[tuple[dict, dict, dict]]:
    tables = [read_jsonl(DATA / name) for name in ("calibration_public.jsonl", "calibration_gold.jsonl", "calibration_assistance.jsonl")]
    if [len(table) for table in tables] != [8, 8, 8]:
        raise ValueError("DATA_COUNT: expected 8 rows in each view")
    return list(zip(*tables))


def inspect() -> dict:
    config = json.loads(CONFIG.read_text(encoding="utf-8"))
    expected = {"stage": "stage1_offline", "seed": 20261015, "calibration_case_count": 8,
                "allow_model_calls": False, "allow_paid_calls": False, "allow_gpu_jobs": False,
                "max_calls": 0, "max_cost_usd": 0, "model_id": None,
                "model_selection_status": "UNSELECTED"}
    errors = [] if config == expected else ["CONFIG_CONTRACT:config/stage1.json"]
    all_cases = cases()
    ids = [p["case_id"] for p, _, _ in all_cases]
    if len(set(ids)) != len(ids):
        errors.append("DATA_DUPLICATE_CASE_ID:data/calibration_public.jsonl")
    families = Counter()
    states = Counter()
    focal = {"T1": Counter(), "T2": Counter()}
    object_count = 0
    rendering = []
    for public, gold, assist in all_cases:
        families[gold["family_id"]] += 1
        errors.extend(validate_case(public, gold, assist))
        object_count += len(gold["objects"])
        states.update(d["state"] for d in gold["decisions"])
        focal[gold["family_id"]].update(d["state"] for d in gold["decisions"] if d["object_id"] == gold["focal_object_id"])
        base = render_public(public)
        allowed = ("A", "B") if public["task_type"] == "reference_existence" else ("A", "B", "C")
        hashes = {}
        for condition in allowed:
            rendered = render_input(public, assist, condition)
            if not rendered.startswith(base):
                errors.append(f"{public['case_id']}:RENDER_BASE:{condition}")
            hashes[condition] = hashlib.sha256(base.encode("utf-8")).hexdigest()
        if len(set(hashes.values())) != 1:
            errors.append(f"{public['case_id']}:MATERIAL_HASH_MISMATCH")
        rendering.append({"case_id": public["case_id"], "conditions": list(allowed), "public_material_sha256": hashes["A"]})
    if dict(families) != {"T1": 4, "T2": 4} or object_count != 32:
        errors.append("DATA_LAYOUT:expected 2 families x 4 versions x 4 objects")
    for family, counts in focal.items():
        if set(counts) != set(STATES) or any(counts[state] != 1 for state in STATES):
            errors.append(f"FOCAL_STATES:{family}")
    memory_records = read_jsonl(ROOT / "tests/fixtures/memory_audit.jsonl")
    memory_counts = Counter(classify_transition(row["pre_status"], row["post_status"]) for row in memory_records)
    if any(row["record_kind"] != "TEST_FIXTURE" for row in memory_records):
        errors.append("MEMORY_FIXTURE_KIND:tests/fixtures/memory_audit.jsonl")
    result = {"marker": "STAGE1_OFFLINE_VALIDATION", "status": "PASS" if not errors else "FAIL", "case_count": len(all_cases),
              "family_counts": dict(families), "object_count": object_count,
              "state_counts": dict(states), "focal_state_counts": {k: dict(v) for k, v in focal.items()},
              "public_material_hashes": rendering, "memory_fixture_counts": dict(memory_counts),
              "correct_content_loss_denominator_fixture_only": sum(row["pre_status"] == "CORRECT" for row in memory_records),
              "errors": errors, "model_calls": 0, "paid_calls": 0, "gpu_jobs": 0,
              "human_review_status": "NOT_REVIEWED", "scope": "OFFLINE_CALIBRATION_ONLY"}
    return result


def validate_command() -> int:
    result = inspect()
    write_json(REPORTS / "validation.json", result)
    print(f"validate: {result['case_count']} cases, {result['object_count']} objects, {len(result['errors'])} errors")
    return 0 if not result["errors"] else 1


def render_command() -> int:
    result = inspect()
    if result["errors"]:
        print("render-preview blocked by validation errors", file=sys.stderr)
        return 1
    PREVIEW.mkdir(parents=True, exist_ok=True)
    expected = set()
    for public, _, assist in cases():
        for condition in (("A", "B") if public["task_type"] == "reference_existence" else ("A", "B", "C")):
            path = PREVIEW / f"{public['case_id']}_{condition}.txt"
            path.write_text("DRY_RUN_NOT_SENT\n\n" + render_input(public, assist, condition), encoding="utf-8")
            expected.add(path.name)
    extra = {p.name for p in PREVIEW.glob("*.txt")} - expected
    if extra:
        print("preview directory contains unexpected text files: " + ", ".join(sorted(extra)), file=sys.stderr)
        return 1
    print(f"render-preview: {len(expected)} DRY_RUN_NOT_SENT files; T1 C rejected by design")
    return 0


def _logic(gold: dict, obj: dict) -> str:
    oid = obj["object_id"]
    if gold["family_id"] == "T1":
        facts = _fact_values(gold, oid)
        return f"范围适用={facts['reference_applicable']}；目标存在={facts['target_present']}；材料范围={obj['target_document_id']}。完整范围才能由未出现推出不存在；已出现可直接确认。"
    facts = _fact_values(gold, oid)
    applicable = tri_and(facts["external"], facts["restricted"], tri_not(facts["public"]))
    branches = {}
    for kind in ("approval", "order"):
        candidate = tri_and(*(facts[f"{kind}_{field}"] for field in MATCH_FIELDS))
        branches[kind] = _closed_record(candidate, facts[f"{kind}_registry_complete"])
    satisfied = tri_or(branches["approval"], branches["order"])
    bad = {kind: [field for field in MATCH_FIELDS if facts[f"{kind}_{field}"] == "FALSE"] for kind in ("approval", "order")}
    return (f"适用性 external={facts['external']} AND restricted={facts['restricted']} AND NOT public={tri_not(facts['public'])} => {applicable}；"
            f"批准候选无效项={bad['approval']}，批准登记完整性={facts['approval_registry_complete']}，批准分支={branches['approval']}；"
            f"命令候选无效项={bad['order']}，命令登记完整性={facts['order_registry_complete']}，命令分支={branches['order']}；"
            f"OR 后满足性={satisfied}，最终={decide_obligation(applicable, satisfied)}。时间按含端点 UTC 区间核查。")


def _quoted(public: dict, span: dict) -> str:
    return f"`{span['document_id']}[{span['start']}:{span['end']}]` “{_span_text(public, span).strip()}”"


def review_packet() -> str:
    variant_notes = {
        ("T1", "v1"): "d1 完整且含 4.2；焦点存在。",
        ("T1", "v2"): "d1 完整但不含 4.2；焦点缺失可判违反。",
        ("T1", "v3"): "同一方向改为明确排除的 External Standard Q-7；不适用。",
        ("T1", "v4"): "d1 为部分范围且未见 4.2；不能由缺席推断不存在。",
        ("T2", "v1"): "焦点批准范围不符，但匹配的有效法院命令构成替代满足。",
        ("T2", "v2"): "焦点批准、命令均有记录但范围/时间不符，两个登记均完整。",
        ("T2", "v3"): "状态文件明确焦点资料在发送前已依法公开。",
        ("T2", "v4"): "焦点现有记录无效，命令登记仅为部分摘录；仍可能有未给出的有效命令。",
    }
    lines = ["# DCC Stage 1 逐例人工评审包", "", "**程序验证通过不等于独立人工批准。** 所有 `independent_human_status=NOT_REVIEWED`。本文列出完整公开材料、规则、每个发生对象的计算与原文依据；请人工确认语义和对象全集。八例仅为校准，不是模型效果样本。", ""]
    for public, gold, assist in cases():
        family, variant = gold["family_id"], gold["variant_id"]
        lines += [f"## {public['case_id']} | {family} {variant}（评审用，模型不见家族/版本/焦点）", "", f"**家族变动：**{variant_notes[(family, variant)]}  **焦点对象：**`{gold['focal_object_id']}`（仅评审端）。", "", "**审核指令：**" + public["audit_instruction"], "", "**完整规则：**"]
        lines += [f"- `{r['rule_id']}` {r['text']}" for r in public["rules"]]
        lines += ["", "**统一材料清单：**"] + [f"- {r['text']}" for r in public["material_register"]]
        lines += ["", "**三批公开材料（全文原样）：**"]
        docs = {d["document_id"]: d for d in public["documents"]}
        for batch in public["batches"]:
            lines += [f"### {batch['batch_id']}", ""]
            for span in batch["document_spans"]:
                lines += [f"`{span['document_id']}`：", "```text", docs[span["document_id"]]["text"][span["start"]:span["end"]].rstrip("\n"), "```", ""]
        lines += ["**逐对象 Gold 与原文：**", ""]
        decisions = {d["object_id"]: d for d in gold["decisions"]}
        for obj in gold["objects"]:
            decision = decisions[obj["object_id"]]
            lines += [f"#### `{obj['object_id']}` → `{decision['state']}`", "", "- 发生位置：" + _quoted(public, obj["source_span"])]
            if family == "T1":
                lines += [f"- 目标：`{obj['target_document_id']}` 的 `{obj['target_clause_id']}`；引用范围 `{obj['reference_scope']}`。"]
                if decision["state"] == "COMPLIANT":
                    target_fact = next(f for f in gold["facts"] if f["object_id"] == obj["object_id"] and f["proposition"] == "target_present")
                    lines += ["- 可见目标：" + _quoted(public, target_fact["evidence_span_sets"][0][0])]
            else:
                aid = obj["event"]["event_id"]
                for did, title in (("d3", "资料状态"), ("d4", "书面批准"), ("d5", "法院命令")):
                    doc = docs[did]
                    line = next(line for line in doc["text"].splitlines() if line.startswith(aid + (":" if did == "d3" else " ")))
                    start = doc["text"].index(line)
                    lines += [f"- {title}：" + _quoted(public, {"document_id": did, "start": start, "end": start + len(line)})]
            lines += ["- 计算：" + _logic(gold, obj),
                      f"- 缺失范围依据：{decision['absence_scope_ids'] or '不需要'}；未知条件：{decision['unknown_condition_ids'] or '无'}。", ""]
        lines += ["**评审提示：**规则例外、完整性和全部四个发生对象均已在公开材料中呈现；请独立确认其足以支持上述结构化 Gold，而非只相信程序映射。", ""]
    lines += ["## A/B/C 索引与潜在侧信道", "", "- A 只有完整公开材料；B 额外获得全部对象位置；T2 C 再获得每对象固定五类原文区域：规则、事项、资料状态、批准、命令。T1 C 禁止。", "- 8 个案例 ID 和对象 ID 是固定种子生成的不透明哈希，名称不含结论；模型不见 `family_id`、`variant_id`、焦点、Gold、状态、依赖或评审备注。", "- T2 C 所有版本、所有对象均有 5 个候选，顺序恒为 d1–d5；无空列表、`NO_MATCH`、候选缺失哨兵或正例优先排序。批准与命令中始终保留有效和无效记录。", "- 统一清单每案同格式；T1 d1 完整/部分、T2 d5 完整/部分本身是判定所必需的公开事实。版本间正文长度会因真实的条款/状态变化而不同，不能机械保证等长；这仍是需人工关注的侧信道和可读性权衡。", "- 生成时曾发现 T1 的 PARTIAL 情形会错误地使已出现的其他条款也变成证据不足；已修正为‘出现即可证存在，未出现须完整范围才证不存在’，并加入回归测试。", "", "## 尚需独立人工判断", "", "1. 每案是否真的只含列出的四个适用发生对象；自然语言对象全集不能由程序绝对证明。", "2. 公开英文文字是否足以证明 Gold 中的每个结构化事实、例外及登记完整性；有无事实冲突或歧义。", "3. C 的位置索引及正文长度是否形成不可接受的答案侧信道；虽无显式标签，仍是诊断性 Oracle 辅助。", "4. T2 条件关联是否足够困难，是否仍可被浅层关键词猜中。", "5. 后续被测模型、费用上限与调用授权仍未确定。", ""]
    return "\n".join(lines)


def _tests() -> dict:
    if str(REPO) not in sys.path:
        sys.path.insert(0, str(REPO))
    suite = unittest.defaultTestLoader.discover(str(ROOT / "tests"), pattern="test_*.py")
    sink = io.StringIO()
    result = unittest.TextTestRunner(stream=sink, verbosity=1).run(suite)
    return {"run": result.testsRun, "failures": len(result.failures), "errors": len(result.errors), "passed": result.testsRun - len(result.failures) - len(result.errors), "successful": result.wasSuccessful(), "diagnostic": sink.getvalue() if not result.wasSuccessful() else None}


def report_command() -> int:
    validation = inspect()
    if validation["errors"]:
        print("report blocked by validation errors", file=sys.stderr)
        return 1
    expected_names = {f"{p['case_id']}_{condition}.txt" for p, _, _ in cases() for condition in (("A", "B") if p["task_type"] == "reference_existence" else ("A", "B", "C"))}
    actual_names = {p.name for p in PREVIEW.glob("*.txt")}
    if actual_names != expected_names:
        print("report requires exactly 20 expected previews", file=sys.stderr)
        return 1
    for path in PREVIEW.glob("*.txt"):
        if not path.read_text(encoding="utf-8").startswith("DRY_RUN_NOT_SENT\n\n"):
            print("report rejected non-dry-run preview", file=sys.stderr)
            return 1
    tests = _tests()
    if not tests["successful"]:
        print("report blocked by failed offline tests", file=sys.stderr)
        return 1
    validation["offline_tests"] = tests
    validation["preview_count"] = len(expected_names)
    validation["preview_status"] = "DRY_RUN_NOT_SENT"
    validation["independent_human_status"] = "NOT_REVIEWED"
    write_json(REPORTS / "validation.json", validation)
    (REPORTS / "REVIEW_PACKET.md").write_text(review_packet(), encoding="utf-8")

    input_chars = Counter()
    for public, _, assist in cases():
        for condition in (("A", "B") if public["task_type"] == "reference_existence" else ("A", "B", "C")):
            input_chars[condition] += len(render_input(public, assist, condition))
    budget = {
        "implementer": {"identity": "User-specified Codex GPT-6.1 Sol, medium", "role": "Stage 1 offline author; not the tested model"},
        "future_tested_model": {"provider": "UNSELECTED", "model_id": None, "version": None,
                                "nonsecret_config_source": None, "credential_field_names": [], "credential_status": "NOT_APPLICABLE_UNTIL_SELECTED",
                                "context_window": "UNVERIFIED", "parameter_support": "UNVERIFIED", "pricing": "UNVERIFIED"},
        "current_authorization": json.loads(CONFIG.read_text(encoding="utf-8")),
        "executed": {"model_calls": 0, "paid_calls": 0, "gpu_jobs": 0, "large_downloads": 0},
        "future_proposal_only": {"cases": 8, "requests": 20, "max_output_tokens_per_request_suggestion": 2048,
                                 "reasoning_tokens_possible": "UNVERIFIED; depends on selected model and billing policy",
                                 "input_characters_by_condition": dict(input_chars), "input_tokens": None,
                                 "tokenizer": None, "input_price_per_token": None, "output_price_per_token": None,
                                 "reasoning_token_price": None, "estimated_cost_usd": None,
                                 "authorized_cost_cap_usd": None,
                                 "cost_formula": "sum(input_tokens*input_price + output_tokens*output_price + billed_reasoning_tokens*reasoning_price), including retries",
                                 "permission_to_run": False},
        "note": "Character counts are exact rendered-text lengths, not token counts. No model or provider was selected from an unverified configuration.",
    }
    write_json(REPORTS / "model_and_budget.json", budget)
    code_commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=REPO, text=True).strip()
    inputs = [CONFIG, ROOT / "core.py", ROOT / "stage1.py", ROOT / "SCHEMA.md", ROOT / "README.md", ROOT / "data/authoring.py", ROOT / "tests/test_stage1.py", ROOT / "tests/fixtures/memory_audit.jsonl"]
    inputs += sorted(DATA.glob("calibration_*.jsonl"))
    outputs = [REPORTS / "validation.json", REPORTS / "REVIEW_PACKET.md", REPORTS / "model_and_budget.json"] + sorted(PREVIEW.glob("*.txt"))
    manifest = {"marker": "STAGE1_READY_FOR_REVIEW", "code_commit": code_commit, "code_commit_semantics": "Committed source/data baseline; generated reports are committed in a later delivery commit to avoid a self-referential hash.",
                "python_version": sys.version.split()[0], "seed": 20261015,
                "commands": ["python -m unittest discover -s experiments/dcc_diagnostic_v0/tests -p 'test_*.py' -v",
                             "python experiments/dcc_diagnostic_v0/stage1.py validate",
                             "python experiments/dcc_diagnostic_v0/stage1.py render-preview",
                             "python experiments/dcc_diagnostic_v0/stage1.py report"],
                "test_results": tests, "input_sha256": {str(p.relative_to(ROOT)): sha(p) for p in inputs},
                "output_sha256": {str(p.relative_to(ROOT)): sha(p) for p in outputs},
                "excluded_from_hash_map": ["reports/delivery_manifest.json", "reports/STAGE1_REPORT.md"],
                "model_calls": 0, "paid_calls": 0, "gpu_jobs": 0, "human_review": "NOT_REVIEWED"}
    write_json(REPORTS / "delivery_manifest.json", manifest)
    summary = f"""# DCC Stage 1 交付报告

**标记：`STAGE1_READY_FOR_REVIEW`**。技术门已通过；独立人工科学审查仍为 `NOT_REVIEWED`。本阶段仅离线准备，不是模型效果实验。

## 完成范围

- 8 个手工校准案例：T1/T2 各 4 版、每例 4 对象，共 {validation['object_count']} 个对象；两家族焦点各覆盖四状态。全对象状态计数：`{json.dumps(validation['state_counts'], ensure_ascii=False, sort_keys=True)}`。
- 固定三值逻辑与条款存在性求值；完整范围、UTC 含端点时间、有效替代依据、部分登记未知均由程序核验。结构/逻辑错误 **{len(validation['errors'])}**。
- A/B/C 共 **{len(expected_names)}** 份 `DRY_RUN_NOT_SENT` 文本；T1 只有 A/B，T2 有 A/B/C。Public/Gold/Assistance 分文件，渲染器不读 Gold；同案各条件的原始材料哈希相同。
- 六类记忆转换由明确的 `TEST_FIXTURE` 覆盖；正确内容保持损失分母仅含前序 `CORRECT` 条目，假记录未进入科学结果。
- 离线单元测试 **{tests['passed']}/{tests['run']} 通过**；执行命令见 [delivery_manifest.json](delivery_manifest.json)。Python `{sys.version.split()[0]}`。

## 文件与审查

- [逐例评审包](REVIEW_PACKET.md)：完整公开材料、每对象原文与计算、家族变化、侧信道和待审问题。
- [validation.json](validation.json)、[delivery_manifest.json](delivery_manifest.json)、[model_and_budget.json](model_and_budget.json)、[`../preview/`](../preview/)：检查、哈希、未来预算与未发送预览。
- 人工应重点审查对象全集、例外与材料完整性、事实文字是否支持 Gold，以及 C 的 Oracle 位置索引是否产生侧信道。Sol 自检不填写 `HUMAN_APPROVED`。

## 资源与下一阶段边界

本轮外部推理模型调用 **0**、付费 API 调用 **0**、GPU 作业 **0**、大型下载 **0**。被测模型 `UNSELECTED`，API 凭据未读取，价格/上下文/tokenizer 未核实。20 个请求和单请求输出上限 2048 tokens 只是未来审批建议；授权金额上限仍为 `null`，目前全部调用许可为 `false`。

下一步是用户及规划会话审查本包。未获得独立科学审查及另行授权前，不进入阶段二、完整 Pilot 或 H/S/L 实验。本阶段提交不推送远端。
"""
    (REPORTS / "STAGE1_REPORT.md").write_text(summary, encoding="utf-8")
    print(f"report: STAGE1_READY_FOR_REVIEW; {tests['passed']} tests; human review NOT_REVIEWED")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="DCC Stage 1 offline only")
    parser.add_argument("command", choices=("validate", "render-preview", "report"))
    args = parser.parse_args()
    return {"validate": validate_command, "render-preview": render_command, "report": report_command}[args.command]()


if __name__ == "__main__":
    raise SystemExit(main())
