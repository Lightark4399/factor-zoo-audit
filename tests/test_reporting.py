import hashlib
import json

import numpy as np
import pandas as pd

from fza.provenance import implementation_manifest
from fza.reporting import json_safe, research_gate_ledger


def test_unknowns_are_json_null_and_observed_zero_stays_zero():
    source = [float("nan"), float("inf"), np.float64(-np.inf), pd.NaT, pd.NA, 0.0]
    assert json.loads(json.dumps(json_safe(source), allow_nan=False)) == [None] * 5 + [0.0]


def test_manifest_covers_code_cards_sql_and_lock():
    result = implementation_manifest()
    for name in ["demo.py", "reporting.py", "factors/cards/roe.yaml",
                 "sql/001_schema.sql", "research-requirements.lock"]:
        assert name in result["files"]
    assert result["sha256"] == hashlib.sha256(
        json.dumps(result["files"], sort_keys=True).encode()
    ).hexdigest()


def test_unavailable_research_gates_are_never_passed():
    for state in research_gate_ledger().values():
        assert state["status"] in {"UNRESOLVED", "NOT_IMPLEMENTED"}
        assert state["reason"]
