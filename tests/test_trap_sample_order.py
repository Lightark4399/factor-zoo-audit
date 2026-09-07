"""Diagnostic examples must not depend on unordered SQL or input row order."""

import pandas as pd
import pytest

from fza.store import Store


@pytest.mark.parametrize("grace_days", [0, 20])
def test_trap_examples_have_a_canonical_order(grace_days):
    with Store() as store:
        tickers = [f"T{i:02d}" for i in reversed(range(8))]
        store.con.executemany(
            "INSERT INTO securities (cik, ticker, first_filing, last_filing) "
            "VALUES (?, ?, '2019-01-01', '2021-01-01')",
            [(ticker, ticker) for ticker in tickers],
        )
        store.con.executemany(
            "INSERT INTO fundamentals "
            "(cik, tag, period_start, period_end, filed, value, form, accession, fact_type) "
            "VALUES (?, 'StockholdersEquity', '2019-12-31', '2019-12-31', "
            "'2020-02-15', 100, '10-K', 'test-filing', 'instant')",
            [(ticker,) for ticker in tickers],
        )
        values = pd.DataFrame({"ticker": tickers, "signal_date": pd.Timestamp("2020-01-31")})
        expected_tickers = sorted(tickers)[:5] if grace_days == 0 else []
        for seed in (1, 13, 29):
            result = store.measure_naive_trap(
                values.sample(frac=1, random_state=seed),
                ["StockholdersEquity"], grace_days=grace_days,
            )
            assert result["n_signal_dates"] == 1
            assert result["n_dates_exposed"] == int(grace_days == 0)
            assert result["n_trap_rows"] == (8 if grace_days == 0 else 0)
            assert [row["ticker"] for row in result["sample"]] == expected_tickers
