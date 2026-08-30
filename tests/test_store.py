"""Tests for the point-in-time store and the factor registry.

The store's job is to make a leaking query hard to write and a written one easy
to detect. Both halves are tested: the view returns the pre-restatement value
before the amendment is filed, and the read log catches a factor that went around
the view.

The two checks are kept apart deliberately. ``assert_read_path_respected``
inspects what the reads actually returned and is a check on this code;
``measure_naive_trap`` quantifies what a naive query would have read early and is
a finding about the data. An earlier version conflated them and reported the size
of the hazard as a violation by the code that avoids it.
"""

from __future__ import annotations

import duckdb
import pandas as pd
import pytest

from fza.fixtures import FixtureSpec, build_fixture, load_fixture_into
from fza.store import ReadRecord, Store


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
    # Filtered by tag: the fixture carries four tags per period now, so an
    # unfiltered query returns eight rows and the count assertion below would be
    # about the fixture's breadth rather than about revision handling.
    rows = store.con.execute(
        f"SELECT filed, value, form FROM fundamentals WHERE cik = '{cik}' "
        "AND tag = 'StockholdersEquity' "
        "AND period_end = DATE '2018-12-31' ORDER BY filed"
    ).df()
    assert len(rows) == 2
    assert set(rows["form"]) == {"10-Q", "10-K/A"}
    assert rows["value"].iloc[0] != rows["value"].iloc[1]


def test_asof_returns_the_original_value_before_the_amendment_is_filed(store):
    """The heart of the project: a signal cannot see a filing that does not exist."""
    cik = store._fixture_info["restated_cik"]
    rest = store.restatements()
    rest = rest.loc[rest["tag"] == "StockholdersEquity"]
    row = rest.iloc[0]

    before = pd.Timestamp(row["last_filed"]) - pd.Timedelta(days=1)
    after = pd.Timestamp(row["last_filed"]) + pd.Timedelta(days=1)

    def value_at(d):
        return store.con.execute(
            f"SELECT value FROM fundamentals_asof(DATE '{d.date()}') "
            f"WHERE cik = '{cik}' AND tag = 'StockholdersEquity' "
            f"AND period_end = DATE '{row['period_end']}'"
        ).df()["value"].iloc[0]

    assert value_at(before) == pytest.approx(row["first_value"])
    assert value_at(after) == pytest.approx(row["last_value"])


def test_restated_view_always_shows_the_final_value(store):
    """And is therefore unusable for signal construction, which is why it is named loudly."""
    cik = store._fixture_info["restated_cik"]
    rest = store.restatements()
    rest = rest.loc[rest["tag"] == "StockholdersEquity"]
    row = rest.iloc[0]
    final = store.con.execute(
        "SELECT value FROM fundamentals_restated "
        f"WHERE cik = '{cik}' AND tag = 'StockholdersEquity' "
        f"AND period_end = DATE '{row['period_end']}'"
    ).df()["value"].iloc[0]
    assert final == pytest.approx(row["last_value"])


def test_restatement_size_matches_the_fixture(store):
    """The fixture states the revision in advance, so the test asserts the number."""
    spec = store._fixture_info["spec"]
    rest = store.restatements()
    rest = rest.loc[rest["tag"] == "StockholdersEquity"]
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
            # Columns are named rather than positional: an unnamed INSERT binds
            # by position, so adding a column to the table turns this into a
            # BinderError and the CHECK constraint stops being exercised at all.
            "INSERT INTO fundamentals "
            "(cik, tag, period_end, fiscal_year, fiscal_period, filed, value, "
            " unit, form, accession) "
            "VALUES ('0000000001', 'X', "
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


def test_read_path_check_passes_when_reads_go_through_the_view(store):
    """The honest path returns only filings that already existed."""
    store.access.reads.clear()
    for date in ("2020-06-30", "2021-03-31", "2021-12-01"):
        store.fundamentals_asof(date, tags=["StockholdersEquity"])
    result = store.assert_read_path_respected()
    assert result["ok"] is True
    assert result["n_reads"] == 3
    assert result["n_violations"] == 0


def test_read_path_check_catches_a_bypass(store):
    """The check that an earlier version could not perform.

    The previous implementation re-derived a hypothetical from the raw table and
    never inspected what the reads returned, so a caller who went around the view
    was invisible to it. This one logs the outcome, so it fails.
    """
    store.access.reads.clear()
    # Simulate a caller reading the restated frame and labelling it as of an
    # early date -- exactly what bypassing the view looks like.
    restated = store.fundamentals_restated(caller="test-bypass")
    store.access.reads.append(
        ReadRecord(
            requested_asof=pd.Timestamp("2019-01-31"),
            intended_signal_date=pd.Timestamp("2019-01-31"),
            max_filed=pd.to_datetime(restated["filed"]).max(),
            n_rows=len(restated),
            tags=("StockholdersEquity",),
        )
    )
    result = store.assert_read_path_respected()
    assert result["ok"] is False
    assert result["n_violations"] == 1
    sample = result["sample"][0]
    assert sample["max_filed"] > sample["intended_signal_date"]


def test_read_path_grace_days_are_measured_from_the_intended_signal_date(store):
    """A factor that applies its declared lag at the query site passes.

    The lag must be counted once. An earlier version recorded only the date that
    was asked for -- already shifted by the factor -- and then subtracted the lag
    again, so every honest read failed. Here the read asks for 2020-06-28 while
    intending 2020-06-30, and a two-day declaration is exactly satisfied.
    """
    store.access.reads.clear()
    store.access.reads.append(
        ReadRecord(
            requested_asof=pd.Timestamp("2020-06-28"),
            intended_signal_date=pd.Timestamp("2020-06-30"),
            max_filed=pd.Timestamp("2020-06-28"),
            n_rows=1,
            tags=("StockholdersEquity",),
        )
    )
    assert store.assert_read_path_respected(grace_days=2)["ok"] is True


def test_read_path_catches_a_declared_lag_that_was_never_applied(store):
    """The reason this fix exists: a declaration is checked, not believed.

    This read is legal on its own terms -- nothing came back later than the date
    it asked for, so ``respects_asof`` holds. What it did not do is honour the
    two-day lag the factor declared: it asked for the signal date itself. Under
    grace 0 that is fine; under the declaration it is a violation, and saying so
    is the difference between enforcing the lag and taking its word for it.
    """
    store.access.reads.clear()
    store.access.reads.append(
        ReadRecord(
            requested_asof=pd.Timestamp("2020-06-30"),
            intended_signal_date=pd.Timestamp("2020-06-30"),
            max_filed=pd.Timestamp("2020-06-30"),
            n_rows=1,
            tags=("StockholdersEquity",),
        )
    )
    assert store.access.reads[0].respects_asof is True
    assert store.assert_read_path_respected(grace_days=0)["ok"] is True
    assert store.assert_read_path_respected(grace_days=2)["ok"] is False


def test_intended_signal_date_defaults_to_the_date_asked_for(store):
    """A factor declaring no lag intends the day it asked for."""
    store.access.reads.clear()
    store.fundamentals_asof("2021-12-01", tags=["StockholdersEquity"])
    record = store.access.reads[-1]
    assert record.requested_asof == record.intended_signal_date == pd.Timestamp("2021-12-01")


def test_read_path_check_with_no_reads_says_so(store):
    """Vacuous truth is reported as vacuous, not as a pass."""
    store.access.reads.clear()
    result = store.assert_read_path_respected()
    assert result["n_reads"] == 0
    assert "no point-in-time reads" in result["note"]


def test_naive_trap_measures_the_hazard_not_this_code(store):
    """A large trap means the store is earning its keep.

    The counts are reported at two granularities because they answer different
    questions, and mixing them made a ratio impossible to compute -- the earlier
    version reported 12,844 violations against 3,010 checks.
    """
    ticker = store._fixture_info["restated_ticker"]
    values = pd.DataFrame(
        {"ticker": [ticker], "signal_date": [pd.Timestamp("2019-03-01")]}
    )
    trap = store.measure_naive_trap(values, tags=["StockholdersEquity"])
    assert trap["n_signal_dates"] == 1
    assert trap["n_trap_rows"] > 0
    assert 0.0 <= trap["exposure_rate"] <= 1.0
    assert trap["n_dates_exposed"] <= trap["n_signal_dates"]


def test_naive_trap_is_empty_for_late_signal_dates(store):
    """By the end of the sample every filing has appeared, so the trap is gone."""
    values = pd.DataFrame(
        {"ticker": ["TST00"], "signal_date": [pd.Timestamp("2021-12-01")]}
    )
    trap = store.measure_naive_trap(values, tags=["StockholdersEquity"])
    assert trap["n_trap_rows"] == 0
    assert trap["exposure_rate"] == 0.0


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


# ----------------------------------------------------------------------
# The taxonomy a filer reports under, carried on the security
# ----------------------------------------------------------------------
def test_securities_carry_their_accounting_standard():
    """An IFRS filer has prices and no fundamentals, and that has to be legible.

    Without the column it is indistinguishable from a us-gaap filer whose ingest
    failed, and the fundamental universe is silently smaller than the security
    count implies. See AI_NOTES incident 14.
    """
    s = Store()
    s.load_securities(
        pd.DataFrame(
            {
                "cik": ["0000000001", "0000000002"],
                "ticker": ["AAA", "BBB"],
                "name": ["A", "B"],
                "sic": [None, None],
                "first_filing": ["2015-01-01", "2015-01-01"],
                "last_filing": ["2020-01-01", "2020-01-01"],
                "accounting_standard": ["us-gaap", "ifrs"],
            }
        )
    )
    got = dict(
        s.con.execute("SELECT ticker, accounting_standard FROM securities").fetchall()
    )
    assert got == {"AAA": "us-gaap", "BBB": "ifrs"}
    s.close()


def test_an_unstated_accounting_standard_is_unknown_not_usgaap():
    """A caller that does not know says so. Assuming us-gaap on its behalf is the
    same error as writing 0 for an unknown share count."""
    s = Store()
    s.load_securities(
        pd.DataFrame(
            {
                "cik": ["0000000001"],
                "ticker": ["AAA"],
                "name": ["A"],
                "sic": [None],
                "first_filing": ["2015-01-01"],
                "last_filing": ["2020-01-01"],
            }
        )
    )
    assert s.con.execute(
        "SELECT accounting_standard FROM securities"
    ).fetchone()[0] == "unknown"
    s.close()
