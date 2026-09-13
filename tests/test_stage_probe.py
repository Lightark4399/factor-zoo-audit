import json
import sys

import pytest

from fza.stage_probe import StageProbe


def child(fail=False):
    if fail:
        raise ValueError("synthetic failure")
    return 460


def parent():
    return child()


def test_probe_preserves_value_and_records_nested_calls(tmp_path):
    path = tmp_path / "stages.jsonl"
    targets = {__name__: {"parent", "child"}}
    with StageProbe(path, targets):
        assert parent() == 460
        # Events must already be visible before closing the probe.
        assert '"event": "leave"' in path.read_text()
    events = [json.loads(line) for line in path.read_text().splitlines()]
    entries = [row for row in events if row["event"] == "enter"]
    assert entries[0]["parent"] is None
    assert entries[1]["parent"] == entries[0]["id"]
    assert events[-1]["completed"] is True
    assert events[-1]["open_spans"] == 0
    assert b"\r\n" not in path.read_bytes()
    assert sys.getprofile() is None


def test_failure_is_not_reported_as_success(tmp_path):
    path = tmp_path / "stages.jsonl"
    with pytest.raises(ValueError, match="synthetic failure"):
        with StageProbe(path, {__name__: {"child"}}):
            child(fail=True)
    end = json.loads(path.read_text().splitlines()[-1])
    assert end["completed"] is False
    assert end["exception_type"] == "ValueError"
    assert sys.getprofile() is None


def test_existing_artifact_is_not_overwritten(tmp_path):
    path = tmp_path / "stages.jsonl"
    path.write_text("original")
    with pytest.raises(FileExistsError):
        with StageProbe(path):
            pass
    assert path.read_text() == "original"
