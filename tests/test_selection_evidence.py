"""Evidence for share-count and interval selection gaps (2026-09-23).

The strict xfails record KNOWN GAPS, not accepted behaviour and not a stage pass.
Each asserts the invariant a fix must satisfy; strict=True turns an unexpected
pass into a failure so the marker is removed with the fix. ``raises`` limits the
expected failure to the assertion, so an unrelated error still fails the run.
"""

import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest

import fza.pipeline.run as runner
from fza.ingest.prices import attach_shares_outstanding
from fza.store import Store

SHARES = "CommonStockSharesOutstanding"
KNOWN_GAP = dict(strict=True, raises=AssertionError)


def load_probe():
    path = Path(__file__).parents[1] / "scripts" / "probe_share_candidates.py"
    spec = importlib.util.spec_from_file_location("probe_share_candidates", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def fact(store, tag, start, end, filed, value, accession, fact_type="instant",
         namespace="us-gaap"):
    store.con.execute(
        "INSERT INTO fundamentals (cik, tag, period_start, period_end, filed, value, "
        "unit, form, accession, source_namespace, fact_type) "
        "VALUES ('1', ?, ?, ?, ?, ?, 'USD', '10-Q', ?, ?, ?)",
        [tag, start, end, filed, value, accession, namespace, fact_type],
    )


def test_probe_separates_units_and_latest_end_rows_from_values():
    with Store() as store:
        store.con.execute("INSERT INTO securities (cik, ticker, first_filing, last_filing) "
                          "VALUES ('1', 'A', '2019-01-01', '2021-01-01')")
        # Group 1: one latest-end value reported twice, plus an earlier context.
        fact(store, SHARES, "2020-02-15", "2020-02-15", "2020-02-20", 100, "a", namespace="dei")
        fact(store, SHARES, "2020-02-15", "2020-02-15", "2020-02-20", 100, "b")
        fact(store, SHARES, "2019-12-31", "2019-12-31", "2020-02-20", 90, "a")
        # Group 2: two different values at the latest end (a fact-key conflict).
        fact(store, SHARES, "2020-04-25", "2020-04-25", "2020-05-01", 110, "c")
        fact(store, SHARES, "2020-04-25", "2020-04-25", "2020-05-01", 120, "d")
        # Group 3: a zero candidate leaves max/min undefined, not "small".
        fact(store, SHARES, "2020-06-30", "2020-06-30", "2020-08-01", 0, "e")
        fact(store, SHARES, "2020-07-25", "2020-07-25", "2020-08-01", 50, "e", namespace="dei")
        for day, shares in [("2020-03-31", 90), ("2020-05-29", 110)]:
            store.con.execute("INSERT INTO prices (ticker, trade_date, close, shares_out) "
                              "VALUES ('A', ?, 10, ?)", [day, shares])
        report = load_probe().probe(store.con, history_months=0)
    assert report["fact_keys"]["keys"] == 5
    assert report["fact_keys"]["same_date_conflict_single_filing_date_keys"] == 1
    context = report["disclosure_groups"]["multi_value_context"]
    assert report["disclosure_groups"]["multi_value"] == context["groups"] == 3
    assert context["latest_end_single_value"] == 2
    assert context["latest_end_single_value_several_rows"] == 1
    assert context["latest_end_several_values"] == 1
    assert context["ratio_undefined"] == context["ratio_undefined_zero_min"] == 1
    assert context["ratio_lt_1_01"] == 0
    assert [(r["filed"].isoformat(), r["value"]) for r in report["ratio_undefined_groups"]] == [
        ("2020-08-01", 50.0), ("2020-08-01", 0.0)]
    assert report["checks"] and report["failed_checks"] == []
    assert report["disclosure_groups"]["companies_by_namespace"]["with_both"] == 1
    stored = report["price_rows"]["stored_value_on_exposed_rows"]
    assert stored["rows"] == 2
    assert stored["stored_differs_from_unique_latest_end_value"] == 1
    assert stored["latest_end_not_unique"] == 1
    assert stored["stored_equals_unique_latest_end_value"] == 0
    keys = report["signal_keys"]
    assert (keys["universe_keys"], keys["with_market_cap"], keys["exposed"]) == (2, 1, 1)
    assert keys["stored_differs_from_unique_latest_end_value"] == 1
    assert report["price_rows"]["zero_shares_rows"] == keys["market_cap_row_zero_shares"] == 0


def test_probe_exits_nonzero_when_a_consistency_check_fails(tmp_path, monkeypatch, capsys):
    db = tmp_path / "store.duckdb"
    Store(str(db)).close()
    probe = load_probe()
    stub = {"checks": {"ratio_bins_sum_to_groups": False},
            "failed_checks": ["ratio_bins_sum_to_groups"], "counts": 7}
    monkeypatch.setattr(probe, "probe", lambda con: stub)
    assert probe.main([str(db)]) == 1
    printed = capsys.readouterr().out
    assert '"counts": 7' in printed and "ratio_bins_sum_to_groups" in printed
    monkeypatch.setattr(probe, "probe", lambda con: {"checks": {}, "failed_checks": []})
    assert probe.main([str(db)]) == 0


def test_sample_price_row_is_attributed_only_to_its_asof_group(monkeypatch):
    probe = load_probe()
    monkeypatch.setattr(probe, "SAMPLES", {
        "direct": ("A", "filed = DATE '2020-03-15'"),
        "superseded": ("A", "filed = DATE '2020-02-20'"),
    })
    with Store() as store:
        store.con.execute("INSERT INTO securities (cik, ticker) VALUES ('1', 'A')")
        fact(store, SHARES, "2020-02-15", "2020-02-15", "2020-02-20", 100, "a")
        fact(store, SHARES, "2019-12-31", "2019-12-31", "2020-02-20", 90, "a")
        fact(store, SHARES, "2020-03-10", "2020-03-10", "2020-03-15", 95, "b")
        store.con.execute("INSERT INTO prices (ticker, trade_date, close, shares_out) "
                          "VALUES ('A', '2020-03-31', 10, 95)")
        out = probe.samples(store.con)
    assert out["direct"]["price_row_attribution"]["attributed_to_listed_group"] is True
    superseded = out["superseded"]["price_row_attribution"]
    assert superseded["matches_listed_group"] is False
    assert superseded["attributed_to_listed_group"] is False


@pytest.mark.xfail(**KNOWN_GAP, reason="KNOWN GAP: same-date share candidates are "
                   "resolved by input row order in attach_shares_outstanding")
def test_attached_share_count_does_not_depend_on_input_row_order():
    prices = pd.DataFrame({"ticker": ["A"], "cik": ["1"], "trade_date": ["2020-03-02"],
                           "shares_out": [None]})
    shares = pd.DataFrame({"cik": ["1", "1"], "tag": [SHARES] * 2,
                           "filed": ["2020-02-20"] * 2, "value": [100.0, 90.0],
                           "period_end": ["2020-02-15", "2018-12-31"]})
    forward = attach_shares_outstanding(prices, shares)["shares_out"].tolist()
    backward = attach_shares_outstanding(prices, shares.iloc[::-1])["shares_out"].tolist()
    assert forward == backward


def arm_reads(monkeypatch, rows, store=None):
    """Rows each vintage arm's latest read returns, through compare_vintages."""
    if store is None:
        store = Store()
        for i, (start, value) in enumerate(rows):
            fact(store, "NetIncomeLoss", start, "2020-09-30", "2020-11-01", value, str(i),
                 fact_type="duration")
    seen = {}

    def compute(factor, store, dates, **kwargs):
        got = store.fundamentals_asof(pd.Timestamp("2020-12-31"), tags=["NetIncomeLoss"])
        seen[kwargs["vintage"] + "_frame"] = got
        seen[kwargs["vintage"]] = [
            (str(pd.Timestamp(r.period_start).date()),
             None if pd.isna(r.value) else float(r.value), r.accession)
            for r in got.itertuples()
        ]
        if kwargs["vintage"] == "restated":
            raise RuntimeError("stop after capturing both arms")

    monkeypatch.setattr(runner, "compute_factor", compute)
    monkeypatch.setattr(runner, "historical_universe_membership", lambda *a: object())
    with pytest.raises(RuntimeError, match="stop after"):
        runner.compare_vintages(SimpleNamespace(factor_id="x", uses_fundamentals=True),
                                store, pd.DatetimeIndex(["2020-12-31"]))
    stored = {(str(pd.Timestamp(s).date()), None if pd.isna(v) else float(v), a)
              for s, v, a in store.con.execute(
                  "SELECT period_start, value, accession FROM fundamentals").fetchall()}
    seen["stored_frame"] = store.con.execute("SELECT * FROM fundamentals").df()
    store.close()
    return seen, stored


def as_rows(frame, columns):
    """Rows as comparable tuples; missing values of any kind become None."""
    return {tuple(None if pd.isna(v) else str(v) for v in row)
            for row in frame[columns].itertuples(index=False)}


@pytest.mark.xfail(**KNOWN_GAP, reason="KNOWN GAP: on a (period_end, filed) tie across "
                   "intervals, PIT and restated arms break the tie differently")
def test_both_arms_select_the_same_row_when_filing_visibility_is_equal(monkeypatch):
    # Both rows were filed before the signal date, so relaxing filing
    # visibility must not change the selection.
    seen, _ = arm_reads(monkeypatch, [("2020-01-01", 90.0), ("2020-07-01", 30.0)])
    assert seen["pit"] == seen["restated"]


@pytest.mark.parametrize("rows", [
    [("2020-01-01", 90.0), ("2020-07-01", None)],
    [("2020-07-01", None), ("2020-01-01", 90.0)],
    [("2020-01-01", None), ("2020-07-01", 30.0)],
    [("2020-07-01", 30.0), ("2020-01-01", None)],
    [("2020-01-01", 90.0), ("2020-07-01", 30.0)],
    [("2020-07-01", 30.0), ("2020-01-01", 90.0)],
])
def test_restated_arm_returns_a_whole_stored_row(monkeypatch, rows):
    # Null value in either row, in either insertion order. Which row wins a tie
    # is a separate, unchanged policy; the returned row must be a stored one.
    seen, stored = arm_reads(monkeypatch, rows)
    assert len(seen["restated"]) == 1
    assert set(seen["restated"]) <= stored
    columns = list(seen["restated_frame"].columns)
    assert as_rows(seen["restated_frame"], columns) <= as_rows(seen["stored_frame"], columns)


@pytest.mark.parametrize("reverse", [False, True])
def test_restated_arm_does_not_splice_nulls_in_other_columns(monkeypatch, reverse):
    rows = [("2020-01-01", 2020, "a"), ("2020-07-01", None, "b")]
    store = Store()
    for start, fiscal_year, accession in rows[::-1] if reverse else rows:
        store.con.execute(
            "INSERT INTO fundamentals (cik, tag, period_start, period_end, filed, value, "
            "unit, form, accession, fiscal_year, fact_type) VALUES ('1', 'NetIncomeLoss', "
            "?, '2020-09-30', '2020-11-01', 5, 'USD', '10-Q', ?, ?, 'duration')",
            [start, accession, fiscal_year])
    seen, _ = arm_reads(monkeypatch, None, store=store)
    columns = list(seen["restated_frame"].columns)
    assert len(seen["restated_frame"]) == 1
    assert as_rows(seen["restated_frame"], columns) <= as_rows(seen["stored_frame"], columns)
