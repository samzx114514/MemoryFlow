from pathlib import Path

from memoryflow.factstruct_parser import parse_factstruct_files, parse_reference_map


def test_reference_map_and_observation_parse() -> None:
    text = (
        "before reference_map:{'1': {'title': '标题', 'url': 'https://x', "
        "'content': '正文', 'observation': {'topic': '主题', 'points': ['点一', '点二']}}}"
    )
    result, warnings = parse_reference_map(text)
    assert warnings == []
    assert result["1"]["observation"]["points"] == ["点一", "点二"]


def test_run_recovery_multipart_dedup_and_success_after_error(tmp_path: Path) -> None:
    path = tmp_path / "fact.log"
    path.write_text(
        "2026-03-01 10:00:00.001 | INFO | request param details: messages=[ChatMessage(role='user', content='问题')] thread_id='__default__' graph_format='FactStruct'\n"
        "2026-03-01 10:00:01.001 | DEBUG | Event data: ({}, {'thread_id': '11111111-1111-1111-1111-111111111111'})\n"
        "2026-03-01 10:00:02.001 | ERROR | search failed once\n"
        "2026-03-01 10:00:03.001 | INFO | llm_content|part_1/2|before reference_map:{'1': {'title': 'T', 'url': 'https://x',\n"
        "2026-03-01 10:00:03.002 | INFO | llm_content|part_2/2|'content': 'C', 'observation': {'topic': 'Topic', 'points': ['P']}}}\n"
        "2026-03-01 10:00:04.001 | DEBUG | state:<Thing at 0xabc>\n"
        "2026-03-01 10:00:05.001 | DEBUG | state:<Thing at 0xdef>\n"
        "2026-03-01 10:00:06.001 | INFO | Event data: {'reporter': {'final_report': 'Sentence [1].'}}\n",
        encoding="utf-8",
    )
    runs = list(parse_factstruct_files([path]))
    assert len(runs) == 1
    run = runs[0]
    assert run.run_id == "11111111-1111-1111-1111-111111111111"
    assert run.query == "问题"
    assert run.final_report == "Sentence [1]."
    assert run.sources["1"]["observation"]["topic"] == "Topic"
    assert run.raw_event_count > run.deduplicated_event_count
    assert any("error" in warning.lower() for warning in run.parser_warnings)


def test_fallback_run_id_is_deterministic(tmp_path: Path) -> None:
    path = tmp_path / "fallback.log"
    path.write_text(
        "2026-03-01 10:00:00.001 | INFO | request param details: messages=[ChatMessage(role='user', content=' Q  ')] graph_format='FactStruct'\n"
        "2026-03-01 10:00:01.001 | INFO | before reference_map:{'1': {'title': 'T', 'content': 'C'}}\n"
        "2026-03-01 10:00:02.001 | INFO | Event data: {'reporter': {'final_report': 'A [1].'}}\n",
        encoding="utf-8",
    )
    run = list(parse_factstruct_files([path]))[0]
    assert len(run.run_id) == 64

