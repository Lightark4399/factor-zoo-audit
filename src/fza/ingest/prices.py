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


def fetch_yfinance(ticker: str, start: str | None = None, end: str | None = None) -> pd.DataFrame:
    """Fallback source. Drops delisted tickers, which is why it is second."""
    try:
        import yfinance as yf
    except ImportError as exc:  # pragma: no cover
        raise ImportError(
            "yfinance is needed for the fallback source: pip install yfinance"
        ) from exc

    data = yf.download(
        ticker, start=start, end=end, auto_adjust=False, progress=False, threads=False
    )
    if data is None or data.empty:
        return pd.DataFrame()

    if isinstance(data.columns, pd.MultiIndex):
        data.columns = data.columns.get_level_values(0)

    return pd.DataFrame(
        {
            "ticker": ticker.upper(),
            "trade_date": pd.to_datetime(data.index),
            "open": data["Open"].astype(float).to_numpy(),
            "high": data["High"].astype(float).to_numpy(),
            "low": data["Low"].astype(float).to_numpy(),
            "close": data["Close"].astype(float).to_numpy(),
            "close_adj": data.get("Adj Close", data["Close"]).astype(float).to_numpy(),
            "volume": data["Volume"].astype(float).to_numpy(),
            "shares_out": None,
        }
    ).reset_index(drop=True)


def ingest_prices(
    tickers: list[str],
    session: Any | None = None,
    use_yfinance_fallback: bool = True,
    on_progress=None,
) -> tuple[pd.DataFrame, PriceReport]:
    """Download prices for several tickers, recording which source supplied each.

    A failure for one ticker is collected rather than raised: a single delisted
    or renamed symbol must not abort a five-hundred-name download, and the
    coverage rate is more informative than the exception would have been.
    """
    report = PriceReport(n_requested=len(tickers))
    frames = []

    for i, ticker in enumerate(tickers):
        frame = pd.DataFrame()
        try:
            frame = fetch_stooq(ticker, session=session)
            if not frame.empty:
                report.n_stooq += 1
        except Exception as exc:
            report.failures.append(f"{ticker} (stooq): {type(exc).__name__}: {exc}")

        if frame.empty and use_yfinance_fallback:
            try:
                frame = fetch_yfinance(ticker)
                if not frame.empty:
                    report.n_yfinance += 1
            except Exception as exc:
                report.failures.append(f"{ticker} (yfinance): {type(exc).__name__}: {exc}")

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

    shares["filed"] = pd.to_datetime(shares["filed"])
    shares = shares.sort_values("filed").rename(columns={"value": "shares_filed"})

    px = prices.copy()
    px["trade_date"] = pd.to_datetime(px["trade_date"])
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
