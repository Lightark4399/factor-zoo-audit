"""Tests for the point-in-time store and the factor registry.

The store's job is to make a leaking query hard to write and a written one easy
to detect. Both halves are tested: the view returns the pre-restatement value
before the amendment is filed, and ``assert_no_lookahead`` catches a factor that
went around the view.
"""

from __future__ import annotations

import duckdb
import pandas as pd
import pytest

from fza.fixtures import FixtureSpec, build_fixture, load_fixture_into
from fza.store import Store


@pytest.fixture()
def store():
    s = Store()
    info = load_fixture_into(s)
    s._fixture_info = info  # attached for convenience in tests
    yield s
    s.close()


# ----------------------------------------------------------------------
# Bitemporal storage
# ----------------------------------------------------------------------
def test_restatement_is_stored_as_a_new_row(store):
    """The original filing must survive the amendment.

    If a revision overwrote the first value, no query could reconstruct what was
    knowable at the time, and the project's central claim would be unverifiable.
    """
    cik = store._fixture_info["restated_cik"]
    rows = store.con.execute(
        f"SELECT filed, value, form FROM fundamentals WHERE cik = '{cik}' "
        "AND period_end = DATE '2018-12-31' ORDER BY filed"
    ).df()
    assert len(rows) == 2
    assert set(rows["form"]) == {"10-Q", "10-K/A"}
    assert rows["value"].iloc[0] != rows["value"].iloc[1]


def test_asof_returns_the_original_value_before_the_amendment_is_filed(store):
    """The heart of the project: a signal cannot see a filing that does not exist."""
    cik = store._fixture_info["restated_cik"]
    rest = store.restatements()
    row = rest.iloc[0]

    before = pd.Timestamp(row["last_filed"]) - pd.Timedelta(days=1)
    after = pd.Timestamp(row["last_filed"]) + pd.Timedelta(days=1)

    def value_at(d):
        return store.con.execute(
            f"SELECT value FROM fundamentals_asof(DATE '{d.date()}') "
            f"WHERE cik = '{cik}' AND period_end = DATE '{row['period_end']}'"
        ).df()["value"].iloc[0]

    assert value_at(before) == pytest.approx(row["first_value"])
    assert value_at(after) == pytest.approx(row["last_value"])


def test_restated_view_always_shows_the_final_value(store):
    """And is therefore unusable for signal construction, which is why it is named loudly."""
    cik = store._fixture_info["restated_cik"]
    rest = store.restatements()
    row = rest.iloc[0]
    final = store.con.execute(
        "SELECT value FROM fundamentals_restated "
        f"WHERE cik = '{cik}' AND period_end = DATE '{row['period_end']}'"
    ).df()["value"].iloc[0]
    assert final == pytest.approx(row["last_value"])


def test_restatement_size_matches_the_fixture(store):
    """The fixture states the revision in advance, so the test asserts the number."""
    spec = store._fixture_info["spec"]
    rest = store.restatements()
    assert len(rest) > 0
    expected_pct = spec.restatement_factor - 1.0  # 0.60 -> -0.40
    assert rest["revision_pct"].iloc[0] == pytest.approx(expected_pct, abs=1e-9)
    assert (rest["revision_lag_days"] == spec.restatement_lag_days).all()


def test_asof_excludes_periods_that_had_not_ended(store):
    """Both filters do work; dropping either one lets a different leak through."""
    early = pd.Timestamp("2018-03-01")
    got = store.con.execute(
        f"SELECT * FROM fundamentals_asof(DATE '{early.date()}')"
    ).df()
    assert (pd.to_datetime(got["period_end"]) <= early).all()
    assert (pd.to_datetime(got["filed"]) <= early).all()


def test_filing_before_period_end_is_rejected(store):
    """A filing cannot predate the period it reports on."""
    # Narrowed to the constraint error specifically: a blind `Exception` would
    # also pass on a typo in the table name, which would leave the CHECK
    # constraint untested while the test still went green.
    with pytest.raises(duckdb.ConstraintException):
        store.con.execute(
            "INSERT INTO fundamentals VALUES ('0000000001', 'X', "
            "DATE '2020-12-31', 2020, 'Q4', DATE '2020-06-30', 1.0, 'USD', "
            "'10-K', 'acc')"
        )


# ----------------------------------------------------------------------
# Universe reconstruction
# ----------------------------------------------------------------------
def test_universe_includes_a_security_for_the_dates_it_was_filing(store):
    """Survivorship-free membership is by filing activity, not present existence."""
    early = store.universe_asof("2019-01-02")
    late = store.universe_asof("2021-12-01")
    assert "TST07" in set(early["ticker"])  # the delisted one, while still filing
    assert "TST07" not in set(late["ticker"])
    assert len(late) < len(early)


# ----------------------------------------------------------------------
# Access logging and the look-ahead check
# ----------------------------------------------------------------------
def test_reading_the_restated_view_is_logged(store):
    """A factor run can then assert it never came through here."""
    assert store.access.touched_restated is False
    store.fundamentals_restated(caller="test")
    assert store.access.touched_restated is True
    assert "test" in store.access.restated_callers


def test_pit_reads_are_counted(store):
    before = store.access.pit_reads
    store.fundamentals_asof("2020-06-30", tags=["StockholdersEquity"])
    assert store.access.pit_reads == before + 1


def test_assert_no_lookahead_passes_for_honest_signal_dates(store):
    """Signal dates late enough that every filing they touch already existed."""
    values = pd.DataFrame(
        {
            "ticker": ["TST00", "TST01"],
            "signal_date": [pd.Timestamp("2021-12-01")] * 2,
        }
    )
    result = store.assert_no_lookahead(values, tags=["StockholdersEquity"])
    assert result["ok"] is True
    assert result["violations"] == 0


def test_assert_no_lookahead_flags_a_signal_that_precedes_its_filing(store):
    """The check that would catch a factor bypassing the view.

    A signal formed in early 2019 for a company whose latest filing for a
    then-current period arrives in 2019-08 is exactly the pattern a naive query
    against a mutable table produces.
    """
    ticker = store._fixture_info["restated_ticker"]
    values = pd.DataFrame(
        {"ticker": [ticker], "signal_date": [pd.Timestamp("2019-03-01")]}
    )
    result = store.assert_no_lookahead(values, tags=["StockholdersEquity"])
    assert result["ok"] is False
    assert result["violations"] > 0


def test_grace_days_tightens_the_check(store):
    """A factor requiring a reporting lag can assert it, and the check enforces it."""
    values = pd.DataFrame(
        {"ticker": ["TST00"], "signal_date": [pd.Timestamp("2019-02-14")]}
    )
    lenient = store.assert_no_lookahead(values, tags=["StockholdersEquity"], grace_days=0)
    strict = store.assert_no_lookahead(values, tags=["StockholdersEquity"], grace_days=30)
    assert strict["violations"] >= lenient["violations"]


# ----------------------------------------------------------------------
# Fixture integrity
# ----------------------------------------------------------------------
def test_fixture_contains_a_restatement_by_construction():
    data = build_fixture()
    f = data["fundamentals"]
    dupes = f.groupby(["cik", "tag", "period_end"]).size()
    assert (dupes > 1).any(), "the fixture must contain at least one revision"


def test_fixture_is_deterministic():
    """An audit whose inputs change between runs cannot be checked by a reviewer."""
    a = build_fixture(FixtureSpec(seed=5))["prices"]["close"].to_numpy()
    b = build_fixture(FixtureSpec(seed=5))["prices"]["close"].to_numpy()
    assert (a == b).all()


def test_delisted_security_stops_having_prices():
    data = build_fixture()
    px = data["prices"]
    last = px.groupby("ticker")["trade_date"].max()
    assert last["TST07"] < last["TST00"]
