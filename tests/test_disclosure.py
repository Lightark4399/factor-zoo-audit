"""Explicit histories distinguish repeat publication from numerical changes."""

import importlib.util
import json
from pathlib import Path

import duckdb
import pandas as pd
import pytest

from fza.demo import describe_data
from fza.disclosure import disclosure_summary, uncomparable_reason_counts
from fza.render import disclosure_lines
from fza.store import Store


def add(store, tag, values, dates=None, units=None, types=None):
    dates = dates or [f"2021-0{i + 2}-01" for i in range(len(values))]
    units = units or ["USD"] * len(values)
    types = types or ["instant"] * len(values)
    rows = zip(values, dates, units, types, strict=True)
    for i, (value, date, unit, fact_type) in enumerate(rows):
        store.con.execute(
            "INSERT INTO fundamentals "
            "(cik, tag, period_start, period_end, filed, value, unit, form, accession, "
            "fact_type) VALUES ('1', ?, '2020-12-31', '2020-12-31', ?, ?, ?, "
            "'10-K', ?, ?)",
            [tag, date, value, unit, str(i), fact_type],
        )


def test_explicit_disclosure_partition():
    with Store() as store:
        add(store, "single", [10])
        add(store, "unchanged", [10, 10])
        add(store, "changed", [10, 12])
        add(store, "reverted", [10, 12, 10])
        add(store, "missing", [10, None])
        add(store, "units", [10, 12], units=["USD", "EUR"])
        add(store, "conflict", [10, 12, 14],
            dates=["2021-02-01", "2021-02-01", "2021-03-01"])
        add(store, "same_day", [10, 10], dates=["2021-02-01"] * 2)
        result = disclosure_summary(store.con)
    assert result["fact_keys"] == 8
    assert result["multiple_filing_date_keys"] == 6
    assert result["changed_comparable_keys"] == 2
    assert result["unchanged_comparable_keys"] == 1
    assert result["uncomparable_repeated_keys"] == 3
    assert result["multiple_filing_date_share_of_fact_keys"] == 6 / 8
    assert result["changed_share_of_comparable_repeated_keys"] == 2 / 3


def test_empty_disclosures_are_not_zero_rates():
    with Store() as store:
        result = disclosure_summary(store.con)
    assert result["fact_keys"] == 0
    assert result["multiple_filing_date_share_of_fact_keys"] is None
    assert result["changed_share_of_comparable_repeated_keys"] is None


def test_demo_summary_and_render_use_new_contract():
    with Store() as store:
        add(store, "unchanged", [10, 10])
        info = describe_data(store, "fixture")
    assert info["restatements"] == 1  # unchanged legacy semantics
    assert info["restatement_rate"] == .5  # keys / rows, not a revision rate
    assert info["disclosure_summary"]["changed_comparable_keys"] == 0
    text = "\n".join(disclosure_lines(info))
    assert "comparable repeated keys, unchanged: 1" in text
    assert "50.0%" not in text


def test_legacy_render_does_not_invent_changed_counts():
    lines = disclosure_lines({"restatements": 2, "restatement_rate": .5})
    assert "50.0%" not in "\n".join(lines)
    assert "unavailable" in "\n".join(lines)


@pytest.mark.parametrize("reverse", [False, True])
def test_naive_exposure_is_date_presence_not_row_share(reverse):
    with Store() as store:
        store.con.execute("INSERT INTO securities (cik, ticker) VALUES ('1', 'A')")
        add(store, "equity", [10, 10], dates=["2021-02-01", "2021-04-01"])
        rows = [("A", "2021-03-01"), ("A", "2021-04-01"), ("A", "2021-03-01")]
        values = pd.DataFrame(rows[::-1] if reverse else rows,
                              columns=["ticker", "signal_date"])
        result = store.measure_naive_trap(values, ["equity"])
    assert result["n_signal_dates"] == 2
    assert result["n_dates_exposed"] == 1
    assert result["n_trap_rows"] == 1
    assert result["exposure_rate"] == .5


def test_reason_counts_overlap_and_their_union_matches_summary():
    inf = float("inf")
    with Store() as store:
        add(store, "unchanged", [10, 10])
        add(store, "null", [10, None])
        add(store, "nan", [10, float("nan")])
        add(store, "pos_inf", [10, inf])
        add(store, "neg_inf", [-inf, 10])
        add(store, "no_unit", [10, 10], units=["USD", None])
        add(store, "units", [10, 12], units=["USD", "EUR"])
        add(store, "types", [10, 10], types=["instant", "duration"])
        add(store, "unknown", [10, 10], types=["unknown"] * 2)
        add(store, "conflict", [10, 12, 14],
            dates=["2021-02-01", "2021-02-01", "2021-03-01"])
        add(store, "several", [None, 12], units=["USD", "EUR"])  # two reasons
        add(store, "single_nan", [float("nan")])  # not repeated: out of population
        summary = disclosure_summary(store.con)
        reasons = uncomparable_reason_counts(store.con)
    assert reasons["counting"] == "MULTI_LABEL_MAY_OVERLAP_DO_NOT_SUM"
    assert reasons["reason_keys"] == {
        "nonfinite_or_missing_value": 5, "missing_unit": 1, "mixed_units": 2,
        "mixed_fact_types": 1, "unknown_fact_type": 1, "same_date_conflict": 1,
    }
    assert reasons["any_reason_keys"] == summary["uncomparable_repeated_keys"] == 10
    assert sum(reasons["reason_keys"].values()) > reasons["any_reason_keys"]
    assert summary["unchanged_comparable_keys"] == 1


def test_reason_union_matches_summary_on_partition_fixture():
    with Store() as store:
        add(store, "changed", [10, 12])
        add(store, "missing", [10, None])
        add(store, "same_day", [10, 10], dates=["2021-02-01"] * 2)
        assert uncomparable_reason_counts(store.con)["any_reason_keys"] == (
            disclosure_summary(store.con)["uncomparable_repeated_keys"]) == 1


def load_readonly_script():
    path = Path(__file__).parents[1] / "scripts" / "disclosure_readonly_summary.py"
    spec = importlib.util.spec_from_file_location("disclosure_readonly_summary", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("broken", [None, "union", "partition"])
def test_readonly_script_exits_nonzero_on_failed_consistency(
        tmp_path, monkeypatch, capsys, broken):
    db = tmp_path / "store.duckdb"
    with Store(str(db)) as store:
        add(store, "changed", [10, 12])
        add(store, "missing", [10, None])
    script = load_readonly_script()
    if broken == "union":
        real = script.uncomparable_reason_counts
        monkeypatch.setattr(script, "uncomparable_reason_counts",
                            lambda con: {**real(con), "any_reason_keys": 0})
    elif broken == "partition":
        real = script.disclosure_summary
        monkeypatch.setattr(script, "disclosure_summary",
                            lambda con: {**real(con), "unchanged_comparable_keys": 5})
    code = script.main([str(db)])
    report = json.loads(capsys.readouterr().out)
    expected = {None: [], "union": ["union_matches_summary"],
                "partition": ["partition_matches_repeated"]}[broken]
    assert report["failed_checks"] == expected
    assert code == (1 if broken else 0)
    assert report["disclosure_summary"]["multiple_filing_date_keys"] == 2
    assert "reason_keys" in report["uncomparable_reasons"]


def test_readonly_script_treats_missing_table_as_schema_error(tmp_path, capsys):
    db = tmp_path / "empty.duckdb"
    duckdb.connect(str(db)).close()
    code = load_readonly_script().main([str(db)])
    report = json.loads(capsys.readouterr().out)
    assert code == 2
    assert set(report["missing_columns"]) == {
        "cik", "tag", "period_start", "period_end", "filed", "fact_type", "value", "unit"}
    assert "disclosure_summary" not in report
