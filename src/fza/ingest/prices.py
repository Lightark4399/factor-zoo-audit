"""Price ingestion.

Two sources, in order of preference:

**Stooq.** A plain CSV endpoint, no key, no rate limit worth speaking of, and —
the reason it comes first — it retains data for securities that have since
delisted. That last property is worth more here than anything else a price source
offers, because the universe reconstruction is only useful if prices exist for
the companies it puts back into the sample.

**yfinance.** Wider coverage of recent names and better corporate-action
handling, but it drops delisted tickers, which reintroduces exactly the bias the
rest of this project works to remove. Used as a fallback and recorded as such, so
a run can report how much of its data came from a survivorship-prone source.

Adjusted prices
---------------
Both sources supply a split- and dividend-adjusted series. Factors that compare
prices across time must use it; factors that need a price level at a point in
time — a market capitalisation, a distance from a 52-week high — must use the raw
close. Conflating them produces returns that are wrong by the size of every
dividend, and the error is small enough per event to look like noise rather than
a bug.

The store keeps both columns for that reason, and the reference factors are
explicit about which one they read.
"""

from __future__ import annotations

import io
from dataclasses import dataclass, field
from typing import Any

import pandas as pd

STOOQ_URL = "https://stooq.com/q/d/l/"

# Stooq refuses or returns an HTML error page for requests without a browser-like
# User-Agent. The first live run downloaded zero rows for all thirty tickers
# because the session was created bare -- the SEC client set a User-Agent, this
# one did not, and the failure was silent because an HTML body simply fails to
# parse as CSV.
BROWSER_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
)


@dataclass
class PriceReport:
    """Coverage and provenance of a price download."""

    n_requested: int = 0
    n_stooq: int = 0
    n_yfinance: int = 0
    n_failed: int = 0
    n_rows: int = 0
    failures: list[str] = field(default_factory=list)

    @property
    def survivorship_prone_share(self) -> float:
        """Fraction of tickers sourced from a provider that drops delistings."""
        total = self.n_stooq + self.n_yfinance
        return self.n_yfinance / total if total else float("nan")

    def to_dict(self) -> dict:
        return {
            "n_requested": self.n_requested,
            "n_stooq": self.n_stooq,
            "n_yfinance": self.n_yfinance,
            "n_failed": self.n_failed,
            "n_rows": self.n_rows,
            "survivorship_prone_share": self.survivorship_prone_share,
            "failures": list(self.failures[:20]),
        }


def parse_stooq_csv(text: str, ticker: str) -> pd.DataFrame:
    """Parse a Stooq daily CSV into the store's price schema.

    Stooq returns the string ``No data`` rather than an error status for an
    unknown symbol, so an empty result must be detected from the body. Treating
    the 200 response as success would insert an empty frame and let the ticker
    look downloaded.
    """
    stripped = (text or "").strip()
    if not stripped or stripped.lower().startswith("no data"):
        return pd.DataFrame()
    # A rejected request comes back as an HTML page with a 200 status, which
    # would otherwise reach read_csv and fail with a parser error several frames
    # away from the actual cause.
    if stripped.startswith("<"):
        return pd.DataFrame()

    frame = pd.read_csv(io.StringIO(text))
    expected = {"Date", "Open", "High", "Low", "Close", "Volume"}
    if not expected.issubset(frame.columns):
        return pd.DataFrame()

    out = pd.DataFrame(
        {
            "ticker": ticker.upper(),
            "trade_date": pd.to_datetime(frame["Date"]),
            "open": frame["Open"].astype(float),
            "high": frame["High"].astype(float),
            "low": frame["Low"].astype(float),
            "close": frame["Close"].astype(float),
            # Stooq's daily series is already adjusted for splits and dividends,
            # so the two close columns coincide. They are kept separate because
            # the distinction matters for other sources and for the factors that
            # need an unadjusted level.
            "close_adj": frame["Close"].astype(float),
            "volume": frame["Volume"].astype(float),
            "shares_out": None,
        }
    )
    return out.dropna(subset=["close"]).sort_values("trade_date").reset_index(drop=True)


def fetch_stooq(ticker: str, session: Any | None = None) -> pd.DataFrame:
    """Download one ticker's daily history from Stooq."""
    if session is None:
        try:
            import requests
        except ImportError as exc:  # pragma: no cover
            raise ImportError(
                "requests is needed for ingestion: pip install -e '.[ingest]'"
            ) from exc
        session = requests.Session()
    session.headers.setdefault("User-Agent", BROWSER_USER_AGENT)

    # Stooq expects US symbols suffixed '.us'.
    symbol = ticker.lower()
    if not symbol.endswith(".us"):
        symbol = f"{symbol}.us"

    resp = session.get(STOOQ_URL, params={"s": symbol, "i": "d"}, timeout=30)
    resp.raise_for_status()
    return parse_stooq_csv(resp.text, ticker)


# Without an explicit start date yfinance returns roughly one month of history.
# The first live run downloaded 690 rows across thirty tickers -- about 23 days
# each -- and looked like a success. A default that silently truncates to a
# window too short for any factor is worse than an error, so the start date is
# required rather than optional.
DEFAULT_START = "2010-01-01"


def cumulative_split_factor(splits) -> pd.Series:
    """For each row, the product of every split taking effect strictly AFTER it.

    A split-adjusted series expresses the whole history in today's share terms.
    Multiplying a row by this factor puts it back into the share terms that were
    current on that day.

    STRICTLY AFTER is the boundary that matters, and it is easy to get wrong by
    one row. The price printed ON a split's effective date is already quoted in
    the new, smaller shares -- Apple closed at 129.04 on 2020-08-31, the day its
    4:1 split took effect, not at 516. So the effective date's own ratio must not
    be applied to it. Hence the reverse cumulative product is shifted up by one:
    each row takes the accumulation belonging to the row after it.
    """
    s = pd.Series(splits).astype(float).replace(0.0, 1.0).fillna(1.0)
    return s[::-1].cumprod()[::-1].shift(-1).fillna(1.0)


def unadjust_close(close_adj, splits) -> pd.Series:
    """Recover the price as it was quoted, from a split-adjusted series.

    ``close_adj`` here means *any* split-adjusted price series. In
    ``fetch_yfinance`` it is yfinance's ``Close`` -- which is adjusted for splits
    but not for dividends -- and NOT its ``Adj Close``, which is adjusted for
    both. Feeding the dividend-adjusted series in would produce a number that was
    never quoted: 120.9557 x 4 = 483.82, where Apple actually closed at 499.23.

    Pure and offline: it takes two series and returns one, so the arithmetic is
    tested against constructed splits rather than against a download.
    """
    close = pd.Series(close_adj).astype(float)
    return close * cumulative_split_factor(splits).to_numpy()


def fetch_yfinance(
    ticker: str, start: str = DEFAULT_START, end: str | None = None
) -> pd.DataFrame:
    """Fallback source. Drops delisted tickers, which is why it is second.

    Prices come back split-adjusted whatever is asked for, so the unadjusted
    series is RECONSTRUCTED here rather than downloaded. See the comment on the
    call below.
    """
    try:
        import yfinance as yf
    except ImportError as exc:  # pragma: no cover
        raise ImportError(
            "yfinance is needed for the fallback source: pip install yfinance"
        ) from exc

    # ``auto_adjust=False`` DOES NOT WORK in this version of yfinance (1.6.0).
    # It restores the 'Adj Close' column, but 'Close' comes back split-adjusted
    # regardless. Probed directly on Apple across its 2020-08-31 4:1 split:
    # yf.download(auto_adjust=False), Ticker().history(auto_adjust=False), and
    # Ticker().history(auto_adjust=False, actions=True) all return 124.81 for
    # 2020-08-28, where the price actually quoted that day was 499.23. There is
    # no call that returns the raw series.
    #
    # So the unadjusted price is reconstructed from the split history rather than
    # downloaded, and ``Ticker().history`` is used because it is the only one of
    # the three that carries the 'Stock Splits' column needed to do it.
    #
    # THIS IS A NEW SINGLE POINT OF DEPENDENCE. Every unadjusted price now rests
    # on that column being complete: a split yfinance failed to record would
    # leave the prices before it silently short by that factor, and nothing
    # downstream could tell. Recorded in the README's limitations section.
    data = yf.Ticker(ticker).history(
        start=start, end=end, auto_adjust=False, actions=True
    )
    if data is None or data.empty:
        return pd.DataFrame()

    if isinstance(data.columns, pd.MultiIndex):
        data.columns = data.columns.get_level_values(0)

    # ``history`` returns an exchange-local tz-aware index; the store holds dates.
    idx = pd.DatetimeIndex(data.index)
    if idx.tz is not None:
        idx = idx.tz_localize(None)
    idx = idx.normalize()

    # No split column means no way to reconstruct, and a factor of 1 says so
    # honestly -- the prices are then whatever the provider returned, which is
    # the pre-existing behaviour rather than a silent guess.
    splits = data["Stock Splits"] if "Stock Splits" in data.columns else 0.0
    factor = cumulative_split_factor(pd.Series(splits, index=data.index)).to_numpy()

    # 'Close' is split-adjusted only; 'Adj Close' is split- AND dividend-adjusted.
    # The unadjusted price must be built from the former. The latter is what the
    # return-based factors want and is stored unchanged.
    if "Adj Close" in data.columns:
        adj = data["Adj Close"].astype(float).to_numpy()
    else:
        adj = data["Close"].astype(float).to_numpy()

    return pd.DataFrame(
        {
            "ticker": ticker.upper(),
            "trade_date": idx,
            # The whole bar is put back into the day's share terms together.
            # Un-splitting the close alone would leave rows whose close sat four
            # times above their own high.
            "open": data["Open"].astype(float).to_numpy() * factor,
            "high": data["High"].astype(float).to_numpy() * factor,
            "low": data["Low"].astype(float).to_numpy() * factor,
            "close": data["Close"].astype(float).to_numpy() * factor,
            "close_adj": adj,
            # Volume moves the other way: a split-adjusted volume counts today's
            # smaller shares, so it is divided rather than multiplied. `turnover`
            # divides volume by a point-in-time share count, and the two have to
            # be in the same share terms or the ratio is off by the split.
            "volume": data["Volume"].astype(float).to_numpy() / factor,
            "shares_out": None,
        }
    ).reset_index(drop=True)


def ingest_prices(
    tickers: list[str],
    session: Any | None = None,
    use_yfinance_fallback: bool = True,
    start: str = DEFAULT_START,
    end: str | None = None,
    source_order: tuple[str, ...] = ("stooq", "yfinance"),
    on_progress=None,
) -> tuple[pd.DataFrame, PriceReport]:
    """Download prices for several tickers, recording which source supplied each.

    A failure for one ticker is collected rather than raised: a single delisted
    or renamed symbol must not abort a five-hundred-name download, and the
    coverage rate is more informative than the exception would have been.

    ``source_order`` exists because provider availability is not a constant.
    Stooq is first by default for the survivorship reason above, but it returned
    404 for every major US ticker on the first live run, from an ordinary
    residential connection. Making the order a parameter -- and reporting which
    source actually supplied each row -- keeps that a recorded fact about the run
    rather than an assumption baked into the code.
    """
    report = PriceReport(n_requested=len(tickers))
    frames = []

    fetchers = {
        "stooq": lambda t: fetch_stooq(t, session=session),
        "yfinance": lambda t: fetch_yfinance(t, start=start, end=end),
    }

    # Validate before downloading anything. A misspelled source name would
    # otherwise be caught inside the per-ticker try block and recorded as thirty
    # download failures -- indistinguishable from a network problem, and the
    # operator would go looking at their connection. Per-item error handling must
    # not swallow a configuration error.
    unknown = [s for s in source_order if s not in fetchers]
    if unknown:
        raise ValueError(
            f"unknown price source(s): {unknown}. Valid sources are "
            f"{sorted(fetchers)}."
        )

    for i, ticker in enumerate(tickers):
        frame = pd.DataFrame()
        for source in source_order:
            if source == "yfinance" and not use_yfinance_fallback:
                continue
            try:
                frame = fetchers[source](ticker)
            except Exception as exc:
                report.failures.append(f"{ticker} ({source}): {type(exc).__name__}: {exc}")
                frame = pd.DataFrame()
            if not frame.empty:
                if source == "stooq":
                    report.n_stooq += 1
                else:
                    report.n_yfinance += 1
                break

        if frame.empty:
            report.n_failed += 1
            if not any(ticker in f for f in report.failures):
                report.failures.append(
                    f"{ticker}: both sources returned no rows (check the "
                    "failure entries above for the underlying error)"
                )
        else:
            frames.append(frame)

        if on_progress is not None:
            on_progress(i + 1, len(tickers))

    combined = (
        pd.concat(frames, ignore_index=True)
        if frames
        else pd.DataFrame(
            columns=[
                "ticker", "trade_date", "open", "high", "low",
                "close", "close_adj", "volume", "shares_out",
            ]
        )
    )
    report.n_rows = len(combined)
    return combined, report


def attach_shares_outstanding(
    prices: pd.DataFrame, fundamentals: pd.DataFrame
) -> pd.DataFrame:
    """Fill ``shares_out`` from filed share counts, as of each trade date.

    Market capitalisation needs a share count, and the only point-in-time source
    for one is the filings. The join is as-of on ``filed``: a trade date carries
    the most recent share count that had actually been reported by then, which is
    the same constraint every other fundamental read obeys.

    Prices for dates before a company's first filing keep a null share count
    rather than borrowing the earliest one backwards. Back-filling would put a
    future disclosure into a historical row — the exact error the schema exists
    to prevent, reintroduced through a convenience.
    """
    if prices.empty or fundamentals.empty:
        return prices

    shares = fundamentals.loc[
        fundamentals["tag"] == "CommonStockSharesOutstanding",
        ["cik", "filed", "value"],
    ].copy()
    if shares.empty:
        return prices

    # Both keys are normalised to the same resolution. pandas infers different
    # datetime units depending on how a frame was built, and merge_asof raises on
    # a mismatch rather than coercing. The same failure was fixed in build_panel
    # during the pipeline work and not audited across the other join sites, so it
    # surfaced again here on the first live run -- a fix applied at one call site
    # is not a fix.
    shares["filed"] = pd.to_datetime(shares["filed"]).astype("datetime64[ns]")
    shares = shares.sort_values("filed").rename(columns={"value": "shares_filed"})

    px = prices.copy()
    px["trade_date"] = pd.to_datetime(px["trade_date"]).astype("datetime64[ns]")
    px = px.sort_values("trade_date")

    # merge_asof with direction='backward' takes the most recent filing at or
    # before each trade date, which is the as-of semantics the schema requires.
    merged = pd.merge_asof(
        px,
        shares[["filed", "shares_filed", "cik"]],
        left_on="trade_date",
        right_on="filed",
        by="cik" if "cik" in px.columns else None,
        direction="backward",
    )
    merged["shares_out"] = merged["shares_out"].fillna(merged["shares_filed"])
    return merged.drop(columns=[c for c in ("filed", "shares_filed") if c in merged.columns])
