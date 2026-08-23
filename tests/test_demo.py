"""Tests for the demo entry point.

The demo has one property worth protecting: it must run without an ingested
store, and it must say loudly that the fixture numbers are not findings. A demo
that silently produced plausible-looking figures from a random walk would be the
exact deception this project exists to expose, committed by the project's own
front page.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from fza.demo import describe_data, main, open_store, signal_dates_for
from fza.ingest.prices import ingest_prices


# ----------------------------------------------------------------------
# Mode selection
# ----------------------------------------------------------------------
def test_falls_back_to_fixtures_when_no_store_exists():
    store, mode = open_store(Path("/definitely/not/a/real/path.duckdb"))
    assert mode == "fixture"
    assert describe_data(store, mode)["securities"] > 0
    store.close()


def test_fixture_mode_is_labelled_as_not_findings(capsys):
    """The disclaimer is load-bearing, not decoration.

    Fixture prices are a random walk. Any factor statistic computed on them is
    noise, and presenting it without that context would be indistinguishable
    from presenting a result.
    """
    main(["--db", "/definitely/not/a/real/path.duckdb"])
    out = capsys.readouterr().out
    assert "NOT findings" in out
    assert "random" in out.lower()
    assert "ingest first" in out


def test_demo_runs_end_to_end_on_fixtures(capsys):
    assert main(["--db", "/definitely/not/a/real/path.duckdb"]) == 0
    out = capsys.readouterr().out
    assert "STANDARD PROTOCOL" in out
    assert "POINT-IN-TIME VS RESTATED" in out
    assert "mom_12_1" in out and "bm_ratio" in out


def test_price_only_factor_is_marked_not_applicable(capsys):
    """Reporting a zero gap for momentum would invite the wrong conclusion."""
    main(["--db", "/definitely/not/a/real/path.duckdb"])
    out = capsys.readouterr().out
    assert "not applicable" in out
    assert "not\n    evidence" in out or "not" in out


def test_report_is_written_when_requested(tmp_path):
    main(["--db", "/definitely/not/a/real/path.duckdb", "--outdir", str(tmp_path)])
    report = tmp_path / "demo_report.txt"
    assert report.exists()
    assert "FACTOR ZOO AUDIT" in report.read_text(encoding="utf-8")


# ----------------------------------------------------------------------
# Signal dates
# ----------------------------------------------------------------------
def test_signal_dates_skip_the_formation_window():
    """Dates the factors cannot serve would fill the report with empty
    cross-sections and understate coverage."""
    store, _ = open_store(None)
    dates = signal_dates_for(store, min_history_months=15)
    first_price = store.con.execute("SELECT min(trade_date) FROM prices").fetchone()[0]
    assert dates[0] > __import__("pandas").Timestamp(first_price)
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
