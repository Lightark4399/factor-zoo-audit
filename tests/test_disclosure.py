"""Explicit histories distinguish repeat publication from numerical changes."""

import pandas as pd
import pytest

from fza.demo import describe_data
from fza.disclosure import disclosure_summary
from fza.render import disclosure_lines
from fza.store import Store


def add(store, tag, values, dates=None, units=None):
    dates = dates or [f"2021-0{i + 2}-01" for i in range(len(values))]
    units = units or ["USD"] * len(values)
    for i, (value, date, unit) in enumerate(zip(values, dates, units, strict=True)):
        store.con.execute(
            "INSERT INTO fundamentals "
            "(cik, tag, period_start, period_end, filed, value, unit, form, accession, "
            "fact_type) VALUES ('1', ?, '2020-12-31', '2020-12-31', ?, ?, ?, "
            "'10-K', ?, 'instant')",
            [tag, date, value, unit, str(i)],
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
