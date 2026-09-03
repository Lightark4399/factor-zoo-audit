"""Tests for the cleaning pipeline, the standard protocol and the vintage comparison.

The pipeline's job is to apply the same treatment to every factor, so most of
these tests are about invariance: the same input must produce the same output
regardless of which factor asked, and a comparison must vary exactly one thing.
"""

from __future__ import annotations

import dataclasses

import numpy as np
import pandas as pd
import pytest

from fza.factors.registry import load_all
from fza.fixtures import load_fixture_into
from fza.pipeline.prepare import (
    build_panel_with_report,
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
    historical_universe_membership,
)
from fza.store import Store

SIGNAL_DATES = pd.DatetimeIndex(
    pd.date_range("2019-01-31", "2021-06-30", freq=pd.offsets.MonthEnd())
)


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
# Historical-universe gate
# ----------------------------------------------------------------------
def _fixture_exit_date(store) -> pd.Timestamp:
    return pd.Timestamp(
        store.con.execute(
            "SELECT last_filing FROM securities WHERE ticker = 'TST07'"
        ).fetchone()[0]
    )


def test_universe_gate_reports_and_removes_post_exit_factor_rows(store, factors):
    """The existing delisting fixture must reach the factor pipeline.

    Before the gate was wired, ``asset_growth`` produced fourteen post-exit
    rows for TST07. They passed cleaning, changed 546 surviving z-scores and
    disappeared only at the label join. The exact buggy counts belong in the
    diagnostic capture, not in this assertion; the invariant is simply that no
    post-exit key can survive the eligibility gate.
    """
    exit_date = _fixture_exit_date(store)
    run = compute_factor(factors["asset_growth"], store, SIGNAL_DATES)

    assert run.universe_filter.n_input > run.universe_filter.n_output
    assert run.universe_filter.n_excluded_outside_universe > 0
    assert run.universe_filter.detail["excluded_by_date"]
    assert not (
        (run.values["ticker"] == "TST07")
        & (run.values["signal_date"] > exit_date)
    ).any()


def test_post_exit_ghost_is_identical_to_fully_removing_the_security(store, factors):
    """An ineligible raw value cannot move any surviving result.

    The two inputs differ only by a huge but physically ordinary-looking value
    for the exited security. After the historical-universe gate, the cleaned
    cross-sections, labels and protocol summary must be identical to deleting
    that row at source.
    """
    factor = factors["asset_growth"]
    exit_date = _fixture_exit_date(store)

    def with_ghost(s, dates):
        raw = factor.compute(s, dates).copy()
        mask = (raw["ticker"] == "TST07") & (
            pd.to_datetime(raw["signal_date"]) > exit_date
        )
        raw.loc[mask, "value"] = 9.0
        assert mask.any(), "fixture must produce a post-exit value to exercise the gate"
        return raw

    def without_ghost(s, dates):
        raw = with_ghost(s, dates)
        return raw.loc[
            ~(
                (raw["ticker"] == "TST07")
                & (pd.to_datetime(raw["signal_date"]) > exit_date)
            )
        ].copy()

    included = compute_factor(
        dataclasses.replace(factor, compute=with_ghost), store, SIGNAL_DATES
    )
    removed = compute_factor(
        dataclasses.replace(factor, compute=without_ghost), store, SIGNAL_DATES
    )

    pd.testing.assert_frame_equal(included.values, removed.values)
    pd.testing.assert_frame_equal(included.panel, removed.panel)
    assert included.protocol.summary == removed.protocol.summary


def test_post_exit_ghost_cannot_enter_or_displace_magnitude_extremes(store, factors):
    """Eligibility precedes even the raw-value magnitude check.

    A ghost is made larger than every genuine outlier. Both the input retaining
    it and the counterfactual deleting it must report the same top-N genuine
    extremes, with no TST07 row present.
    """
    factor = factors["asset_growth"]
    exit_date = _fixture_exit_date(store)
    _, hi = factor.plausible_range

    def broken_with_ghost(s, dates):
        raw = factor.compute(s, dates).copy().reset_index(drop=True)
        ghost = (raw["ticker"] == "TST07") & (
            pd.to_datetime(raw["signal_date"]) > exit_date
        )
        raw.loc[ghost, "value"] = 1e20
        genuine = raw.index[raw["ticker"] != "TST07"][:20]
        raw.loc[genuine, "value"] = hi + 100 + np.arange(len(genuine))
        assert ghost.any()
        return raw

    def broken_without_ghost(s, dates):
        raw = broken_with_ghost(s, dates)
        ghost = (raw["ticker"] == "TST07") & (
            pd.to_datetime(raw["signal_date"]) > exit_date
        )
        return raw.loc[~ghost].copy()

    with pytest.raises(ImplausibleMagnitudeError) as included:
        compute_factor(
            dataclasses.replace(factor, compute=broken_with_ghost), store, SIGNAL_DATES
        )
    with pytest.raises(ImplausibleMagnitudeError) as removed:
        compute_factor(
            dataclasses.replace(factor, compute=broken_without_ghost), store, SIGNAL_DATES
        )

    assert included.value.detail["worst"] == removed.value.detail["worst"]
    assert all(row[0] != "TST07" for row in included.value.detail["worst"])
    assert included.value.detail["universe_filter"][
        "n_excluded_outside_universe"
    ] > 0


# ----------------------------------------------------------------------
# Forward returns and the execution lag
# ----------------------------------------------------------------------
def test_forward_returns_start_after_the_execution_lag(store):
    """A signal formed at a close cannot trade at that close."""
    px = store.prices()
    rets = forward_returns(
        px, SIGNAL_DATES[:5], horizon_sessions=21, execution_lag_sessions=1
    )
    assert (rets["formation_session"] <= rets["signal_date"]).all()
    assert (rets["entry_date"] > rets["formation_session"]).all()
    assert (pd.to_datetime(rets["entry_date"]) > pd.to_datetime(rets["signal_date"])).all()


def test_zero_lag_enters_on_the_formation_session(store):
    """Available so the execution-timing audit can price the assumption."""
    px = store.prices()
    rets = forward_returns(
        px, SIGNAL_DATES[:5], horizon_sessions=21, execution_lag_sessions=0
    )
    assert (rets["entry_date"] == rets["formation_session"]).all()
    assert (pd.to_datetime(rets["entry_date"]) <= pd.to_datetime(rets["signal_date"])).all()


def test_weekend_month_end_lag_one_enters_on_monday_not_tuesday():
    prices = pd.DataFrame(
        {
            "ticker": ["A", "A", "A"],
            "trade_date": pd.to_datetime(
                ["2023-12-29", "2024-01-02", "2024-01-03"]
            ),
            "close_adj": [10.0, 11.0, 12.0],
        }
    )

    result = forward_returns(
        prices,
        pd.DatetimeIndex(["2023-12-31"]),
        horizon_sessions=1,
        execution_lag_sessions=1,
    ).iloc[0]

    assert result["formation_session"] == pd.Timestamp("2023-12-29")
    assert result["entry_date"] == pd.Timestamp("2024-01-02")
    assert result["exit_date"] == pd.Timestamp("2024-01-03")


def test_horizon_counts_market_sessions_not_calendar_days():
    sessions = pd.to_datetime(
        ["2024-01-05", "2024-01-08", "2024-01-09", "2024-01-10"]
    )
    prices = pd.DataFrame(
        {"ticker": "A", "trade_date": sessions, "close_adj": [10.0, 11.0, 12.0, 13.0]}
    )

    result = forward_returns(
        prices,
        pd.DatetimeIndex(["2024-01-05"]),
        horizon_sessions=2,
        execution_lag_sessions=1,
    ).iloc[0]

    assert result["entry_date"] == pd.Timestamp("2024-01-08")
    assert result["exit_date"] == pd.Timestamp("2024-01-10")


def test_empty_forward_returns_keep_their_dtypes(store):
    """An empty frame with object columns fails a join with a confusing error."""
    px = store.prices()
    far_future = pd.DatetimeIndex([pd.Timestamp("2099-01-31")])
    rets = forward_returns(px, far_future)
    assert rets.empty
    assert str(rets["signal_date"].dtype).startswith("datetime64")


def test_label_join_counts_each_missing_return_outcome():
    """No signal row may disappear from an inner join without a reason."""
    dates = pd.to_datetime(["2024-01-02", "2024-01-03", "2024-01-04"])
    observations = {
        "A": {dates[0]: 10.0, dates[1]: 11.0},
        "B": {dates[0]: 10.0},
        "D": {dates[0]: 0.0, dates[1]: 1.0},
        "E": {dates[1]: 10.0},
        "F": {dates[2]: 10.0},
    }
    price_rows = []
    for ticker, series in observations.items():
        for date, close in series.items():
            price_rows.append(
                {"ticker": ticker, "trade_date": date, "close_adj": close}
            )
    factors = pd.DataFrame(
        {
            "ticker": ["A", "B", "C", "D", "E", "F"],
            "signal_date": dates[0],
            "value": np.arange(6, dtype=float),
        }
    )

    panel, report = build_panel_with_report(
        factors,
        pd.DataFrame(price_rows),
        horizon_sessions=1,
        execution_lag_sessions=0,
    )

    assert panel["ticker"].tolist() == ["A"]
    assert report.n_input == 6
    assert report.n_output == 1
    assert report.n_dropped_without_label == 5
    assert report.outcome_counts == {
        "matched": 1,
        "missing_exit_price": 1,
        "no_price_history": 1,
        "nonfinite_return": 1,
        "missing_entry_price": 1,
        "missing_entry_and_exit_price": 1,
    }


def test_label_join_counts_dates_without_a_full_horizon():
    prices = pd.DataFrame(
        {
            "ticker": ["A", "A"],
            "trade_date": pd.to_datetime(["2024-01-02", "2024-01-03"]),
            "close_adj": [10.0, 11.0],
        }
    )
    factors = pd.DataFrame(
        {"ticker": ["A"], "signal_date": [pd.Timestamp("2024-01-03")], "value": [1.0]}
    )

    panel, report = build_panel_with_report(
        factors, prices, horizon_sessions=1, execution_lag_sessions=0
    )

    assert panel.empty
    assert report.outcome_counts == {"no_full_horizon": 1}


def test_label_join_counts_signal_dates_before_the_market_calendar():
    prices = pd.DataFrame(
        {
            "ticker": ["A", "A"],
            "trade_date": pd.to_datetime(["2024-01-02", "2024-01-03"]),
            "close_adj": [10.0, 11.0],
        }
    )
    factors = pd.DataFrame(
        {"ticker": ["A"], "signal_date": [pd.Timestamp("2024-01-01")], "value": [1.0]}
    )

    panel, report = build_panel_with_report(
        factors, prices, horizon_sessions=1, execution_lag_sessions=0
    )

    assert panel.empty
    assert report.outcome_counts == {"no_formation_session": 1}


def test_factor_run_exposes_label_attrition_separately(store, factors):
    run = compute_factor(factors["asset_growth"], store, SIGNAL_DATES)

    assert run.label_join.n_input == run.cleaning.n_output
    assert run.label_join.n_output == len(run.panel)
    assert sum(run.label_join.outcome_counts.values()) == run.label_join.n_input


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
    dates = pd.date_range("2020-01-31", periods=12, freq=pd.offsets.MonthEnd())
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
    dates = pd.date_range("2020-01-31", periods=24, freq=pd.offsets.MonthEnd())
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
    assert len(c.detail["universe_membership_key_hash"]) == 64


def test_vintage_comparison_builds_one_membership_panel(
    store, factors, monkeypatch
):
    """Vintage is the only dimension the PIT/restated comparison may vary."""
    import fza.pipeline.run as runner

    original = historical_universe_membership
    calls = 0

    def counted_membership(s, dates):
        nonlocal calls
        calls += 1
        return original(s, dates)

    monkeypatch.setattr(runner, "historical_universe_membership", counted_membership)
    comparison = runner.compare_vintages(factors["bm_ratio"], store, SIGNAL_DATES)

    assert calls == 1
    assert comparison.detail["universe_membership_key_hash"]


def test_leaking_path_relaxes_only_the_filing_constraint(store, factors):
    """The substitution must vary exactly one thing.

    An earlier version also allowed the restated arm to read accounting periods
    that had not ended yet, so the measured gap mixed two different leaks and the
    cruder one dominated.
    """
    c = compare_vintages(factors["bm_ratio"], store, SIGNAL_DATES)
    # Both arms see the same number of observations; only the values differ.
    assert c.pit.n_observations == c.restated.n_observations


def test_ttm_leaking_path_changes_only_filing_visibility(factors):
    """TTM must receive the same contexts on both vintage arms.

    A row-count assertion cannot detect a start/end context being silently
    replaced by another row.  Use a date after the original FY filing but before
    its amendment so both arms must expose the same context keys; the restated
    arm may differ only by selecting the future-filed version of that FY context.
    """
    audited = Store()
    info = load_fixture_into(audited)
    cik = info["restated_cik"]
    original = audited.con.execute(
        """
        SELECT * FROM fundamentals
        WHERE cik = ? AND tag = 'NetIncomeLoss'
          AND period_start = DATE '2018-01-01'
          AND period_end = DATE '2018-12-31'
        """,
        [cik],
    ).df()
    assert len(original) == 1

    amendment = original.copy()
    amendment["filed"] = pd.Timestamp("2019-08-13")
    amendment["value"] = amendment["value"] * 0.5
    amendment["form"] = "10-K/A"
    amendment["accession"] = f"{cik}-2018-12-31-amended-income"
    audited.load_fundamentals(amendment)

    audit_signal = pd.Timestamp("2019-02-28")
    audit_asof = audit_signal - pd.Timedelta(days=2)
    seen: list[pd.DataFrame] = []
    ep_ratio = factors["ep_ratio"]

    def recording_compute(store, signal_dates):
        seen.append(
            store.fundamentals_history_asof(
                audit_asof,
                tags=["NetIncomeLoss"],
                intended_signal_date=audit_signal,
            ).copy()
        )
        return ep_ratio.compute(store, signal_dates)

    instrumented = dataclasses.replace(ep_ratio, compute=recording_compute)
    signal_dates = pd.DatetimeIndex(
        pd.date_range("2019-02-28", "2019-07-31", freq=pd.offsets.MonthEnd())
    )
    try:
        compare_vintages(instrumented, audited, signal_dates)
    finally:
        audited.close()

    assert len(seen) == 2
    pit, restated = seen
    context = ["cik", "tag", "period_start", "period_end", "fact_type"]
    pit = pit.sort_values(context).set_index(context)
    restated = restated.sort_values(context).set_index(context)

    assert pit.index.equals(restated.index)
    assert (
        pd.to_datetime(pit.index.get_level_values("period_end")) <= audit_asof
    ).all()
    assert (
        pd.to_datetime(restated.index.get_level_values("period_end")) <= audit_asof
    ).all()
    assert (pd.to_datetime(pit["filed"]) <= audit_asof).all()

    changed = pit.index[
        pd.to_datetime(pit["filed"]).to_numpy()
        != pd.to_datetime(restated["filed"]).to_numpy()
    ].tolist()
    expected = (
        cik,
        "NetIncomeLoss",
        pd.Timestamp("2018-01-01"),
        pd.Timestamp("2018-12-31"),
        "duration",
    )
    assert changed == [expected]
    assert pd.Timestamp(restated.loc[expected, "filed"]) > audit_asof

    stable = [
        "fiscal_year",
        "fiscal_period",
        "unit",
        "source_namespace",
        "frame",
        "duration_days",
    ]
    pd.testing.assert_frame_equal(pit[stable], restated[stable])


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
    assert "0.0001" in message and "100" in message
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
    assert result["range"] == (1e-4, 100.0)
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


def test_bm_magnitude_range_is_deliberately_asymmetric():
    """A real near-zero book value passes; a collapsed positive one does not.

    Buybacks can drive book equity close to zero without corrupting either side
    of the ratio. The upper tail has no equivalent ordinary path, so the range
    must encode two different failure modes rather than mirror one threshold.
    """
    factor = load_all()["bm_ratio"]
    raw_rows = {
        "ticker": ["LOW", "MID"],
        "signal_date": pd.to_datetime(["2025-01-31", "2025-01-31"]),
    }
    plausible_buyback_tail = pd.DataFrame(
        {**raw_rows, "value": [0.005, 1.0]}
    )

    result = check_plausible_magnitude(
        factor, plausible_buyback_tail, max_share=0.0
    )
    assert result["range"] == (1e-4, 100.0)
    assert result["n_outside"] == 0

    collapsed_positive_book = pd.DataFrame(
        {**raw_rows, "value": [9e-5, 1.0]}
    )
    with pytest.raises(ImplausibleMagnitudeError):
        check_plausible_magnitude(
            factor, collapsed_positive_book, max_share=0.0
        )
