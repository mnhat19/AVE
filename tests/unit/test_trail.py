import json

import pytest

from ave.models.trail import TrailEntry


def test_trail_entry_validation() -> None:
    with pytest.raises(ValueError):
        TrailEntry(session_id="s1", reasoning_summary="x" * 501)
    with pytest.raises(ValueError):
        TrailEntry(session_id="s1", confidence=1.5)


def test_trail_entry_round_trip() -> None:
    entry = TrailEntry(
        session_id="s1",
        agent_id="ingestion",
        action_type="FILE_RECEIVED",
        input_hash="abc",
        output_hash="def",
        reasoning_summary="ok",
    )
    line = entry.to_jsonl_line()
    assert "\n" not in line
    parsed = TrailEntry.from_jsonl_line(line)
    assert parsed.session_id == entry.session_id
    assert parsed.agent_id == entry.agent_id
    assert parsed.timestamp.endswith("+00:00")


def test_trail_entry_json_is_valid() -> None:
    entry = TrailEntry(session_id="s2", reasoning_summary="ok")
    json.loads(entry.to_jsonl_line())
