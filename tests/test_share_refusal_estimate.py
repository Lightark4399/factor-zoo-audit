"""Controls for the read-only share-refusal estimate script."""

import importlib.util
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

import fza.factors.library as library
from fza.factors.registry import load_all
from fza.fixtures import load_fixture_into
from fza.store import Store

SCRIPT = Path(__file__).parents[1] / "scripts" / "estimate_share_refusal.py"
SHARES = "CommonStockSharesOutstanding"


def load_script():
    spec = importlib.util.spec_from_file_location("estimate_share_refusal", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def share(store, period_end, filed, value, accession):
    store.con.execute(
        "INSERT INTO fundamentals (cik, tag, period_start, period_end, filed, value, unit, "
        "form, accession, fact_type) VALUES ('1', ?, ?, ?, ?, ?, 'shares', '10-Q', ?, "
        "'instant')", [SHARES, period_end, period_end, filed, value, accession])


def carry_store():
    """One ticker; a clean group filed 2019-12-15 and a two-value group filed 2020-02-25."""
    store = Store()
    store.con.execute("INSERT INTO securities (cik, ticker, first_filing, last_filing) "
                      "VALUES ('1', 'A', '2019-01-01', '2021-01-01')")
    share(store, "2019-12-10", "2019-12-15", 100.0, "a")
    share(store, "2020-02-20", "2020-02-25", 110.0, "b")
    share(store, "2019-12-31", "2020-02-25", 90.0, "b")
    for day in pd.bdate_range("2020-01-02", "2020-03-31"):
        stored = 110.0 if day >= pd.Timestamp("2020-02-25") else 100.0
        store.con.execute(
            "INSERT INTO prices (ticker, trade_date, close, volume, shares_out) "
            "VALUES ('A', ?, 10, 1000, ?)", [day.date(), stored])
    return store


@pytest.mark.parametrize("fid,value_of", [
    ("log_mktcap", lambda shares: -np.log(10 * shares)),
    ("turnover", lambda shares: -1000 / shares),
])
def test_exact_keys_and_ten_day_carry(fid, value_of):
    script = load_script()
    with carry_store() as store, script.memoized_numerators():
        dates, members, base = script.prepare(store, ("refuse_multi_value",), history_months=0)
        values = script.variants(load_all()[fid], store, base, dates, members,
                                 "refuse_multi_value")
    key = {day: ("A", pd.Timestamp(day)) for day in ("2020-01-31", "2020-02-29", "2020-03-31")}
    assert list(values["current"].index) == list(key.values())
    # Zeroed: the refused rows used on 02-29 (row 02-28) and 03-31 are dropped,
    # and the zero blocks any carry.
    assert list(values["zeroed_no_carry"].index) == [key["2020-01-31"]]
    # NULL: on 02-29 the carry reaches row 02-24 (5 days, older group, 100 shares);
    # on 03-31 every row within 10 days is refused, so the key is lost.
    kept = values["null_with_carry"]
    assert list(kept.index) == [key["2020-01-31"], key["2020-02-29"]]
    assert kept[key["2020-02-29"]] == pytest.approx(value_of(100.0))
    assert values["current"][key["2020-02-29"]] == pytest.approx(value_of(110.0))
    counts, checks = script.summarize(values)
    assert counts["simulated_key_loss_zeroed_no_carry"] == 2
    assert counts["simulated_key_loss_null_with_carry"] == 1
    assert counts["kept_by_carry_value_changed"] == 1
    assert all(checks.values())


def test_duplicate_ticker_is_rejected():
    script = load_script()
    with carry_store() as store:
        store.con.execute("INSERT INTO securities (cik, ticker) VALUES ('2', 'A')")
        with pytest.raises(script.EstimateError, match="duplicate tickers"):
            script.prepare(store, ("refuse_multi_value",), history_months=0)


def test_refused_group_on_fixture_store_is_bounded():
    script = load_script()
    originals = (library._fundamental_panel, library._ttm_fundamental_panel)
    with Store() as store:
        load_fixture_into(store)
        cik, filed, period_end = store.con.execute(
            f"SELECT cik, filed, period_end FROM fundamentals WHERE tag = '{SHARES}' "
            "ORDER BY filed DESC, cik LIMIT 1 OFFSET 40").fetchone()
        # A second, different candidate in the same (cik, filed) group.
        store.con.execute(
            "INSERT INTO fundamentals (cik, tag, period_start, period_end, filed, value, "
            "unit, form, accession, fact_type) VALUES (?, ?, ?, ?, ?, 1.0, 'shares', "
            "'10-Q', 'control', 'instant')",
            [cik, SHARES, period_end - pd.Timedelta(days=90),
             period_end - pd.Timedelta(days=90), filed])
        report = script.estimate(store, factors=("log_mktcap", "turnover"),
                                 rules=("refuse_multi_value",))
    # The memo must not outlive the estimate.
    assert (library._fundamental_panel, library._ttm_fundamental_panel) == originals
    assert report["failed_checks"] == []
    assert report["price_rows"]["refuse_multi_value"] > 0
    for fid in ("log_mktcap", "turnover"):
        row = report["factors"][fid]["refuse_multi_value"]
        assert row["simulated_key_loss_zeroed_no_carry"] > 0
        assert (row["simulated_key_loss_zeroed_no_carry"]
                >= row["simulated_key_loss_null_with_carry"])
        assert (row["remaining_keys_null_with_carry"]
                + row["simulated_key_loss_null_with_carry"] == row["current_keys"])
