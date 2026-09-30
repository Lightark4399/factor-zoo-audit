"""Known-truth tests for the calendar windows of mom_12_1, mom_6_1 and rev_1m.

Anchors are calendar month ends before the signal month end s:
  mom_12_1 = P(s-1)/P(s-12) - 1    lags 2-12, eleven monthly returns
  mom_6_1  = P(s-1)/P(s-7)  - 1    lags 2-7, six monthly returns
  rev_1m   = -[P(s)/P(s-1)  - 1]
P(m) is the last adjusted close on or before m, carried at most MAX_CARRY_DAYS.
Expected values below are written from these definitions, not from any output.

Each check takes ``compute(factor_id, store, dates)`` so the same checks can be
run against another implementation, such as an isolated v0.1.0 copy.
"""

import numpy as np
import pandas as pd
import pytest

from fza.factors import library
from fza.factors.registry import load_all
from fza.fixtures import load_fixture_into
from fza.store import Store

S = pd.Timestamp("2022-12-31")


def month_end(k: int) -> pd.Timestamp:
    """s - k: the k-th calendar month end before S."""
    return S - pd.offsets.MonthEnd(k) if k else S


def store_with(rows):
    """Store holding exactly the given (ticker, date, adjusted close) rows."""
    store = Store()
    for ticker, date, price in rows:
        store.con.execute(
            "INSERT INTO prices (ticker, trade_date, close, close_adj) VALUES (?, ?, ?, ?)",
            [ticker, pd.Timestamp(date).date(), price, price])
    return store


def real_compute(factor_id, store, dates):
    return load_all()[factor_id].compute(store, pd.DatetimeIndex(dates))


def values(compute, factor_id, store, dates):
    out = compute(factor_id, store, dates)
    return {(t, pd.Timestamp(d)): v for t, d, v in
            zip(out["ticker"], out["signal_date"], out["value"], strict=True)}


# ----------------------------------------------------------------------
# 1. Window and skipped month
# ----------------------------------------------------------------------
def window_store():
    """X: +100% in month s-12, +50% in month s. Y: +50% in month s-5."""
    rows = []
    for k in range(13, -1, -1):
        x = 100.0 if k == 13 else 300.0 if k == 0 else 200.0
        y = 100.0 if k >= 6 else 150.0
        rows += [("X", month_end(k), x), ("Y", month_end(k), y)]
    return store_with(rows)


def check_window_and_skip(compute):
    # X distinguishes the wrong formulas: old window P(s-1)/P(s-13)-1 = 1.0,
    # most recent month included P(s)/P(s-12)-1 = 0.5, both P(s)/P(s-13)-1 = 2.0.
    expected = {
        "mom_12_1": {"X": 0.0, "Y": 0.5},
        "mom_6_1": {"X": 0.0, "Y": 0.5},
        "rev_1m": {"X": -0.5, "Y": 0.0},
    }
    with window_store() as store:
        for dates in ([S], [month_end(k) for k in range(13, -1, -1)]):
            for factor_id, by_ticker in expected.items():
                got = values(compute, factor_id, store, dates)
                for ticker, want in by_ticker.items():
                    assert (ticker, S) in got, (factor_id, ticker, len(dates))
                    assert got[(ticker, S)] == pytest.approx(want, abs=1e-12), (
                        factor_id, ticker, len(dates))


def test_window_and_skipped_month():
    check_window_and_skip(real_compute)


# ----------------------------------------------------------------------
# 2. Date-set invariance on an independent price path
# ----------------------------------------------------------------------
def check_date_set_invariance(compute):
    # Anchor j = 0..30 is s-(30-j); price 100 * 1.01**j (+1% every month).
    rows = [("A", month_end(30 - j), 100.0 * 1.01 ** j) for j in range(31)]
    requests = {
        "D1 all 31": [month_end(k) for k in range(30, -1, -1)],
        "D2 {s}": [S],
        "D3 every other": [month_end(k) for k in range(30, -1, -2)],
    }
    # A skip-two-rows shift on D3 would give 1.01**22-1, 1.01**12-1 and -0.0201.
    expected = {"mom_12_1": 1.01 ** 11 - 1, "mom_6_1": 1.01 ** 6 - 1, "rev_1m": -0.01}
    with store_with(rows) as store:
        for name, dates in requests.items():
            for factor_id, want in expected.items():
                got = values(compute, factor_id, store, dates)
                assert ("A", S) in got, (factor_id, name)
                assert got[("A", S)] == pytest.approx(want, rel=1e-12), (factor_id, name)


def test_value_at_s_does_not_depend_on_the_requested_date_set():
    check_date_set_invariance(real_compute)


# ----------------------------------------------------------------------
# 3. Compatibility, early recovery, and anchors that stay missing
# ----------------------------------------------------------------------
FULL_GRID = pd.date_range("2019-06-30", "2021-12-31", freq=pd.offsets.MonthEnd())


def v010_reference(store, dates, factor_id):
    """v0.1.0's computation, reproduced from its source: shifts of requested rows."""
    closes = library._at_signal_dates(
        library._wide(store.prices(), "close_adj"), dates,
        max_staleness_days=library.MAX_CARRY_DAYS)
    with np.errstate(divide="ignore", invalid="ignore"):
        if factor_id == "rev_1m":
            wide = -((closes / closes.shift(1)) - 1.0)
        else:
            wide = closes.shift(1) / closes.shift(7) - 1.0  # mom_6_1: formation 6, skip 1
    wide = wide.replace([np.inf, -np.inf], np.nan)
    # stack() keeps NaN under pandas 3 and drops it under pandas 2; be explicit.
    return {(t, pd.Timestamp(d)): v for (d, t), v in wide.stack().dropna().items()}


def check_full_grid_compatibility_and_early_recovery(compute):
    with Store() as store:
        load_fixture_into(store)
        for factor_id, dropped_rows in (("mom_6_1", 7), ("rev_1m", 1)):
            old = v010_reference(store, FULL_GRID, factor_id)
            new = values(compute, factor_id, store, FULL_GRID)
            # Every key v0.1.0 could compute keeps its value on a consecutive grid.
            assert set(old) <= set(new), factor_id
            for key, value in old.items():
                assert new[key] == pytest.approx(value, rel=1e-12), (factor_id, key)
            # The first rows v0.1.0 dropped mechanically come back: the fixture's
            # prices start 2018-01-01, so their calendar anchors are valid.
            recovered = {d for (_, d) in set(new) - set(old)}
            assert recovered == set(FULL_GRID[:dropped_rows]), factor_id
        # The earliest requested date gets the value its own anchors define.
        wide = library._wide(store.prices(), "close_adj")
        first = FULL_GRID[0]
        p_1 = wide.loc[:first - pd.offsets.MonthEnd(1)].iloc[-1]
        p_12 = wide.loc[:first - pd.offsets.MonthEnd(12)].iloc[-1]
        got = values(compute, "mom_12_1", store, [first])
        for ticker in wide.columns:
            assert got[(ticker, first)] == pytest.approx(p_1[ticker] / p_12[ticker] - 1,
                                                         rel=1e-12), ticker


def check_missing_anchor_stays_missing(compute):
    # History starts at s-11: s-12 does not exist, so mom_12_1 has no value at s,
    # while mom_6_1 (needs s-7) and rev_1m (needs s-1) do.
    short = [("A", month_end(k), 100.0 + k) for k in range(11, -1, -1)]
    with store_with(short) as store:
        assert ("A", S) not in values(compute, "mom_12_1", store, [S])
        assert ("A", S) in values(compute, "mom_6_1", store, [S])
        assert ("A", S) in values(compute, "rev_1m", store, [S])
    # s-12 alone is removed: the last close on or before it is s-13, about 30
    # days older, beyond the carry limit. An earlier month must not stand in.
    gap = [("A", month_end(k), 100.0 + k) for k in range(20, -1, -1) if k != 12]
    with store_with(gap) as store:
        got = values(compute, "mom_12_1", store, [month_end(k) for k in range(20, -1, -1)])
        assert ("A", S) not in got
        assert ("A", month_end(1)) in got  # its s-12 anchor (month_end(13)) exists


def test_old_valid_keys_keep_their_values_and_early_keys_recover():
    check_full_grid_compatibility_and_early_recovery(real_compute)


def test_a_missing_or_stale_anchor_leaves_the_key_missing():
    check_missing_anchor_stays_missing(real_compute)


# ----------------------------------------------------------------------
# 4. Non-trading month ends and the staleness limit
# ----------------------------------------------------------------------
def daily_store(overrides=None, drop=()):
    """Business-day closes of 100, 2020-01-01..2020-04-30, with edits."""
    overrides = overrides or {}
    rows = [("A", day, overrides.get(day.strftime("%Y-%m-%d"), 100.0))
            for day in pd.bdate_range("2020-01-01", "2020-04-30")
            if day.strftime("%Y-%m-%d") not in drop]
    return store_with(rows)


def check_non_trading_month_end_and_staleness(compute):
    s = pd.Timestamp("2020-03-31")  # Tuesday; s-1 = 2020-02-29 is a Saturday
    # The Friday close carries to Saturday's month end; Monday's close does not.
    with daily_store({"2020-02-28": 110.0, "2020-03-02": 999.0}) as store:
        got = values(compute, "rev_1m", store, [s])
        assert ("A", s) in got
        assert got[("A", s)] == pytest.approx(-(100.0 / 110.0 - 1), rel=1e-12)
    # Last close 2020-02-20: 9 days before the month end, inside the limit.
    feb_tail = [d.strftime("%Y-%m-%d") for d in pd.bdate_range("2020-02-21", "2020-02-28")]
    with daily_store({"2020-02-20": 125.0}, drop=feb_tail) as store:
        got = values(compute, "rev_1m", store, [s])
        assert ("A", s) in got
        assert got[("A", s)] == pytest.approx(-(100.0 / 125.0 - 1), rel=1e-12)
    # Last close 2020-02-14: 15 days before the month end, beyond the limit.
    feb_late = [d.strftime("%Y-%m-%d") for d in pd.bdate_range("2020-02-17", "2020-02-28")]
    with daily_store(drop=feb_late) as store:
        assert ("A", s) not in values(compute, "rev_1m", store, [s])


def test_non_trading_month_end_and_staleness_follow_the_existing_rule():
    check_non_trading_month_end_and_staleness(real_compute)
