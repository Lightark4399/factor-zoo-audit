"""Generative rule boundaries and the live runner guard, not saved outputs."""

from dataclasses import replace

import pandas as pd
import pytest

from fza.factors.plausibility import PlausibilityRule, evaluate_rule
from fza.factors.registry import load_all
from fza.pipeline.run import ImplausibleMagnitudeError, check_plausible_magnitude


def rule(**kwargs):
    return PlausibilityRule(**{
        "rule_id": "test", "kind": "construction", "severity": "error",
        "lower": None, "upper": 0., "rationale": "Synthetic nonpositive output.",
        **kwargs,
    })


@pytest.mark.parametrize("change", [
    {"kind": "unknown"}, {"severity": "unknown"}, {"rationale": " "},
    {"rule_id": ""}, {"lower": float("-inf")}, {"upper": float("nan")},
    {"lower": 1., "upper": 0.},
])
def test_invalid_declarations_fail(change):
    with pytest.raises(ValueError):
        rule(**change)


def test_unbounded_and_unavailable_are_not_passes():
    raw = pd.DataFrame({"value": [float("nan"), float("inf")]})
    assert evaluate_rule(rule(), raw)["status"] == "NO_FINITE_VALUES"
    result = evaluate_rule(rule(upper=None), raw)
    assert result["status"] == "DECLARED_UNBOUNDED"
    assert result["share_outside"] is None
    assert result["n_nonfinite_or_missing"] == 2


def test_sign_rule_has_no_false_turnover_cap_and_zero_tolerance():
    raw = pd.DataFrame({"value": [-1000., -2., 0., 0.01]})
    result = evaluate_rule(rule(), raw, max_share=1.)
    assert result["n_outside"] == 1
    assert result["blocking"] is True
    assert evaluate_rule(rule(severity="warning"), raw)["blocking"] is False


def test_economic_tolerance_does_not_erase_violation_count():
    raw = pd.DataFrame({"value": [-1.] * 99 + [1.]})
    result = evaluate_rule(rule(kind="economic"), raw)
    assert result["n_outside"] == 1
    assert result["status"] == "WITHIN_TOLERANCE"
    assert result["blocking"] is False


def test_multiple_rules_are_checked_by_runner_and_ids_cannot_collide():
    factor = load_all()["log_mktcap"]
    raw = pd.DataFrame({"value": [1.]})
    assert check_plausible_magnitude(factor, raw)["rules"][0]["status"] == "DECLARED_UNBOUNDED"
    factor = replace(factor, plausibility_rules=(*factor.plausibility_rules, rule()))
    with pytest.raises(ImplausibleMagnitudeError) as exc:
        check_plausible_magnitude(factor, raw)
    assert len(exc.value.detail["rules"]) == 2
    with pytest.raises(ValueError, match="unique"):
        replace(factor, plausibility_rules=(rule(), rule()))


def test_turnover_rule_is_wired_and_does_not_change_inputs():
    raw = pd.DataFrame({"value": [-10., -1., 0.]})
    before = raw.copy(deep=True)
    result = check_plausible_magnitude(load_all()["turnover"], raw)
    assert result["rules"][0]["n_outside"] == 0
    pd.testing.assert_frame_equal(raw, before)
    with pytest.raises(ImplausibleMagnitudeError):
        check_plausible_magnitude(load_all()["turnover"], pd.DataFrame({"value": [1.]}))


def test_legacy_rules_keep_counts_extremes_and_expose_economic_scope():
    factor = load_all()["bm_ratio"]
    raw = pd.DataFrame({"ticker": ["A"], "signal_date": [pd.Timestamp("2024-01-02")],
                        "value": [5752.]})
    with pytest.raises(ImplausibleMagnitudeError) as exc:
        check_plausible_magnitude(factor, raw)
    detail = exc.value.detail
    assert detail["n_outside"] == 1
    assert detail["worst"] == [("A", "2024-01-02", 5752.)]
    assert detail["rules"][0]["kind"] == "economic"
    assert detail["rules"][0]["blocking"] is True
    assert detail["compatibility_field_scope"] == "legacy_range_only"


def test_every_declared_rule_reaches_structured_results():
    for factor in load_all().values():
        # Empty numeric input avoids inventing one valid value for all factors.
        result = check_plausible_magnitude(factor, pd.DataFrame({"value": []}))
        assert [r["rule_id"] for r in result["rules"]] == [
            r.rule_id for r in factor.declared_rules
        ]
        assert all(r["status"] in {"NO_FINITE_VALUES", "DECLARED_UNBOUNDED"}
                   for r in result["rules"])
