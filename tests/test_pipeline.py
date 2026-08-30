"""Tests for the cleaning pipeline, the standard protocol and the vintage comparison.

The pipeline's job is to apply the same treatment to every factor, so most of
these tests are about invariance: the same input must produce the same output
regardless of which factor asked, and a comparison must vary exactly one thing.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from fza.factors.registry import load_all
from fza.fixtures import load_fixture_into
from fza.pipeline.prepare import (
    forward_returns,
    neutralise,
    prepare_cross_sections,
    standardise,
    winsorise,
)
from fza.pipeline.protocol import (
    information_coefficient,
    long_short_series,
    monotonicity,
    quantile_portfolios,
    run_protocol,
)
from fza.pipeline.run import (
    ImplausibleMagnitudeError,
    check_plausible_magnitude,
    compare_vintages,
    compute_factor,
)
from fza.store import Store

SIGNAL_DATES = pd.DatetimeIndex(pd.date_range("2019-01-31", "2021-06-30", freq="ME"))


@pytest.fixture(scope="module")
def store():
    s = Store()
    info = load_fixture_into(s)
    s._fixture_info = info
    yield s
    s.close()


@pytest.fixture(scope="module")
def factors():
    return load_all()


# ----------------------------------------------------------------------
# Cleaning primitives
# ----------------------------------------------------------------------
def test_winsorise_clips_both_tails_and_counts():
    v = pd.Series([-100.0, 1.0, 2.0, 3.0, 4.0, 5.0, 500.0])
    clipped, n = winsorise(v, 0.1, 0.9)
    assert clipped.max() < 500.0
    assert clipped.min() > -100.0
    assert n == 2


def test_standardise_gives_zero_mean_unit_sd():
    v = pd.Series([1.0, 2.0, 3.0, 4.0, 5.0])
    z = standardise(v)
    assert z.mean() == pytest.approx(0.0, abs=1e-12)
    assert z.std(ddof=1) == pytest.approx(1.0, abs=1e-12)


def test_standardise_returns_zeros_when_there_is_no_dispersion():
    """A constant cross-section carries no ranking information.

    Zeros propagate that fact; dividing by a zero standard deviation would emit
    noise that looks like a signal.
    """
    assert (standardise(pd.Series([3.0] * 5)) == 0.0).all()


def test_neutralise_removes_the_group_mean():
    v = pd.Series([1.0, 3.0, 10.0, 20.0], index=list("abcd"))
    g = pd.Series(["x", "x", "y", "y"], index=list("abcd"))
    out = neutralise(v, g)
    assert out.loc["a"] == pytest.approx(-1.0)
    assert out.loc["c"] == pytest.approx(-5.0)


def test_neutralise_zeroes_a_group_of_one():
    """A stock alone in its industry has no within-industry comparison."""
    v = pd.Series([1.0, 3.0, 99.0], index=list("abc"))
    g = pd.Series(["x", "x", "lonely"], index=list("abc"))
    assert neutralise(v, g).loc["c"] == pytest.approx(0.0)


def test_empty_factor_raises_rather_than_propagating():
    """An empty factor is always a bug, and it must surface where it happened.

    Returning an empty frame let the emptiness travel several layers before
    failing as a dtype mismatch in a join, which points the reader at the wrong
    file.
    """
    with pytest.raises(ValueError, match="no values"):
        prepare_cross_sections(pd.DataFrame(columns=["ticker", "signal_date", "value"]))


def test_cleaning_reports_attrition(store, factors):
    raw = factors["bm_ratio"].compute(store, SIGNAL_DATES)
    _, report = prepare_cross_sections(raw)
    assert report.n_input > 0
    assert 0 < report.retention <= 1.0
    assert report.n_dates > 0


# ----------------------------------------------------------------------
# Forward returns and the execution lag
# ----------------------------------------------------------------------
def test_forward_returns_start_after_the_execution_lag(store):
    """A signal formed at a close cannot trade at that close."""
    px = store.prices()
    rets = forward_returns(px, SIGNAL_DATES[:5], horizon_days=21, execution_lag=1)
    assert (pd.to_datetime(rets["entry_date"]) > pd.to_datetime(rets["signal_date"])).all()


def test_zero_lag_enters_on_the_signal_date(store):
    """Available so the execution-timing audit can price the assumption."""
    px = store.prices()
    rets = forward_returns(px, SIGNAL_DATES[:5], horizon_days=21, execution_lag=0)
    assert (pd.to_datetime(rets["entry_date"]) >= pd.to_datetime(rets["signal_date"])).all()


def test_empty_forward_returns_keep_their_dtypes(store):
    """An empty frame with object columns fails a join with a confusing error."""
    px = store.prices()
    far_future = pd.DatetimeIndex([pd.Timestamp("2099-01-31")])
    rets = forward_returns(px, far_future)
    assert rets.empty
    assert str(rets["signal_date"].dtype).startswith("datetime64")


# ----------------------------------------------------------------------
# Protocol
# ----------------------------------------------------------------------
def test_quantiles_and_long_short_are_consistent(store, factors):
    run = compute_factor(factors["bm_ratio"], store, SIGNAL_DATES)
    q = quantile_portfolios(run.panel, n_quantiles=5)
    ls = long_short_series(q, n_quantiles=5)
    assert not q.empty
    assert len(ls) > 0
    assert set(q["quantile"]) == {0, 1, 2, 3, 4}


def test_protocol_reports_the_distribution_of_quantile_breadth():
    """An average must not hide a month whose quantile portfolios nearly vanish."""
    rows = []
    for date, n_names in [("2024-01-31", 20), ("2024-02-29", 25), ("2024-03-31", 30)]:
        for i in range(n_names):
            rows.append(
                {
                    "ticker": f"T{i:03d}",
                    "signal_date": pd.Timestamp(date),
                    "prediction": float(i),
                    "label": float(i) / 100.0,
                }
            )
    panel = pd.DataFrame(rows)

    summary = run_protocol("breadth", panel).summary

    assert summary["names_per_quantile_avg"] == pytest.approx(5.0)
    assert summary["names_per_quantile_min"] == 4
    assert summary["names_per_quantile_p10"] >= 4
    assert summary["names_per_quantile_median"] == 5
    assert summary["names_per_quantile_p90"] <= 6
    assert summary["names_per_quantile_max"] == 6
    assert summary["n_dates_dropped_insufficient_cross_section"] == 0


def test_perfect_signal_is_monotone_and_has_ic_one():
    """A factor equal to the forward return must score at the ceiling."""
    dates = pd.date_range("2020-01-31", periods=12, freq="ME")
    rows = []
    rng = np.random.default_rng(0)
    for d in dates:
        for i in range(50):
            r = rng.normal()
            rows.append({"ticker": f"T{i:02d}", "signal_date": d, "prediction": r, "label": r})
    panel = pd.DataFrame(rows)

    res = run_protocol("perfect", panel)
    assert res.summary["ic_mean"] == pytest.approx(1.0, abs=1e-9)
    assert res.monotonicity_rho == pytest.approx(1.0, abs=1e-9)
    assert res.summary["ls_mean"] > 0


def test_independent_signal_has_ic_near_zero():
    dates = pd.date_range("2020-01-31", periods=24, freq="ME")
    rng = np.random.default_rng(1)
    rows = []
    for d in dates:
        for i in range(60):
            rows.append(
                {
                    "ticker": f"T{i:02d}",
                    "signal_date": d,
                    "prediction": rng.normal(),
                    "label": rng.normal(),
                }
            )
    res = run_protocol("noise", pd.DataFrame(rows))
    assert abs(res.summary["ic_mean"]) < 0.1


def test_monotonicity_detects_a_non_monotone_pattern():
    """A factor whose extremes differ but whose middle is unordered."""
    q = pd.DataFrame(
        {
            "signal_date": [pd.Timestamp("2020-01-31")] * 5,
            "quantile": [0, 1, 2, 3, 4],
            "ret": [0.01, 0.05, 0.02, 0.04, 0.03],
            "n": [10] * 5,
        }
    )
    rho, _ = monotonicity(q)
    assert abs(rho) < 0.6


def test_ic_is_rank_based(store, factors):
    """Spearman, so a monotone rescaling of the signal leaves it unchanged."""
    run = compute_factor(factors["bm_ratio"], store, SIGNAL_DATES)
    base = information_coefficient(run.panel).mean()
    rescaled = run.panel.assign(prediction=np.exp(run.panel["prediction"]))
    assert information_coefficient(rescaled).mean() == pytest.approx(base, abs=1e-9)


# ----------------------------------------------------------------------
# Vintage comparison
# ----------------------------------------------------------------------
def test_price_only_factor_is_not_applicable(store, factors):
    """Momentum reads no fundamentals, so this channel cannot apply to it.

    Reporting a gap of zero would invite the reader to conclude the factor is
    clean, when the truth is that this particular test says nothing about it.
    """
    c = compare_vintages(factors["mom_12_1"], store, SIGNAL_DATES)
    assert c.applicable is False
    assert c.passed is None
    assert "NOT APPLICABLE" in c.verdict


def test_vintage_comparison_scores_both_arms_on_shared_dates(store, factors):
    """Otherwise the gap is partly a comparison of different samples."""
    c = compare_vintages(factors["bm_ratio"], store, SIGNAL_DATES)
    assert c.applicable is True
    assert c.detail["n_shared_dates"] > 0
    assert c.pit.n_dates == c.restated.n_dates


def test_leaking_path_relaxes_only_the_filing_constraint(store, factors):
    """The substitution must vary exactly one thing.

    An earlier version also allowed the restated arm to read accounting periods
    that had not ended yet, so the measured gap mixed two different leaks and the
    cruder one dominated.
    """
    c = compare_vintages(factors["bm_ratio"], store, SIGNAL_DATES)
    # Both arms see the same number of observations; only the values differ.
    assert c.pit.n_observations == c.restated.n_observations


def test_restatements_without_predictive_content_produce_no_gap(store, factors):
    """The control. Fixture prices are a random walk, so the revised values
    cannot predict returns, and reading them early must confer no advantage."""
    c = compare_vintages(factors["bm_ratio"], store, SIGNAL_DATES)
    assert abs(c.ic_gap) < 0.01
    assert c.passed is True


def test_restated_read_is_logged(store, factors):
    """A factor run can then state that it never came through the restated view."""
    before = store.access.restated_reads
    compare_vintages(factors["bm_ratio"], store, SIGNAL_DATES)
    assert store.access.restated_reads > before
    assert any("bm_ratio" in c for c in store.access.restated_callers)


# ----------------------------------------------------------------------
# Magnitude assertions -- the check incident 12 did not have
# ----------------------------------------------------------------------
def test_the_market_cap_of_incident_12_is_caught(store):
    """The regression test for incident 12, and the reason the check exists.

    A constraint that cannot catch the failure it was written for is decoration.
    So this reproduces the fault rather than describing it: market capitalisation
    understated by the factor actually measured on the real data -- an implied
    $20.9m against an actual $80.0bn for Apple at the 2014-06-30 signal date --
    and asserts that `bm_ratio` now refuses instead of returning an IC.

    Before the check, this same input produced +0.0365 with a monotonicity of
    +0.70, a result agreeing with the value literature, and nothing anywhere
    objected.
    """
    understatement = 3832.0  # measured, see AI_NOTES incident 12

    broken = Store()
    load_fixture_into(broken)
    broken.con.execute(f"UPDATE prices SET close = close / {understatement}")

    factor = load_all()["bm_ratio"]
    raw = factor.compute(broken, SIGNAL_DATES)
    assert not raw.empty, "the fixture must still produce values, only wrong ones"

    with pytest.raises(ImplausibleMagnitudeError) as exc:
        check_plausible_magnitude(factor, raw)

    message = str(exc.value)
    assert "bm_ratio" in message
    assert "0.01" in message and "100" in message
    # It must point at the data rather than at the factor, which is the mistake
    # the error in incident 11 made.
    assert "data problem" in message

    # And the same fault stops the full run, not just the standalone check.
    with pytest.raises(ImplausibleMagnitudeError):
        compute_factor(factor, broken, SIGNAL_DATES)
    broken.close()


def test_an_undeclared_range_is_reported_as_unchecked_not_as_passing(store):
    """`None` means undefined, which is a different state from verified.

    The same distinction the store keeps between a null share count and a zero
    one. Collapsing the two would make the check weakest exactly where nobody
    has yet thought about the factor.
    """
    factor = load_all()["mom_12_1"]
    assert factor.plausible_range is None

    result = check_plausible_magnitude(factor, factor.compute(store, SIGNAL_DATES))
    assert result["checked"] is False
    assert "unverified" in result["note"]
    assert "share_outside" not in result, "an unchecked factor has no pass rate"


def test_a_declared_range_reports_its_pass_rate(store):
    """A checked factor carries the numbers behind the verdict, not just a flag."""
    factor = load_all()["bm_ratio"]
    result = check_plausible_magnitude(factor, factor.compute(store, SIGNAL_DATES))

    assert result["checked"] is True
    assert result["range"] == (0.01, 100.0)
    assert result["n_values"] > 0
    assert result["share_outside"] == 0.0


def test_a_few_out_of_range_values_are_tolerated_but_counted(store):
    """One bad row is a bad row; a systematically wrong column is a bug.

    The tolerance is what separates them, so it has to be exercised from both
    sides rather than assumed.
    """
    factor = load_all()["bm_ratio"]
    raw = factor.compute(store, SIGNAL_DATES).copy().reset_index(drop=True)
    n_bad = int(len(raw) * 0.005)
    raw.loc[: n_bad - 1, "value"] = 5752.68

    result = check_plausible_magnitude(factor, raw, max_share=0.01)
    assert result["n_outside"] == n_bad
    assert 0 < result["share_outside"] < 0.01

    with pytest.raises(ImplausibleMagnitudeError):
        check_plausible_magnitude(factor, raw, max_share=0.001)
