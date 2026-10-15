"""Offline, fixed-contract validation and dry-run rendering for DCC Stage 1."""

from __future__ import annotations

import json
from datetime import datetime, timezone

SCHEMA_VERSION = "dcc-diagnostic-v0.1"
TRI = ("TRUE", "FALSE", "UNKNOWN")
STATES = ("COMPLIANT", "VIOLATION", "NOT_APPLICABLE", "INSUFFICIENT_EVIDENCE")
TRANSITIONS = (
    "RETENTION_LOSS", "PREEXISTING_ERROR", "NEVER_ACQUIRED",
    "RETAINED", "RECOVERY", "UNASSESSABLE",
)
MATCH_FIELDS = ("subject_match", "scope_match", "event_match", "time_match", "effective")


def tri_and(*values: str) -> str:
    if any(value not in TRI for value in values):
        raise ValueError("TRI_INVALID")
    if "FALSE" in values:
        return "FALSE"
    return "TRUE" if all(value == "TRUE" for value in values) else "UNKNOWN"


def tri_or(*values: str) -> str:
    if any(value not in TRI for value in values):
        raise ValueError("TRI_INVALID")
    if "TRUE" in values:
        return "TRUE"
    return "FALSE" if all(value == "FALSE" for value in values) else "UNKNOWN"


def tri_not(value: str) -> str:
    if value not in TRI:
        raise ValueError("TRI_INVALID")
    return {"TRUE": "FALSE", "FALSE": "TRUE", "UNKNOWN": "UNKNOWN"}[value]


def decide_obligation(applicable: str, satisfied: str) -> str:
    if applicable not in TRI or satisfied not in TRI:
        raise ValueError("TRI_INVALID")
    if applicable == "FALSE":
        return "NOT_APPLICABLE"
    if applicable == "UNKNOWN":
        return "INSUFFICIENT_EVIDENCE"
    return {"TRUE": "COMPLIANT", "FALSE": "VIOLATION", "UNKNOWN": "INSUFFICIENT_EVIDENCE"}[satisfied]


def _utc(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo != timezone.utc:
        raise ValueError("TIME_NOT_UTC")
    return parsed


def _fact_values(gold: dict, object_id: str) -> dict[str, str]:
    return {f["proposition"]: f["value"] for f in gold["facts"] if f["object_id"] == object_id}


def _record_matches(event: dict, record: dict) -> dict[str, str]:
    sent_at = _utc(event["sent_at"])
    return {
        "subject_match": "TRUE" if event["subject"] == record["subject"] else "FALSE",
        "scope_match": "TRUE" if event["scope"] == record["scope"] else "FALSE",
        "event_match": "TRUE" if event["event_id"] == record["event_id"] else "FALSE",
        "time_match": "TRUE" if _utc(record["valid_from"]) <= sent_at <= _utc(record["valid_until"]) else "FALSE",
        "effective": "TRUE" if record["effective"] is True else "FALSE",
    }


def _closed_record(candidate: str, registry_complete: str) -> str:
    if candidate == "TRUE":
        return "TRUE"
    if candidate == "FALSE" and registry_complete == "TRUE":
        return "FALSE"
    return "UNKNOWN"


def evaluate_object(public: dict, gold: dict, obj: dict) -> str:
    if public["task_type"] == "reference_existence":
        if obj["reference_scope"] == "EXTERNAL_EXCLUDED":
            return "NOT_APPLICABLE"
        register = {r["document_id"]: r for r in public["material_register"]}
        target = register[obj["target_document_id"]]
        if not target["provided"]:
            return "INSUFFICIENT_EVIDENCE"
        doc = next(d for d in public["documents"] if d["document_id"] == obj["target_document_id"])
        if obj["target_clause_id"] in {c["clause_id"] for c in doc["clauses"]}:
            return "COMPLIANT"
        return "VIOLATION" if target["coverage"] == "COMPLETE" else "INSUFFICIENT_EVIDENCE"

    facts = _fact_values(gold, obj["object_id"])
    applicable = tri_and(facts["external"], facts["restricted"], tri_not(facts["public"]))
    validity = []
    for kind in ("approval", "order"):
        candidate = tri_and(*(facts[f"{kind}_{field}"] for field in MATCH_FIELDS))
        validity.append(_closed_record(candidate, facts[f"{kind}_registry_complete"]))
    return decide_obligation(applicable, tri_or(*validity))


def register_text(document_id: str, provided: bool, coverage: str) -> str:
    availability = "provided" if provided else "not provided"
    return f"{document_id}: {availability}; coverage {coverage}."


def _span_text(public: dict, span: dict) -> str:
    doc = next(d for d in public["documents"] if d["document_id"] == span["document_id"])
    return doc["text"][span["start"]:span["end"]]


def _span_error(public: dict, span: dict) -> bool:
    if not isinstance(span, dict) or not {"document_id", "start", "end"} <= span.keys():
        return True
    doc = next((d for d in public.get("documents", []) if d.get("document_id") == span["document_id"]), None)
    return doc is None or not isinstance(span["start"], int) or not isinstance(span["end"], int) or not (0 <= span["start"] < span["end"] <= len(doc["text"]))


def validate_case(public: dict, gold: dict, assistance: dict) -> list[str]:
    """Return stable error codes with case and field location; never repair data."""
    cid = public.get("case_id", "<missing-case-id>")
    errors = []

    def err(code: str, where: str) -> None:
        errors.append(f"{cid}:{code}:{where}")

    if public.get("schema_version") != SCHEMA_VERSION:
        err("SCHEMA_VERSION", "public.schema_version")
    if public.get("task_type") not in ("reference_existence", "conditional_obligation") or public.get("language") != "en":
        err("PUBLIC_TYPE", "public.task_type/language")
    if gold.get("case_id") != cid or assistance.get("case_id") != cid:
        err("CASE_ID", "gold/assistance.case_id")
    if gold.get("ambiguity", {}).get("flag") or gold.get("ambiguity", {}).get("reasons"):
        err("AMBIGUOUS", "gold.ambiguity")
    if gold.get("review", {}).get("independent_human_status") != "NOT_REVIEWED":
        err("HUMAN_STATUS", "gold.review.independent_human_status")

    docs = public.get("documents", [])
    register = public.get("material_register", [])
    doc_ids = [d["document_id"] for d in docs]
    reg_ids = [r["document_id"] for r in register]
    if len(doc_ids) != len(set(doc_ids)) or len(reg_ids) != len(set(reg_ids)):
        err("DUPLICATE_ID", "public.documents/material_register")
    if not set(doc_ids) <= set(reg_ids):
        err("REGISTER_CONFLICT", "public.documents")
    for i, entry in enumerate(register):
        coverage = entry.get("coverage")
        if coverage not in ("COMPLETE", "PARTIAL", "UNAVAILABLE") or entry.get("provided") != (coverage != "UNAVAILABLE") or entry.get("text") != register_text(entry["document_id"], entry.get("provided"), coverage):
            err("REGISTER_CONFLICT", f"public.material_register[{i}]")
        if (entry["document_id"] in doc_ids) != entry.get("provided"):
            err("REGISTER_CONFLICT", f"public.material_register[{i}].provided")
    for i, doc in enumerate(docs):
        clause_ids = [c["clause_id"] for c in doc.get("clauses", [])]
        if len(clause_ids) != len(set(clause_ids)):
            err("DUPLICATE_ID", f"public.documents[{i}].clauses")
        for j, clause in enumerate(doc.get("clauses", [])):
            span = dict(document_id=doc["document_id"], start=clause["start"], end=clause["end"])
            if _span_error(public, span):
                err("SPAN_RANGE", f"public.documents[{i}].clauses[{j}]")
            elif not _span_text(public, span).startswith(clause["clause_id"] + ":"):
                err("CLAUSE_TEXT", f"public.documents[{i}].clauses[{j}]")
    if public.get("task_type") == "conditional_obligation" and set(doc_ids) == {"d1", "d2", "d3", "d4", "d5"}:
        for did in ("d4", "d5"):
            body = next(d["text"] for d in docs if d["document_id"] == did)
            expected = "complete for all listed TX events" if next(r["coverage"] for r in register if r["document_id"] == did) == "COMPLETE" else "partial extract for TX-01"
            if expected not in body:
                err("REGISTER_CONFLICT", f"public.documents[{did}].text")

    batches = public.get("batches", [])
    if len(batches) < 3 or len({b["batch_id"] for b in batches}) != len(batches):
        err("BATCH_LAYOUT", "public.batches")
    coverage = {did: [] for did in doc_ids}
    for i, batch in enumerate(batches):
        for j, span in enumerate(batch["document_spans"]):
            if _span_error(public, span):
                err("SPAN_RANGE", f"public.batches[{i}].document_spans[{j}]")
            else:
                coverage[span["document_id"]].append((span["start"], span["end"]))
    for doc in docs:
        intervals = sorted(coverage[doc["document_id"]])
        if intervals != [(0, len(doc["text"]))]:
            err("BATCH_COVERAGE", f"public.documents[{doc['document_id']}]")

    objects = gold.get("objects", [])
    object_ids = [o["object_id"] for o in objects]
    if len(objects) < 4 or len(object_ids) != len(set(object_ids)):
        err("DUPLICATE_ID", "gold.objects")
    if gold.get("focal_object_id") not in object_ids:
        err("FOCAL_ID", "gold.focal_object_id")
    decisions = gold.get("decisions", [])
    if len(decisions) != len(objects) or {d["object_id"] for d in decisions} != set(object_ids):
        err("DECISION_COVERAGE", "gold.decisions")
    fact_ids = [f["fact_id"] for f in gold.get("facts", [])]
    dep_ids = [d["conclusion_id"] for d in gold.get("dependencies", [])]
    if len(fact_ids) != len(set(fact_ids)) or len(dep_ids) != len(set(dep_ids)) or set(fact_ids) & set(dep_ids):
        err("DUPLICATE_ID", "gold.facts/dependencies")
    all_condition_ids = set(fact_ids + dep_ids)
    for i, fact in enumerate(gold.get("facts", [])):
        if fact.get("value") not in TRI or fact.get("object_id") not in object_ids:
            err("FACT_VALUE", f"gold.facts[{i}]")
        if not fact.get("evidence_span_sets"):
            err("FACT_EVIDENCE", f"gold.facts[{i}]")
        for spans in fact.get("evidence_span_sets", []):
            if not spans or any(_span_error(public, span) for span in spans):
                err("SPAN_RANGE", f"gold.facts[{i}].evidence_span_sets")
    for i, dep in enumerate(gold.get("dependencies", [])):
        if dep.get("operator") not in ("AND", "OR", "NOT", "REGISTER_CLOSURE", "REFERENCE_LOOKUP") or any(pid not in all_condition_ids for pid in dep.get("premise_ids", [])):
            err("DEPENDENCY", f"gold.dependencies[{i}]")
    reg_by_id = {r["document_id"]: r for r in register}
    for i, obj in enumerate(objects):
        oid = obj["object_id"]
        if _span_error(public, obj.get("source_span")):
            err("SPAN_RANGE", f"gold.objects[{i}].source_span")
        if public.get("task_type") == "reference_existence":
            if obj.get("reference_scope") not in ("IN_SCOPE", "EXTERNAL_EXCLUDED") or obj.get("target_document_id") not in reg_by_id:
                err("REFERENCE_SCOPE", f"gold.objects[{i}]")
            elif not _span_error(public, obj["source_span"]):
                source = _span_text(public, obj["source_span"])
                if obj["target_clause_id"] not in source or (obj["reference_scope"] == "EXTERNAL_EXCLUDED") != ("External Standard" in source):
                    err("REFERENCE_SOURCE", f"gold.objects[{i}]")
                facts = _fact_values(gold, oid)
                expected_applicable = "FALSE" if obj["reference_scope"] == "EXTERNAL_EXCLUDED" else "TRUE"
                if facts.get("reference_applicable") != expected_applicable:
                    err("FACT_REFERENCE_MISMATCH", f"gold.objects[{i}].reference_applicable")
                if obj["reference_scope"] == "EXTERNAL_EXCLUDED":
                    expected_present = "UNKNOWN"
                else:
                    target = reg_by_id[obj["target_document_id"]]
                    target_doc = next((d for d in docs if d["document_id"] == obj["target_document_id"]), None)
                    found = target_doc is not None and obj["target_clause_id"] in {c["clause_id"] for c in target_doc["clauses"]}
                    expected_present = "TRUE" if found else ("FALSE" if target["coverage"] == "COMPLETE" else "UNKNOWN")
                if facts.get("target_present") != expected_present:
                    err("FACT_REFERENCE_MISMATCH", f"gold.objects[{i}].target_present")
        else:
            event = obj.get("event", {})
            fact_values = _fact_values(gold, oid)
            if not _span_error(public, obj.get("source_span")):
                source = _span_text(public, obj["source_span"])
                if fact_values.get("external") != ("TRUE" if "external recipient" in source else "FALSE"):
                    err("FACT_SOURCE_MISMATCH", f"gold.objects[{i}].external")
            status_doc = next((d for d in docs if d["document_id"] == "d3"), None)
            if status_doc:
                status_lines = [line for line in status_doc["text"].splitlines() if line.startswith(event.get("event_id", "<missing>") + ":")]
                if len(status_lines) != 1 or fact_values.get("restricted") != ("TRUE" if "was restricted" in status_lines[0] else "FALSE") or fact_values.get("public") != ("FALSE" if "and not lawfully public" in status_lines[0] else "TRUE"):
                    err("FACT_SOURCE_MISMATCH", f"gold.objects[{i}].status")
            for kind in ("approval", "order"):
                record = obj.get(f"{kind}_record", {})
                try:
                    expected = _record_matches(event, record)
                    facts = _fact_values(gold, oid)
                    for field, value in expected.items():
                        if facts.get(f"{kind}_{field}") != value:
                            err("FACT_RECORD_MISMATCH", f"gold.objects[{i}].{kind}_{field}")
                    coverage_value = reg_by_id[f"d{'4' if kind == 'approval' else '5'}"]["coverage"]
                    if facts.get(f"{kind}_registry_complete") != ("TRUE" if coverage_value == "COMPLETE" else "UNKNOWN"):
                        err("FACT_SCOPE_MISMATCH", f"gold.objects[{i}].{kind}_registry_complete")
                    record_doc = next(d for d in docs if d["document_id"] == ("d4" if kind == "approval" else "d5"))
                    record_lines = [line for line in record_doc["text"].splitlines() if line.startswith(event["event_id"] + f" {kind} record:")]
                    expected_fragments = [record[key] for key in ("subject", "scope", "event_id", "valid_from", "valid_until")]
                    expected_fragments.append("effective yes" if record["effective"] else "effective no")
                    if len(record_lines) != 1 or any(fragment not in record_lines[0] for fragment in expected_fragments):
                        err("RECORD_SOURCE_MISMATCH", f"gold.objects[{i}].{kind}_record")
                except (KeyError, ValueError, TypeError):
                    err("RECORD_INVALID", f"gold.objects[{i}].{kind}_record")
            if not _span_error(public, obj["source_span"]):
                source = _span_text(public, obj["source_span"])
                if any(str(event.get(key, "<missing>")) not in source for key in ("event_id", "subject", "scope", "sent_at")):
                    err("EVENT_SOURCE", f"gold.objects[{i}]")
    for i, decision in enumerate(decisions):
        if decision.get("state") not in STATES:
            err("STATE_INVALID", f"gold.decisions[{i}].state")
        if any(condition not in all_condition_ids for condition in decision.get("required_condition_ids", [])):
            err("CONDITION_REF", f"gold.decisions[{i}].required_condition_ids")
        for evidence_set in decision.get("acceptable_evidence_sets", []):
            if not evidence_set or any(condition not in all_condition_ids for condition in evidence_set):
                err("EVIDENCE_SET", f"gold.decisions[{i}].acceptable_evidence_sets")
        if decision.get("state") == "VIOLATION":
            scope_ids = decision.get("absence_scope_ids", [])
            expected_scopes = ["d1"] if public.get("task_type") == "reference_existence" else ["d4", "d5"]
            if sorted(scope_ids) != expected_scopes or any(reg_by_id[sid]["coverage"] != "COMPLETE" for sid in scope_ids):
                err("ABSENCE_SCOPE", f"gold.decisions[{i}].absence_scope_ids")
        if decision.get("object_id") in object_ids:
            obj = next(o for o in objects if o["object_id"] == decision["object_id"])
            try:
                if decision.get("state") != evaluate_object(public, gold, obj):
                    err("GOLD_MISMATCH", f"gold.decisions[{i}].state")
            except (KeyError, ValueError, TypeError):
                err("EVALUATION_INPUT", f"gold.objects[{obj['object_id']}]")

    index = assistance.get("object_index", [])
    if len(index) != len(objects) or {row["object_id"] for row in index} != set(object_ids) or len({row["object_id"] for row in index}) != len(index):
        err("INDEX_COVERAGE", "assistance.object_index")
    for row in index:
        obj = next((o for o in objects if o["object_id"] == row["object_id"]), None)
        if obj and row.get("source_span") != obj["source_span"]:
            err("INDEX_SPAN", f"assistance.object_index[{row['object_id']}]")
    evidence = assistance.get("evidence_index", [])
    if public.get("task_type") == "reference_existence" and evidence:
        err("T1_C_FORBIDDEN", "assistance.evidence_index")
    if public.get("task_type") == "conditional_obligation":
        if len(evidence) != len(objects) or {row["object_id"] for row in evidence} != set(object_ids):
            err("INDEX_COVERAGE", "assistance.evidence_index")
        for row in evidence:
            spans = row.get("candidate_spans", [])
            if len(spans) != 5 or any(_span_error(public, span) for span in spans):
                err("INDEX_SPAN", f"assistance.evidence_index[{row['object_id']}]")
            elif [span["document_id"] for span in spans] != ["d1", "d2", "d3", "d4", "d5"]:
                err("INDEX_ORDER", f"assistance.evidence_index[{row['object_id']}]")
    return errors


def render_public(public: dict) -> str:
    """Only explicitly model-visible fields are read here. No Gold argument exists."""
    lines = [
        f"DCC controlled material | case {public['case_id']}",
        f"Task: {public['task_type']} | language: {public['language']}",
        f"Audit instruction: {public['audit_instruction']}",
        "Rules (complete from batch 1):",
    ]
    lines += [f"{rule['rule_id']}: {rule['text']}" for rule in public["rules"]]
    lines += ["Material register:"]
    lines += [entry["text"] for entry in public["material_register"]]
    docs = {d["document_id"]: d["text"] for d in public["documents"]}
    for batch in public["batches"]:
        lines.append(f"BATCH {batch['batch_id']}")
        for span in batch["document_spans"]:
            lines.append(f"DOCUMENT {span['document_id']} [{span['start']}:{span['end']}]")
            lines.append(docs[span["document_id"]][span["start"]:span["end"]])
    lines.append("Output JSON only: {\"checks\":[{\"object_id\":null,\"source_span\":{\"document_id\":\"...\",\"start\":0,\"end\":1},\"state\":\"INSUFFICIENT_EVIDENCE\",\"evidence_spans\":[],\"brief_basis\":\"...\"}]}. A may use null object_id; B/C should use supplied IDs. Check every occurrence. States: " + ", ".join(STATES) + ".")
    return "\n".join(lines) + "\n"


def render_input(public: dict, assistance: dict | None, condition: str) -> str:
    if condition not in ("A", "B", "C"):
        raise ValueError("CONDITION_INVALID")
    if condition == "C" and public["task_type"] == "reference_existence":
        raise ValueError("T1_C_FORBIDDEN")
    base = render_public(public)
    if condition == "A":
        return base
    if assistance is None or assistance.get("case_id") != public["case_id"]:
        raise ValueError("ASSISTANCE_MISSING")
    index = [{"object_id": row["object_id"], "source_span": {k: row["source_span"][k] for k in ("document_id", "start", "end")}} for row in assistance["object_index"]]
    result = base + "Object occurrence index (locations only):\n" + json.dumps(index, ensure_ascii=False, separators=(",", ":")) + "\n"
    if condition == "C":
        evidence = [{"object_id": row["object_id"], "candidate_spans": [{k: span[k] for k in ("document_id", "start", "end")} for span in row["candidate_spans"]]} for row in assistance["evidence_index"]]
        result += "Candidate original-text spans (not answers):\n" + json.dumps(evidence, ensure_ascii=False, separators=(",", ":")) + "\n"
    return result


def classify_transition(pre_status: str, post_status: str) -> str:
    allowed = ("CORRECT", "INCORRECT", "ABSENT", "UNASSESSABLE")
    if pre_status not in allowed or post_status not in allowed:
        raise ValueError("MEMORY_STATUS_INVALID")
    if "UNASSESSABLE" in (pre_status, post_status):
        return "UNASSESSABLE"
    if pre_status == "CORRECT":
        return "RETAINED" if post_status == "CORRECT" else "RETENTION_LOSS"
    if post_status == "CORRECT":
        return "RECOVERY"
    if pre_status == "INCORRECT":
        return "PREEXISTING_ERROR"
    return "NEVER_ACQUIRED"


def assess_prediction(public: dict, gold: dict, prediction: dict) -> dict:
    """Occurrence matching for future outputs; never used to score Stage 1 models."""
    objects = {tuple(o["source_span"][k] for k in ("document_id", "start", "end")): o for o in gold["objects"]}
    decisions = {d["object_id"]: d["state"] for d in gold["decisions"]}
    seen = set()
    counts = {"matched": 0, "state_correct": 0, "state_wrong": 0, "missing": 0, "duplicate": 0, "conflict": 0, "format_error": 0}
    if not isinstance(prediction, dict) or not isinstance(prediction.get("checks"), list):
        counts["format_error"] = 1
        counts["missing"] = len(objects)
        return counts
    for check in prediction["checks"]:
        try:
            span = check["source_span"]
            key = tuple(span[k] for k in ("document_id", "start", "end"))
            if key in seen:
                counts["duplicate"] += 1
                continue
            seen.add(key)
            if key not in objects or check["state"] not in STATES or not isinstance(check.get("evidence_spans"), list) or not isinstance(check.get("brief_basis"), str):
                counts["format_error"] += 1
                continue
            obj = objects[key]
            if check.get("object_id") not in (None, obj["object_id"]):
                counts["conflict"] += 1
                continue
            if any(_span_error(public, evidence) for evidence in check["evidence_spans"]):
                counts["format_error"] += 1
                continue
            counts["matched"] += 1
            counts["state_correct" if check["state"] == decisions[obj["object_id"]] else "state_wrong"] += 1
        except (KeyError, TypeError):
            counts["format_error"] += 1
    counts["missing"] = len(objects) - counts["matched"]
    return counts
