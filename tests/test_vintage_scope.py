"""Observation-scope properties and the actual comparison-runner call path.

Explicit synthetic panels, not archived real-data outputs, are the oracle.
"""

from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

import fza.pipeline.run as runner
from fza.pipeline.protocol import run_protocol


def panel(names, date="2020-01-31", reverse=False):
    x = np.arange(len(names), dtype=float)
    return pd.DataFrame({
        "ticker": names, "signal_date": pd.Timestamp(date),
        "prediction": -x if reverse else x, "label": x / 100,
        "formation_session": pd.Timestamp(date),
        "entry_date": pd.Timestamp(date) + pd.Timedelta(days=1),
        "exit_date": pd.Timestamp(date) + pd.Timedelta(days=30),
    })


def compare_panels(monkeypatch, pit, restated, exercised=True, n_quantiles=5):
    """Run the real comparator with controlled panels from its compute boundary."""
    fundamentals = pd.DataFrame({
        "cik": ["1"], "tag": ["assets"],
        "period_end": [pd.Timestamp("2019-12-31")],
    })
    store = SimpleNamespace(
        fundamentals_asof=lambda *a, **k: fundamentals,
        fundamentals_history_asof=lambda *a, **k: fundamentals,
        fundamentals_restated=lambda **k: fundamentals,
    )
    original = store.fundamentals_asof
    original_history = store.fundamentals_history_asof
    membership = object()
    monkeypatch.setattr(runner, "historical_universe_membership", lambda *a: membership)

    def compute(factor, store, dates, **kwargs):
        assert kwargs["universe_membership"] is membership
        if exercised:
            store.fundamentals_asof(pd.Timestamp("2020-12-31"))
        data = pit if kwargs["vintage"] == "pit" else restated
        return SimpleNamespace(
            panel=data, protocol=run_protocol(factor.factor_id, data),
            universe_filter=SimpleNamespace(
                membership_key_hash="same", n_excluded_outside_universe=0,
            ),
            read_path_check={"n_violations": 0}, naive_trap={"n_trap_rows": 0},
        )

    monkeypatch.setattr(runner, "compute_factor", compute)
    result = runner.compare_vintages(
        SimpleNamespace(factor_id="synthetic", uses_fundamentals=True), store,
        pd.DatetimeIndex(["2020-01-31"]),
        n_quantiles=n_quantiles,
    )
    assert store.fundamentals_asof is original
    assert store.fundamentals_history_asof is original_history
    return result


def test_requested_quantiles_reach_runner_rescoring_and_layers(monkeypatch):
    data = panel([f"S{i}" for i in range(20)])
    result = compare_panels(monkeypatch, data, data, n_quantiles=2)
    assert result.pit.summary["names_per_quantile_avg"] == 10
    for name in ("original-process", "common-observation"):
        assert result.detail["layers"][name]["pit"]["names_per_quantile_avg"] == 10


def test_same_dates_and_counts_do_not_establish_same_observations():
    left, right = panel(["A", "B"]), panel(["B", "C"])
    report = runner.comparison_sample_report(left, right)
    assert report["pit_observations"] == report["restated_observations"] == 2
    assert report["common_observations"] == 1
    assert report["pit_only_observations"] == report["restated_only_observations"] == 1
    assert report["identical_observation_keys"] is False
    assert report["pit_key_hash"] != report["restated_key_hash"]
    assert report == runner.comparison_sample_report(left.iloc[::-1], right.iloc[::-1])


@pytest.mark.parametrize("invalid", ["duplicate", "null"])
def test_ambiguous_observation_keys_fail_closed(invalid):
    data = panel(["A", "A"] if invalid == "duplicate" else ["A", None])
    with pytest.raises(ValueError, match="non-null and unique"):
        runner.comparison_sample_report(data, data)


def test_runner_discloses_asymmetric_samples_without_changing_original_scores(monkeypatch):
    left = panel([f"S{i}" for i in range(15)])
    right = panel([f"S{i}" for i in range(25)])
    result = compare_panels(monkeypatch, left, right)
    sample = result.detail["sample_comparison"]
    assert sample["pit_observations"] == 15
    assert sample["restated_observations"] == 25
    assert sample["common_observations"] == 15
    assert sample["restated_only_observations"] == 10
    assert sample["cleaning_scope"] == "ARM_SPECIFIC_INPUT_KEYS"
    assert sample["label_and_holding_period_identity"] == "MATCHED"
    for protocol, original in [(result.pit, left), (result.restated, right)]:
        expected = run_protocol("synthetic", original)
        pd.testing.assert_series_equal(protocol.ic_series, expected.ic_series)
        pd.testing.assert_frame_equal(protocol.quantile_returns, expected.quantile_returns)
    assert result.to_dict()["sample_comparison"] == sample


def test_no_shared_dates_is_unscorable_not_fallback_to_unpaired_scores(monkeypatch):
    names = [f"S{i}" for i in range(15)]
    result = compare_panels(monkeypatch, panel(names), panel(names, "2020-02-29"))
    assert result.passed is None
    assert "no shared signal dates" in result.verdict
    assert np.isnan(result.ic_gap)
    assert result.pit.n_observations == result.restated.n_observations == 0
    assert result.detail["sample_comparison"]["pit_observations_before_date_alignment"] == 15


def test_declared_fundamentals_without_exercised_path_cannot_pass(monkeypatch):
    data = panel([f"S{i}" for i in range(15)])
    result = compare_panels(monkeypatch, data, data, exercised=False)
    assert result.applicable is False
    assert result.passed is None
    assert np.isnan(result.ic_gap)
    assert result.detail["read_path_coverage"] == "NOT_EXERCISED"
    assert sum(result.detail["substituted_read_calls"].values()) == 0


@pytest.mark.parametrize("reverse_pit,reverse_restated,passed", [
    (True, False, False), (False, True, True), (False, False, True),
])
def test_threshold_verdicts_never_claim_significance_or_absence_of_information(
    monkeypatch, reverse_pit, reverse_restated, passed,
):
    names = [f"S{i}" for i in range(15)]
    result = compare_panels(
        monkeypatch, panel(names, reverse=reverse_pit), panel(names, reverse=reverse_restated),
    )
    assert result.passed is passed
    assert "diagnostic threshold" in result.verdict
    assert result.detail["threshold_kind"] == "PRECONFIGURED_DIAGNOSTIC_NOT_SIGNIFICANCE_TEST"
    assert "conferred no advantage" not in result.verdict
    assert "carried no information" not in result.verdict
    assert "is information that was not available" not in result.verdict


def test_exercised_shared_dates_with_unscorable_ic_is_inconclusive(monkeypatch):
    names = [f"S{i}" for i in range(15)]
    flat = panel(names).assign(prediction=0.0)  # constant ranks: no finite IC
    result = compare_panels(monkeypatch, panel(names), flat)
    assert result.applicable is True
    assert result.detail["read_path_coverage"] == "EXERCISED"
    assert result.detail["n_shared_dates"] == 1
    assert np.isnan(result.restated.summary["ic_mean"])
    assert result.passed is None
    assert result.verdict == "INCONCLUSIVE: metric_unscorable."
