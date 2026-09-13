"""Renderer invariants use constructed inputs, never stored financial outputs."""

import json

import pytest

from fza.demo import failure_record
from fza.render import validate_report_width, wrap_report_line
from fza.replay import legacy_presentation, replay


def test_long_reason_wraps_without_losing_words():
    reason = "  reasons: " + "qualification remains diagnostic " * 20
    rendered = "\n".join(wrap_report_line(reason))
    validate_report_width(rendered)
    assert rendered.split() == reason.split()
    assert all(line.startswith("    ") for line in rendered.splitlines()[1:])


def test_rendered_output_mutation_names_offending_line():
    with pytest.raises(ValueError, match="line 2: 85 columns exceeds 84"):
        validate_report_width("header\n" + "x" * 85)


def test_short_table_columns_are_not_reflowed():
    rows = [f"  {name:<14}{count:>12,}{0.5:>11.1%}"
            for name, count in [("a", 1), ("long_name", 999)]]
    rendered = [wrap_report_line(row)[0] for row in rows]
    assert rendered == rows
    assert [row.index("50.0%") for row in rendered] == [34, 34]


def test_unbroken_long_token_is_preserved():
    token = "x" * 240
    rendered = "\n".join(wrap_report_line("  " + token))
    validate_report_width(rendered)
    assert "".join(rendered.split()) == token


def test_failure_details_round_trip_as_data():
    class ExampleFailure(ValueError):
        detail = {"n_outside": 3, "reason": "constructed example"}
    failure = failure_record(ExampleFailure("first line\nsecond line"))
    assert json.loads(json.dumps(failure)) == failure
    assert failure["message"] == "first line\nsecond line"
    assert failure["detail"]["n_outside"] == 3
    assert failure["display_reasons"] == ["first line"]


def test_legacy_missing_presentation_fails_before_writing(tmp_path):
    bundle = tmp_path / "input.json"
    bundle.write_text('{"schema_version": 1}', encoding="utf-8")
    with pytest.raises(ValueError, match="requires companion text"):
        replay(bundle, tmp_path / "output")
    assert not (tmp_path / "output").exists()


def test_legacy_display_fields_are_explicitly_rounded():
    text = "\n".join([
        "  DATA: example.duckdb", "DATA QUALITY",
        f"  {'shares_out':<16}{75:>12,}{0.75:>11.1%}",
        "REGISTERED FACTORS",
        f"  {'example':<14}{'value':<14}{'yes':<14}{3:>14}{'undefined':>20}",
        "PUBLISHED-ANOMALY DENOMINATOR",
    ])
    supplement = legacy_presentation(text)
    assert supplement["price_coverage"] == [
        {"column": "shares_out", "non_null": 75, "coverage": 0.75},
    ]
    assert "display_rounding_only" in supplement["coverage_precision"]
    assert supplement["registered_factors"][0]["n_falsification_criteria"] == 3


def test_conflicting_sources_do_not_create_archive(tmp_path, monkeypatch):
    bundle = tmp_path / "input.json"
    bundle.write_text('{"schema_version": 1}', encoding="utf-8")
    text = tmp_path / "input.txt"
    text.write_text("observed original", encoding="utf-8")
    monkeypatch.setattr("fza.replay.legacy_presentation", lambda _: {})
    monkeypatch.setattr("fza.replay.render_report", lambda _, **kwargs: "conflicting output")
    with pytest.raises(ValueError, match="source conflict"):
        replay(bundle, tmp_path / "output", text)
    assert not (tmp_path / "output").exists()
