"""Synthetic fixtures with known ground truth.

The sandbox this was developed in has no access to SEC or price data, so the
correctness argument had to rest on fixtures rather than on a live download.
That turned out to be the better arrangement, for the same reason it was in
``backtest-audit``: a test against real data can only assert that today's output
matches yesterday's, which locks in whatever is wrong today. A fixture whose
answer is known by construction can fail.

The fixture contains one thing that cannot be obtained from a live source at all:
**a restatement whose direction and size are known**. One company files an equity
figure, then revises it months later. Any factor reading the point-in-time view
must see the original until the revision is filed, and a factor reading the
restated view sees the final value throughout. The gap between the two is the
quantity the project reports, and here it is known in advance.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class FixtureSpec:
    # Large enough that the default minimum cross-section of 10 is a realistic
    # constraint rather than one the fixture has to be weakened to satisfy.
    n_securities: int = 40
    start: str = "2018-01-01"
    end: str = "2021-12-31"
    seed: int = 11
    # The company whose filing gets revised, and by how much. Stated here so the
    # test can assert the exact gap rather than merely that one exists.
    restated_index: int = 3
    restatement_factor: float = 0.60  # final equity is 60% of first reported
    restatement_lag_days: int = 180


def build_fixture(spec: FixtureSpec | None = None) -> dict[str, pd.DataFrame]:
    """Securities, prices and fundamentals, with one deliberate restatement."""
    spec = spec or FixtureSpec()
    rng = np.random.default_rng(spec.seed)

    tickers = [f"TST{i:02d}" for i in range(spec.n_securities)]
    ciks = [str(1000000 + i).zfill(10) for i in range(spec.n_securities)]
    dates = pd.bdate_range(spec.start, spec.end)

    # ---- securities -------------------------------------------------
    # One security is delisted part-way through, so universe reconstruction has
    # something to reconstruct. Its last_filing precedes the end of the sample.
    delisted_idx = 7  # one name leaves part-way through, for universe reconstruction
    delist_date = dates[int(len(dates) * 0.6)]
    securities = pd.DataFrame(
        {
            "cik": ciks,
            "ticker": tickers,
            "name": [f"Test Company {i}" for i in range(spec.n_securities)],
            "sic": [f"{2000 + (i % 5) * 100}" for i in range(spec.n_securities)],
            "first_filing": [dates[0]] * spec.n_securities,
            "last_filing": [
                delist_date if i == delisted_idx else dates[-1]
                for i in range(spec.n_securities)
            ],
            # Every fixture company files us-gaap. The fixture exists to
            # exercise the machinery, and an IFRS filer there would test the
            # exclusion rather than the pipeline; the real ingest is where that
            # case belongs.
            "accounting_standard": ["us-gaap"] * spec.n_securities,
        }
    )

    # ---- prices -----------------------------------------------------
    rows = []
    for i, ticker in enumerate(tickers):
        n = len(dates)
        drift = 0.0002 + 0.0001 * (i % 3)
        ret = rng.normal(drift, 0.015, n)
        close = 50.0 * np.exp(np.cumsum(ret))
        shares = 1e7 * (1.0 + 0.5 * (i % 4))
        frame = pd.DataFrame(
            {
                "ticker": ticker,
                "trade_date": dates,
                "open": close * (1 + rng.normal(0, 0.002, n)),
                "high": close * (1 + abs(rng.normal(0, 0.004, n))),
                "low": close * (1 - abs(rng.normal(0, 0.004, n))),
                "close": close,
                "close_adj": close,
                "volume": rng.lognormal(13, 0.5, n),
                "shares_out": shares,
            }
        )
        if i == delisted_idx:
            frame = frame.loc[frame["trade_date"] <= delist_date]
        rows.append(frame)
    prices = pd.concat(rows, ignore_index=True)

    # ---- fundamentals, with the restatement -------------------------
    fundamentals = []
    for i, cik in enumerate(ciks):
        for period_end in pd.date_range(spec.start, spec.end, freq="QE"):
            # A filing appears roughly 45 days after the period ends, which is
            # the pattern that makes point-in-time matter: for six weeks after a
            # quarter closes, the market does not yet know its numbers.
            filed = period_end + pd.Timedelta(days=45)
            if filed > pd.Timestamp(spec.end):
                continue
            equity = 5e8 * (1.0 + 0.3 * (i % 4)) * (1.0 + 0.02 * period_end.quarter)

            # Every tag the factor library reads. An earlier fixture carried only
            # equity and share count, so three factors failed with "produced no
            # values" -- which correctly pointed at the factor, since a factor
            # that returns nothing is always a bug, but the bug was in the
            # fixture. A fixture that cannot exercise the library is not a
            # fixture for it.
            years_elapsed = (period_end.year - pd.Timestamp(spec.start).year)
            values_by_tag = {
                "StockholdersEquity": equity,
                # Income scales with equity so ROE is stable per firm and varies
                # across them -- otherwise the factor has no cross-section to rank.
                "NetIncomeLoss": equity * (0.02 + 0.01 * (i % 5)),
                # Assets grow at a firm-specific rate, which is what asset growth
                # measures. A constant would make the factor degenerate.
                "Assets": equity * 3.0 * (1.0 + 0.05 * (i % 6)) ** years_elapsed,
                "CommonStockSharesOutstanding": 1e7 * (1.0 + 0.5 * (i % 4)),
            }

            for tag, value in values_by_tag.items():
                fundamentals.append(
                    {
                        "cik": cik,
                        "tag": tag,
                        "period_end": period_end.date(),
                        "fiscal_year": period_end.year,
                        "fiscal_period": f"Q{period_end.quarter}",
                        "filed": filed.date(),
                        "value": value,
                        "unit": "shares"
                        if tag == "CommonStockSharesOutstanding"
                        else "USD",
                        "form": "10-Q",
                        "accession": f"{cik}-{period_end.date()}-orig",
                    }
                )

            # The restatement: same period, later filing, different value. Stored
            # as an additional row so the original belief survives.
            if i == spec.restated_index:
                revised_filed = filed + pd.Timedelta(days=spec.restatement_lag_days)
                if revised_filed <= pd.Timestamp(spec.end):
                    fundamentals.append(
                        {
                            "cik": cik,
                            "tag": "StockholdersEquity",
                            "period_end": period_end.date(),
                            "fiscal_year": period_end.year,
                            "fiscal_period": f"Q{period_end.quarter}",
                            "filed": revised_filed.date(),
                            "value": equity * spec.restatement_factor,
                            "unit": "USD",
                            "form": "10-K/A",
                            "accession": f"{cik}-{period_end.date()}-amended",
                        }
                    )

    return {
        "securities": securities,
        "prices": prices,
        "fundamentals": pd.DataFrame(fundamentals),
        "spec": spec,
    }


def load_fixture_into(store, spec: FixtureSpec | None = None) -> dict:
    """Build the fixture and load it, returning the counts and the spec."""
    data = build_fixture(spec)
    n_sec = store.load_securities(data["securities"])
    n_px = store.load_prices(data["prices"])
    n_fun = store.load_fundamentals(data["fundamentals"])
    return {
        "securities": n_sec,
        "prices": n_px,
        "fundamentals": n_fun,
        "spec": data["spec"],
        "restated_cik": str(1000000 + data["spec"].restated_index).zfill(10),
        "restated_ticker": f"TST{data['spec'].restated_index:02d}",
    }
