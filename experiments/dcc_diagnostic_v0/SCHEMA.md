# DCC diagnostic v0.1 schema

This is a controlled, English-language calibration package. It contains no real contract, model output, or legal advice. All offsets are Python Unicode string indices, half-open `[start,end)`. A span is `{document_id,start,end}` and refers to the exact `documents[].text` string. Neither byte offsets nor normalized text are used.

## Three separate views

| View | File | Model visibility |
|---|---|---|
| `PublicCase` | `data/calibration_public.jsonl` | Full rules, audit instruction, uniformly formatted material register, and provided document text in three ordered batches. |
| `GoldCase` | `data/calibration_gold.jsonl` | Evaluator and human reviewer only. Never passed to `render_input`. |
| `AssistanceCase` | `data/calibration_assistance.jsonl` | B sees `object_index`; C (T2 only) also sees `evidence_index`. |

Every file has eight JSON objects in the same order and uses the same opaque `case_id`. `schema_version` is `dcc-diagnostic-v0.1`, `language` is `en`, and `task_type` is `reference_existence` or `conditional_obligation`. IDs are SHA256-derived from seed `20261015`, then truncated; they do not contain label words. `family_id`, `variant_id`, and `focal_object_id` exist only in Gold.

### PublicCase

Required fields: `schema_version`, `case_id`, `task_type`, `language`, `audit_instruction`, `rules:[{rule_id,text}]`, `material_register:[{document_id,provided,coverage,text}]`, `documents:[{document_id,text,clauses:[{clause_id,start,end}]}]`, and `batches:[{batch_id,document_spans:[span]}]`. `coverage` is `COMPLETE`, `PARTIAL`, or `UNAVAILABLE`; the visible `text` for every register row has the same canonical shape, `dN: provided/not provided; coverage VALUE.`. `coverage` describes the provided source's completeness, not a model search outcome. An unavailable document has no hidden body in PublicCase. `batches` enumerate provided documents; the complete rule text is also shown before batch 1 and is never revised later.

The A renderer reads an explicit whitelist of these fields and emits document text, not the internal batch JSON or any unknown extra fields. B/C append their allowed indices after exactly the same public body and output contract. Preview files add a `DRY_RUN_NOT_SENT` header; it is a local preview marker.

### GoldCase

Required fields: `case_id`, `family_id`, `variant_id`, `focal_object_id`, `objects`, `facts`, `dependencies`, `decisions`, `ambiguity`, and `review`. Each `objects[]` has `object_id`, `object_kind`, `source_span`, and `rule_ids`. T1 objects additionally have `reference_scope`, `target_document_id`, and `target_clause_id`. T2 objects additionally hold structured `event`, `approval_record`, and `order_record` facts. Those structured values are checked against the original public lines before a Gold decision is accepted.

Each `facts[]` item has `fact_id`, `object_id`, `proposition`, a `TRUE`/`FALSE`/`UNKNOWN` `value`, `evidence_span_sets` (a list of alternative complete span combinations), and `scope_basis`. Every span must point to provided text. T2 atomic propositions are `external`, `restricted`, `public`, and for each `approval`/`order`: `subject_match`, `scope_match`, `event_match`, `time_match`, `effective`, `registry_complete`. A match is a factual comparison, not a verdict. `registry_complete=UNKNOWN` means the relevant public register is partial; an invalid listed candidate then cannot prove that no other valid record exists. T1 uses `reference_applicable` and `target_present`. An in-scope target found in a partial file is still present; an absent target in that partial file is unknown.

`dependencies:[{dependency_id,premise_ids,operator,conclusion_id}]` records the fixed derivation: `NOT`, `AND`, `OR`, `REGISTER_CLOSURE`, or `REFERENCE_LOOKUP`. There is no general rule engine. `REGISTER_CLOSURE` means a known valid candidate yields TRUE regardless of register completeness; an invalid candidate yields FALSE only for a complete register, otherwise UNKNOWN. T2 sends are checked at UTC times with both interval endpoints included. The deterministic `evaluate_object` function computes the state independently of `decisions[].state`, and validation rejects disagreement.

Every `decisions[]` item has `object_id`, `state`, `required_condition_ids`, `acceptable_evidence_sets` (alternative lists of fact/dependency IDs), `absence_scope_ids`, and `unknown_condition_ids`. `absence_scope_ids` refers to public material-register rows that must be COMPLETE before a missing-target or missing-valid-record VIOLATION is allowed. All four states are `COMPLIANT`, `VIOLATION`, `NOT_APPLICABLE`, and `INSUFFICIENT_EVIDENCE`; ambiguity is separate and rejects a case from the main set. `review.independent_human_status` remains `NOT_REVIEWED` until a genuinely independent human review. `executor_checked=true` only records this offline implementation check.

### AssistanceCase

Required fields: `case_id`, `object_index:[{object_id,source_span}]`, `evidence_index:[{object_id,candidate_spans:[span]}]`. B receives all object occurrences and no verdict or focal flag. T1 has no evidence index and C is explicitly rejected as `T1_C_FORBIDDEN`. T2 C receives, for every object, five original-text spans in the same category/order: d1 rule, d2 sending occurrence, d3 material status, d4 approval record, d5 order record. Invalid, valid, and alternative records remain in the public body. Candidate count and category order do not encode the label. `render_input` serializes only the whitelisted index keys, so extra fields are ignored. These are Oracle-linked *locations* for diagnosis, not a deployable retrieval method.

## T1 and T2 state semantics

T1 checks each explicit reference in d1. d1 internal and d2 annex references are in scope; External Standard Q-7 (d3) is excluded. Complete target document plus missing exact clause gives VIOLATION. A provided but partial target permits COMPLIANT when the clause is visible, and INSUFFICIENT_EVIDENCE when it is not. Repeated numbering, unresolved target identity, and conflicting scope statements invalidate a calibration input rather than creating a fifth label.

T2 uses the exact three-valued rule in `core.py`: `applicable = external AND restricted AND NOT public`; `satisfied = valid_approval OR valid_order`. Any FALSE dominates AND; any TRUE dominates OR. `applicable=FALSE` gives NOT_APPLICABLE; `applicable=UNKNOWN` gives INSUFFICIENT_EVIDENCE; for applicable TRUE, satisfied TRUE/FALSE/UNKNOWN maps to COMPLIANT/VIOLATION/INSUFFICIENT_EVIDENCE. Written approvals and court orders both require matching subject, scope, sending event, effective status, and `valid_from <= sent_at <= valid_until` in UTC. The public register must be complete before both invalid listed candidates imply absence. A known valid order can satisfy the obligation despite an invalid approval, and vice versa.

## Future output and memory audit contracts

All conditions would use `{"checks":[{"object_id":null,"source_span":{"document_id":"d1","start":0,"end":12},"state":"INSUFFICIENT_EVIDENCE","evidence_spans":[],"brief_basis":"..."}]}`. A may leave `object_id` null. The evaluator matches exact occurrence span first, then checks any supplied ID; duplicate predictions receive no extra credit. Conflict, missing object, format failure, and wrong state remain separate counts. No model predictions exist in Stage 1.

`tests/fixtures/memory_audit.jsonl` contains only `record_kind=TEST_FIXTURE` and fields `run_id`, `case_id`, `object_id`, `condition_id`, `checkpoint_id`, `visible_input_ids`, `visible_input_hash`, `pre_record`, `compressed_record`, `pre_status`, `post_status`, `judgment_before`, `judgment_after`, `assessment_basis_spans`, `assessor_type`, and `review_status`. Allowed pre/post statuses are CORRECT, INCORRECT, ABSENT, UNASSESSABLE. `classify_transition` returns RETENTION_LOSS, PREEXISTING_ERROR, NEVER_ACQUIRED, RETAINED, RECOVERY, or UNASSESSABLE. CORRECT→ABSENT/INCORRECT is observed retention loss, **not** automatically a causal memory failure. CORRECT→CORRECT with a wrong final judgment is retained information and a possible later use/judgment error. All records remain in the sample inventory; initial errors, initial absence, and unassessable items are outside the correct-content-loss denominator.
