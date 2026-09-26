"""Running a factor, and running it twice on purpose.

The comparison relaxes filing visibility, retaining the accounting-period bound.
It holds the historical-membership input and protocol settings fixed, not the
effective sample: filing visibility can change both values and their availability.

The original-process diagnostic scores each arm's own cleaned observations on
shared signal dates. It does NOT intersect securities before cleaning or scoring.
Counts and key hashes disclose that distinction. Its gap is not an isolated
restatement-value effect, a causal decomposition, or evidence of significance.
Common-observation and common-support re-cleaning diagnostics are reported
separately, with outcome/timing and metric-date eligibility checks beside them.

Declared fundamental tags do not establish coverage of the substituted methods.
The runner counts actual calls to those methods; an untouched embedded price-table
share count cannot produce evidence about share-count revisions merely by giving
a zero gap. No common dates or no exercised read path can produce a PASS.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from ..factors.plausibility import evaluate_rule
from ..factors.registry import Factor
from ..store import Store
from .prepare import (
    CleaningReport,
    LabelJoinReport,
    build_panel_with_report,
    prepare_cross_sections,
)
from .protocol import ProtocolResult, run_protocol
from .vintage import SCOPES, SENSITIVITY_NOTICE, diagnostic_layers

# Preconfigured directional diagnostic threshold; not calibrated to sampling
# uncertainty, not a significance/equivalence test, and not evidence of no effect.
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
        if not self.applicable or self.restated is None:
            return float("nan")
        if "layers" in self.detail:
            gap = self.detail["layers"]["original-process"]["ic_gap"]
            return float("nan") if gap is None else gap
        return self.restated.summary["ic_mean"] - self.pit.summary["ic_mean"]

    @property
    def sharpe_gap(self) -> float:
        if not self.applicable or self.restated is None:
            return float("nan")
        if "layers" in self.detail:
            gap = self.detail["layers"]["original-process"]["ls_sharpe_gap"]
            return float("nan") if gap is None else gap
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
    # Definition-level eligibility rules applied inside the factor before the
    # common universe and cleaning pipeline.
    construction_filters: list[dict]
    # What the historical-membership gate removed before any value was allowed
    # to influence a magnitude check or a cross-sectional statistic.
    universe_filter: UniverseFilterReport
    # What was lost when cleaned signals were aligned to realised returns.
    label_join: LabelJoinReport
    vintage: str
    # Exact post-membership input; never reconstruct this from cleaned z-scores.
    eligible_values: pd.DataFrame | None = None


@dataclass
class UniverseFilterReport:
    """Attrition at the historical-membership gate.

    This is separate from ``CleaningReport`` because membership is not data
    cleaning.  A row outside the declared universe is ineligible even when its
    value is finite and economically plausible, and it must be removed before
    either of those properties is inspected.
    """

    n_input: int
    n_output: int
    n_excluded_outside_universe: int
    n_requested_dates: int
    n_dates_with_membership: int
    n_membership_keys: int
    membership_key_hash: str
    detail: dict = field(default_factory=dict)

    @property
    def retention(self) -> float:
        return self.n_output / self.n_input if self.n_input else float("nan")

    def to_dict(self) -> dict:
        return {
            "n_input": self.n_input,
            "n_output": self.n_output,
            "n_excluded_outside_universe": self.n_excluded_outside_universe,
            "retention": self.retention,
            "n_requested_dates": self.n_requested_dates,
            "n_dates_with_membership": self.n_dates_with_membership,
            "n_membership_keys": self.n_membership_keys,
            "membership_key_hash": self.membership_key_hash,
            **self.detail,
        }


class ImplausibleMagnitudeError(ValueError):
    """Raised when a factor's raw values leave the range it declared.

    The numbers are carried as ``detail`` as well as in the message. A
    caller that has to render this failure in a table -- the demo does --
    should not have to parse English back out of the string to do it.
    """

    def __init__(self, message: str, detail: dict | None = None) -> None:
        super().__init__(message)
        self.detail: dict = detail or {}


def historical_universe_membership(
    store: Store, signal_dates: pd.DatetimeIndex
) -> pd.DataFrame:
    """Return the eligible ``(ticker, signal_date)`` keys for a run.

    The store owns the definition of historical membership.  The runner owns
    making that definition unavoidable: building the key panel here lets a
    vintage comparison construct it once and give both arms the exact same
    keys.
    """
    dates = pd.DatetimeIndex(pd.to_datetime(signal_dates)).unique().sort_values()
    rows: list[pd.DataFrame] = []
    for date in dates:
        universe = store.universe_asof(date)
        if universe.empty:
            continue
        rows.append(
            pd.DataFrame(
                {
                    "ticker": universe["ticker"].astype(str),
                    "signal_date": pd.Timestamp(date),
                }
            )
        )

    if not rows:
        return pd.DataFrame(
            {
                "ticker": pd.Series(dtype="object"),
                "signal_date": pd.Series(dtype="datetime64[ns]"),
            }
        )
    return (
        pd.concat(rows, ignore_index=True)
        .drop_duplicates(["ticker", "signal_date"])
        .sort_values(["signal_date", "ticker"])
        .reset_index(drop=True)
    )


def filter_to_historical_universe(
    raw: pd.DataFrame,
    membership: pd.DataFrame,
    signal_dates: pd.DatetimeIndex,
) -> tuple[pd.DataFrame, UniverseFilterReport]:
    """Remove ineligible keys before magnitude checks and cross-section work."""
    required = {"ticker", "signal_date", "value"}
    missing = required.difference(raw.columns)
    if missing:
        raise ValueError(f"factor output is missing required columns: {sorted(missing)}")

    values = raw.copy()
    values["ticker"] = values["ticker"].astype(str)
    values["signal_date"] = pd.to_datetime(values["signal_date"])
    keys = membership[["ticker", "signal_date"]].copy()
    keys["ticker"] = keys["ticker"].astype(str)
    keys["signal_date"] = pd.to_datetime(keys["signal_date"])
    keys = keys.drop_duplicates(["ticker", "signal_date"])

    # A temporary order column makes this an eligibility gate, not an
    # accidental reordering of factor output that downstream code might expose.
    values["_universe_input_order"] = np.arange(len(values))
    filtered = (
        values.merge(keys, on=["ticker", "signal_date"], how="inner", sort=False)
        .sort_values("_universe_input_order")
        .drop(columns="_universe_input_order")
        .reset_index(drop=True)
    )

    membership_for_hash = keys.sort_values(["signal_date", "ticker"])
    hashed = pd.util.hash_pandas_object(
        membership_for_hash[["ticker", "signal_date"]], index=False
    )
    membership_hash = hashlib.sha256(hashed.to_numpy().tobytes()).hexdigest()

    input_counts = values.groupby("signal_date").size()
    output_counts = filtered.groupby("signal_date").size()
    dropped = input_counts.sub(output_counts, fill_value=0).astype(int)
    dropped = dropped.loc[dropped > 0]
    membership_dates = pd.DatetimeIndex(keys["signal_date"].unique())
    requested_dates = pd.DatetimeIndex(pd.to_datetime(signal_dates)).unique()

    report = UniverseFilterReport(
        n_input=int(len(values)),
        n_output=int(len(filtered)),
        n_excluded_outside_universe=int(len(values) - len(filtered)),
        n_requested_dates=int(len(requested_dates)),
        n_dates_with_membership=int(len(membership_dates)),
        n_membership_keys=int(len(keys)),
        membership_key_hash=membership_hash,
        detail={
            "excluded_by_date": {
                str(pd.Timestamp(date).date()): int(count)
                for date, count in dropped.items()
            }
        },
    )
    return filtered, report


def check_plausible_magnitude(factor: Factor, raw: pd.DataFrame, max_share=0.01) -> dict:
    """Legacy economic guard plus independently scoped raw-output rules."""
    if not 0 <= max_share <= 1:
        raise ValueError("max_share must be between zero and one")
    rules = [evaluate_rule(rule, raw, max_share) for rule in factor.plausibility_rules]
    failure = None
    try:
        result = _check_legacy_magnitude(factor, raw, max_share)
    except ImplausibleMagnitudeError as exc:
        failure, result = exc, exc.detail
    if factor.plausible_range is not None:
        legacy = {
            **factor.declared_rules[0].to_dict(), **result,
            "scope": "post_universe_raw_output",
            "status": ("VIOLATION" if failure else "WITHIN_TOLERANCE")
            if result["n_values"] else "NO_FINITE_VALUES",
            "blocking": failure is not None,
            "max_share": max_share,
            "compatibility_semantics": "missing excluded; infinity counted by legacy bounds",
        }
        rules.insert(0, legacy)
    result["compatibility_field_scope"] = "legacy_range_only"
    result["rules"] = rules
    if failure:
        raise failure
    for rule in rules:
        if rule["blocking"]:
            raise ImplausibleMagnitudeError(
                f"{factor.factor_id}: raw-output rule {rule['rule_id']} violated",
                detail={**rule, "rules": rules},
            )
    return result


def _check_legacy_magnitude(
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
    incident 9, where the check's name and its behaviour had come apart. These
    retained intervals are economic scale guards, not universal physical limits
    or calibrated tests. Valid economic extremes can exceed them. Their historical
    tolerance and extreme-row ranking remain unchanged during schema migration.
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
    horizon_sessions: int = 21,
    execution_lag_sessions: int = 1,
    n_quantiles: int = 5,
    vintage: str = "pit",
    universe_membership: pd.DataFrame | None = None,
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
    construction_filters = list(raw.attrs.get("construction_filters", []))

    # Eligibility is the first gate.  A value for a name that had already left
    # the declared universe must not reach the magnitude check, winsor bounds,
    # neutralisation or standardisation.  Removing it only at the label join is
    # too late: it has already changed every surviving name's z-score.
    if universe_membership is None:
        universe_membership = historical_universe_membership(store, signal_dates)
    raw, universe_report = filter_to_historical_universe(
        raw, universe_membership, signal_dates
    )

    # Before any cleaning, but after eligibility. Winsorising would pull an
    # impossible value back to a plausible one and standardising would erase
    # the units the bound is stated in, so a check placed after either would be
    # checking the wrong number. An ineligible value is not evidence about the
    # factor at all and must never appear in the extremes table.
    try:
        magnitude = check_plausible_magnitude(factor, raw)
    except ImplausibleMagnitudeError as exc:
        exc.detail["universe_filter"] = universe_report.to_dict()
        raise

    cleaned, report = prepare_cross_sections(raw, groups=groups)
    panel, label_report = build_panel_with_report(
        cleaned,
        store.prices(),
        horizon_sessions=horizon_sessions,
        execution_lag_sessions=execution_lag_sessions,
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
        construction_filters=construction_filters,
        universe_filter=universe_report,
        label_join=label_report,
        vintage=vintage,
        eligible_values=raw.copy(deep=True),
    )


def comparison_sample_report(pit: pd.DataFrame, restated: pd.DataFrame) -> dict:
    """Describe scoring keys, not label identity or common cleaning inputs.

    Keys are unique observations, not just counts: equal counts can hide entirely
    different securities. Hashes use the same canonical order as membership.
    """
    columns = ["ticker", "signal_date"]

    def keys(panel):
        out = panel[columns].copy()
        out["signal_date"] = pd.to_datetime(out["signal_date"])
        if out.isna().any().any() or out.duplicated(columns).any():
            raise ValueError("Vintage scoring keys must be non-null and unique")
        return out.sort_values(["signal_date", "ticker"]).reset_index(drop=True)

    def key_hash(frame):
        hashed = pd.util.hash_pandas_object(frame[columns], index=False)
        return hashlib.sha256(hashed.to_numpy().tobytes()).hexdigest()

    left, right = keys(pit), keys(restated)
    joined = left.merge(right, on=columns, how="outer", indicator=True, validate="one_to_one")
    common = keys(joined.loc[joined["_merge"] == "both", columns])
    return {
        "scoring_scope": "ARM_SPECIFIC_OBSERVATIONS_ON_SHARED_DATES",
        "cleaning_scope": "ARM_SPECIFIC_INPUT_KEYS",
        "pit_observations": len(left),
        "restated_observations": len(right),
        "common_observations": len(common),
        "pit_only_observations": int((joined["_merge"] == "left_only").sum()),
        "restated_only_observations": int((joined["_merge"] == "right_only").sum()),
        "identical_observation_keys": left.equals(right),
        "pit_key_hash": key_hash(left),
        "restated_key_hash": key_hash(right),
        "common_key_hash": key_hash(common),
        "label_and_holding_period_identity": "NOT_CHECKED",
    }


def compare_vintages(
    factor: Factor,
    store: Store,
    signal_dates: pd.DatetimeIndex,
    groups: pd.Series | None = None,
    **kwargs,
) -> VintageComparison:
    """Run a factor on both data vintages and report the gap.

    Both fundamental read methods retain ``period_end <= asof`` but ignore filing
    visibility. This includes premature access to first filings as well as later
    amendments. Each arm retains its own effective sample and cleaning inputs;
    this diagnostic does not isolate amendments to already-available facts.
    """
    # Construct membership once.  Reusing the exact key panel makes it
    # impossible for the PIT/restated comparison to vary both vintage and
    # membership by accident.
    membership = historical_universe_membership(store, signal_dates)
    pit_run = compute_factor(
        factor,
        store,
        signal_dates,
        groups=groups,
        vintage="pit",
        universe_membership=membership,
        **kwargs,
    )

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
            detail={
                "sensitivity_notice": SENSITIVITY_NOTICE,
                "layers": {name: {
                    "scope": scope, "status": "NOT_APPLICABLE",
                    "reason": "no_declared_fundamental_dependency",
                    "outcome_identity": {"status": "NOT_CHECKED"},
                    "ic_gap": None, "ls_sharpe_gap": None,
                } for name, scope in SCOPES.items()},
            },
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
    substituted_calls = {"fundamentals_asof": 0, "fundamentals_history_asof": 0}

    def leaking_asof(signal_date, tags=None, intended_signal_date=None):
        substituted_calls["fundamentals_asof"] += 1
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
        # One whole stored row per (cik, tag). groupby().last() took the last
        # non-null value per column and could splice two rows together. The sort
        # and its tie order are unchanged; only the splicing is removed.
        return (
            out.sort_values(["cik", "tag", "period_end"])
            .drop_duplicates(["cik", "tag"], keep="last")
            .reset_index(drop=True)
        )

    def leaking_history_asof(signal_date, tags=None, intended_signal_date=None):
        """Restated arm retaining every start/end context needed for TTM."""
        substituted_calls["fundamentals_history_asof"] += 1
        out = restated_frame
        if tags:
            out = out.loc[out["tag"].isin(tags)]
        return out.loc[out["period_end"] <= pd.Timestamp(signal_date)].copy()

    try:
        store.fundamentals_asof = leaking_asof  # type: ignore[method-assign]
        store.fundamentals_history_asof = leaking_history_asof  # type: ignore[method-assign]
        restated_run = compute_factor(
            factor,
            store,
            signal_dates,
            groups=groups,
            vintage="restated",
            universe_membership=membership,
            **kwargs,
        )
    finally:
        store.fundamentals_asof = original  # type: ignore[method-assign]
        store.fundamentals_history_asof = original_history  # type: ignore[method-assign]

    # Incident 6 in the sibling repository needed date alignment for its fixture.
    # That fix shape does not establish identical (date, ticker) subsets here.
    # Preserve this original-process diagnostic and explicitly expose the scope.
    shared = sorted(
        set(pit_run.panel["signal_date"]).intersection(restated_run.panel["signal_date"])
    )
    pit_scored = pit_run.panel[pit_run.panel["signal_date"].isin(shared)]
    restated_scored = restated_run.panel[restated_run.panel["signal_date"].isin(shared)]
    sample = comparison_sample_report(pit_scored, restated_scored)
    sample["pit_observations_before_date_alignment"] = len(pit_run.panel)
    sample["restated_observations_before_date_alignment"] = len(restated_run.panel)
    n_quantiles = kwargs.get("n_quantiles", 5)
    pit_protocol = run_protocol(factor.factor_id, pit_scored, n_quantiles=n_quantiles)
    restated_protocol = run_protocol(factor.factor_id, restated_scored, n_quantiles=n_quantiles)

    gap = restated_protocol.summary["ic_mean"] - pit_protocol.summary["ic_mean"]

    if (
        pit_run.universe_filter.membership_key_hash
        != restated_run.universe_filter.membership_key_hash
    ):
        raise RuntimeError(
            "PIT and restated runs used different historical-universe keys; "
            "the vintage comparison is confounded"
        )

    path_exercised = sum(substituted_calls.values()) > 0
    comparison_prices = None

    def label_builder(cleaned):
        nonlocal comparison_prices
        if comparison_prices is None:
            comparison_prices = store.prices()
        return build_panel_with_report(
            cleaned, comparison_prices, horizon_sessions=kwargs.get("horizon_sessions", 21),
            execution_lag_sessions=kwargs.get("execution_lag_sessions", 1),
        )

    layers = diagnostic_layers(
        factor.factor_id, pit_scored, restated_scored,
        getattr(pit_run, "eligible_values", None), getattr(restated_run, "eligible_values", None),
        groups=groups, label_builder=label_builder, n_quantiles=n_quantiles,
        sample_report=comparison_sample_report, path_exercised=path_exercised,
    )
    original_layer = layers["original-process"]
    sample["label_and_holding_period_identity"] = original_layer["outcome_identity"]["status"]
    if not path_exercised:
        passed, verdict = None, (
            "NOT APPLICABLE: substituted fundamental read methods were not called; "
            "embedded price-table inputs were not revised. No cleanliness inference."
        )
    elif not shared:
        passed, verdict = None, "INCONCLUSIVE: no shared signal dates."
    elif original_layer["ic_gap"] is None:
        passed, verdict = None, f"INCONCLUSIVE: {original_layer['reason']}."
    elif not np.isfinite(gap):
        passed, verdict = None, "INCONCLUSIVE: one of the vintages could not be scored."
    elif gap > MATERIAL_GAP:
        passed = False
        verdict = (
            f"FAIL: the restated vintage scores {gap:+.4f} higher in IC "
            f"({restated_protocol.summary['ic_mean']:+.4f} vs "
            f"{pit_protocol.summary['ic_mean']:+.4f}), exceeding the positive "
            f"diagnostic threshold {MATERIAL_GAP:.4f}. This is not a significance test "
            "or an isolated restatement-value effect."
        )
    elif gap < -MATERIAL_GAP:
        passed = True
        verdict = (
            f"PASS (opposite direction): the point-in-time vintage scores HIGHER "
            f"by {-gap:.4f}. The negative gap exceeds the diagnostic threshold "
            "in magnitude; PASS only means the positive-gap trigger did not fire. "
            "This is not evidence of cleanliness or statistical significance."
        )
    else:
        passed = True
        verdict = (
            f"PASS: absolute IC gap {abs(gap):.4f} is within the preconfigured "
            f"diagnostic threshold {MATERIAL_GAP:.4f}. This does not establish "
            "equivalence, absence of information, or an estimation-noise bound."
        )

    return VintageComparison(
        factor_id=factor.factor_id,
        pit=pit_protocol,
        restated=restated_protocol,
        applicable=path_exercised,
        passed=passed,
        verdict=verdict,
        detail={
            "n_shared_dates": len(shared),
            "material_gap_threshold": MATERIAL_GAP,
            "threshold_kind": "PRECONFIGURED_DIAGNOSTIC_NOT_SIGNIFICANCE_TEST",
            "sample_comparison": sample,
            "layers": layers,
            "sensitivity_notice": SENSITIVITY_NOTICE,
            "substituted_read_calls": substituted_calls,
            "read_path_coverage": "EXERCISED" if path_exercised else "NOT_EXERCISED",
            "read_path_violations": pit_run.read_path_check["n_violations"],
            "naive_trap_rows": pit_run.naive_trap["n_trap_rows"],
            "universe_membership_key_hash": (
                pit_run.universe_filter.membership_key_hash
            ),
            "universe_rows_excluded_pit": (
                pit_run.universe_filter.n_excluded_outside_universe
            ),
            "universe_rows_excluded_restated": (
                restated_run.universe_filter.n_excluded_outside_universe
            ),
        },
    )
