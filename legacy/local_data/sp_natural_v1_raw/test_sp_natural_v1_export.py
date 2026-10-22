import importlib.util
import json
from pathlib import Path


MODULE_PATH = Path(__file__).with_name("build_sp_natural_v1.py")
SPEC = importlib.util.spec_from_file_location("sp_natural_export", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(MODULE)


def event(line, position, timestamp="2026-01-01 00:00:00.000"):
    return {
        "absolute_path": r"F:\raw\sp.log",
        "start_line": line,
        "end_line": line,
        "event_position": position,
        "timestamp": timestamp,
        "content_sha256": f"event-{position}",
    }


def sample_trace():
    outline = "1. Overview\n- Explain the process."
    observation = "Research finding with a complete fact and unit: 42 percent."
    report = "# Report\n\nFirst complete paragraph.\n\nSecond complete paragraph."
    return {
        "run_id": "run-001",
        "query": "Explain the process.",
        "raw_log_provenance": {
            "absolute_path": r"F:\raw\sp.log",
            "request_start_line": 1,
            "request_end_line": 40,
        },
        "delegates": [
            {"source_agent": "central", "target_agent": "outline", "task_description": "Create outline", "timestamp": "2026-01-01 00:00:01.000", "raw_event": event(2, 2)},
            {"source_agent": "central", "target_agent": "researcher", "task_description": "Find facts", "timestamp": "2026-01-01 00:00:02.000", "raw_event": event(3, 3)},
            {"source_agent": "central", "target_agent": "reporter", "task_description": "Write report", "timestamp": "2026-01-01 00:00:03.000", "raw_event": event(4, 4)},
        ],
        "central_decisions": [],
        "outline": {
            "present": True,
            "full_output": outline,
            "content_sha256": MODULE.sha256_text(outline),
            "raw_event": event(5, 5),
        },
        "observations_field_seen": True,
        "observations": [{
            "text": observation,
            "content_sha256": MODULE.sha256_text(observation),
            "producer_event": event(6, 6),
        }],
        "memory_stack_summary": {
            "entries": [
                {"agent_type": "researcher", "content": "研究任务: Find facts", "result": {"observations": [observation]}},
                {"agent_type": "reporter", "content": "委派任务: Write report", "result": {"final_report": report}},
            ]
        },
        "final_report": {
            "present": True,
            "text": report,
            "content_sha256": MODULE.sha256_text(report),
            "raw_event": event(8, 8),
        },
        "natural_errors": [],
    }


def test_cleaning_is_nonsemantic():
    raw = "A\r\nB\x00  \n"
    assert MODULE.clean_text(raw) == "A\nB"


def test_report_uses_all_natural_paragraphs_without_prefix_truncation():
    text = "First paragraph.\n\nSecond paragraph.\n\nLast paragraph."
    spans = MODULE.paragraph_spans(text)
    assert [part for _, _, part in spans] == ["First paragraph.", "Second paragraph.", "Last paragraph."]
    assert all(text[start:end] == part for start, end, part in spans)


def test_trace_nodes_preserve_raw_text_and_explicit_memory_evidence():
    trace = sample_trace()
    nodes, warnings = MODULE.trace_to_nodes(trace)
    assert warnings == []
    assert len({node["node_id"] for node in nodes}) == len(nodes)
    assert [node["order"] for node in nodes] == list(range(len(nodes)))
    assert nodes[0]["step_type"] == "query"
    observation = next(node for node in nodes if node["step_type"] == "retrieval_observation")
    assert observation["text_raw"] == trace["observations"][0]["text"]
    assert observation["evidence_type"] == "explicit"
    reports = [node for node in nodes if node["step_type"] == "report_paragraph"]
    assert reports[-1]["text_raw"] == "Second complete paragraph."
    assert all(node["text_raw"] in trace["final_report"]["text"] for node in reports)


def test_empty_and_numeric_nodes_are_retained_and_flagged():
    trace = sample_trace()
    trace["observations"] = []
    nodes, _ = MODULE.trace_to_nodes(trace)
    empty = next(node for node in nodes if node["step_type"] == "retrieval_observation")
    assert empty["text_raw"] == ""
    assert "empty_text" in empty["quality_flags"]
    assert "explicit_empty_observation_state" in empty["quality_flags"]
    assert "not_evaluation_target" in MODULE.quality_flags("123", kind="report_paragraph")


def test_parent_integrity_and_no_citation_nodes():
    trace = sample_trace()
    nodes, _ = MODULE.trace_to_nodes(trace)
    checks = MODULE.validate(nodes, {"run-001": trace})
    assert checks["missing_parent_id_count"] == 0
    assert checks["citation_candidate_node_count"] == 0
    assert checks["raw_replay_failure_count"] == 0
    assert checks["passed"] is True


def test_serialized_rows_are_json_parseable():
    nodes, _ = MODULE.trace_to_nodes(sample_trace())
    for node in nodes:
        assert json.loads(json.dumps(node, ensure_ascii=False))["node_id"] == node["node_id"]


def test_pilot_selection_is_deterministic_and_structural():
    trace = sample_trace()
    cases = {}
    inventory = {}
    for index in range(25):
        copied = json.loads(json.dumps(trace))
        copied["run_id"] = f"run-{index:03d}"
        nodes, _ = MODULE.trace_to_nodes(copied)
        cases[copied["run_id"]] = nodes
        inventory[copied["run_id"]] = {
            "agent_order": ["outline", "researcher", "reporter"],
            "source_log": {"absolute_path": fr"F:\raw\sp-{index % 4}.log"},
        }
    first = MODULE.choose_pilot(cases, inventory)
    second = MODULE.choose_pilot(cases, inventory)
    assert first == second
    assert len(first) == 20
