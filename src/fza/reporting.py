"""Diagnostic serialization, not a new scoring or research-approval layer."""

import math
from copy import deepcopy
from datetime import date, datetime

import numpy as np
import pandas as pd


def json_safe(value):
    """Use JSON null for undefined numbers; never emit nonstandard NaN tokens."""
    if value is pd.NaT or value is pd.NA:
        return None
    if isinstance(value, dict):
        return {str(key): json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_safe(item) for item in value]
    if isinstance(value, np.generic):
        return json_safe(value.item())
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def factor_record(run, evidence):
    """Reuse computed reports; do not rerun factors or alter their samples."""
    return {
        "computation_status": "COMPLETED",
        "statistics_status": evidence["statistics_status"],
        "policy_id": evidence["policy_id"],
        "protocol": run.protocol.to_dict(),
        "universe_filter": run.universe_filter.to_dict(),
        "cleaning": run.cleaning.to_dict(),
        "label_join": run.label_join.to_dict(),
        "construction_filters": run.construction_filters,
        "read_path_check": run.read_path_check,
        "magnitude_check": run.magnitude_check,
        "naive_trap": run.naive_trap,
        "claims": deepcopy(evidence["claims"]),
    }


def research_gate_ledger():
    """Delivery status, not a synthetic passed verdict for unavailable checks."""
    return {
        "historical_membership_completeness": {
            "status": "UNRESOLVED", "reason": "filing_proxy_does_not_validate_initial_roster",
        },
        "terminal_outcomes": {
            "status": "UNRESOLVED", "reason": "label_loss_counting_is_not_exit_settlement",
        },
        "post_publication_out_of_sample": {
            "status": "NOT_IMPLEMENTED", "reason": "no_publication_date_gate_in_demo",
        },
        "multiple_testing": {
            "status": "NOT_IMPLEMENTED", "reason": "no_dsr_fdr_gate_in_demo",
        },
        "free_baseline": {
            "status": "NOT_IMPLEMENTED", "reason": "backtest_audit_bridge_not_connected",
        },
        "trading_costs": {
            "status": "NOT_IMPLEMENTED", "reason": "no_cost_gate_in_demo",
        },
    }
