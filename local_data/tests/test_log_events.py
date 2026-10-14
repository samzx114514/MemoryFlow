from pathlib import Path

from memoryflow.log_events import deduplicate_events, iter_log_events


def test_multiline_utf8_and_truncated_event(tmp_path: Path) -> None:
    path = tmp_path / "events.log"
    path.write_text(
        "orphan continuation\n"
        "2026-03-01 10:00:00.001 | INFO | first 中文\n"
        "continued English\n"
        "2026-03-01 10:00:01.002 | INFO | second\n",
        encoding="utf-8",
    )
    events = list(iter_log_events(path))
    assert len(events) == 3
    assert events[0].truncated is True
    assert events[1].text.endswith("continued English")
    assert "中文" in events[1].text


def test_stable_dedup_ignores_timestamp_and_memory_address(tmp_path: Path) -> None:
    path = tmp_path / "duplicates.log"
    path.write_text(
        "2026-03-01 10:00:00.001 | DEBUG | state:<Thing at 0xabc123>\n"
        "2026-03-01 10:00:01.001 | DEBUG | state:<Thing at 0xdef456>\n"
        "2026-03-01 10:00:02.001 | INFO | distinct\n",
        encoding="utf-8",
    )
    raw = list(iter_log_events(path))
    assert len(deduplicate_events(raw)) == 2


def test_unterminated_multipart_is_truncated(tmp_path: Path) -> None:
    path = tmp_path / "parts.log"
    path.write_text(
        "2026-03-01 10:00:00.001 | INFO | llm_content|part_1/2|payload\n",
        encoding="utf-8",
    )
    event = list(iter_log_events(path))[0]
    assert event.multipart == (1, 2)
    assert event.truncated is True

