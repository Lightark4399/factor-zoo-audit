"""The factor library.

Each factor is a thin function over one of two shared accessors — a wide price
panel or a point-in-time fundamentals read. Anything that would otherwise be
duplicated across factors lives in this module's helpers rather than in the
factors themselves, because forty copies of a resampling rule become forty
slightly different resampling rules.

Sign convention
---------------
Every factor is signed so that **a positive IC means the factor predicts
returns**. Size, volatility, turnover and asset growth are therefore negated at
the point of construction, and their cards say so. The alternative — reporting a
negative IC and remembering which factors are "supposed to be" negative — makes
the summary table unreadable and invites the reader to interpret a sign error as
a finding.

What the exclusions have in common
----------------------------------
Several factors drop rather than winsorise a class of observation: negative book
value, negative earnings, non-positive equity. The rule behind all of them is
the same. Winsorising assumes the extreme values are the same quantity measured
badly; these are a different quantity. A firm with negative equity does not have
a very low book-to-market, it has a ratio whose ordering carries no information
about the mechanism the factor claims. Clipping it to the first percentile would
place it among the growth stocks, which is a statement nobody intends to make.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from ..store import Store
from .registry import register


# ----------------------------------------------------------------------
# Shared accessors
# ----------------------------------------------------------------------
def _wide(prices: pd.DataFrame, column: str) -> pd.DataFrame:
    """Wide panel of one price column, dates by ticker, sorted.

    Raises if the column is entirely null. That case previously produced an
    empty factor, and the pipeline then reported "factor produced no values" --
    naming the factor when the fault was in the data. Four price factors failed
    that way at once on the first real run, and the shared cause took a
    comparison of which factors read which column to find.
    """
    if column not in prices.columns:
        raise ValueError(
            f"price column {column!r} is absent. Available: "
            f"{sorted(prices.columns)}"
        )
    if prices[column].notna().sum() == 0:
        raise ValueError(
            f"price column {column!r} is entirely null, so every factor reading "
            "it will produce nothing. Check the ingest: this is a data problem, "
            "not a factor problem. Store.column_coverage('prices') reports the "
            "non-null rate of every column."
        )

    px = prices.copy()
    px["trade_date"] = pd.to_datetime(px["trade_date"])
    return px.pivot_table(
        index="trade_date", columns="ticker", values=column, aggfunc="last"
    ).sort_index()


# How old an observation may be before a share-count-derived quantity stops
# being carried forward. A month end that lands on a weekend or a holiday is at
# most four days from the last trade; ten leaves room for a longer closure.
# Past that there is no observation to carry, and the forward fill would be
# inventing one -- see AI_NOTES incident 13.
MAX_CARRY_DAYS = 10


def _at_signal_dates(
    wide: pd.DataFrame,
    signal_dates: pd.DatetimeIndex,
    max_staleness_days: int | None = None,
) -> pd.DataFrame:
    """Values at the signal dates, forward-filled from the last observation.

    Forward-filling only. A stock that did not trade on a signal date carries its
    last observed value, which is what a forecaster would have had; back-filling
    would import a future price into a historical row.

    ``max_staleness_days`` bounds how far a value may be carried. Without it the
    fill runs to the end of the panel, which is how a share count that stopped
    being filed in 2012 produced a market capitalisation in 2026 even after the
    ingest had correctly nulled it: the null was real, and the fill overwrote it.
    The default is None -- unbounded, the original behaviour -- because for a
    price a long carry is a stale quote and for a share count it is a fiction,
    and only the caller knows which it is holding.
    """
    idx = pd.DatetimeIndex(signal_dates)
    full = wide.index.union(idx)
    reindexed = wide.reindex(full)
    filled = reindexed.ffill()

    if max_staleness_days is None:
        return filled.reindex(idx)

    # Per column, the timestamp of the last observation carried into each row.
    # Computed rather than assumed: columns go null at different times, and a
    # single panel-wide age would be wrong for every column but one.
    stamps = pd.DataFrame(
        np.where(reindexed.notna(), full.to_numpy()[:, None], np.datetime64("NaT", "ns")),
        index=full,
        columns=reindexed.columns,
    ).ffill()
    age_days = (full.to_numpy()[:, None] - stamps.to_numpy()) / np.timedelta64(1, "D")
    return filled.mask(age_days > max_staleness_days).reindex(idx)


def _long(frame: pd.DataFrame, name: str = "value") -> pd.DataFrame:
    """Wide panel back to the long factor-value contract."""
    out = (
        frame.stack(future_stack=True)
        .rename(name)
        .reset_index()
        .rename(columns={frame.index.name or "index": "signal_date", "level_0": "signal_date"})
        .dropna(subset=[name])
    )
    if "signal_date" not in out.columns:
        out = out.rename(columns={out.columns[0]: "signal_date"})
    return out[["ticker", "signal_date", name]]


def _fundamental_history(
    store: Store,
    signal_dates: pd.DatetimeIndex,
    tags: list[str],
    lag_days: int = 2,
) -> pd.DataFrame:
    """All periods visible at each signal date, not only the latest.

    ``_fundamental_panel`` returns one row per (cik, tag) -- the most recent
    figure, which is what a ratio needs. A factor comparing two periods needs the
    history, and asking for it through the same lagged read keeps both
    observations at one vintage: comparing today's reported assets against a
    figure that has since been restated would make the growth rate depend on a
    revision nobody had seen.
    """
    securities = store.con.execute("SELECT cik, ticker FROM securities").df()
    cik_to_ticker = dict(zip(securities["cik"], securities["ticker"], strict=False))

    rows = []
    for date in signal_dates:
        asof = (pd.Timestamp(date) - pd.Timedelta(days=lag_days)).date()
        got = store.fundamentals_history_asof(
            asof,
            tags=tags,
            intended_signal_date=date,
        )
        if got.empty:
            continue
        got = got.assign(
            ticker=got["cik"].map(cik_to_ticker), signal_date=pd.Timestamp(date)
        )
        rows.append(got.dropna(subset=["ticker"]))

    if not rows:
        return pd.DataFrame(columns=["ticker", "signal_date", "tag", "value", "period_end"])
    return pd.concat(rows, ignore_index=True)


def _ttm_value(facts: pd.DataFrame) -> float | None:
    """Construct one trailing-twelve-month flow from explicit SEC intervals.

    Companyfacts often supplies Q1, Q2 YTD, Q3 YTD and FY. Those are cumulative
    contexts, not four values to add. Within each common period start we take
    successive differences, which makes Q4 ``FY - Q3 YTD`` and prevents the FY
    total from double-counting its first three quarters. Direct quarter contexts
    are preferred when SEC supplies both representations.
    """
    if facts.empty or "period_start" not in facts:
        return None
    work = facts.copy()
    work["period_start"] = pd.to_datetime(work["period_start"], errors="coerce")
    work["period_end"] = pd.to_datetime(work["period_end"], errors="coerce")
    work["filed"] = pd.to_datetime(work.get("filed"), errors="coerce")
    work["value"] = pd.to_numeric(work["value"], errors="coerce")
    work = work.dropna(subset=["period_start", "period_end", "value"])
    work = work.loc[work["period_end"] >= work["period_start"]]
    if work.empty:
        return None

    # Keep the latest visible filing for an exact interval. Different starts are
    # deliberately retained: that is the distinction the old ingest destroyed.
    work = (
        work.sort_values("filed")
        .drop_duplicates(["period_start", "period_end"], keep="last")
        .sort_values(["period_start", "period_end"])
    )

    annual = work.loc[(work["period_end"] - work["period_start"]).dt.days.between(300, 430)]
    discrete: list[dict] = []
    for period_start, group in work.groupby("period_start", sort=True):
        previous_value = 0.0
        previous_end = period_start
        for row in group.sort_values("period_end").itertuples():
            interval_days = (row.period_end - previous_end).days
            delta = float(row.value) - previous_value
            original_days = (row.period_end - row.period_start).days
            if 45 <= interval_days <= 130 and np.isfinite(delta):
                discrete.append(
                    {
                        "period_end": row.period_end,
                        "value": delta,
                        # A directly reported quarter is preferred over the same
                        # quarter recovered as a difference of cumulative facts.
                        "priority": 0 if original_days <= 130 else 1,
                        "filed": row.filed,
                    }
                )
            previous_value = float(row.value)
            previous_end = row.period_end

    if discrete:
        quarters = pd.DataFrame(discrete).sort_values(["period_end", "priority", "filed"])
        quarters = quarters.drop_duplicates("period_end", keep="first").sort_values("period_end")
        latest = quarters.tail(4)
        if len(latest) == 4:
            gaps = latest["period_end"].diff().dropna().dt.days
            if gaps.between(60, 130).all():
                return float(latest["value"].sum())

    # Annual-only filers still have a genuine trailing-twelve-month observation.
    # It updates only annually, which is disclosed rather than filled with an
    # invented quarterly path.
    if not annual.empty:
        return float(annual.sort_values(["period_end", "filed"]).iloc[-1]["value"])
    return None


def _ttm_fundamental_panel(
    store: Store,
    signal_dates: pd.DatetimeIndex,
    tag: str,
    lag_days: int = 2,
) -> pd.DataFrame:
    """Point-in-time TTM values for a duration tag at each signal date."""
    history = _fundamental_history(store, signal_dates, [tag], lag_days=lag_days)
    rows = []
    for (ticker, signal_date), group in history.groupby(["ticker", "signal_date"]):
        value = _ttm_value(group)
        if value is not None and np.isfinite(value):
            rows.append({"ticker": ticker, "signal_date": signal_date, "value": value})
    return pd.DataFrame(rows, columns=["ticker", "signal_date", "value"])


def _fundamental_panel(
    store: Store,
    signal_dates: pd.DatetimeIndex,
    tags: list[str],
    lag_days: int = 2,
) -> pd.DataFrame:
    """Point-in-time fundamentals for every signal date, as a long frame.

    One read per date through ``fundamentals_asof``, with the declared reporting
    lag applied to the query and the true signal date recorded alongside it — the
    pair that lets ``assert_read_path_respected`` verify the lag was actually
    applied rather than only declared.
    """
    securities = store.con.execute("SELECT cik, ticker FROM securities").df()
    cik_to_ticker = dict(zip(securities["cik"], securities["ticker"], strict=False))

    rows = []
    for date in signal_dates:
        asof = pd.Timestamp(date) - pd.Timedelta(days=lag_days)
        got = store.fundamentals_asof(asof, tags=tags, intended_signal_date=date)
        if got.empty:
            continue
        got = got.assign(
            ticker=got["cik"].map(cik_to_ticker), signal_date=pd.Timestamp(date)
        )
        rows.append(got.dropna(subset=["ticker"]))

    if not rows:
        return pd.DataFrame(columns=["ticker", "signal_date", "tag", "value", "period_end"])
    return pd.concat(rows, ignore_index=True)


def _pivot_tags(panel: pd.DataFrame) -> pd.DataFrame:
    """One column per tag, indexed by (ticker, signal_date)."""
    if panel.empty:
        return pd.DataFrame()
    return panel.pivot_table(
        index=["ticker", "signal_date"], columns="tag", values="value", aggfunc="last"
    ).reset_index()


def _market_cap(store: Store, signal_dates: pd.DatetimeIndex) -> pd.DataFrame:
    """Unadjusted close times shares outstanding, at each signal date.

    The unadjusted close is deliberate. Market capitalisation is a level at a
    point in time, and the adjusted series has been rescaled by every subsequent
    split — using it would make a firm's historical market cap depend on
    corporate actions that had not happened yet.
    """
    prices = store.prices()
    if prices.empty:
        return pd.DataFrame()
    px = prices.copy()
    px["trade_date"] = pd.to_datetime(px["trade_date"])
    px["mktcap"] = px["close"] * px["shares_out"]
    wide = px.pivot_table(
        index="trade_date", columns="ticker", values="mktcap", aggfunc="last"
    ).sort_index()
    # Bounded, because a null here is a decision and not a gap. The ingest nulls
    # a share count that is more than 400 days old; an unbounded fill would put
    # the last market cap back over the top of that null and undo it one layer
    # further down. That is what happened: Berkshire's share count stops in 2012
    # and its market cap was still being reported in 2026.
    return _at_signal_dates(wide, signal_dates, max_staleness_days=MAX_CARRY_DAYS)


# ----------------------------------------------------------------------
# Momentum and reversal
# ----------------------------------------------------------------------
def _momentum(
    store: Store, signal_dates: pd.DatetimeIndex, formation: int, skip: int
) -> pd.DataFrame:
    prices = store.prices()
    if prices.empty:
        return pd.DataFrame(columns=["ticker", "signal_date", "value"])

    closes = _at_signal_dates(_wide(prices, "close_adj"), signal_dates)
    # One row is one signal period. Windows are in rows, not trading days -- an
    # earlier version shifted by 21 rows to mean a month on a month-end frame and
    # silently produced nothing.
    end = closes.shift(skip)
    start = closes.shift(formation + skip)
    with np.errstate(divide="ignore", invalid="ignore"):
        value = (end / start) - 1.0
    return _long(value.replace([np.inf, -np.inf], np.nan))


@register("mom_12_1")
def momentum_12_1(store: Store, signal_dates: pd.DatetimeIndex) -> pd.DataFrame:
    """Cumulative return from t-12 to t-1 months."""
    return _momentum(store, signal_dates, formation=12, skip=1)


@register("mom_6_1")
def momentum_6_1(store: Store, signal_dates: pd.DatetimeIndex) -> pd.DataFrame:
    """The same effect over a shorter window, as a check on window sensitivity."""
    return _momentum(store, signal_dates, formation=6, skip=1)


@register("rev_1m")
def reversal_1m(store: Store, signal_dates: pd.DatetimeIndex) -> pd.DataFrame:
    """Negative of the most recent month's return.

    No skip, by construction: this factor *is* the month that momentum skips.
    """
    prices = store.prices()
    if prices.empty:
        return pd.DataFrame(columns=["ticker", "signal_date", "value"])
    closes = _at_signal_dates(_wide(prices, "close_adj"), signal_dates)
    with np.errstate(divide="ignore", invalid="ignore"):
        ret = (closes / closes.shift(1)) - 1.0
    return _long(-ret.replace([np.inf, -np.inf], np.nan))


# ----------------------------------------------------------------------
# Size, risk, liquidity
# ----------------------------------------------------------------------
@register("log_mktcap", tags=("CommonStockSharesOutstanding",), filing_lag_days=2)
def log_market_cap(store: Store, signal_dates: pd.DatetimeIndex) -> pd.DataFrame:
    """Negative log market capitalisation, so that small is the long side."""
    caps = _market_cap(store, signal_dates)
    if caps.empty:
        return pd.DataFrame(columns=["ticker", "signal_date", "value"])
    positive = caps.where(caps > 0)
    return _long(-np.log(positive))


@register("idio_vol")
def idiosyncratic_volatility(
    store: Store, signal_dates: pd.DatetimeIndex, window: int = 60
) -> pd.DataFrame:
    """Negative trailing volatility of daily returns, so that low vol is long.

    Computed on the daily grid and then sampled at the signal dates, rather than
    on the resampled frame: a standard deviation of monthly observations is a
    different quantity from the one the literature measures, and the window
    length would silently mean sixty months.
    """
    prices = store.prices()
    if prices.empty:
        return pd.DataFrame(columns=["ticker", "signal_date", "value"])

    daily = _wide(prices, "close_adj")
    returns = daily.pct_change()
    vol = returns.rolling(window, min_periods=window // 2).std()
    return _long(-_at_signal_dates(vol, signal_dates))


@register("turnover", tags=("CommonStockSharesOutstanding",), filing_lag_days=2)
def share_turnover(
    store: Store, signal_dates: pd.DatetimeIndex, window: int = 21
) -> pd.DataFrame:
    """Negative average daily volume over shares outstanding, so low turnover is long."""
    prices = store.prices()
    if prices.empty:
        return pd.DataFrame(columns=["ticker", "signal_date", "value"])

    volume = _wide(prices, "volume").rolling(window, min_periods=window // 2).mean()
    shares = _wide(prices, "shares_out")

    avg_volume = _at_signal_dates(volume, signal_dates)
    # Same bound, same reason: a share count that is no longer filed must not be
    # carried into a present-day volume. turnover has no plausible range yet, so
    # nothing downstream would have caught it here.
    shares_at = _at_signal_dates(shares, signal_dates, max_staleness_days=MAX_CARRY_DAYS)

    with np.errstate(divide="ignore", invalid="ignore"):
        turn = avg_volume / shares_at.where(shares_at > 0)
    return _long(-turn.replace([np.inf, -np.inf], np.nan))


# ----------------------------------------------------------------------
# Value, profitability, investment -- the fundamentals path
# ----------------------------------------------------------------------
def _ratio_to_market_cap(
    store: Store,
    signal_dates: pd.DatetimeIndex,
    tag: str,
    drop_non_positive: bool = True,
) -> pd.DataFrame:
    """A filed quantity divided by market capitalisation at the signal date."""
    panel = _fundamental_panel(store, signal_dates, tags=[tag])
    if panel.empty:
        return pd.DataFrame(columns=["ticker", "signal_date", "value"])

    caps = _market_cap(store, signal_dates)
    if caps.empty:
        return pd.DataFrame(columns=["ticker", "signal_date", "value"])
    cap_long = caps.stack(future_stack=True).rename("mktcap").reset_index()
    cap_long.columns = ["signal_date", "ticker", "mktcap"]

    merged = panel.merge(cap_long, on=["ticker", "signal_date"], how="inner")
    if drop_non_positive:
        merged = merged.loc[merged["value"] > 0]
    merged = merged.loc[merged["mktcap"] > 0]

    merged["ratio"] = merged["value"] / merged["mktcap"]
    out = merged[["ticker", "signal_date", "ratio"]].rename(columns={"ratio": "value"})
    return out.replace([np.inf, -np.inf], np.nan).dropna(subset=["value"])


# A firm at a hundred times its book, or at a hundredth of it, is already
# extraordinary; past that the number is not a book-to-market. Incident 12
# produced 5752 here.
@register(
    "bm_ratio",
    tags=("StockholdersEquity",),
    filing_lag_days=2,
    plausible_range=(0.01, 100.0),
)
def book_to_market(store: Store, signal_dates: pd.DatetimeIndex) -> pd.DataFrame:
    """Filed common equity over market capitalisation.

    Negative book values are dropped rather than winsorised: the ratio has no
    economic reading there, and clipping would place a distressed firm among the
    growth stocks.
    """
    return _ratio_to_market_cap(store, signal_dates, "StockholdersEquity")


# Losses are excluded, so the ratio is positive. The upper bound is a P/E of
# 0.1 and the lower a P/E of a hundred thousand: both absurd, which is the
# point of a physical bound.
@register(
    "ep_ratio",
    tags=("NetIncomeLoss",),
    filing_lag_days=2,
    plausible_range=(1e-5, 10.0),
)
def earnings_to_price(store: Store, signal_dates: pd.DatetimeIndex) -> pd.DataFrame:
    """Point-in-time TTM net income over market capitalisation; losses excluded."""
    income = _ttm_fundamental_panel(store, signal_dates, "NetIncomeLoss")
    if income.empty:
        return income
    caps = _market_cap(store, signal_dates)
    if caps.empty:
        return pd.DataFrame(columns=["ticker", "signal_date", "value"])
    cap_long = caps.stack(future_stack=True).rename("mktcap").reset_index()
    cap_long.columns = ["signal_date", "ticker", "mktcap"]
    merged = income.rename(columns={"value": "income"}).merge(
        cap_long, on=["ticker", "signal_date"], how="inner"
    )
    merged = merged.loc[(merged["income"] > 0) & (merged["mktcap"] > 0)].copy()
    merged["value"] = merged["income"] / merged["mktcap"]
    return merged[["ticker", "signal_date", "value"]].replace(
        [np.inf, -np.inf], np.nan
    ).dropna(subset=["value"])


# Net income at ten times equity, in either direction. Equity is already
# constrained positive at the query site, so the sign here is income's.
@register(
    "roe",
    tags=("NetIncomeLoss", "StockholdersEquity"),
    filing_lag_days=2,
    plausible_range=(-10.0, 10.0),
)
def return_on_equity(store: Store, signal_dates: pd.DatetimeIndex) -> pd.DataFrame:
    """Point-in-time TTM net income over latest positive filed equity.

    Both quantities come from the same read, so they are the same vintage. Taking
    income from one date's filing and equity from another's would produce a ratio
    that never appeared in any single report.
    """
    income = _ttm_fundamental_panel(store, signal_dates, "NetIncomeLoss")
    equity = _fundamental_panel(store, signal_dates, tags=["StockholdersEquity"])
    if income.empty or equity.empty:
        return pd.DataFrame(columns=["ticker", "signal_date", "value"])
    equity = equity[["ticker", "signal_date", "value"]].rename(columns={"value": "equity"})
    usable = income.rename(columns={"value": "income"}).merge(
        equity, on=["ticker", "signal_date"], how="inner"
    )
    usable = usable.loc[usable["equity"] > 0].copy()
    usable["value"] = usable["income"] / usable["equity"]
    out = usable[["ticker", "signal_date", "value"]]
    return out.replace([np.inf, -np.inf], np.nan).dropna(subset=["value"])


# Year-on-year asset growth of a thousand per cent either way, and the sign
# is already inverted by the factor.
@register(
    "asset_growth",
    tags=("Assets",),
    filing_lag_days=2,
    plausible_range=(-10.0, 10.0),
)
def asset_growth(store: Store, signal_dates: pd.DatetimeIndex) -> pd.DataFrame:
    """Negative year-over-year growth in total assets, so low growth is long.

    The two observations come from the same point-in-time read: the current
    figure and the one from roughly a year earlier, both as known at the signal
    date. Comparing today's reported assets against a figure that has since been
    restated would make the growth rate depend on a revision nobody had seen.
    """
    panel = _fundamental_history(store, signal_dates, tags=["Assets"])
    if panel.empty:
        return pd.DataFrame(columns=["ticker", "signal_date", "value"])

    panel = panel.copy()
    panel["period_end"] = pd.to_datetime(panel["period_end"])

    rows = []
    for (ticker, date), group in panel.groupby(["ticker", "signal_date"]):
        group = group.sort_values("period_end")
        if len(group) < 2:
            continue
        latest = group.iloc[-1]
        # The comparison period is the observation closest to a year before the
        # latest one, chosen from what was visible at this signal date.
        target = latest["period_end"] - pd.DateOffset(years=1)
        earlier = group.iloc[(group["period_end"] - target).abs().argsort().iloc[0]]

        if earlier["period_end"] >= latest["period_end"] or earlier["value"] <= 0:
            continue
        growth = (latest["value"] / earlier["value"]) - 1.0
        if np.isfinite(growth):
            rows.append({"ticker": ticker, "signal_date": date, "value": -growth})

    return pd.DataFrame(rows, columns=["ticker", "signal_date", "value"])

# ----------------------------------------------------------------------
# Factors with no declared plausible range
# ----------------------------------------------------------------------
# mom_12_1, mom_6_1, rev_1m, log_mktcap, idio_vol and turnover register with
# plausible_range left at None, which the registry reports as "undefined" and
# NOT as passing. Each needs a bound stated in its own units before it can have
# one, and guessing would be worse than the gap: a range set too wide never
# fires while making the table look guarded.
#
#   log_mktcap  stores -log(mktcap), so the bound belongs on the log, not on
#               1e6..1e13 as one would first write it
#   idio_vol    is a residual standard deviation whose scale depends on the
#               regression window and on whether it is annualised
#   turnover    changed scale when volume was put back into point-in-time share
#               terms, so any bound written before that is stale
#   momentum    and reversal are returns over different horizons and cannot
#               share one bound
