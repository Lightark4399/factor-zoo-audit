"""Ingestion entry point: `python -m fza.ingest.run`.

The only part of this project that reaches the internet. Everything downstream —
the whole test suite, the pipeline, the audits — runs on what this produces or on
fixtures, so a reviewer can verify the correctness argument without downloading
anything.

Defaults are deliberately small. A first run should be twenty or thirty companies
so that a failure is cheap and legible; scaling up after that is a flag change,
not a different code path.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

from ..store import Store
from .prices import attach_shares_outstanding, ingest_prices
from .sec import (
    CORE_TAGS,
    STANDARD_UNKNOWN,
    IngestReport,
    SECClient,
    derive_filing_history,
    ingest_companies,
)

# How far the two coverage numbers may drift before the run says something.
# They measure different things -- one that the request worked, one that it
# returned anything usable -- and a gap means companies answered and gave
# nothing back.
COVERAGE_GAP_WARNING = 0.05


def _warn_on_coverage_gap(
    report: IngestReport, tickers: pd.DataFrame, threshold: float = COVERAGE_GAP_WARNING
) -> list[str]:
    """Name the companies a fundamental factor cannot read.

    The same rule as the price column check below: a coverage number that
    only aggregates cannot say which company is missing, and the failure then
    surfaces much later as a thin cross-section that nobody traces back. On
    the first sixty-company run twelve companies sat in this gap while the
    reported coverage read 98%.

    The bar is an accounting row, not any row. Accepting 20-F let five IFRS
    filers through on a DEI cover-page share count alone, which lifted
    ``data_coverage_rate`` to 95% and closed the gap below this threshold
    while nothing about those companies had become readable. A check that a
    fix can silence without fixing anything is worse than no check.

    Returns the tickers named, so a caller can assert on them."""
    unusable = set(report.companies_without_accounting_rows)
    if not unusable:
        return []

    empty = set(report.companies_without_rows)
    named = tickers.loc[tickers["cik"].isin(unusable), ["ticker", "cik"]]
    labels = []
    for row in named.itertuples():
        standard = report.standard_per_company.get(row.cik, STANDARD_UNKNOWN)
        why = "no rows" if row.cik in empty else "share count only"
        labels.append(f"{row.ticker} ({standard}, {why})")

    gap = report.request_success_rate - report.accounting_coverage_rate
    if gap > threshold:
        print(
            f"  WARNING: {len(unusable)} companies answered but carry no "
            f"readable accounting series ({gap:.0%} of the universe).",
            flush=True,
        )
        print("  Fundamental factors will not see them:", flush=True)
        for label in labels:
            print(f"    {label}", flush=True)
    return labels


def _progress(label: str):
    def report(done: int, total: int) -> None:
        if done % 10 == 0 or done == total:
            print(f"  {label}: {done}/{total}", flush=True)

    return report


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="fza-ingest",
        description="Download SEC filings and prices into a DuckDB store.",
    )
    ap.add_argument("--out", type=Path, default=Path("data/fza.duckdb"))
    ap.add_argument(
        "--user-agent",
        required=True,
        help=(
            "SEC requires a User-Agent identifying you, with a contact address: "
            "'Your Name your.email@example.com'. It is a condition of the "
            "fair-access policy."
        ),
    )
    ap.add_argument(
        "--limit",
        type=int,
        default=30,
        help="number of companies to ingest (default 30; start small)",
    )
    ap.add_argument(
        "--tickers",
        type=str,
        default=None,
        help="comma-separated tickers; overrides --limit when given",
    )
    ap.add_argument("--skip-prices", action="store_true")
    ap.add_argument(
        "--start",
        default="2010-01-01",
        help="earliest price date (default 2010-01-01)",
    )
    ap.add_argument(
        "--price-source",
        default="stooq,yfinance",
        help=(
            "comma-separated source order. Stooq is first by default because it "
            "retains delisted securities; if it fails from your connection, use "
            "'yfinance,stooq' and note that the run report will show the "
            "survivorship-prone share."
        ),
    )
    args = ap.parse_args(argv)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    client = SECClient(user_agent=args.user_agent)

    print("fetching ticker map...", flush=True)
    tickers = client.fetch_ticker_map()
    if args.tickers:
        wanted = {t.strip().upper() for t in args.tickers.split(",")}
        tickers = tickers.loc[tickers["ticker"].str.upper().isin(wanted)]
    else:
        tickers = tickers.head(args.limit)

    if tickers.empty:
        print("no tickers selected", file=sys.stderr)
        return 2
    print(f"  {len(tickers)} companies selected", flush=True)

    print("fetching filings...", flush=True)
    fundamentals, sec_report = ingest_companies(
        client, tickers["cik"].tolist(), tags=CORE_TAGS, on_progress=_progress("filings")
    )
    print(
        f"  {len(fundamentals):,} rows, "
        f"requests {sec_report.request_success_rate:.0%}, "
        f"data {sec_report.data_coverage_rate:.0%}, "
        f"accounting {sec_report.accounting_coverage_rate:.0%}",
        flush=True,
    )
    _warn_on_coverage_gap(sec_report, tickers)

    prices = pd.DataFrame()
    price_report = None
    if not args.skip_prices:
        print("fetching prices...", flush=True)
        prices, price_report = ingest_prices(
            tickers["ticker"].tolist(),
            start=args.start,
            source_order=tuple(s.strip() for s in args.price_source.split(",")),
            on_progress=_progress("prices"),
        )
        print(f"  {len(prices):,} rows", flush=True)

    # The report is written BEFORE the database. The first live run crashed
    # inside the store on a constraint violation, and because the report was
    # written afterwards, every diagnostic from a four-minute download was lost --
    # including the reason the prices had failed. Diagnostics that only survive a
    # successful run are diagnostics for the case that needs them least.
    report = {
        "sec": sec_report.to_dict(),
        "prices": price_report.to_dict() if price_report else None,
        "n_companies": len(tickers),
        "n_fundamental_rows": len(fundamentals),
        "n_price_rows": len(prices),
    }
    report_path = args.out.with_suffix(".report.json")
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"  diagnostics written to {report_path}", flush=True)

    if price_report and price_report.failures:
        print("  first price failures:", flush=True)
        for f in price_report.failures[:3]:
            print(f"    {f}", flush=True)

    print(f"writing {args.out}...", flush=True)
    if args.out.exists():
        args.out.unlink()
    store = Store(str(args.out))

    history = derive_filing_history(fundamentals)
    securities = tickers.merge(history, on="cik", how="left")
    securities["sic"] = None
    # Recorded on the security, not inferred later from an empty join. An
    # IFRS filer has no fundamentals here, and without this column that is
    # indistinguishable from a us-gaap filer whose ingest failed.
    securities["accounting_standard"] = (
        securities["cik"].map(sec_report.standard_per_company).fillna(STANDARD_UNKNOWN)
    )
    store.load_securities(securities)
    store.load_fundamentals(fundamentals)

    if not prices.empty:
        prices = attach_shares_outstanding(
            prices.merge(tickers[["cik", "ticker"]], on="ticker", how="left"), fundamentals
        )
        store.load_prices(prices)

    # Column coverage, checked immediately after load. A column that is entirely
    # null is invisible until a factor reading it returns nothing several steps
    # later, and the error then names the factor rather than the column.
    coverage = store.column_coverage("prices")
    empty_cols = coverage.loc[coverage["coverage"] == 0.0, "column"].tolist()
    if empty_cols:
        print(f"  WARNING: price columns entirely null: {empty_cols}", flush=True)
        print("  Factors reading them will produce nothing.", flush=True)
    report["price_column_coverage"] = coverage.set_index("column")[
        "coverage"
    ].to_dict()

    # Now that the store loaded, enrich the report with what only it knows.
    report["n_securities"] = len(securities)
    report["n_restatements"] = len(store.restatements())
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")

    print()
    print(f"securities   {len(securities):>8,}")
    print(f"fundamentals {len(fundamentals):>8,}")
    print(f"prices       {len(prices):>8,}")
    print(f"restatements {report['n_restatements']:>8,}")
    print(f"requests ok  {sec_report.request_success_rate:>8.0%}")
    print(f"data coverage{sec_report.data_coverage_rate:>8.0%}")
    print(f"accounting   {sec_report.accounting_coverage_rate:>8.0%}")
    by_standard = securities["accounting_standard"].value_counts().to_dict()
    report["securities_by_standard"] = {k: int(v) for k, v in by_standard.items()}
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(
        "taxonomy     "
        + ", ".join(f"{k} {v}" for k, v in sorted(by_standard.items()))
    )
    if price_report and pd.notna(price_report.survivorship_prone_share):
        print(
            f"of prices, {price_report.survivorship_prone_share:.0%} came from a "
            "source that drops delisted tickers"
        )
    print(f"\nreport written to {report_path}")
    store.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
