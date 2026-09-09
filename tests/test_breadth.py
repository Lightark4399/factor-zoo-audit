"""Display policy is scoped to groups and cannot mutate scoring inputs."""

from copy import deepcopy

import pytest

from fza.reporting import breadth_diagnostic


@pytest.mark.parametrize("minimum,dates,status,marker", [
    (3, 12, "THIN_GROUP_WARNING", "[B]"),
    (2, 12, "THIN_GROUP_WARNING", "[B]"),
    (4, 12, "NO_LOW_GROUP_FLAG", ""),
    (None, 12, "UNAVAILABLE", "[B?]"),
    (float("nan"), 12, "UNAVAILABLE", "[B?]"),
    (0, 0, "UNAVAILABLE", "[B?]"),
])
def test_breadth_is_not_a_power_verdict(minimum, dates, status, marker):
    summary = {"names_per_quantile_min": minimum, "n_quantile_dates": dates}
    result = breadth_diagnostic(summary)
    assert result["status"] == status
    assert result["marker"] == marker
    assert result["unit"] == "names_per_retained_date_quantile"
    assert result["threshold_origin"] == "POST_OBSERVATION_DISPLAY_RULE"
    assert result["changes_samples_or_metrics"] is False


def test_breadth_does_not_modify_summary_or_treat_missing_as_pass():
    summary = {"ic_mean": 0.25}
    before = deepcopy(summary)
    assert breadth_diagnostic(summary)["status"] == "UNAVAILABLE"
    assert summary == before
