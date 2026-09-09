"""Check explicit current-interface tables, not arbitrary prose identifiers."""

from pathlib import Path

import pandas as pd

from fza.pipeline.prepare import forward_returns
from fza.pipeline.vintage import SCOPES

ROOT = Path(__file__).parents[1]


def first_column(document, header):
    lines = document.splitlines()
    start = next(i for i, line in enumerate(lines) if line.startswith(header))
    result = []
    for line in lines[start + 2:]:
        if not line.startswith("|"):
            break
        result.append(line.split("|")[1].strip().strip("`"))
    assert result, "contract table must not disappear silently"
    return result


def test_documented_timing_fields_are_actual_label_output():
    dates = pd.bdate_range("2024-01-02", periods=4)
    prices = pd.DataFrame({"ticker": "A", "trade_date": dates,
                           "close_adj": [10., 11., 12., 13.]})
    labels = forward_returns(prices, [dates[0]], horizon_sessions=1,
                             execution_lag_sessions=1)
    fields = first_column((ROOT / "B_DELIVERY.md").read_text(encoding="utf-8"),
                          "| Current local timing field |")
    actual = {name for name in labels if pd.api.types.is_datetime64_any_dtype(labels[name])}
    assert set(fields) == actual
    assert len(fields) == len(actual)
    assert labels[fields].notna().all().all()


def test_documented_layers_match_the_executable_registry():
    layers = first_column((ROOT / "VINTAGE_COMPARISON.md").read_text(encoding="utf-8"),
                          "| Layer |")
    assert set(layers) == set(SCOPES)
    assert len(layers) == len(SCOPES)
