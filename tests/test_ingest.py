"""Tests for the ingestion parsers.

Network access is confined to two functions; everything else is a pure function
of a response body and is tested here against a recorded payload. The fixture
keeps the real structure — a dict keyed by index, restatements as repeated
``end`` values, custom namespaces, unexpected units — because those quirks are
exactly what a hand-written fixture would leave out and what breaks a parser.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from fza.ingest.prices import parse_stooq_csv
from fza.ingest.sec import (
    ACCEPTED_FORMS,
    CORE_TAGS,
    IngestReport,
    SECClient,
    derive_filing_history,
    parse_companyfacts,
    parse_ticker_map,
)

FIXTURES = Path(__file__).resolve().parent / "fixtures"


@pytest.fixture(scope="module")
def payload():
    return json.loads((FIXTURES / "companyfacts_sample.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def parsed(payload):
    report = IngestReport(n_companies_requested=1)
    return parse_companyfacts(payload, report=report), report


# ----------------------------------------------------------------------
# The property the project depends on
# ----------------------------------------------------------------------
def test_restatement_survives_as_two_rows(parsed):
    """SEC already records revisions as repeated periods with later filings.

    No reconstruction is needed, and none should be attempted: the source shape
    is exactly what the bitemporal table wants.
    """
    df, _ = parsed
    se = df[(df["tag"] == "StockholdersEquity") & (df["period_end"] == "2020-03-31")]
    assert len(se) == 2
    assert set(se["form"]) == {"10-Q", "10-K/A"}
    assert se["value"].nunique() == 2


def test_filed_is_never_estimated(parsed):
    """A fact without `filed` is dropped rather than assigned a guess.

    An assumed reporting lag would fabricate the one field the entire
    point-in-time guarantee rests on.
    """
    df, report = parsed
    assert df["filed"].notna().all()
    assert report.n_excluded_no_filed == 1


# ----------------------------------------------------------------------
# Exclusions, all counted rather than silent
# ----------------------------------------------------------------------
def test_custom_namespace_is_excluded_and_counted(parsed):
    """A tag one filer invented is not comparable with anything else."""
    _, report = parsed
    assert report.n_excluded_non_usgaap == 2


def test_unaccepted_forms_are_excluded(parsed):
    df, report = parsed
    assert report.n_excluded_form == 1
    assert set(df["form"]).issubset(set(ACCEPTED_FORMS))


def test_unexpected_units_are_excluded(parsed):
    """A figure in EUR is not comparable with the USD panel."""
    df, report = parsed
    assert report.n_excluded_unit == 1
    assert set(df["unit"]).issubset({"USD", "shares"})


def test_duplicate_facts_within_one_filing_are_deduplicated(parsed):
    """A filing may report the same figure in several contexts."""
    df, _ = parsed
    key = ["cik", "tag", "period_end", "filed", "form"]
    assert not df.duplicated(subset=key).any()


def test_only_core_tags_are_kept(parsed):
    df, _ = parsed
    assert set(df["tag"]).issubset(set(CORE_TAGS))


def test_tag_coverage_is_reported(parsed):
    """So a factor built on a thinly-reported tag can be recognised as such."""
    _, report = parsed
    assert report.tag_coverage["StockholdersEquity"] > 0
    assert "Assets" in report.tag_coverage


# ----------------------------------------------------------------------
# Ticker map and filing history
# ----------------------------------------------------------------------
def test_ticker_map_handles_a_dict_keyed_by_index():
    """The payload is a dict, not a list; treating it as a list yields nothing."""
    data = json.loads((FIXTURES / "company_tickers_sample.json").read_text(encoding="utf-8"))
    out = parse_ticker_map(data)
    assert len(out) == 3
    assert (out["cik"].str.len() == 10).all()
    assert "AAPL" in set(out["ticker"])


def test_filing_history_spans_first_to_last(parsed):
    """The basis of survivorship-free universe reconstruction."""
    df, _ = parsed
    hist = derive_filing_history(df)
    assert len(hist) == 1
    assert hist["first_filing"].iloc[0] == pd.Timestamp("2020-05-01")
    assert hist["last_filing"].iloc[0] == pd.Timestamp("2021-02-15")


def test_filing_history_of_empty_input_is_empty():
    assert derive_filing_history(pd.DataFrame()).empty


# ----------------------------------------------------------------------
# Client contract
# ----------------------------------------------------------------------
def test_client_requires_a_contact_user_agent():
    """SEC's fair-access policy asks for one; a default would misattribute traffic."""
    with pytest.raises(ValueError, match="User-Agent"):
        SECClient(user_agent="my-scraper")
    with pytest.raises(ValueError, match="User-Agent"):
        SECClient(user_agent="")


# ----------------------------------------------------------------------
# Prices
# ----------------------------------------------------------------------
def test_stooq_parser_reads_a_normal_response():
    csv = (
        "Date,Open,High,Low,Close,Volume\n"
        "2020-01-02,100.0,101.0,99.0,100.5,1000000\n"
        "2020-01-03,100.5,102.0,100.0,101.5,1200000\n"
    )
    out = parse_stooq_csv(csv, "TEST")
    assert len(out) == 2
    assert out["ticker"].iloc[0] == "TEST"
    assert out["close"].iloc[1] == pytest.approx(101.5)


def test_stooq_no_data_is_not_mistaken_for_success():
    """Stooq returns 200 with the body 'No data' for an unknown symbol.

    Treating the status code as the answer would insert an empty frame and let
    the ticker look downloaded.
    """
    assert parse_stooq_csv("No data", "NOPE").empty
    assert parse_stooq_csv("", "NOPE").empty


def test_stooq_parser_rejects_an_unexpected_schema():
    assert parse_stooq_csv("Foo,Bar\n1,2\n", "TEST").empty
