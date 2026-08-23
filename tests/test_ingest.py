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

from fza.ingest.prices import fetch_stooq, parse_stooq_csv
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


def test_facts_filed_before_their_period_end_are_excluded():
    """Real XBRL contains impossible dates, and the schema rejects them.

    Filers mistype period ends and nothing in the submission process catches it.
    The constraint is right; handling the violation at parse time is what keeps
    one bad filing from aborting an ingest of thirty thousand rows. The first
    live run failed exactly this way.
    """
    payload = {
        "cik": 1234567,
        "facts": {
            "us-gaap": {
                "Assets": {
                    "units": {
                        "USD": [
                            # filed BEFORE the period it reports on: impossible
                            {
                                "end": "2029-12-31", "val": 1.0, "form": "10-K",
                                "filed": "2021-02-15", "accn": "bad",
                            },
                            {
                                "end": "2020-12-31", "val": 2.0, "form": "10-K",
                                "filed": "2021-02-15", "accn": "good",
                            },
                        ]
                    }
                }
            }
        },
    }
    report = IngestReport()
    out = parse_companyfacts(payload, report=report)
    assert len(out) == 1
    assert out["accession"].iloc[0] == "good"
    assert report.n_excluded_filed_before_period == 1


def test_excluded_impossible_dates_are_counted_not_silent():
    """The count is what distinguishes a filer error from an absence."""
    payload = {
        "cik": 1,
        "facts": {"us-gaap": {"Assets": {"units": {"USD": [
            {"end": "2030-12-31", "val": 1.0, "form": "10-K", "filed": "2020-01-01"},
        ]}}}},
    }
    report = IngestReport()
    assert parse_companyfacts(payload, report=report).empty
    assert report.n_excluded_filed_before_period == 1
    assert "n_excluded_filed_before_period" in report.to_dict()


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


def test_stooq_parser_rejects_an_html_error_page():
    """A rejected request comes back as HTML with a 200 status.

    Reaching read_csv with it fails several frames from the real cause, which is
    that the request was refused. The first live run returned zero rows for all
    thirty tickers this way.
    """
    html = "<!DOCTYPE html><html><body>Access denied</body></html>"
    assert parse_stooq_csv(html, "TEST").empty


def test_stooq_request_carries_a_browser_user_agent():
    """Stooq refuses a bare session, and the failure is silent.

    Asserting the header rather than the download keeps this testable offline.
    """

    class FakeResponse:
        text = "Date,Open,High,Low,Close,Volume\n2020-01-02,1,1,1,1,1\n"

        def raise_for_status(self):
            return None

    class FakeSession:
        def __init__(self):
            self.headers = {}
            self.seen = None

        def get(self, url, params=None, timeout=None):
            self.seen = dict(self.headers)
            return FakeResponse()

    session = FakeSession()
    fetch_stooq("TEST", session=session)
    assert "User-Agent" in session.seen
    assert "Mozilla" in session.seen["User-Agent"]


def test_attach_shares_survives_mismatched_datetime_units():
    """merge_asof raises on differing datetime resolutions rather than coercing.

    The identical failure was fixed in build_panel during the pipeline work and
    not audited across the other join sites, so it surfaced again here on the
    first live run. A fix applied at one call site is not a fix.
    """
    from fza.ingest.prices import attach_shares_outstanding

    prices = pd.DataFrame(
        {
            "ticker": ["AAA", "AAA"],
            "cik": ["0000000001"] * 2,
            "trade_date": pd.to_datetime(
                ["2020-06-01", "2020-06-02"]
            ).astype("datetime64[s]"),
            "open": [1.0, 1.0],
            "high": [1.0, 1.0],
            "low": [1.0, 1.0],
            "close": [1.0, 1.0],
            "close_adj": [1.0, 1.0],
            "volume": [1.0, 1.0],
            "shares_out": [None, None],
        }
    )
    fundamentals = pd.DataFrame(
        {
            "cik": ["0000000001"],
            "tag": ["CommonStockSharesOutstanding"],
            "filed": pd.to_datetime(["2020-05-01"]).astype("datetime64[us]"),
            "value": [1_000_000.0],
        }
    )
    out = attach_shares_outstanding(prices, fundamentals)
    assert (out["shares_out"] == 1_000_000.0).all()


def test_shares_are_not_backfilled_before_the_first_filing():
    """Back-filling would put a future disclosure into a historical row.

    That is the exact error the schema exists to prevent, reintroduced through a
    convenience.
    """
    from fza.ingest.prices import attach_shares_outstanding

    prices = pd.DataFrame(
        {
            "ticker": ["AAA", "AAA"],
            "cik": ["0000000001"] * 2,
            "trade_date": pd.to_datetime(["2020-01-02", "2020-06-02"]),
            "open": [1.0, 1.0],
            "high": [1.0, 1.0],
            "low": [1.0, 1.0],
            "close": [1.0, 1.0],
            "close_adj": [1.0, 1.0],
            "volume": [1.0, 1.0],
            "shares_out": [None, None],
        }
    )
    fundamentals = pd.DataFrame(
        {
            "cik": ["0000000001"],
            "tag": ["CommonStockSharesOutstanding"],
            "filed": pd.to_datetime(["2020-05-01"]),
            "value": [1_000_000.0],
        }
    )
    out = attach_shares_outstanding(prices, fundamentals).sort_values("trade_date")
    assert pd.isna(out["shares_out"].iloc[0])  # before the filing existed
    assert out["shares_out"].iloc[1] == 1_000_000.0


def test_yfinance_has_an_explicit_default_start():
    """Without one, yfinance returns about a month and the run looks successful.

    The first live run produced 690 rows across thirty tickers -- roughly 23 days
    each -- which is too short for any factor here and did not raise.
    """
    from fza.ingest.prices import DEFAULT_START

    assert pd.Timestamp(DEFAULT_START) < pd.Timestamp("2015-01-01")


def test_yfinance_is_declared_as_an_ingest_dependency():
    """The fallback is part of ingestion, not optional within it.

    Omitting it made every fallback raise ImportError, which was then swallowed
    as a per-ticker failure -- so the run reported "no data" for tickers whose
    only problem was a missing package.
    """
    root = Path(__file__).resolve().parents[1]
    pyproject = (root / "pyproject.toml").read_text(encoding="utf-8")
    ingest_line = next(
        line for line in pyproject.splitlines() if line.strip().startswith("ingest =")
    )
    assert "yfinance" in ingest_line
