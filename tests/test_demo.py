"""Tests for the demo entry point.

The demo has one property worth protecting: it must run without an ingested
store, and it must say loudly that the fixture numbers are not findings. A demo
that silently produced plausible-looking figures from a random walk would be the
exact deception this project exists to expose, committed by the project's own
front page.
"""

from __future__ import annotations

import json
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

import pandas as pd
import pytest

from fza.demo import describe_data, main, open_store, signal_dates_for
from fza.ingest.prices import ingest_prices
from fza.provenance import research_environment


def _capture_demo(args):
    output = StringIO()
    with redirect_stdout(output):
        code = main(args)
    return code, output.getvalue()


@pytest.fixture(scope="module")
def full_fixture_report(tmp_path_factory):
    # Reuse one fresh full-window execution, never a stored historical output.
    # Console and --outdir paths are exercised together; assertions stay separate.
    outdir = tmp_path_factory.mktemp("full-demo")
    code, output = _capture_demo(
        ["--db", "/definitely/not/a/real/path.duckdb", "--outdir", str(outdir)]
    )
    return code, output, outdir / "demo_report.txt"


# ----------------------------------------------------------------------
# Mode selection
# ----------------------------------------------------------------------
def test_falls_back_to_fixtures_when_no_store_exists():
    store, mode = open_store(Path("/definitely/not/a/real/path.duckdb"))
    assert mode == "fixture"
    assert describe_data(store, mode)["securities"] > 0
    store.close()


def test_fixture_mode_is_labelled_as_not_findings(full_fixture_report):
    """The disclaimer is load-bearing, not decoration.

    Fixture prices are a random walk. Any factor statistic computed on them is
    noise, and presenting it without that context would be indistinguishable
    from presenting a result.
    """
    _, out, _ = full_fixture_report
    assert "NOT findings" in out
    assert "random" in out.lower()
    assert "ingest first" in out


def test_demo_runs_end_to_end_on_fixtures(full_fixture_report):
    code, out, _ = full_fixture_report
    assert code == 0
    assert "RESEARCH ENVIRONMENT" in out
    assert "lock SHA-256" in out
    assert f"lock status   {research_environment()['lock_status']}" in out
    assert "STANDARD PROTOCOL" in out
    assert "PUBLISHED-ANOMALY DENOMINATOR" in out
    assert "current base      8 included (baseline 10, delta -2)" in out
    assert "FACTOR-CONSTRUCTION SAMPLE FILTERS" in out
    assert "latest_equity_must_be_positive" in out
    assert "HISTORICAL UNIVERSE GATE" in out
    assert "FORWARD-LABEL ATTRITION" in out
    assert "POINT-IN-TIME VS RESTATED" in out
    assert "mom_12_1" in out and "bm_ratio" in out


def test_price_only_factor_is_marked_not_applicable(full_fixture_report):
    """Reporting a zero gap for momentum would invite the wrong conclusion."""
    _, out, _ = full_fixture_report
    assert "not applicable" in out
    assert "not\n    evidence" in out or "not" in out


def test_report_is_written_when_requested(full_fixture_report):
    _, out, report = full_fixture_report
    assert report.exists()
    saved = report.read_text(encoding="utf-8")
    assert "FACTOR ZOO AUDIT" in saved
    assert "NOT findings" in saved
    assert out.startswith(saved)
    bundle = json.loads(report.with_name("demo_run.json").read_text(encoding="utf-8"))
    assert bundle["evidence"]["mode"] == "fixture"
    assert bundle["fixture_spec"]["seed"] == 11
    assert len(bundle["factors"]) == 10


# ----------------------------------------------------------------------
# Signal dates
# ----------------------------------------------------------------------
def test_signal_dates_skip_the_formation_window():
    """Dates the factors cannot serve would fill the report with empty
    cross-sections and understate coverage."""
    store, _ = open_store(None)
    dates = signal_dates_for(store, min_history_months=15)
    first_price = store.con.execute("SELECT min(trade_date) FROM prices").fetchone()[0]
    assert dates[0] > pd.Timestamp(first_price)
    assert (dates.is_month_end).all()
    pd.testing.assert_index_equal(
        dates, signal_dates_for(store, freq=pd.offsets.MonthEnd(), min_history_months=15)
    )
    store.close()


# ----------------------------------------------------------------------
# Configuration errors must not masquerade as download failures
# ----------------------------------------------------------------------
def test_unknown_price_source_raises_before_downloading():
    """A misspelled source would otherwise be recorded as N download failures.

    Indistinguishable from a network problem, and the operator would go looking
    at their connection. Per-item error handling must not swallow a
    configuration error.
    """
    with pytest.raises(ValueError, match="unknown price source"):
        ingest_prices(["AAPL"], source_order=("stooq", "yfinanace"))


def test_valid_sources_are_listed_in_the_error():
    with pytest.raises(ValueError, match="yfinance"):
        ingest_prices(["AAPL"], source_order=("nonsense",))


# ----------------------------------------------------------------------
# A failing factor stays visible
# ----------------------------------------------------------------------
# The demo runs the full pipeline per factor, so a test that calls it twice
# costs more than the rest of this file put together. Six dates exercise every
# branch these tests are about.
_FAST = ["--db", "/definitely/not/a/real/path.duckdb", "--max-dates", "6"]


def _factors_with_impossible_range(factor_id: str = "bm_ratio"):
    """load_all(), with one factor given a range nothing can satisfy."""
    import dataclasses

    from fza.factors.registry import load_all

    factors = load_all()
    factors[factor_id] = dataclasses.replace(
        factors[factor_id], plausible_range=(1e9, 2e9)
    )
    return factors


@pytest.fixture(scope="module")
def failed_fixture_report():
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr("fza.demo.load_all", _factors_with_impossible_range)
        return _capture_demo(_FAST)


@pytest.fixture(scope="module")
def fast_fixture_report():
    return _capture_demo(_FAST)


def test_a_factor_that_fails_its_magnitude_check_stays_in_the_table(failed_fixture_report):
    """Catching the error must not be the same as hiding it.

    The magnitude check is only worth having if a reader can see it fire. A demo
    that dropped the failing row would leave nine plausible factors on screen and
    no sign that a tenth had been rejected -- which is how a check becomes
    decoration.
    """
    code, out = failed_fixture_report
    assert code == 0
    assert "FAILED: magnitude" in out
    # the row itself, not just the word
    protocol = out.split("STANDARD PROTOCOL")[1].split("THE TRAP")[0]
    row = next(ln for ln in protocol.splitlines() if ln.strip().startswith("bm_ratio"))
    assert "FAILED: magnitude" in row
    # and the reason, with the numbers that produced it
    assert "fall outside" in out
    assert "1e+09, 2e+09" in out
    assert "most extreme:" in out


def test_the_other_factors_still_run_when_one_fails(failed_fixture_report):
    """One rejected factor must not take the report down with it."""
    _, out = failed_fixture_report
    protocol = out.split("STANDARD PROTOCOL")[1].split("THE TRAP")[0]

    def status_of(factor_id: str) -> str:
        line = next(
            ln for ln in protocol.splitlines() if ln.strip().startswith(factor_id + " ")
        )
        return line.split()[-1]

    assert status_of("bm_ratio") == "magnitude"
    for still_working in ("ep_ratio", "roe", "log_mktcap", "asset_growth"):
        assert status_of(still_working) == "OK"
    assert protocol.count("  OK") >= 7


def test_the_status_column_reports_an_empty_factor_as_its_own_outcome(fast_fixture_report):
    """'FAILED: empty' and 'FAILED: magnitude' are different things.

    Six subsampled signal dates leave the momentum factors without a formation
    window, so they legitimately produce nothing. Collapsing that into the same
    label as a rejected magnitude would tell a reader to go looking in the wrong
    place -- which is the failure mode of incident 11, where the message named
    the factor and the fault was in a column.
    """
    _, out = fast_fixture_report
    protocol = out.split("STANDARD PROTOCOL")[1].split("THE TRAP")[0]

    assert "FAILED: empty" in protocol
    assert "produced no values at all" in protocol
    assert "FAILED: magnitude" not in protocol


def test_a_failed_factor_is_named_in_the_vintage_section_too(failed_fixture_report):
    """Absent for a reason and absent by omission look identical on the page."""
    _, out = failed_fixture_report
    vintages = out.split("POINT-IN-TIME VS RESTATED")[1]
    assert "bm_ratio" in vintages
    assert "not compared" in vintages
    assert "FAILED: magnitude" in vintages


def test_an_undeclared_range_is_printed_as_undefined_not_as_a_pass(fast_fixture_report):
    """The report must distinguish 'checked and fine' from 'never checked'.

    Six of the ten factors have no plausible range yet. Printing a blank, or
    nothing at all, would let a reader take silence for a clean bill -- the same
    error as writing 0 where the share count is unknown.
    """
    _, out = fast_fixture_report
    registered = out.split("REGISTERED FACTORS")[1].split("STANDARD PROTOCOL")[0]

    assert "plausible range" in registered
    assert "undefined" in registered  # the six that have none
    assert "0.0001 .. 100" in registered  # bm_ratio, deliberately asymmetric
    assert "NOT that the factor passed" in out


def test_the_universe_is_reported_by_taxonomy_not_as_one_number(fast_fixture_report):
    """'60 securities' overstates what a value factor sees by the IFRS filers.

    Seven of the first sixty companies report under ifrs-full and so have no
    fundamentals at all. They belong in the universe a momentum factor sees and
    not in the one a value factor sees, and a single count cannot say that.
    """
    _, out = fast_fixture_report

    assert "with us-gaap" in out
    assert "fundamental factors see only these" in out
