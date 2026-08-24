"""Reference factor implementations.

Two factors, chosen to exercise the two data paths the rest of the library will
follow:

* ``mom_12_1`` reads prices only. It establishes the signal-date convention and
  the return-window arithmetic.
* ``bm_ratio`` reads fundamentals through the point-in-time view. It is the one
  that matters for this project's central claim, because accounting data is where
  restatement leakage lives.

Both are written so that every subsequent factor can be a copy with the middle
replaced. Anything that would otherwise be duplicated — universe selection,
signal-date generation, cross-sectional cleaning — belongs in the pipeline, not
here.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from ..store import Store
from .registry import register

# NOTE ON UNITS. `_monthly_closes` resamples to the signal dates, so one row is
# one signal period -- typically one month. Windows are therefore expressed in
# ROWS OF THE RESAMPLED FRAME, not in trading days.
#
# An earlier version shifted by 21 rows to mean "one month", which on a
# month-end frame shifts twenty-one MONTHS. The factor returned zero rows, and
# the emptiness propagated silently all the way to the join. Keeping the unit in
# the name is the cheap guard against repeating it.


def _monthly_closes(prices: pd.DataFrame, signal_dates: pd.DatetimeIndex) -> pd.DataFrame:
    """Adjusted close for each ticker at each signal date, forward-filled.

    Forward-filling is deliberate and one-directional: a stock that did not trade
    on a signal date carries its last observed price, which is the information a
    forecaster would have had. Back-filling would import a future price, which is
    the error this project exists to detect.
    """
    px = prices.copy()
    px["trade_date"] = pd.to_datetime(px["trade_date"])
    wide = px.pivot_table(
        index="trade_date", columns="ticker", values="close_adj", aggfunc="last"
    ).sort_index()
    return wide.reindex(wide.index.union(signal_dates)).ffill().reindex(signal_dates)


@register("mom_12_1")
def momentum_12_1(
    store: Store,
    signal_dates: pd.DatetimeIndex,
    formation_months: int = 12,
    skip_months: int = 1,
) -> pd.DataFrame:
    """Cumulative return from t-12 months to t-1 month.

    The skip is applied by ending the window one month before the signal date,
    not by dropping the last observation of a 12-month window: the two differ
    when a stock has gaps, and only the first matches the definition in the
    literature.

    ``formation_months`` and ``skip_months`` are parameters rather than
    constants so the neighbourhood scan can vary them. A factor that only works
    at (12, 1) and fails at (11, 1) and (12, 2) is fitted to a grid point, and
    the audit reports that as a lack of robustness rather than as a result.
    """
    prices = store.prices()
    if prices.empty:
        return pd.DataFrame(columns=["ticker", "signal_date", "value"])

    closes = _monthly_closes(prices, signal_dates)

    # One row of `closes` is one signal period. The window ends `skip_months`
    # periods before the signal date and starts `formation_months` before that,
    # which is the literature's definition: a 12-month return skipping the most
    # recent month.
    end = closes.shift(skip_months)
    start = closes.shift(formation_months + skip_months)

    with np.errstate(divide="ignore", invalid="ignore"):
        value = (end / start) - 1.0
    value = value.replace([np.inf, -np.inf], np.nan)

    out = (
        value.stack(future_stack=True)
        .rename("value")
        .reset_index()
        .rename(columns={"level_0": "signal_date", "trade_date": "signal_date"})
        .dropna(subset=["value"])
    )
    return out[["ticker", "signal_date", "value"]]


@register("bm_ratio", tags=("StockholdersEquity",), filing_lag_days=2)
def book_to_market(
    store: Store,
    signal_dates: pd.DatetimeIndex,
) -> pd.DataFrame:
    """Book value per the latest available filing, over market capitalisation.

    The fundamentals read goes through ``store.fundamentals_asof(date)``, which
    filters ``filed <= date``. The two-day lag is applied by the subtraction in
    the loop below, so a value is only used if its filing had been public for at
    least two days when the signal was formed. The ``filing_lag_days=2`` on the
    registration declares that intent; passing ``intended_signal_date`` is what
    lets the read-path check confirm the subtraction actually happened.

    Negative book values are dropped rather than winsorised. A negative
    book-to-market has no economic reading — the ordering it induces is
    meaningless, since a firm with equity of −1 would rank above one with equity
    of −100 for no reason connected to the mechanism the factor claims.
    """
    prices = store.prices()
    if prices.empty:
        return pd.DataFrame(columns=["ticker", "signal_date", "value"])

    px = prices.copy()
    px["trade_date"] = pd.to_datetime(px["trade_date"])
    px["mktcap"] = px["close"] * px["shares_out"]
    caps = (
        px.pivot_table(index="trade_date", columns="ticker", values="mktcap", aggfunc="last")
        .sort_index()
    )
    caps = caps.reindex(caps.index.union(signal_dates)).ffill().reindex(signal_dates)

    securities = store.con.execute("SELECT cik, ticker FROM securities").df()
    cik_to_ticker = dict(zip(securities["cik"], securities["ticker"], strict=False))

    rows = []
    for date in signal_dates:
        # The lag is applied to the QUERY, not to the result: asking for the
        # vintage as of two days earlier is what "the filing had been public for
        # two days" means. Filtering afterwards would still have read the newer
        # filing, and a future change could easily let it through.
        asof = pd.Timestamp(date) - pd.Timedelta(days=2)
        fundamentals = store.fundamentals_asof(
            asof, tags=["StockholdersEquity"], intended_signal_date=date
        )
        if fundamentals.empty:
            continue

        for _, row in fundamentals.iterrows():
            ticker = cik_to_ticker.get(row["cik"])
            if ticker is None or ticker not in caps.columns:
                continue
            equity = row["value"]
            cap = caps.at[date, ticker]
            if (
                equity is None
                or not np.isfinite(equity)
                or equity <= 0  # negative book value: no economic reading
                or not np.isfinite(cap)
                or cap <= 0
            ):
                continue
            rows.append({"ticker": ticker, "signal_date": date, "value": equity / cap})

    return pd.DataFrame(rows, columns=["ticker", "signal_date", "value"])
