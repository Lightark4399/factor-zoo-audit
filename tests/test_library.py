"""Tests for the factor library.

Two things are checked for every factor, and one for the library as a whole.

Per factor: it produces values on the fixture, and its reads respect the as-of
contract. Neither says the factor is any good -- fixture prices are a random walk
-- but both would catch the failures that have actually occurred here: a window
expressed in the wrong unit, a tag the fixture does not carry, a read that
bypassed the view.

For the library: every registered factor has a card whose falsification criteria
are non-empty, and every category the SPEC promises is represented. A factor
library is only comparable across rows if every row went through the same
protocol, and the registry is what makes that structural rather than aspirational.
"""

from __future__ import annotations

import pandas as pd
import pytest

from fza.factors.library import (
    _annual_asset_growth_value,
    _long,
    _ttm_value,
    idiosyncratic_volatility,
)
from fza.factors.registry import VALID_CATEGORIES, all_factors, load_all, summary_table
from fza.fixtures import load_fixture_into
from fza.pipeline.run import compute_factor
from fza.store import Store

SIGNAL_DATES = pd.DatetimeIndex(
    pd.date_range("2019-06-30", "2021-12-31", freq=pd.offsets.MonthEnd())
)


@pytest.fixture(scope="module")
def store():
    s = Store()
    load_fixture_into(s)
    yield s
    s.close()


@pytest.fixture(scope="module")
def factors():
    return load_all()


def _factor_ids():
    load_all()
    return sorted(all_factors())


def test_wide_to_long_is_stable_across_supported_pandas_versions():
    dates = pd.DatetimeIndex(["2020-01-31", "2020-02-29"])
    wide = pd.DataFrame(
        {"BBB": [2.0, float("nan")], "AAA": [1.0, 3.0]},
        index=dates,
    )

    got = _long(wide, "measurement")

    assert got.to_dict(orient="records") == [
        {"ticker": "AAA", "signal_date": pd.Timestamp("2020-01-31"), "measurement": 1.0},
        {"ticker": "BBB", "signal_date": pd.Timestamp("2020-01-31"), "measurement": 2.0},
        {"ticker": "AAA", "signal_date": pd.Timestamp("2020-02-29"), "measurement": 3.0},
    ]


# ----------------------------------------------------------------------
# Every factor, individually
# ----------------------------------------------------------------------
@pytest.mark.parametrize("factor_id", _factor_ids())
def test_factor_produces_values(factor_id, store, factors):
    """An empty factor is always a bug, and the pipeline refuses to pass one on.

    This has caught two real defects: a momentum window expressed in rows of a
    resampled frame while meaning trading days, and three factors reading tags
    the fixture did not carry.
    """
    run = compute_factor(factors[factor_id], store, SIGNAL_DATES)
    assert len(run.values) > 0
    assert len(run.panel) > 0
    assert run.protocol.n_dates > 0


@pytest.mark.parametrize("factor_id", _factor_ids())
def test_factor_respects_the_asof_contract(factor_id, store, factors):
    """No read may return a filing dated after the day it was asked for."""
    run = compute_factor(factors[factor_id], store, SIGNAL_DATES)
    assert run.read_path_check["ok"], run.read_path_check.get("sample")


@pytest.mark.parametrize("factor_id", _factor_ids())
def test_factor_values_are_finite(factor_id, store, factors):
    """Infinities from a zero denominator would survive standardisation as NaN
    and quietly shrink the cross-section instead of raising."""
    run = compute_factor(factors[factor_id], store, SIGNAL_DATES)
    import numpy as np

    assert np.isfinite(run.values["value"]).all()


# ----------------------------------------------------------------------
# The library as a whole
# ----------------------------------------------------------------------
def test_every_factor_has_falsification_criteria(factors):
    """A card with no stated way to fail cannot be tested against."""
    for factor_id, factor in factors.items():
        assert factor.card.falsification, f"{factor_id} has no falsification criteria"
        assert len(factor.card.falsification) >= 2


def test_every_factor_has_a_reference(factors):
    """These are reimplementations of published definitions, and a reader who
    doubts a result has to be able to find the paper."""
    for factor_id, factor in factors.items():
        assert factor.card.references, f"{factor_id} cites nothing"


def test_categories_are_valid_and_broad(factors):
    """The SPEC promises coverage across categories, not depth in one."""
    categories = {f.category for f in factors.values()}
    assert categories <= VALID_CATEGORIES
    assert len(categories) >= 6, f"only {len(categories)} categories represented"


def test_fundamental_factors_declare_their_tags(factors):
    """A factor that reads a tag it did not declare escapes the trap
    measurement, which is scoped by the declaration."""
    for factor_id, factor in factors.items():
        if factor.filing_lag_days > 0:
            assert factor.tags, f"{factor_id} declares a lag but no tags"


def test_summary_table_covers_every_registered_factor(factors):
    table = summary_table()
    assert len(table) == len(factors)
    assert set(table["factor_id"]) == set(factors)


def test_sign_convention_is_documented_for_inverted_factors(factors):
    """Size, volatility, turnover and asset growth are negated so that a
    positive IC means the factor predicts returns. The card has to say so, or a
    reader will interpret the sign as a finding."""
    for factor_id in ("log_mktcap", "idio_vol", "turnover", "asset_growth"):
        card = factors[factor_id].card
        text = (card.definition + card.economic_rationale).lower()
        assert "negat" in text or "invert" in text or "long side" in text


def test_cards_state_the_close_price_the_protocol_actually_uses(factors):
    """A hypothesis card is a contract, so a false execution time is worse than none."""
    for factor_id, factor in factors.items():
        assert factor.card.timing["earliest_execution"] == "next_trading_day_close", factor_id
        assert factor.card.timing["execution_price"] == "adjusted_close", factor_id


def test_ttm_uses_four_discrete_quarters_without_counting_fy_and_q4_twice():
    """TTM must turn cumulative SEC contexts into quarters before summing them.

    Q4 is normally FY minus Q3 YTD. Adding FY to Q1/Q2/Q3 would count the first
    three quarters twice while still yielding a perfectly plausible E/P ratio.
    """
    facts = pd.DataFrame(
        [
            (2023, "Q1", "2023-01-01", "2023-03-31", 10.0),
            (2023, "Q2", "2023-01-01", "2023-06-30", 25.0),
            (2023, "Q3", "2023-01-01", "2023-09-30", 45.0),
            (2023, "FY", "2023-01-01", "2023-12-31", 70.0),
            (2024, "Q1", "2024-01-01", "2024-03-31", 12.0),
            (2024, "Q2", "2024-01-01", "2024-06-30", 30.0),
        ],
        columns=["fiscal_year", "fiscal_period", "period_start", "period_end", "value"],
    )
    facts["period_start"] = pd.to_datetime(facts["period_start"])
    facts["period_end"] = pd.to_datetime(facts["period_end"])
    facts["duration_days"] = (facts["period_end"] - facts["period_start"]).dt.days
    facts["filed"] = facts["period_end"] + pd.Timedelta(days=45)

    assert _ttm_value(facts.iloc[:4]) == pytest.approx(70.0)
    assert _ttm_value(facts) == pytest.approx(75.0)


def test_asset_growth_uses_consecutive_annual_contexts_only():
    facts = pd.DataFrame(
        [
            (2022, "FY", "2022-12-31", "2023-02-15", 100.0),
            (2023, "FY", "2023-12-31", "2024-02-15", 110.0),
            # The old implementation selected this latest quarterly context and
            # compared it with the nearest date a year earlier.
            (2024, "Q1", "2024-03-31", "2024-05-15", 990.0),
        ],
        columns=["fiscal_year", "fiscal_period", "period_end", "filed", "value"],
    )

    assert _annual_asset_growth_value(facts) == pytest.approx(-0.10)


def test_asset_growth_rejects_a_missing_fiscal_year():
    facts = pd.DataFrame(
        [
            (2021, "FY", "2021-12-31", "2022-02-15", 100.0),
            (2023, "FY", "2023-12-31", "2024-02-15", 120.0),
        ],
        columns=["fiscal_year", "fiscal_period", "period_end", "filed", "value"],
    )

    assert _annual_asset_growth_value(facts) is None


# ----------------------------------------------------------------------
# A null column must name itself, not the factors that read it
# ----------------------------------------------------------------------
def test_entirely_null_price_column_raises_naming_the_column(store):
    """Four price factors failed at once on the first real run because
    close_adj was never populated. Each reported 'factor produced no values',
    which names the factor when the fault is in the data -- and finding the
    shared cause required noticing which factors read which column."""
    import pandas as pd

    from fza.factors.library import _wide

    prices = store.prices().assign(close_adj=None)
    with pytest.raises(ValueError, match="entirely null"):
        _wide(prices, "close_adj")

    # And the message points at the diagnostic rather than leaving the reader
    # to work out where to look.
    try:
        _wide(prices, "close_adj")
    except ValueError as exc:
        assert "column_coverage" in str(exc)
    assert isinstance(prices, pd.DataFrame)


def test_absent_price_column_lists_what_is_available(store):
    from fza.factors.library import _wide

    with pytest.raises(ValueError, match="absent"):
        _wide(store.prices(), "not_a_column")


def test_column_coverage_reports_a_null_column():
    """The diagnostic the error message points to.

    Built on a store with a deliberately emptied column rather than on the
    shared fixture, whose columns are all populated -- asserting against the
    fixture would make this test pass or fail on how the fixture happens to be
    built rather than on what the method does.
    """
    from fza.store import Store

    with Store() as s:
        prices = pd.DataFrame(
            {
                "ticker": ["AAA", "AAA"],
                "trade_date": pd.to_datetime(["2020-01-02", "2020-01-03"]),
                "open": [1.0, 1.0],
                "high": [1.0, 1.0],
                "low": [1.0, 1.0],
                "close": [1.0, 1.0],
                "close_adj": [None, None],  # the failure mode being reported
                "volume": [1.0, 1.0],
                "shares_out": [1.0, 1.0],
            }
        )
        s.load_prices(prices)
        coverage = s.column_coverage("prices").set_index("column")

    assert coverage.loc["close", "coverage"] == 1.0
    assert coverage.loc["close_adj", "coverage"] == 0.0


def test_the_registry_distinguishes_an_undefined_range_from_a_declared_one(factors):
    """"Undefined" and "checked" must be separable by looking at the table.

    Four factors declare a plausible range and six do not. If the report
    rendered a missing range as blank or as a pass, the six unverified factors
    would be indistinguishable from verified ones -- which is the failure this
    field exists to prevent, one level up.
    """
    table = summary_table().set_index("factor_id")

    declared = {"bm_ratio", "ep_ratio", "roe", "asset_growth"}
    for factor_id, factor in factors.items():
        rendered = table.loc[factor_id, "plausible_range"]
        if factor_id in declared:
            assert factor.plausible_range is not None
            assert rendered != "undefined"
        else:
            assert factor.plausible_range is None
            assert rendered == "undefined"

    # Stated as a count as well, so adding a factor without a range is visible
    # as a change in this number rather than as nothing.
    assert (table["plausible_range"] == "undefined").sum() == 6


# ----------------------------------------------------------------------
# A forward fill that never stops is a second carry-forward
# ----------------------------------------------------------------------
def _panel_going_null(last_good: str) -> pd.DataFrame:
    """One column of daily observations that stops on ``last_good``."""
    idx = pd.date_range("2020-01-01", "2020-12-31", freq="D")
    s = pd.Series(100.0, index=idx)
    s.loc[s.index > pd.Timestamp(last_good)] = None
    return s.to_frame("AAA")


def test_market_closure_carries_but_a_long_suspension_does_not():
    """A calendar gap and a stale security-level quote are different states.

    Four days covers a long weekend or exchange closure and is carried. Four
    months cannot be explained by the trading calendar and is rejected. The
    historical-universe gate separately decides whether the security has exited;
    this test is only about freshness while it remains eligible.
    """
    from fza.factors.library import _at_signal_dates

    panel = _panel_going_null("2020-03-01")
    dates = pd.DatetimeIndex(["2020-03-05", "2020-06-30"])

    unbounded = _at_signal_dates(panel, dates)
    assert unbounded["AAA"].notna().all()  # the old behaviour, still available

    bounded = _at_signal_dates(panel, dates, max_staleness_days=10)
    assert bounded["AAA"].iloc[0] == 100.0  # four days old, a real observation
    assert pd.isna(bounded["AAA"].iloc[1])  # four months old, an invention


def test_brief_suspension_is_carried_within_the_declared_bound():
    """A short halt keeps the last observable quote without opening a new rule."""
    from fza.factors.library import _at_signal_dates

    panel = _panel_going_null("2020-03-01")
    out = _at_signal_dates(
        panel, pd.DatetimeIndex(["2020-03-09"]), max_staleness_days=10
    )

    assert out.loc[pd.Timestamp("2020-03-09"), "AAA"] == 100.0


def test_rolling_quantity_uses_source_freshness_not_calculation_date():
    """Rolling windows can look current while containing only old observations."""
    from fza.factors.library import _at_signal_dates, _derived_at_signal_dates

    observations = _panel_going_null("2020-03-01")
    derived = observations.rolling(60, min_periods=30).std()
    signal_dates = pd.DatetimeIndex(["2020-03-20"])

    # pandas recomputes this row on March 20 from old observations, so checking
    # the derived frame alone mistakes a current calculation for current data.
    assert _at_signal_dates(
        derived, signal_dates, max_staleness_days=10
    )["AAA"].notna().all()
    assert _derived_at_signal_dates(
        derived, observations, signal_dates, max_staleness_days=10
    )["AAA"].isna().all()


def test_the_staleness_bound_is_measured_per_column():
    """Columns go null at different times, and a panel-wide age would be wrong
    for every column but one."""
    from fza.factors.library import _at_signal_dates

    panel = _panel_going_null("2020-03-01")
    panel["BBB"] = 200.0

    out = _at_signal_dates(
        panel, pd.DatetimeIndex(["2020-06-30"]), max_staleness_days=10
    )
    assert pd.isna(out["AAA"].iloc[0])
    assert out["BBB"].iloc[0] == 200.0


def test_a_share_count_that_stopped_yields_no_market_cap():
    """The same thing again, through the factor rather than the helper."""
    from fza.factors.library import _market_cap

    s = Store()
    load_fixture_into(s)
    cut = "2020-06-30"
    tickers = [t for t in s.prices()["ticker"].unique()]
    dead = tickers[0]
    s.con.execute(
        "UPDATE prices SET shares_out = NULL "
        "WHERE ticker = ? AND trade_date > ?",
        [dead, cut],
    )

    caps = _market_cap(s, pd.DatetimeIndex(["2020-06-30", "2021-06-30"]))
    assert pd.notna(caps.loc[pd.Timestamp("2020-06-30"), dead])
    assert pd.isna(caps.loc[pd.Timestamp("2021-06-30"), dead])
    # every other name is untouched
    others = [t for t in tickers if t != dead]
    assert caps.loc[pd.Timestamp("2021-06-30"), others].notna().any()
    s.close()


def test_market_factors_stop_after_the_fixture_quote_is_stale(store, factors):
    """Every production price/volume call site declares freshness explicitly."""
    exit_date = pd.Timestamp(
        store.con.execute(
            "SELECT last_filing FROM securities WHERE ticker = 'TST07'"
        ).fetchone()[0]
    )
    stale_after = exit_date + pd.Timedelta(days=40)

    for factor_id in ("mom_12_1", "mom_6_1", "rev_1m", "idio_vol", "turnover"):
        raw = factors[factor_id].compute(store, SIGNAL_DATES)
        stale = raw.loc[
            (raw["ticker"] == "TST07")
            & (pd.to_datetime(raw["signal_date"]) > stale_after)
        ]
        assert stale.empty, factor_id


def test_idio_vol_does_not_fabricate_zero_returns_across_a_price_gap():
    """A missing quote is not a zero return under any supported pandas version.

    pandas 2.x padded ``pct_change`` inputs by default. With that default, AAA's
    absent middle quote became a zero return and its next real quote produced a
    seemingly valid volatility. Explicit missing semantics must leave AAA
    without a signal while the fully observed control remains available.
    """
    dates = pd.to_datetime(["2020-01-01", "2020-01-02", "2020-01-03"])
    rows = []
    for ticker, observed, closes in (
        ("AAA", [dates[0], dates[2]], [100.0, 110.0]),
        ("BBB", list(dates), [100.0, 101.0, 103.0]),
    ):
        for date, close in zip(observed, closes, strict=True):
            rows.append(
                {
                    "ticker": ticker,
                    "trade_date": date,
                    "open": close,
                    "high": close,
                    "low": close,
                    "close": close,
                    "close_adj": close,
                    "volume": 100.0,
                    "shares_out": 1000.0,
                }
            )

    with Store() as sparse:
        sparse.load_prices(pd.DataFrame(rows))
        result = idiosyncratic_volatility(
            sparse, pd.DatetimeIndex([dates[-1]]), window=2
        )

    assert "AAA" not in set(result["ticker"])
    assert "BBB" in set(result["ticker"])
