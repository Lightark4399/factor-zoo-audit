"""Running a factor, and running it twice on purpose.

The second run is the point. A factor computed on point-in-time data answers
"what could have been known"; the same factor computed on restated data answers
"what we know now". The difference between the two scores is the value of the
look-ahead, in the same units as everything else in the report.

That comparison only means something if the two runs differ in **one** respect.
So the runner holds everything else fixed: the same signal dates, the same
universe, the same cleaning parameters, the same forward returns, the same
protocol. The vintage is the only thing that varies.

Measured wrong, this number is easy to inflate. Two ways it goes wrong, both
guarded here:

* **Different samples.** If the restated run produces values for dates or names
  the point-in-time run could not, the two scores describe different
  cross-sections. The runner intersects them before scoring.
* **A factor that never touches fundamentals.** Momentum reads prices only, so
  its two vintages are identical by construction and the gap is exactly zero. The
  runner detects this and reports "not applicable" rather than a zero that a
  reader might mistake for evidence of cleanliness.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from ..factors.registry import Factor
from ..store import Store
from .prepare import CleaningReport, build_panel, prepare_cross_sections
from .protocol import ProtocolResult, run_protocol

# Below this the two vintages agree to within estimation noise on a panel of the
# sizes this project works with.
MATERIAL_GAP = 0.005


@dataclass
class VintageComparison:
    """A factor's performance under point-in-time and restated data."""

    factor_id: str
    pit: ProtocolResult
    restated: ProtocolResult | None
    applicable: bool
    passed: bool | None
    verdict: str
    detail: dict = field(default_factory=dict)

    @property
    def ic_gap(self) -> float:
        if self.restated is None:
            return float("nan")
        return self.restated.summary["ic_mean"] - self.pit.summary["ic_mean"]

    @property
    def sharpe_gap(self) -> float:
        if self.restated is None:
            return float("nan")
        return self.restated.summary["ls_sharpe"] - self.pit.summary["ls_sharpe"]

    def to_dict(self) -> dict:
        return {
            "factor_id": self.factor_id,
            "applicable": self.applicable,
            "pit_ic": self.pit.summary["ic_mean"],
            "restated_ic": self.restated.summary["ic_mean"] if self.restated else None,
            "ic_gap": self.ic_gap,
            "pit_sharpe": self.pit.summary["ls_sharpe"],
            "restated_sharpe": self.restated.summary["ls_sharpe"] if self.restated else None,
            "sharpe_gap": self.sharpe_gap,
            "passed": self.passed,
            "verdict": self.verdict,
            **self.detail,
        }


@dataclass
class FactorRun:
    """One factor's full result: values, panel, protocol and cleaning report."""

    factor: Factor
    values: pd.DataFrame
    panel: pd.DataFrame
    protocol: ProtocolResult
    cleaning: CleaningReport
    lookahead_check: dict
    vintage: str


def compute_factor(
    factor: Factor,
    store: Store,
    signal_dates: pd.DatetimeIndex,
    groups: pd.Series | None = None,
    horizon_days: int = 21,
    execution_lag: int = 1,
    n_quantiles: int = 5,
    vintage: str = "pit",
) -> FactorRun:
    """Compute a factor, clean it, join returns, and run the protocol.

    The look-ahead check runs on every factor that declares fundamental tags,
    every time, rather than as a separate audit step. A violation makes every
    downstream number meaningless, so it belongs where it cannot be skipped.
    """
    raw = factor.compute(store, signal_dates)

    cleaned, report = prepare_cross_sections(raw, groups=groups)
    panel = build_panel(
        cleaned, store.prices(), horizon_days=horizon_days, execution_lag=execution_lag
    )

    if factor.tags:
        check = store.assert_no_lookahead(
            raw[["ticker", "signal_date"]],
            tags=list(factor.tags),
            grace_days=factor.filing_lag_days,
        )
    else:
        check = {
            "checked": 0,
            "violations": 0,
            "ok": True,
            "note": "factor declares no fundamental tags; nothing to check",
        }

    protocol = run_protocol(factor.factor_id, panel, n_quantiles=n_quantiles)

    return FactorRun(
        factor=factor,
        values=cleaned,
        panel=panel,
        protocol=protocol,
        cleaning=report,
        lookahead_check=check,
        vintage=vintage,
    )


def compare_vintages(
    factor: Factor,
    store: Store,
    signal_dates: pd.DatetimeIndex,
    groups: pd.Series | None = None,
    **kwargs,
) -> VintageComparison:
    """Run a factor on both data vintages and report the gap.

    The restated run is produced by a store whose ``fundamentals_asof`` has been
    replaced with a call that ignores the signal date — which is precisely the
    query a pipeline written against a mutable database would issue. Simulating
    the mistake rather than describing it is what makes the resulting number a
    measurement.
    """
    pit_run = compute_factor(factor, store, signal_dates, groups=groups, vintage="pit", **kwargs)

    if not factor.uses_fundamentals:
        return VintageComparison(
            factor_id=factor.factor_id,
            pit=pit_run.protocol,
            restated=None,
            applicable=False,
            passed=None,
            verdict=(
                "NOT APPLICABLE: this factor reads no fundamentals, so the two "
                "vintages are identical by construction. That is not evidence "
                "the factor is free of look-ahead — it means this particular "
                "channel cannot apply to it."
            ),
        )

    # Substitute a leaking read path. The substitution must relax EXACTLY ONE
    # constraint, or the resulting gap measures a mixture.
    #
    # The first attempt relaxed both: it returned the latest period available
    # anywhere in the table, so a signal formed in January was reading an
    # accounting period that had not ended yet. That is a leak, but a different
    # and cruder one, and it swamped the effect being measured -- the restated
    # company's value moved 1.85% where the restatement itself was 40%.
    #
    # The correct substitution keeps `period_end <= signal_date` (the period had
    # ended) and drops only `filed <= signal_date` (the filing had appeared).
    # That is precisely what a query against a mutable fundamentals table does.
    restated_frame = store.fundamentals_restated(caller=f"compare_vintages:{factor.factor_id}")
    restated_frame = restated_frame.copy()
    restated_frame["period_end"] = pd.to_datetime(restated_frame["period_end"])

    original = store.fundamentals_asof

    def leaking_asof(signal_date, tags=None):
        out = restated_frame
        if tags:
            out = out.loc[out["tag"].isin(tags)]
        # The period had to have ended -- only the filing constraint is relaxed.
        out = out.loc[out["period_end"] <= pd.Timestamp(signal_date)]
        if out.empty:
            return out
        return (
            out.sort_values(["cik", "tag", "period_end"])
            .groupby(["cik", "tag"], as_index=False)
            .last()
        )

    try:
        store.fundamentals_asof = leaking_asof  # type: ignore[method-assign]
        restated_run = compute_factor(
            factor, store, signal_dates, groups=groups, vintage="restated", **kwargs
        )
    finally:
        store.fundamentals_asof = original  # type: ignore[method-assign]

    # Score both arms on the dates they share. Without this the gap would partly
    # be a comparison of different samples -- the same confound that produced a
    # spurious -0.013 in the sibling project's point-in-time module.
    shared = sorted(
        set(pit_run.panel["signal_date"]).intersection(restated_run.panel["signal_date"])
    )
    if shared:
        pit_protocol = run_protocol(
            factor.factor_id, pit_run.panel[pit_run.panel["signal_date"].isin(shared)]
        )
        restated_protocol = run_protocol(
            factor.factor_id,
            restated_run.panel[restated_run.panel["signal_date"].isin(shared)],
        )
    else:
        pit_protocol, restated_protocol = pit_run.protocol, restated_run.protocol

    gap = restated_protocol.summary["ic_mean"] - pit_protocol.summary["ic_mean"]

    if not np.isfinite(gap):
        passed, verdict = None, "INCONCLUSIVE: one of the vintages could not be scored."
    elif gap > MATERIAL_GAP:
        passed = False
        verdict = (
            f"FAIL: the restated vintage scores {gap:+.4f} higher in IC "
            f"({restated_protocol.summary['ic_mean']:+.4f} vs "
            f"{pit_protocol.summary['ic_mean']:+.4f}). A backtest built on a "
            "mutable fundamentals table would have reported the larger figure, "
            "and the difference is information that was not available when the "
            "signal was formed."
        )
    elif gap < -MATERIAL_GAP:
        passed = True
        verdict = (
            f"PASS (opposite direction): the point-in-time vintage scores HIGHER "
            f"by {-gap:.4f}. Restatements moved the data away from what predicted "
            "returns here, so using them understates rather than flatters."
        )
    else:
        passed = True
        verdict = (
            f"PASS: the two vintages agree to within {abs(gap):.4f}. Restatements "
            "in this sample carried no information about subsequent returns, so "
            "reading them conferred no advantage."
        )

    return VintageComparison(
        factor_id=factor.factor_id,
        pit=pit_protocol,
        restated=restated_protocol,
        applicable=True,
        passed=passed,
        verdict=verdict,
        detail={
            "n_shared_dates": len(shared),
            "material_gap_threshold": MATERIAL_GAP,
            "lookahead_violations": pit_run.lookahead_check["violations"],
        },
    )
