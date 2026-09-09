"""Explicit generation controls for sample/cleaning sensitivities."""

from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from fza.pipeline.prepare import prepare_cross_sections
from fza.pipeline.run import comparison_sample_report
from fza.pipeline.vintage import diagnostic_layers, outcome_identity


def raw(names):
    return pd.DataFrame({"ticker": names, "signal_date": pd.Timestamp("2020-01-31"),
                         "value": np.arange(len(names), dtype=float)})


def labels(values):
    panel = values.rename(columns={"value": "prediction"}).copy()
    panel["label"] = panel.ticker.str.removeprefix("S").astype(float) / 100
    panel["formation_session"] = panel.signal_date
    panel["entry_date"] = panel.signal_date + pd.Timedelta(days=1)
    panel["exit_date"] = panel.signal_date + pd.Timedelta(days=30)
    return panel, SimpleNamespace(to_dict=lambda: {"n_output": len(panel)})


def layers(left, right, raw_left=None, raw_right=None, groups=None, n_quantiles=5):
    return diagnostic_layers(
        "synthetic", left, right, raw_left, raw_right, groups=groups,
        label_builder=labels, n_quantiles=n_quantiles,
        sample_report=comparison_sample_report, path_exercised=True,
    )


def test_recleaning_fixed_support_removes_external_name_cleaning_effect():
    a = raw([f"S{i}" for i in range(20)])
    b = raw([f"S{i}" for i in range(21)])
    b.loc[20, "value"] = 10000
    groups = pd.Series({f"S{i}": "a" if i < 10 or i == 20 else "b" for i in range(21)})
    left = labels(prepare_cross_sections(a, groups=groups)[0])[0]
    right = labels(prepare_cross_sections(b, groups=groups)[0])[0]
    result = layers(left, right, a, b, groups)
    assert result["common-observation"]["ic_gap"] != pytest.approx(0)
    support = result["common-support"]
    assert support["outcome_identity"]["status"] == "MATCHED"
    assert support["ic_gap"] == pytest.approx(0, abs=1e-15)
    assert support["cleaning_input_sample"]["identical_observation_keys"] is True
    assert support["cleaning_input_sample"]["common_observations"] == 20
    assert support["cleaning"][0] == support["cleaning"][1]


@pytest.mark.parametrize("column", ["label", "formation_session", "entry_date", "exit_date"])
def test_outcome_mismatch_blocks_comparison(column):
    left = labels(raw([f"S{i}" for i in range(20)]))[0]
    right = left.copy()
    right.loc[0, column] += 1 if column == "label" else pd.Timedelta(days=1)
    result = layers(left, right)
    for name in ("original-process", "common-observation"):
        assert result[name]["outcome_identity"]["status"] == "MISMATCH"
        assert result[name]["ic_gap"] is None
        assert result[name]["ls_sharpe_gap"] is None


def test_missing_outcomes_are_not_equal_by_shared_missingness():
    left = labels(raw([f"S{i}" for i in range(20)]))[0]
    left.loc[0, "label"] = np.nan
    assert outcome_identity(left, left)["status"] == "MISMATCH"
    assert outcome_identity(left.drop(columns="entry_date"), left)["status"] == "NOT_CHECKED"


def test_rebuilding_labels_cannot_hide_invalid_source_outcomes():
    data = raw([f"S{i}" for i in range(20)])
    left = labels(prepare_cross_sections(data)[0])[0]
    right = left.copy()
    right.loc[0, "label"] += 1
    row = layers(left, right, data, data)["common-support"]
    assert row["outcome_identity"]["status"] == "MATCHED"
    assert row["source_outcome_identity"]["status"] == "MISMATCH"
    assert row["ic_gap"] is None
    assert row["reason"] == "source_outcomes_not_verified"


def test_identically_invalid_holding_periods_cannot_pass_identity():
    data = labels(raw([f"S{i}" for i in range(20)]))[0]
    data["exit_date"] = data.entry_date
    assert outcome_identity(data, data)["status"] == "MISMATCH"


def test_common_keys_with_different_ic_eligible_dates_do_not_get_a_gap():
    left = labels(raw([f"S{i}" for i in range(20)]))[0]
    right = left.copy()
    right["prediction"] = 0.0
    row = layers(left, right)["common-observation"]
    assert row["outcome_identity"]["status"] == "MATCHED"
    assert row["ic_gap"] is None
    assert row["reason"] == "metric_dates_differ"


def test_nondefault_quantile_setting_reaches_every_layer():
    data = raw([f"S{i}" for i in range(20)])
    panel = labels(prepare_cross_sections(data)[0])[0]
    result = layers(panel, panel, data, data, n_quantiles=2)
    for row in result.values():
        assert row["pit"]["names_per_quantile_avg"] == 10
        assert row["restated"]["names_per_quantile_avg"] == 10


def test_empty_common_raw_support_is_explicitly_unscorable():
    a = raw([f"S{i}" for i in range(20)])
    b = raw([f"S{i}" for i in range(20, 40)])
    row = layers(labels(a)[0], labels(b)[0], a, b)["common-support"]
    assert row["ic_gap"] is None
    assert row["status"] == "INCONCLUSIVE"
    assert row["reason"] == "no_common_outcomes"
