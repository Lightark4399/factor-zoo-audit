"""The standard protocol, run identically on every factor.

No factor-specific adjustment is permitted. That constraint is the reason the
resulting table means anything: if each factor were allowed its own quantile
count, its own weighting, its own sub-period, the comparison across rows would be
a comparison of forty different studies, and the best-looking row would be the
one whose author tried hardest.

The protocol is deliberately conventional. Quantile portfolios, long-short
spreads, monotonicity, an IC series, Fama-MacBeth, and a sub-period split are all
standard, and being standard is the point — a reader can compare these numbers
against published ones. The contribution of this project is not a new test; it is
what happens to these numbers when the audit layer is applied afterwards.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd
from scipy import stats

MIN_PER_QUANTILE = 3


@dataclass
class ProtocolResult:
    """Everything the standard protocol produces for one factor."""

    factor_id: str
    n_dates: int
    n_observations: int
    quantile_returns: pd.DataFrame
    long_short: pd.Series
    ic_series: pd.Series
    monotonicity_rho: float
    monotonicity_p: float
    fama_macbeth: dict
    subperiods: pd.DataFrame
    summary: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "factor_id": self.factor_id,
            "n_dates": self.n_dates,
            "n_observations": self.n_observations,
            "monotonicity_rho": self.monotonicity_rho,
            "monotonicity_p": self.monotonicity_p,
            "fama_macbeth": self.fama_macbeth,
            **self.summary,
        }


def quantile_portfolios(
    panel: pd.DataFrame,
    n_quantiles: int = 5,
    weights: pd.Series | None = None,
) -> pd.DataFrame:
    """Mean forward return per quantile per date.

    ``weights`` supplies market capitalisation for a value-weighted variant.
    Both are reported because they answer different questions: equal weighting
    asks whether the signal ranks stocks, value weighting asks whether the
    ranking survives in the part of the market that can absorb capital. A factor
    that works only equal-weighted is usually a small-cap effect, and the pair of
    numbers says so without further analysis.
    """
    rows = []
    for date, g in panel.groupby("signal_date", sort=True):
        if len(g) < n_quantiles * MIN_PER_QUANTILE:
            continue
        # duplicates='drop' handles a cross-section with heavy ties, which
        # happens for count-like factors. The resulting date has fewer quantiles
        # and is excluded below rather than silently contributing a partial row.
        try:
            q = pd.qcut(g["prediction"], n_quantiles, labels=False, duplicates="drop")
        except ValueError:
            continue
        if q.nunique() < n_quantiles:
            continue

        g = g.assign(quantile=q)
        for qi, sub in g.groupby("quantile"):
            if weights is not None:
                w = weights.reindex(sub["ticker"]).to_numpy(float)
                if not np.isfinite(w).all() or w.sum() <= 0:
                    continue
                ret = float(np.average(sub["label"].to_numpy(float), weights=w))
            else:
                ret = float(sub["label"].mean())
            rows.append({"signal_date": date, "quantile": int(qi), "ret": ret, "n": len(sub)})

    return pd.DataFrame(rows)


def long_short_series(quantiles: pd.DataFrame, n_quantiles: int = 5) -> pd.Series:
    """Top quantile minus bottom quantile, per date."""
    if quantiles.empty:
        return pd.Series(dtype=float)
    wide = quantiles.pivot(index="signal_date", columns="quantile", values="ret")
    top, bottom = n_quantiles - 1, 0
    if top not in wide.columns or bottom not in wide.columns:
        return pd.Series(dtype=float)
    return (wide[top] - wide[bottom]).dropna()


def information_coefficient(panel: pd.DataFrame) -> pd.Series:
    """Spearman rank correlation between signal and forward return, per date.

    Rank-based rather than Pearson: forward returns are heavy-tailed enough that
    one extreme name can otherwise dominate a date's estimate, and a factor is a
    claim about ordering rather than about magnitude.
    """
    out = {}
    for date, g in panel.groupby("signal_date", sort=True):
        if len(g) < 5:
            continue
        x, y = g["prediction"].to_numpy(float), g["label"].to_numpy(float)
        if np.std(x) <= 0 or np.std(y) <= 0:
            continue
        rho, _ = stats.spearmanr(x, y)
        if np.isfinite(rho):
            out[date] = float(rho)
    return pd.Series(out, dtype=float)


def monotonicity(quantiles: pd.DataFrame) -> tuple[float, float]:
    """Is mean return monotone in quantile rank?

    Reported as a Spearman correlation between quantile index and mean return
    across the whole sample. A factor whose extreme portfolios differ but whose
    middle is unordered is usually picking up a tail characteristic rather than a
    continuous relationship — and that distinction determines whether the effect
    survives when the extremes become uninvestable.

    This is one of the falsification criteria most hypothesis cards state, which
    is why it is computed for every factor rather than on request.
    """
    if quantiles.empty:
        return float("nan"), float("nan")
    means = quantiles.groupby("quantile")["ret"].mean()
    if len(means) < 3:
        return float("nan"), float("nan")
    rho, p = stats.spearmanr(means.index.to_numpy(), means.to_numpy())
    return float(rho), float(p)


def fama_macbeth(
    panel: pd.DataFrame, controls: pd.DataFrame | None = None
) -> dict:
    """Cross-sectional regression per date, then a t-test on the coefficients.

    The standard asset-pricing estimator. The t-statistic uses a Newey-West
    correction because the monthly coefficient series is autocorrelated — the
    naive standard error would overstate significance, which for a project about
    overstated significance would be an unfortunate place to cut a corner.
    """
    coefs, dates = [], []
    for date, g in panel.groupby("signal_date", sort=True):
        if len(g) < 10:
            continue
        x = g["prediction"].to_numpy(float)
        y = g["label"].to_numpy(float)

        if controls is not None:
            c = controls.reindex(g["ticker"]).to_numpy(float)
            design = np.column_stack([np.ones(len(g)), x, c])
            design = design[:, ~np.isnan(design).any(axis=0)]
        else:
            design = np.column_stack([np.ones(len(g)), x])

        if np.linalg.matrix_rank(design) < design.shape[1]:
            continue
        try:
            beta = np.linalg.lstsq(design, y, rcond=None)[0]
        except np.linalg.LinAlgError:
            continue
        coefs.append(float(beta[1]))
        dates.append(date)

    if len(coefs) < 5:
        return {"n_periods": len(coefs), "mean_coef": float("nan"), "tstat": float("nan")}

    series = pd.Series(coefs, index=pd.DatetimeIndex(dates))
    mean = float(series.mean())

    try:
        import statsmodels.api as sm

        lags = max(1, int(np.floor(4 * (len(series) / 100) ** (2 / 9))))
        model = sm.OLS(series.to_numpy(), np.ones((len(series), 1))).fit(
            cov_type="HAC", cov_kwds={"maxlags": lags, "use_correction": True}
        )
        tstat, pval, naive = float(model.tvalues[0]), float(model.pvalues[0]), float(
            mean / (series.std(ddof=1) / np.sqrt(len(series)))
        )
    except Exception:
        tstat = pval = float("nan")
        naive = float(mean / (series.std(ddof=1) / np.sqrt(len(series))))

    return {
        "n_periods": len(series),
        "mean_coef": mean,
        "tstat": tstat,
        "tstat_naive": naive,
        "pvalue": pval,
    }


def subperiod_split(long_short: pd.Series, n_periods: int = 3) -> pd.DataFrame:
    """Long-short performance by equal-length sub-period.

    "The effect is concentrated in a single sub-period" is a falsification
    criterion on most cards, so the split runs for every factor. A factor that
    earns everything in one stretch and nothing elsewhere is a description of that
    stretch, not a relationship.
    """
    if long_short.empty:
        return pd.DataFrame()
    chunks = np.array_split(np.arange(len(long_short)), n_periods)
    rows = []
    for i, idx in enumerate(chunks):
        seg = long_short.iloc[idx]
        if seg.empty:
            continue
        sd = seg.std(ddof=1)
        rows.append(
            {
                "period": i + 1,
                "start": seg.index[0],
                "end": seg.index[-1],
                "n": len(seg),
                "mean": float(seg.mean()),
                "sharpe": float(seg.mean() / sd) if sd > 0 else float("nan"),
                "hit_rate": float((seg > 0).mean()),
            }
        )
    return pd.DataFrame(rows)


def run_protocol(
    factor_id: str,
    panel: pd.DataFrame,
    n_quantiles: int = 5,
    weights: pd.Series | None = None,
    controls: pd.DataFrame | None = None,
) -> ProtocolResult:
    """The whole protocol, in the order the report presents it."""
    quantiles = quantile_portfolios(panel, n_quantiles=n_quantiles, weights=weights)
    ls = long_short_series(quantiles, n_quantiles=n_quantiles)
    ic = information_coefficient(panel)
    rho, p = monotonicity(quantiles)
    fm = fama_macbeth(panel, controls=controls)
    subs = subperiod_split(ls)

    ls_sd = ls.std(ddof=1) if len(ls) > 1 else float("nan")
    summary = {
        "ic_mean": float(ic.mean()) if len(ic) else float("nan"),
        "ic_std": float(ic.std(ddof=1)) if len(ic) > 1 else float("nan"),
        "ic_hit_rate": float((ic > 0).mean()) if len(ic) else float("nan"),
        "ls_mean": float(ls.mean()) if len(ls) else float("nan"),
        "ls_sharpe": float(ls.mean() / ls_sd) if np.isfinite(ls_sd) and ls_sd > 0 else float("nan"),
        "ls_hit_rate": float((ls > 0).mean()) if len(ls) else float("nan"),
        "n_quantile_dates": int(quantiles["signal_date"].nunique()) if len(quantiles) else 0,
    }

    return ProtocolResult(
        factor_id=factor_id,
        n_dates=int(panel["signal_date"].nunique()),
        n_observations=len(panel),
        quantile_returns=quantiles,
        long_short=ls,
        ic_series=ic,
        monotonicity_rho=rho,
        monotonicity_p=p,
        fama_macbeth=fm,
        subperiods=subs,
        summary=summary,
    )
