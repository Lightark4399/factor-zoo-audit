"""Characterise the historical-universe wiring gap without asserting it.

This is an investigation aid, not a regression test.  It records what the
current pipeline does to the synthetic security that exits the declared
universe mid-sample, including whether that row changes the cleaned values of
securities that remain eligible.  A pre-fix capture belongs in
``examples/outputs`` and must stay labelled diagnostic: tests should assert the
target invariant after the fix, never preserve these buggy outputs.
"""

from __future__ import annotations

import json
import platform

import numpy as np
import pandas as pd

from fza.factors.registry import load_all
from fza.fixtures import FixtureSpec, load_fixture_into
from fza.pipeline.prepare import build_panel, prepare_cross_sections
from fza.pipeline.run import check_plausible_magnitude
from fza.store import Store

SIGNAL_DATES = pd.DatetimeIndex(
    pd.date_range("2019-01-31", "2021-06-30", freq=pd.offsets.MonthEnd())
)
DELISTED_TICKER = "TST07"


def _clean(raw: pd.DataFrame) -> pd.DataFrame:
    cleaned, _ = prepare_cross_sections(raw)
    return cleaned.sort_values(["signal_date", "ticker"]).reset_index(drop=True)


def _survivor_shift(
    cleaned_with_ghost: pd.DataFrame,
    cleaned_without_ghost: pd.DataFrame,
    exit_date: pd.Timestamp,
) -> tuple[int, float]:
    keys = ["ticker", "signal_date"]
    left = cleaned_with_ghost.loc[
        (cleaned_with_ghost["ticker"] != DELISTED_TICKER)
        & (cleaned_with_ghost["signal_date"] > exit_date),
        keys + ["value"],
    ]
    right = cleaned_without_ghost.loc[
        cleaned_without_ghost["signal_date"] > exit_date, keys + ["value"]
    ]
    joined = left.merge(right, on=keys, suffixes=("_with", "_without"))
    if joined.empty:
        return 0, float("nan")
    delta = (joined["value_with"] - joined["value_without"]).abs()
    return int((delta > 1e-12).sum()), float(delta.max())


def main() -> None:
    store = Store()
    try:
        load_fixture_into(store, FixtureSpec())
        exit_date = pd.Timestamp(
            store.con.execute(
                "SELECT last_filing FROM securities WHERE ticker = ?",
                [DELISTED_TICKER],
            ).fetchone()[0]
        )
        prices = store.prices()
        rows: list[dict] = []

        for factor_id, factor in sorted(load_all().items()):
            raw = factor.compute(store, SIGNAL_DATES).copy()
            raw["signal_date"] = pd.to_datetime(raw["signal_date"])
            ghost_mask = (raw["ticker"] == DELISTED_TICKER) & (
                raw["signal_date"] > exit_date
            )
            raw_without_ghost = raw.loc[~ghost_mask].copy()

            cleaned = _clean(raw)
            cleaned_without_ghost = _clean(raw_without_ghost)
            panel = build_panel(cleaned, prices)
            cleaned_ghost_mask = (cleaned["ticker"] == DELISTED_TICKER) & (
                cleaned["signal_date"] > exit_date
            )
            panel_ghost_mask = (panel["ticker"] == DELISTED_TICKER) & (
                panel["signal_date"] > exit_date
            )
            changed, max_shift = _survivor_shift(
                cleaned, cleaned_without_ghost, exit_date
            )
            magnitude = check_plausible_magnitude(factor, raw)
            post_exit_values = raw.loc[ghost_mask, "value"]

            rows.append(
                {
                    "factor_id": factor_id,
                    "raw_rows_after_exit": int(ghost_mask.sum()),
                    "raw_exact_zero_after_exit": int(
                        np.isclose(post_exit_values.fillna(np.inf), 0.0).sum()
                    ),
                    "cleaned_rows_after_exit": int(cleaned_ghost_mask.sum()),
                    "labelled_rows_after_exit": int(panel_ghost_mask.sum()),
                    "rows_dropped_at_label_join": int(
                        cleaned_ghost_mask.sum() - panel_ghost_mask.sum()
                    ),
                    "surviving_rows_with_changed_zscore": changed,
                    "max_abs_surviving_zscore_shift": max_shift,
                    "magnitude_values_seen": int(magnitude["n_values"]),
                    "magnitude_checked": bool(magnitude["checked"]),
                }
            )

        payload = {
            "status": "PRE_FIX",
            "evidence_status": "DIAGNOSTIC_ONLY",
            "assertion_status": "NOT_AN_ASSERTION",
            "purpose": (
                "Characterise the unwired historical-universe gate before the "
                "target invariant is implemented. Numeric rows must not become "
                "regression expectations."
            ),
            "environment": {
                "python": platform.python_version(),
                "pandas": pd.__version__,
                "numpy": np.__version__,
            },
            "fixture": {
                "delisted_ticker": DELISTED_TICKER,
                "declared_exit_date": str(exit_date.date()),
                "signal_date_start": str(SIGNAL_DATES.min().date()),
                "signal_date_end": str(SIGNAL_DATES.max().date()),
            },
            "matrix": rows,
        }
        print(json.dumps(payload, indent=2, sort_keys=True, allow_nan=True))
    finally:
        store.close()


if __name__ == "__main__":
    main()
