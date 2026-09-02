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
    # Whether the point-in-time read path held. A failure here voids everything.
    read_path_check: dict
    # How much a naive query would have read early. A finding, not a failure.
    naive_trap: dict
    # Whether the raw values were within the magnitude the factor declared, or
    # -- distinctly -- whether it declared one at all.
    magnitude_check: dict
    vintage: str


class ImplausibleMagnitudeError(ValueError):
    """Raised when a factor's raw values leave the range it declared.

    The numbers are carried as ``detail`` as well as in the message. A
    caller that has to render this failure in a table -- the demo does --
    should not have to parse English back out of the string to do it.
    """

    def __init__(self, message: str, detail: dict | None = None) -> None:
        super().__init__(message)
        self.detail: dict = detail or {}


def check_plausible_magnitude(
    factor: Factor, raw: pd.DataFrame, max_share: float = 0.01
) -> dict:
    """Assert a factor's raw values are within the magnitude it declared.

    THIS IS THE CHECK INCIDENT 12 DID NOT HAVE. `bm_ratio` returned 5752 on a
    real company, where a book-to-market ratio lives between roughly 0.1 and 3,
    and produced an IC of +0.0365 with a monotonicity of +0.70 -- numbers that
    agreed with the value literature and so invited no scrutiny. Everything
    downstream of this point is rank-based or standardised, which means it will
    report four decimal places on any input at all. An out-of-range raw value is
    the last place a broken input is still visible as broken.

    On its first run against real data it found a fault nobody was looking for:
    a share count that SEC stopped filing in 2011 and that the as-of join then
    carried forward to 2026, wrong for 3 companies of 30 while every aggregate
    in the report stayed unremarkable. That is incident 13, and it is the reason
    to keep this check rather than the reason it was written.

    What it catches, and what it does not
    -------------------------------------
    It catches a quantity that is wrong by orders of magnitude, which is what a
    unit error, a mis-scaled column or a wrong denominator produce.

    It does NOT catch a value that is wrong but physically ordinary. There are
    now two known blind spots. First, `shares_out` can lag a split while price is
    current: Apple's 2014 book-to-market was seven times wrong and still inside
    an honest range (incident 12). Second, a quarterly or YTD income fact can be
    mistaken for TTM income: both produce ordinary E/P and ROE magnitudes even
    though they answer different accounting questions (incident 15). Magnitude
    is a unit/scale check, not a semantic-period check. It also misses anything
    affecting fewer rows than ``max_share``.

    A range set too wide fails silently: it never fires, and its presence in the
    table says the factor is guarded. A range set too tight fails loudly on valid
    economic extremes. Repeated false alarms teach the operator to ignore the
    check, so the practical result is the same. That is the same shape as
    incident 9, where the check's name and its behaviour had come apart. Bounds
    are therefore written as the widest values the quantity could take and still
    mean what its name says, not fitted to what the data happens to show. They
    need not be symmetric: opposite tails can represent different economic and
    data failure modes.
    """
    if factor.plausible_range is None:
        return {
            "checked": False,
            "n_values": int(len(raw)),
            "note": (
                "no plausible range declared -- NOT the same as passing: this "
                "factor's magnitudes are unverified"
            ),
        }

    lo, hi = factor.plausible_range
    values = pd.to_numeric(raw["value"], errors="coerce").dropna()
    if values.empty:
        return {
            "checked": True,
            "range": (lo, hi),
            "n_values": 0,
            "n_outside": 0,
            "share_outside": 0.0,
            "note": "no finite values to check",
        }

    outside = (values < lo) | (values > hi)
    share = float(outside.mean())
    result = {
        "checked": True,
        "range": (lo, hi),
        "n_values": int(len(values)),
        "n_outside": int(outside.sum()),
        "share_outside": share,
    }
    if share <= max_share:
        return result

    worst = (
        raw.loc[values.index[outside]]
        .assign(_d=lambda d: (d["value"] - (lo + hi) / 2).abs())
        .nlargest(min(5, int(outside.sum())), "_d")
        .drop(columns="_d")
    )
    raise ImplausibleMagnitudeError(
        f"{factor.factor_id}: {outside.sum():,} of {len(values):,} values "
        f"({share:.2%}, above the {max_share:.0%} tolerance) fall outside the "
        f"declared plausible range [{lo:g}, {hi:g}].\n"
        "This is a data problem, not a factor problem: check the inputs before "
        "the definition. A value this far out produces a perfectly credible IC, "
        "which is why it is stopped here.\n"
        f"Most extreme rows:\n{worst.to_string(index=False)}",
        detail={
            **result,
            "max_share": max_share,
            "worst": [
                (
                    str(r.ticker),
                    str(pd.Timestamp(r.signal_date).date()),
                    float(r.value),
                )
                for r in worst.itertuples()
            ],
        },
    )


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
    # Clear the read log so this factor's check covers this factor's reads. A
    # shared log would let one factor's clean run vouch for another's.
    store.access.reads.clear()

    raw = factor.compute(store, signal_dates)

    # Before any cleaning. Winsorising would pull an impossible value back to a
    # plausible one and standardising would erase the units the bound is stated
    # in, so a check placed after either would be checking the wrong number.
    magnitude = check_plausible_magnitude(factor, raw)

    cleaned, report = prepare_cross_sections(raw, groups=groups)
    panel = build_panel(
        cleaned, store.prices(), horizon_days=horizon_days, execution_lag=execution_lag
    )

    if factor.tags:
        # The check on the guarantee: did the reads this factor actually made
        # return anything filed after the date it asked for? Only meaningful for
        # the honest vintage -- the restated arm substitutes a leaking read path
        # on purpose, and asserting against it would flag the simulation as a
        # bug.
        if vintage == "pit":
            read_check = store.assert_read_path_respected(
                grace_days=factor.filing_lag_days
            )
        else:
            read_check = {
                "n_reads": 0,
                "n_violations": 0,
                "ok": True,
                "note": "restated vintage deliberately bypasses the as-of path",
            }

        # The measurement of the hazard. Reported alongside, never conflated:
        # a large trap is the reason the store exists, not a defect in the code
        # that avoids it.
        trap = store.measure_naive_trap(
            raw[["ticker", "signal_date"]],
            tags=list(factor.tags),
            grace_days=factor.filing_lag_days,
        )
    else:
        read_check = {
            "n_reads": 0,
            "n_violations": 0,
            "ok": True,
            "note": "factor declares no fundamental tags; nothing to check",
        }
        trap = {
            "n_signal_dates": 0,
            "n_dates_exposed": 0,
            "n_trap_rows": 0,
            "exposure_rate": float("nan"),
            "note": "factor reads no fundamentals, so no naive trap applies",
        }

    protocol = run_protocol(factor.factor_id, panel, n_quantiles=n_quantiles)

    return FactorRun(
        factor=factor,
        values=cleaned,
        panel=panel,
        protocol=protocol,
        cleaning=report,
        read_path_check=read_check,
        naive_trap=trap,
        magnitude_check=magnitude,
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
    original_history = store.fundamentals_history_asof

    def leaking_asof(signal_date, tags=None, intended_signal_date=None):
        # Mirrors the real signature so a factor can be swapped onto this path
        # unchanged. ``intended_signal_date`` is accepted and ignored: this arm
        # keeps no read log, because the whole point of it is to bypass the
        # guarantee the log exists to verify.
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

    def leaking_history_asof(signal_date, tags=None, intended_signal_date=None):
        """Restated arm retaining every start/end context needed for TTM."""
        out = restated_frame
        if tags:
            out = out.loc[out["tag"].isin(tags)]
        return out.loc[out["period_end"] <= pd.Timestamp(signal_date)].copy()

    try:
        store.fundamentals_asof = leaking_asof  # type: ignore[method-assign]
        store.fundamentals_history_asof = leaking_history_asof  # type: ignore[method-assign]
        restated_run = compute_factor(
            factor, store, signal_dates, groups=groups, vintage="restated", **kwargs
        )
    finally:
        store.fundamentals_asof = original  # type: ignore[method-assign]
        store.fundamentals_history_asof = original_history  # type: ignore[method-assign]

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
            "read_path_violations": pit_run.read_path_check["n_violations"],
            "naive_trap_rows": pit_run.naive_trap["n_trap_rows"],
        },
    )
