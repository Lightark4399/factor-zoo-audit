"""Cross-sectional preparation, applied identically to every factor.

Each step here is a choice that changes results, so each is made once, centrally,
and documented — rather than being made forty times inside forty factor
implementations that then cannot be compared with each other.

The order is winsorise, then neutralise, then standardise, and the order matters:

**Winsorise first, on raw values.** A single mis-scaled observation — a stock
whose book value was filed in thousands rather than millions — dominates both the
mean and the standard deviation, so standardising first would let that one row
compress every other observation toward zero. Clipping before scaling makes the
scale robust to exactly the data errors that a real ingestion pipeline produces.

**Neutralise before standardising.** Industry neutralisation subtracts a group
mean; doing it after standardisation would mean subtracting a group mean of
already-scaled values, which leaves the result depending on how many industries
happen to be present that day. Subtracting first and scaling the residual gives
a quantity whose units are stable across dates.

**Standardise last, and cross-sectionally.** Every metric downstream is
cross-sectional, so the scaling has to be too. A time-series standardisation
would import information from other dates into a number that is supposed to
describe one day's ranking.

What is deliberately not done here
----------------------------------
No filling of missing values. A stock without a book value is not a stock with an
average book value; it is a stock the factor cannot rank, and it is dropped with
a count rather than imputed. Imputation would put a fabricated number into the
cross-section and let it influence every quantile boundary.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd


class EmptyFactorError(ValueError):
    """Raised when a factor returns no values at all.

    A subclass rather than a bare ValueError so a caller can tell an empty
    factor apart from every other way cleaning can fail, and report it as its
    own status instead of a generic failure. It stays a ValueError so code
    written against the older behaviour still catches it.
    """


@dataclass
class CleaningReport:
    """What the cleaning did, so attrition is visible rather than silent."""

    n_input: int
    n_output: int
    n_dropped_missing: int
    n_winsorised: int
    n_dates: int
    n_dates_too_small: int
    min_cross_section: int
    detail: dict = field(default_factory=dict)

    @property
    def retention(self) -> float:
        return self.n_output / self.n_input if self.n_input else float("nan")

    def to_dict(self) -> dict:
        return {
            "n_input": self.n_input,
            "n_output": self.n_output,
            "n_dropped_missing": self.n_dropped_missing,
            "n_winsorised": self.n_winsorised,
            "retention": self.retention,
            "n_dates": self.n_dates,
            "n_dates_too_small": self.n_dates_too_small,
            "min_cross_section": self.min_cross_section,
            **self.detail,
        }


@dataclass
class LabelJoinReport:
    """Where cleaned signal rows went when forward labels were attached."""

    n_input: int
    n_output: int
    n_dropped_without_label: int
    outcome_counts: dict[str, int]
    detail: dict = field(default_factory=dict)

    @property
    def retention(self) -> float:
        return self.n_output / self.n_input if self.n_input else float("nan")

    def to_dict(self) -> dict:
        return {
            "n_input": self.n_input,
            "n_output": self.n_output,
            "n_dropped_without_label": self.n_dropped_without_label,
            "retention": self.retention,
            "outcome_counts": dict(self.outcome_counts),
            **self.detail,
        }


def winsorise(values: pd.Series, lower: float = 0.01, upper: float = 0.99) -> tuple[pd.Series, int]:
    """Clip to the given quantiles. Returns the clipped series and a count."""
    if values.notna().sum() < 3:
        return values, 0
    lo, hi = values.quantile(lower), values.quantile(upper)
    clipped = values.clip(lower=lo, upper=hi)
    n = int((clipped != values).sum())
    return clipped, n


def standardise(values: pd.Series) -> pd.Series:
    """Zero mean, unit standard deviation within the cross-section.

    Returns zeros when the cross-section has no dispersion. That is the honest
    encoding: a factor that assigns every stock the same value carries no ranking
    information, and zeros propagate that fact rather than producing division-by-
    zero noise that looks like a signal.
    """
    sd = values.std(ddof=1)
    if not np.isfinite(sd) or sd <= 0:
        return pd.Series(0.0, index=values.index)
    return (values - values.mean()) / sd


def neutralise(values: pd.Series, groups: pd.Series) -> pd.Series:
    """Subtract the group mean, leaving within-group deviations.

    Groups with a single member get a residual of exactly zero, which is correct:
    a stock alone in its industry has no within-industry comparison, so it should
    carry no within-industry signal. Leaving it at its raw value would let the
    industry's level leak back in through a group of one.
    """
    aligned = groups.reindex(values.index)
    return values - values.groupby(aligned).transform("mean")


def prepare_cross_sections(
    factor_values: pd.DataFrame,
    groups: pd.Series | None = None,
    winsor: tuple[float, float] | None = (0.01, 0.99),
    do_standardise: bool = True,
    min_cross_section: int = 10,
) -> tuple[pd.DataFrame, CleaningReport]:
    """Clean a long factor frame date by date.

    ``factor_values`` has columns ``ticker, signal_date, value``. ``groups`` maps
    ticker to an industry code; when absent, neutralisation is skipped rather
    than silently approximated.

    Dates with fewer than ``min_cross_section`` names are dropped entirely. A
    cross-sectional statistic computed on eight stocks is not a small
    measurement, it is a different quantity, and averaging it together with days
    of five hundred names would let the noisiest days move the result most.
    """
    if factor_values.empty:
        # Failing loudly here rather than returning an empty frame: an empty
        # factor is always a bug in the factor, and letting it propagate means
        # the error surfaces several layers later as a dtype mismatch in a join,
        # which sends the reader to the wrong file.
        raise EmptyFactorError(
            "factor produced no values. Check the computation before the "
            "cleaning stage -- an empty result is never a legitimate outcome."
        )

    df = factor_values.copy()
    df["signal_date"] = pd.to_datetime(df["signal_date"])
    n_input = len(df)

    finite = df["value"].notna() & np.isfinite(df["value"])
    n_dropped = int((~finite).sum())
    df = df.loc[finite]

    out, n_winsorised, n_small = [], 0, 0
    for date, g in df.groupby("signal_date", sort=True):
        if len(g) < min_cross_section:
            n_small += 1
            continue
        v = g.set_index("ticker")["value"]

        if winsor is not None:
            v, k = winsorise(v, *winsor)
            n_winsorised += k
        if groups is not None:
            v = neutralise(v, groups)
        if do_standardise:
            v = standardise(v)

        out.append(pd.DataFrame({"ticker": v.index, "signal_date": date, "value": v.to_numpy()}))

    result = (
        pd.concat(out, ignore_index=True)
        if out
        else pd.DataFrame(columns=["ticker", "signal_date", "value"])
    )
    # Building the frame date by date leaves signal_date as object dtype when
    # the per-date frames are concatenated. Normalising here rather than at each
    # call site keeps the join in build_panel from failing on a dtype mismatch --
    # a failure mode that is silent until the merge produces zero rows.
    result["signal_date"] = pd.to_datetime(result["signal_date"])

    report = CleaningReport(
        n_input=n_input,
        n_output=len(result),
        n_dropped_missing=n_dropped,
        n_winsorised=n_winsorised,
        n_dates=int(result["signal_date"].nunique()) if len(result) else 0,
        n_dates_too_small=n_small,
        min_cross_section=min_cross_section,
        detail={
            "winsor": list(winsor) if winsor else None,
            "standardised": do_standardise,
            "neutralised": groups is not None,
        },
    )
    return result, report


def _forward_return_candidates(
    prices: pd.DataFrame,
    signal_dates: pd.DatetimeIndex,
    horizon_days: int = 21,
    execution_lag: int = 1,
) -> tuple[pd.DataFrame, set[pd.Timestamp]]:
    """Return every price-history candidate and its label outcome.

    Unlike the public ``forward_returns``, this retains rows with missing entry
    or exit prices so the label join can count why a cleaned factor row was
    dropped. Numerical timing is deliberately unchanged here.
    """
    px = prices.copy()
    px["trade_date"] = pd.to_datetime(px["trade_date"])
    wide = px.pivot_table(
        index="trade_date", columns="ticker", values="close_adj", aggfunc="last"
    ).sort_index()

    rows = []
    dates_without_horizon: set[pd.Timestamp] = set()
    all_dates = wide.index
    for date in signal_dates:
        signal_date = pd.Timestamp(date)
        pos = all_dates.searchsorted(signal_date)
        entry_idx = pos + execution_lag
        exit_idx = entry_idx + horizon_days
        if exit_idx >= len(all_dates):
            dates_without_horizon.add(signal_date)
            continue

        entry = wide.iloc[entry_idx]
        exit_ = wide.iloc[exit_idx]
        with np.errstate(divide="ignore", invalid="ignore"):
            ret = (exit_ / entry) - 1.0
        finite = np.isfinite(ret)
        both_missing = entry.isna() & exit_.isna()
        outcome = pd.Series("matched", index=ret.index, dtype="object")
        outcome.loc[both_missing] = "missing_entry_and_exit_price"
        outcome.loc[entry.isna() & ~both_missing] = "missing_entry_price"
        outcome.loc[exit_.isna() & ~both_missing] = "missing_exit_price"
        outcome.loc[~finite & entry.notna() & exit_.notna()] = "nonfinite_return"

        rows.append(
            pd.DataFrame(
                {
                    "ticker": ret.index,
                    "signal_date": signal_date,
                    "forward_return": ret.where(finite).to_numpy(),
                    "entry_date": all_dates[entry_idx],
                    "exit_date": all_dates[exit_idx],
                    "label_outcome": outcome.to_numpy(),
                }
            )
        )

    columns = {
        "ticker": pd.Series(dtype="object"),
        "signal_date": pd.Series(dtype="datetime64[ns]"),
        "forward_return": pd.Series(dtype="float64"),
        "entry_date": pd.Series(dtype="datetime64[ns]"),
        "exit_date": pd.Series(dtype="datetime64[ns]"),
        "label_outcome": pd.Series(dtype="object"),
    }
    candidates = pd.concat(rows, ignore_index=True) if rows else pd.DataFrame(columns)
    return candidates, dates_without_horizon


def forward_returns(
    prices: pd.DataFrame,
    signal_dates: pd.DatetimeIndex,
    horizon_days: int = 21,
    execution_lag: int = 1,
) -> pd.DataFrame:
    """Return realised over the holding period, starting after the execution lag.

    ``execution_lag=1`` is the honest default: a signal formed at a close cannot
    trade at that close, so the position opens at the next available price. The
    lag is a parameter so the execution-timing audit can vary it and measure what
    the assumption is worth — a strategy that only works at lag 0 is trading at a
    price that did not exist when the signal did.

    Returns are computed from adjusted closes, so splits and dividends are
    already handled; using raw closes here would introduce fake jumps that the
    factor would appear to predict.
    """
    candidates, _ = _forward_return_candidates(
        prices, signal_dates, horizon_days, execution_lag
    )
    return candidates.loc[
        candidates["label_outcome"] == "matched",
        ["ticker", "signal_date", "forward_return", "entry_date", "exit_date"],
    ].reset_index(drop=True)


def build_panel(
    factor_values: pd.DataFrame,
    prices: pd.DataFrame,
    horizon_days: int = 21,
    execution_lag: int = 1,
) -> pd.DataFrame:
    """Join cleaned factor values to forward returns.

    The result is the four-column contract ``backtest-audit`` consumes, plus the
    forward return the execution-timing audit needs. Joining here rather than
    inside each test keeps every downstream metric on an identical sample — the
    same principle that made the point-in-time comparison attributable.
    """
    panel, _ = build_panel_with_report(
        factor_values,
        prices,
        horizon_days=horizon_days,
        execution_lag=execution_lag,
    )
    return panel


def build_panel_with_report(
    factor_values: pd.DataFrame,
    prices: pd.DataFrame,
    horizon_days: int = 21,
    execution_lag: int = 1,
) -> tuple[pd.DataFrame, LabelJoinReport]:
    """Join labels and count every cleaned factor row that cannot be labelled."""
    signal_dates = pd.DatetimeIndex(
        sorted(pd.to_datetime(factor_values["signal_date"]).unique())
    )
    candidates, dates_without_horizon = _forward_return_candidates(
        prices, signal_dates, horizon_days, execution_lag
    )

    fv = factor_values.copy()
    fv["signal_date"] = pd.to_datetime(fv["signal_date"])

    # Both sides are normalised to the same resolution before joining. pandas
    # infers different datetime units depending on how a frame was built, and a
    # mismatch raises rather than returning an empty result -- which is better
    # than silently dropping every row, but only if the join is guarded here.
    fv["signal_date"] = fv["signal_date"].astype("datetime64[ns]")
    if not candidates.empty:
        candidates["signal_date"] = candidates["signal_date"].astype("datetime64[ns]")

    joined = fv.merge(candidates, on=["ticker", "signal_date"], how="left")
    no_horizon = joined["signal_date"].isin(dates_without_horizon)
    joined.loc[no_horizon, "label_outcome"] = "no_full_horizon"
    joined["label_outcome"] = joined["label_outcome"].fillna("no_price_history")

    outcome_counts = {
        str(outcome): int(count)
        for outcome, count in joined["label_outcome"].value_counts().items()
    }
    dropped = joined.loc[joined["label_outcome"] != "matched"]
    dropped_by_date = {
        str(pd.Timestamp(date).date()): int(count)
        for date, count in dropped.groupby("signal_date").size().items()
    }
    matched = joined.loc[joined["label_outcome"] == "matched"].copy()
    panel = matched.rename(
        columns={"value": "prediction", "forward_return": "label"}
    )[
        ["ticker", "signal_date", "prediction", "label", "entry_date", "exit_date"]
    ]
    report = LabelJoinReport(
        n_input=int(len(fv)),
        n_output=int(len(panel)),
        n_dropped_without_label=int(len(fv) - len(panel)),
        outcome_counts=outcome_counts,
        detail={"dropped_by_date": dropped_by_date},
    )
    return panel.reset_index(drop=True), report
