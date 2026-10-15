"""Eight hand-authored calibration variants; creates offsets without inventing text."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

SEED = 20261015
HERE = Path(__file__).resolve().parent


def opaque(*parts: str) -> str:
    raw = ":".join([str(SEED), *parts]).encode("utf-8")
    return "x" + hashlib.sha256(raw).hexdigest()[:12]


def document(document_id: str, lines: list[tuple[str, str]]) -> tuple[dict, dict[str, dict]]:
    text = ""
    spans = {}
    clauses = []
    for name, line in lines:
        start = len(text)
        text += line + "\n"
        end = len(text)
        spans[name] = {"document_id": document_id, "start": start, "end": end}
        if ":" in line and line.split(":", 1)[0] in ("1.1", "2.1", "3.1", "4.2", "A.3", "G.1", "R.1", "R.2", "R.3"):
            clauses.append({"clause_id": line.split(":", 1)[0], "start": start, "end": end})
    return {"document_id": document_id, "text": text, "clauses": clauses}, spans


def register(document_id: str, coverage: str) -> dict:
    provided = coverage != "UNAVAILABLE"
    return {"document_id": document_id, "provided": provided, "coverage": coverage,
            "text": f"{document_id}: {'provided' if provided else 'not provided'}; coverage {coverage}."}


def fact(object_id: str, proposition: str, value: str, spans: list[dict], scope_basis=None) -> dict:
    return {"fact_id": f"{object_id}:{proposition}", "object_id": object_id, "proposition": proposition,
            "value": value, "evidence_span_sets": [spans], "scope_basis": scope_basis}


def t1(variant: int):
    cid = opaque("T1", f"v{variant}")
    focus = "R1: For retention, see " + ("External Standard Q-7 Clause 4.2." if variant == 3 else "Section 4.2.")
    main_lines = [
        ("definition", "1.1: Definitions govern this agreement."),
        ("delivery", "2.1: Delivery shall occur by noon."),
        ("use", "3.1: The following four directions contain the reviewable references."),
        ("r2", "R2: For delivery, see Section 2.1."),
        ("r3", "R3: For schedule, see Annex A Clause A.3."),
        ("r4", "R4: For definitions, see Section 1.1."),
        ("r1", focus),
    ]
    if variant == 1:
        main_lines.append(("retention", "4.2: Retain audit records for thirty days."))
    main, ms = document("d1", main_lines)
    annex, ax = document("d2", [("schedule", "A.3: The schedule is attached and effective." )])
    guide, gx = document("d4", [("guide", "G.1: Clause labels identify exact positions; no other clause is incorporated here.")])
    docs = [main, annex, guide]
    material = [register("d1", "PARTIAL" if variant == 4 else "COMPLETE"), register("d2", "COMPLETE"), register("d3", "UNAVAILABLE"), register("d4", "COMPLETE")]
    rules = [{"rule_id": "R-REF", "text": "Check each explicit internal clause reference in d1 and the in-scope annex d2. When the target document is fully provided, a cited clause exists only if that exact clause label appears there. External Standard Q-7 in d3 is excluded from this rule. If an in-scope target's provided coverage is partial or unavailable, do not infer absence."}]
    public = {"schema_version": "dcc-diagnostic-v0.1", "case_id": cid, "task_type": "reference_existence", "language": "en",
              "audit_instruction": "Check every explicit clause-reference occurrence in d1 against the supplied scope and material register.",
              "rules": rules, "material_register": material, "documents": docs,
              "batches": [{"batch_id": "b1", "document_spans": [{"document_id": "d1", "start": 0, "end": len(main["text"])}]},
                          {"batch_id": "b2", "document_spans": [{"document_id": "d2", "start": 0, "end": len(annex["text"])}]},
                          {"batch_id": "b3", "document_spans": [{"document_id": "d4", "start": 0, "end": len(guide["text"])}]}]}
    descriptions = [
        ("r1", "d3" if variant == 3 else "d1", "4.2", "EXTERNAL_EXCLUDED" if variant == 3 else "IN_SCOPE"),
        ("r2", "d1", "2.1", "IN_SCOPE"),
        ("r3", "d2", "A.3", "IN_SCOPE"),
        ("r4", "d1", "1.1", "IN_SCOPE"),
    ]
    objects, facts, dependencies, decisions, index = [], [], [], [], []
    for slot, target_doc, clause, scope in descriptions:
        oid = opaque("T1", slot)
        source = ms[slot]
        obj = {"object_id": oid, "object_kind": "clause_reference", "source_span": source,
               "rule_ids": ["R-REF"], "reference_scope": scope, "target_document_id": target_doc, "target_clause_id": clause}
        objects.append(obj)
        index.append({"object_id": oid, "source_span": source})
        if scope == "EXTERNAL_EXCLUDED":
            state, applicable, present = "NOT_APPLICABLE", "FALSE", "UNKNOWN"
            target_evidence = source
            basis = "d3"
        elif target_doc == "d1" and clause == "4.2" and variant == 4:
            state, applicable, present = "INSUFFICIENT_EVIDENCE", "TRUE", "UNKNOWN"
            target_evidence = source
            basis = "d1"
        elif target_doc == "d1" and clause == "4.2" and variant == 2:
            state, applicable, present = "VIOLATION", "TRUE", "FALSE"
            target_evidence = source
            basis = "d1"
        else:
            state, applicable, present = "COMPLIANT", "TRUE", "TRUE"
            target_evidence = ms.get("retention") if clause == "4.2" else (ms["delivery"] if clause == "2.1" else (ax["schedule"] if clause == "A.3" else ms["definition"]))
            basis = target_doc
        facts.extend([fact(oid, "reference_applicable", applicable, [source], basis),
                      fact(oid, "target_present", present, [target_evidence], basis)])
        dependencies.append({"dependency_id": oid + ":ref", "premise_ids": [oid + ":reference_applicable", oid + ":target_present"],
                             "operator": "REFERENCE_LOOKUP", "conclusion_id": oid + ":state"})
        decisions.append({"object_id": oid, "state": state, "required_condition_ids": [oid + ":reference_applicable", oid + ":target_present"],
                          "acceptable_evidence_sets": [[oid + ":reference_applicable"]] if scope == "EXTERNAL_EXCLUDED" else [[oid + ":reference_applicable", oid + ":target_present"]],
                          "absence_scope_ids": ["d1"] if state == "VIOLATION" else [],
                          "unknown_condition_ids": [oid + ":target_present"] if present == "UNKNOWN" else []})
    gold = {"case_id": cid, "family_id": "T1", "variant_id": f"v{variant}", "focal_object_id": opaque("T1", "r1"),
            "objects": objects, "facts": facts, "dependencies": dependencies, "decisions": decisions,
            "ambiguity": {"flag": False, "reasons": []},
            "review": {"executor_checked": True, "independent_human_status": "NOT_REVIEWED", "reviewer_note": "Awaiting independent clause and scope review."}}
    assistance = {"case_id": cid, "object_index": index, "evidence_index": []}
    return public, gold, assistance


EVENTS = [
    {"event_id": "TX-01", "subject": "Orion Labs", "scope": "Dataset Cedar", "sent_at": "2026-04-10T10:00:00Z", "recipient": "external recipient Northbay"},
    {"event_id": "TX-02", "subject": "Cobalt Works", "scope": "Dataset Hazel", "sent_at": "2026-04-11T09:00:00Z", "recipient": "external recipient Bayfield"},
    {"event_id": "TX-03", "subject": "Elm Institute", "scope": "Dataset Maple", "sent_at": "2026-04-12T12:00:00Z", "recipient": "external recipient Shoreline"},
    {"event_id": "TX-04", "subject": "Vale Group", "scope": "Dataset Birch", "sent_at": "2026-04-13T08:00:00Z", "recipient": "internal archive team"},
]


def record(event: dict, kind: str, *, scope=None, start=None, end=None, effective=False):
    return {"subject": event["subject"], "scope": scope or event["scope"], "event_id": event["event_id"],
            "valid_from": start or "2026-04-01T00:00:00Z", "valid_until": end or "2026-04-30T23:59:59Z", "effective": effective}


def t2(variant: int):
    cid = opaque("T2", f"v{variant}")
    e1, e2, e3, e4 = EVENTS
    approvals = [
        record(e1, "approval", scope="Dataset Pine", end="2026-04-09T23:59:59Z" if variant == 2 else None, effective=True),
        record(e2, "approval", effective=True),
        record(e3, "approval", scope="Dataset Fir", effective=False),
        record(e4, "approval", scope="Dataset Pine", effective=False),
    ]
    orders = [
        record(e1, "order", scope="Dataset Pine" if variant != 1 else None, end="2026-04-09T23:59:59Z" if variant == 2 else None, effective=variant == 1),
        record(e2, "order", effective=True),
        record(e3, "order", effective=True),
        record(e4, "order", scope="Dataset Pine", effective=False),
    ]
    rule_lines = [
        ("rule1", "R.1: A sending obligation applies when material is sent to an external recipient, is restricted, and was not lawfully public before sending."),
        ("rule2", "R.2: If applicable, sending requires either prior effective written approval or a valid court order for this same sending."),
        ("rule3", "R.3: Approval and order each require matching subject, data scope and sending event, effective status, and sending time inside the UTC validity interval including both endpoints. An incomplete register cannot establish absence; a known valid alternative still suffices."),
    ]
    rules_doc, rs = document("d1", rule_lines)
    dispatch_lines = [(e["event_id"], f"{e['event_id']}: {e['subject']} sent {e['scope']} to {e['recipient']} on {e['sent_at']}.") for e in EVENTS]
    dispatch, ds = document("d2", dispatch_lines)
    status_lines = []
    for e in EVENTS:
        public_status = "lawfully public before sending" if e["event_id"] == "TX-01" and variant == 3 else "not lawfully public before sending"
        status_lines.append((e["event_id"], f"{e['event_id']}: {e['scope']} was restricted and {public_status}."))
    status, ss = document("d3", status_lines)

    def register_lines(kind, entries, complete):
        lines = [("header", f"{kind.title()} register: {'complete for all listed TX events' if complete else 'partial extract for TX-01; additional entries may exist'}." )]
        for event, item in zip(EVENTS, entries):
            lines.append((event["event_id"], f"{event['event_id']} {kind} record: subject {item['subject']}; scope {item['scope']}; event {item['event_id']}; valid {item['valid_from']} through {item['valid_until']} inclusive UTC; effective {'yes' if item['effective'] else 'no'}."))
        return lines

    approvals_doc, aps = document("d4", register_lines("approval", approvals, True))
    orders_doc, ors = document("d5", register_lines("order", orders, variant != 4))
    docs = [rules_doc, dispatch, status, approvals_doc, orders_doc]
    material = [register(f"d{i}", "PARTIAL" if i == 5 and variant == 4 else "COMPLETE") for i in range(1, 6)]
    rules = [
        {"rule_id": "R.1", "text": rule_lines[0][1].split(": ", 1)[1]},
        {"rule_id": "R.2", "text": rule_lines[1][1].split(": ", 1)[1]},
        {"rule_id": "R.3", "text": rule_lines[2][1].split(": ", 1)[1]},
    ]
    public = {"schema_version": "dcc-diagnostic-v0.1", "case_id": cid, "task_type": "conditional_obligation", "language": "en",
              "audit_instruction": "Check each of the four sending events under R.1–R.3. Treat missing entries in a partial register as unknown, not absent.",
              "rules": rules, "material_register": material, "documents": docs,
              "batches": [
                  {"batch_id": "b1", "document_spans": [{"document_id": d["document_id"], "start": 0, "end": len(d["text"])} for d in (rules_doc, dispatch)]},
                  {"batch_id": "b2", "document_spans": [{"document_id": "d3", "start": 0, "end": len(status["text"])}]},
                  {"batch_id": "b3", "document_spans": [{"document_id": d["document_id"], "start": 0, "end": len(d["text"])} for d in (approvals_doc, orders_doc)]},
              ]}
    objects, facts, dependencies, decisions, object_index, evidence_index = [], [], [], [], [], []
    for n, event in enumerate(EVENTS):
        oid = opaque("T2", event["event_id"])
        event_id = event["event_id"]
        source = ds[event_id]
        obj = {"object_id": oid, "object_kind": "sending_event", "source_span": source, "rule_ids": ["R.1", "R.2", "R.3"],
               "event": {k: event[k] for k in ("event_id", "subject", "scope", "sent_at")},
               "approval_record": approvals[n], "order_record": orders[n]}
        objects.append(obj)
        object_index.append({"object_id": oid, "source_span": source})
        evidence_index.append({"object_id": oid, "candidate_spans": [rs["rule3"], source, ss[event_id], aps[event_id], ors[event_id]]})
        basic = [("external", "FALSE" if n == 3 else "TRUE", [source]),
                 ("restricted", "TRUE", [ss[event_id]]),
                 ("public", "TRUE" if n == 0 and variant == 3 else "FALSE", [ss[event_id]])]
        for name, value, evidence in basic:
            facts.append(fact(oid, name, value, evidence, "d2" if name == "external" else "d3"))
        valid_kinds = {}
        for kind, item, span, register_doc in (("approval", approvals[n], aps[event_id], "d4"), ("order", orders[n], ors[event_id], "d5")):
            matches = {"subject_match": event["subject"] == item["subject"], "scope_match": event["scope"] == item["scope"],
                       "event_match": event_id == item["event_id"],
                       "time_match": item["valid_from"] <= event["sent_at"] <= item["valid_until"],
                       "effective": item["effective"]}
            for name, value in matches.items():
                facts.append(fact(oid, f"{kind}_{name}", "TRUE" if value else "FALSE", [source, span], register_doc))
            complete = not (kind == "order" and variant == 4)
            facts.append(fact(oid, f"{kind}_registry_complete", "TRUE" if complete else "UNKNOWN", [aps["header"] if kind == "approval" else ors["header"]], register_doc))
            valid_kinds[kind] = all(matches.values())
            dependencies.append({"dependency_id": oid + f":{kind}_candidate", "premise_ids": [oid + f":{kind}_{name}" for name in matches],
                                 "operator": "AND", "conclusion_id": oid + f":{kind}_candidate"})
            dependencies.append({"dependency_id": oid + f":{kind}_closed", "premise_ids": [oid + f":{kind}_candidate", oid + f":{kind}_registry_complete"],
                                 "operator": "REGISTER_CLOSURE", "conclusion_id": oid + f":{kind}_valid"})
        dependencies.extend([
            {"dependency_id": oid + ":not_public", "premise_ids": [oid + ":public"], "operator": "NOT", "conclusion_id": oid + ":not_public"},
            {"dependency_id": oid + ":applicable", "premise_ids": [oid + ":external", oid + ":restricted", oid + ":not_public"], "operator": "AND", "conclusion_id": oid + ":applicable"},
            {"dependency_id": oid + ":satisfied", "premise_ids": [oid + ":approval_valid", oid + ":order_valid"], "operator": "OR", "conclusion_id": oid + ":satisfied"},
        ])
        state = ("COMPLIANT" if variant == 1 else "VIOLATION" if variant == 2 else "NOT_APPLICABLE" if variant == 3 else "INSUFFICIENT_EVIDENCE") if n == 0 else ("NOT_APPLICABLE" if n == 3 else "COMPLIANT")
        if state == "NOT_APPLICABLE":
            sufficient = [[oid + (":public" if n == 0 else ":external")]]
        elif state == "COMPLIANT":
            sufficient = [[oid + ":external", oid + ":restricted", oid + ":public"] + [oid + f":{kind}_{field}" for field in ("subject_match", "scope_match", "event_match", "time_match", "effective")] for kind in ("approval", "order") if valid_kinds[kind]]
        elif state == "VIOLATION":
            sufficient = [[oid + ":external", oid + ":restricted", oid + ":public", oid + ":approval_valid", oid + ":order_valid"]]
        else:
            sufficient = [[oid + ":order_registry_complete"]]
        decisions.append({"object_id": oid, "state": state, "required_condition_ids": [oid + ":applicable", oid + ":satisfied"],
                          "acceptable_evidence_sets": sufficient, "absence_scope_ids": ["d4", "d5"] if state == "VIOLATION" else [],
                          "unknown_condition_ids": [oid + ":order_registry_complete"] if n == 0 and variant == 4 else []})
    gold = {"case_id": cid, "family_id": "T2", "variant_id": f"v{variant}", "focal_object_id": opaque("T2", "TX-01"),
            "objects": objects, "facts": facts, "dependencies": dependencies, "decisions": decisions,
            "ambiguity": {"flag": False, "reasons": []},
            "review": {"executor_checked": True, "independent_human_status": "NOT_REVIEWED", "reviewer_note": "Awaiting independent semantic and object-coverage review."}}
    assistance = {"case_id": cid, "object_index": object_index, "evidence_index": evidence_index}
    return public, gold, assistance


def write():
    cases = [t1(v) for v in range(1, 5)] + [t2(v) for v in range(1, 5)]
    for offset, name in enumerate(("calibration_public.jsonl", "calibration_gold.jsonl", "calibration_assistance.jsonl")):
        path = HERE / name
        if path.exists():
            raise FileExistsError(path)
        path.write_text("".join(json.dumps(case[offset], ensure_ascii=False, sort_keys=True) + "\n" for case in cases), encoding="utf-8")


if __name__ == "__main__":
    write()
