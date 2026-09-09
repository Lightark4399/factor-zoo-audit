"""Sample/processing sensitivities, never a causal value/sample decomposition."""

import numpy as np
import pandas as pd

from .prepare import prepare_cross_sections
from .protocol import run_protocol

KEYS = ["ticker", "signal_date"]
OUTCOMES = ["label", "formation_session", "entry_date", "exit_date"]
SENSITIVITY_NOTICE = (
    "Differences between layers reflect sensitivity to sample selection and "
    "processing, not a decomposition into value and sample effects."
)
SCOPES = {
    "original-process": "Shared dates; arm-specific effective samples and cleaning inputs.",
    "common-observation": "Scoring keys aligned; upstream cleaning-sample effects remain.",
    "common-support": "Cleaning input keys fixed; the common set is selected, not the cohort.",
}


def indexed(frame):
    frame = frame.copy()
    frame["signal_date"] = pd.to_datetime(frame["signal_date"])
    if frame[KEYS].isna().any().any() or frame.duplicated(KEYS).any():
        raise ValueError("Vintage observation keys must be non-null and unique")
    return frame.set_index(KEYS).sort_index()


def outcome_identity(left, right):
    """Exact outcome/timing agreement on shared keys, with explicit missingness."""
    a, b = indexed(left), indexed(right)
    common = a.index.intersection(b.index)
    missing = sorted(set(OUTCOMES) - set(a.columns).intersection(b.columns))
    result = {"status": "NOT_CHECKED", "common_keys": len(common),
              "missing_columns": missing, "mismatches": {}}
    if missing:
        result["reason"] = "required_outcome_columns_missing"
        return result
    if not len(common):
        result.update(status="INCONCLUSIVE", reason="no_common_outcomes")
        return result
    a, b = a.loc[common, OUTCOMES], b.loc[common, OUTCOMES]
    for column in OUTCOMES:
        x, y = a[column], b[column]
        if column == "label":
            valid = np.isfinite(x) & np.isfinite(y)
        else:
            x, y = pd.to_datetime(x), pd.to_datetime(y)
            valid = x.notna() & y.notna()
        result["mismatches"][column] = int((~valid | (x != y)).sum())
    valid_order = True
    for arm in (a, b):
        dates = arm[OUTCOMES[1:]].apply(pd.to_datetime)
        valid_order &= bool(((dates.formation_session <= dates.entry_date)
                             & (dates.entry_date < dates.exit_date)).all())
    result["valid_holding_period_order"] = valid_order
    passed = not any(result["mismatches"].values()) and valid_order
    result.update(status="MATCHED" if passed else "MISMATCH",
                  reason="exact_shared_outcomes" if passed else "outcome_identity_failed")
    return result


def diagnostic_layers(factor_id, left, right, raw_left, raw_right, *, groups,
                      label_builder, n_quantiles, sample_report, path_exercised):
    """Retain per-layer conditions alongside every number and blocked result.

    Raw inputs are post-universe, pre-cleaning. Common support is their finite
    intersection, not an intersection selected after arm-specific cleaning.
    Labels are rebuilt under the original execution configuration.
    """
    layers = {}

    def evaluate(name, a, b):
        identity = outcome_identity(a, b)
        row = {"scope": SCOPES[name], "status": "INCONCLUSIVE", "reason": None,
               "outcome_identity": identity, "sample": sample_report(a, b),
               "ic_gap": None, "ls_sharpe_gap": None, "metrics": {}}
        row["sample"]["label_and_holding_period_identity"] = identity["status"]
        if name != "original-process":
            row["sample"]["scoring_scope"] = "COMMON_OBSERVATION_KEYS"
        if name == "common-support":
            row["sample"]["cleaning_scope"] = "FIXED_COMMON_INPUT_KEYS"
        layers[name] = row
        if not path_exercised:
            row.update(status="NOT_APPLICABLE", reason="substituted_path_not_exercised")
            return
        if identity["status"] != "MATCHED":
            row["reason"] = identity["reason"]
            return
        p, r = [run_protocol(factor_id, panel, n_quantiles=n_quantiles) for panel in (a, b)]
        for metric, series_name, summary_name, output_name in [
            ("ic", "ic_series", "ic_mean", "ic_gap"),
            ("ls_sharpe", "long_short", "ls_sharpe", "ls_sharpe_gap"),
        ]:
            ps, rs = getattr(p, series_name), getattr(r, series_name)
            same_dates = ps.index.equals(rs.index)
            finite = np.isfinite(p.summary[summary_name]) and np.isfinite(r.summary[summary_name])
            eligible = finite and (same_dates or name == "original-process")
            row["metrics"][metric] = {
                "pit_dates": [str(pd.Timestamp(d).date()) for d in ps.index],
                "restated_dates": [str(pd.Timestamp(d).date()) for d in rs.index],
                "identical_metric_dates": same_dates,
                "reason": (None if eligible else "metric_dates_differ" if not same_dates
                           else "metric_unscorable"),
            }
            if eligible:
                row[output_name] = float(r.summary[summary_name] - p.summary[summary_name])
        row["pit"] = p.to_dict()
        row["restated"] = r.to_dict()
        row.update(status="DIAGNOSTIC_ONLY" if row["ic_gap"] is not None else "INCONCLUSIVE",
                   reason=row["metrics"]["ic"]["reason"])

    evaluate("original-process", left, right)
    a, b = indexed(left), indexed(right)
    common = a.index.intersection(b.index)
    evaluate("common-observation", a.loc[common].reset_index(), b.loc[common].reset_index())

    if raw_left is None or raw_right is None or not path_exercised:
        layers["common-support"] = {
            "scope": SCOPES["common-support"], "status": "NOT_APPLICABLE"
            if not path_exercised else "INCONCLUSIVE",
            "reason": ("substituted_path_not_exercised" if not path_exercised
                       else "raw_inputs_missing"),
            "outcome_identity": {"status": "NOT_CHECKED"},
            "ic_gap": None, "ls_sharpe_gap": None,
        }
        return layers

    a, b = indexed(raw_left), indexed(raw_right)
    a, b = a.loc[np.isfinite(a.value)], b.loc[np.isfinite(b.value)]
    common = a.index.intersection(b.index)
    inputs = [arm.loc[common].reset_index() for arm in (a, b)]
    support = sample_report(*inputs)
    support["scoring_scope"] = "NOT_SCORED_RAW_INPUT_KEYS"
    support["cleaning_scope"] = "FIXED_COMMON_INPUT_KEYS"
    panels, cleaning, labels = [], [], []
    for raw in inputs:
        if raw.empty:
            panels.append(left.iloc[:0].copy())
            cleaning.append(None)
            labels.append(None)
            continue
        cleaned, report = prepare_cross_sections(raw, groups=groups)
        panel, label_report = label_builder(cleaned)
        panels.append(panel)
        cleaning.append(report.to_dict())
        labels.append(label_report.to_dict())
    evaluate("common-support", *panels)
    row = layers["common-support"]
    row["cleaning_input_sample"] = support
    row["cleaning"] = cleaning
    row["label_join"] = labels
    row["source_outcome_identity"] = layers["original-process"]["outcome_identity"]
    if row["source_outcome_identity"]["status"] in {"MISMATCH", "NOT_CHECKED"}:
        row.update(status="INCONCLUSIVE", reason="source_outcomes_not_verified",
                   ic_gap=None, ls_sharpe_gap=None)
    # Never silently re-intersect asymmetric output from a supposedly shared input.
    if not row["sample"]["identical_observation_keys"]:
        row.update(status="INCONCLUSIVE", reason="post_cleaning_keys_differ",
                   ic_gap=None, ls_sharpe_gap=None)
    return layers
