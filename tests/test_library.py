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

from fza.factors.registry import VALID_CATEGORIES, all_factors, load_all, summary_table
from fza.fixtures import load_fixture_into
from fza.pipeline.run import compute_factor
from fza.store import Store

SIGNAL_DATES = pd.DatetimeIndex(pd.date_range("2019-06-30", "2021-12-31", freq="ME"))


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


def test_a_value_is_not_carried_past_the_staleness_bound():
    """The bug the ingest fix did not reach.

    ``attach_shares_outstanding`` nulls a share count older than 400 days, and
    the factor layer then forward-filled the resulting null away: Berkshire's
    count stops in 2012 and its market cap was still being reported in 2026. A
    null that means "no observation" must survive the fill that exists to bridge
    a missing quote. See AI_NOTES incident 13.
    """
    from fza.factors.library import _at_signal_dates

    panel = _panel_going_null("2020-03-01")
    dates = pd.DatetimeIndex(["2020-03-05", "2020-06-30"])

    unbounded = _at_signal_dates(panel, dates)
    assert unbounded["AAA"].notna().all()  # the old behaviour, still available

    bounded = _at_signal_dates(panel, dates, max_staleness_days=10)
    assert bounded["AAA"].iloc[0] == 100.0  # four days old, a real observation
    assert pd.isna(bounded["AAA"].iloc[1])  # four months old, an invention


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
