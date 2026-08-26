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

from ..store import ReadRecord, Store
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


def _at_signal_dates(wide: pd.DataFrame, signal_dates: pd.DatetimeIndex) -> pd.DataFrame:
    """Values at the signal dates, forward-filled from the last observation.

    Forward-filling only. A stock that did not trade on a signal date carries its
    last observed value, which is what a forecaster would have had; back-filling
    would import a future price into a historical row.
    """
    idx = pd.DatetimeIndex(signal_dates)
    return wide.reindex(wide.index.union(idx)).ffill().reindex(idx)


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
        placeholders = ", ".join(f"'{t}'" for t in tags)
        got = store.con.execute(
            f"SELECT * FROM fundamentals_asof(DATE '{asof.isoformat()}') "
            f"WHERE tag IN ({placeholders})"
        ).df()
        # Logged by hand because this path goes through the macro directly rather
        # than through the store's read helper; without the record the read-path
        # check would not cover this factor at all.
        max_filed = pd.to_datetime(got["filed"]).max() if len(got) else None
        store.access.pit_reads += 1
        store.access.reads.append(
            ReadRecord(
                requested_asof=pd.Timestamp(asof),
                intended_signal_date=pd.Timestamp(date),
                max_filed=None if max_filed is None or pd.isna(max_filed) else max_filed,
                n_rows=len(got),
                tags=tuple(tags),
            )
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
    return _at_signal_dates(wide, signal_dates)


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
    shares_at = _at_signal_dates(shares, signal_dates)

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


@register("bm_ratio", tags=("StockholdersEquity",), filing_lag_days=2)
def book_to_market(store: Store, signal_dates: pd.DatetimeIndex) -> pd.DataFrame:
    """Filed common equity over market capitalisation.

    Negative book values are dropped rather than winsorised: the ratio has no
    economic reading there, and clipping would place a distressed firm among the
    growth stocks.
    """
    return _ratio_to_market_cap(store, signal_dates, "StockholdersEquity")


@register("ep_ratio", tags=("NetIncomeLoss",), filing_lag_days=2)
def earnings_to_price(store: Store, signal_dates: pd.DatetimeIndex) -> pd.DataFrame:
    """Filed net income over market capitalisation. Losses are excluded."""
    return _ratio_to_market_cap(store, signal_dates, "NetIncomeLoss")


@register("roe", tags=("NetIncomeLoss", "StockholdersEquity"), filing_lag_days=2)
def return_on_equity(store: Store, signal_dates: pd.DatetimeIndex) -> pd.DataFrame:
    """Filed net income over filed equity, both point-in-time.

    Both quantities come from the same read, so they are the same vintage. Taking
    income from one date's filing and equity from another's would produce a ratio
    that never appeared in any single report.
    """
    panel = _fundamental_panel(
        store, signal_dates, tags=["NetIncomeLoss", "StockholdersEquity"]
    )
    wide = _pivot_tags(panel)
    if wide.empty or "NetIncomeLoss" not in wide or "StockholdersEquity" not in wide:
        return pd.DataFrame(columns=["ticker", "signal_date", "value"])

    usable = wide.loc[wide["StockholdersEquity"] > 0].copy()
    usable["value"] = usable["NetIncomeLoss"] / usable["StockholdersEquity"]
    out = usable[["ticker", "signal_date", "value"]]
    return out.replace([np.inf, -np.inf], np.nan).dropna(subset=["value"])


@register("asset_growth", tags=("Assets",), filing_lag_days=2)
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
