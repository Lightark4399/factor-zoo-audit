import io
import json
import runpy
from pathlib import Path

import pytest

Timings = runpy.run_path(
    str(Path(__file__).resolve().parents[1] / "scripts" / "real_stage_worker.py")
)["Timings"]


def test_nested_stage_values_and_parents():
    stream = io.StringIO()
    timing = Timings(stream)
    child = timing.wrap(lambda x: x + 1, "child")
    parent = timing.wrap(lambda x: child(x) * 2, "parent")
    assert parent(3) == 8
    events = [json.loads(line) for line in stream.getvalue().splitlines()]
    assert events[0]["parent"] is None
    assert events[1]["parent"] == events[0]["id"]
    assert events[-1]["completed"] is True
    assert timing.stack == []


def test_exception_is_preserved_and_stage_closed():
    timing = Timings(io.StringIO())

    def fail():
        raise ValueError("known failure")

    with pytest.raises(ValueError, match="known failure"):
        timing.wrap(fail, "failure")()
    assert timing.stack == []
    event = json.loads(timing.stream.getvalue().splitlines()[-1])
    assert event["completed"] is False


def test_ttm_count_does_not_replace_function():
    timing = Timings(io.StringIO())
    wrapped = timing.wrap(sum, "library._ttm_value")
    assert wrapped([100, 110, 120, 130]) == 460
    assert wrapped([1, 2]) == 3
    assert timing.ttm_calls == 2
    assert timing.ttm_input_rows == [4, 2]
