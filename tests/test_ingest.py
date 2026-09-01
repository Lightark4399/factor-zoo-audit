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

from fza.ingest.prices import (
    cumulative_split_factor,
    fetch_stooq,
    parse_stooq_csv,
    unadjust_close,
)
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


# ----------------------------------------------------------------------
# Shares outstanding lives in the DEI namespace, not us-gaap
# ----------------------------------------------------------------------
def _dei_payload(include_other_dei_tag: bool = True) -> dict:
    """A payload shaped like the real thing for the namespace question.

    Constructed rather than recorded, because the recorded fixture happens to
    report `CommonStockSharesOutstanding` under us-gaap and so cannot exercise
    the case that actually occurred: eleven of the first thirty companies had no
    us-gaap share count at all, and their cover-page figure sat under `dei`.
    """
    dei_facts = {
        "EntityCommonStockSharesOutstanding": {
            "units": {
                "shares": [
                    {"end": "2020-04-24", "val": 4_300_000_000, "filed": "2020-04-30",
                     "form": "10-Q", "accn": "0000021344-20-000018", "fy": 2020, "fp": "Q1"},
                    {"end": "2021-04-23", "val": 4_310_000_000, "filed": "2021-04-29",
                     "form": "10-Q", "accn": "0000021344-21-000012", "fy": 2021, "fp": "Q1"},
                ]
            }
        }
    }
    if include_other_dei_tag:
        # In DEI, but not in DEI_TAGS. Must stay excluded: what was opened is a
        # named tag, not the namespace.
        dei_facts["EntityPublicFloat"] = {
            "units": {
                "USD": [
                    {"end": "2020-06-30", "val": 2.0e11, "filed": "2021-02-22",
                     "form": "10-K", "accn": "0000021344-21-000009", "fy": 2020, "fp": "FY"},
                    {"end": "2021-06-30", "val": 2.4e11, "filed": "2022-02-22",
                     "form": "10-K", "accn": "0000021344-22-000009", "fy": 2021, "fp": "FY"},
                    {"end": "2022-06-30", "val": 2.6e11, "filed": "2023-02-21",
                     "form": "10-K", "accn": "0000021344-23-000011", "fy": 2022, "fp": "FY"},
                ]
            }
        }
    return {
        "cik": 21344,
        "facts": {
            # No us-gaap share count, which is the real shape: Coca-Cola's
            # us-gaap namespace carries 724 tags and this is not one of them.
            "us-gaap": {
                "Assets": {
                    "units": {
                        "USD": [
                            {"end": "2020-03-31", "val": 8.7e10, "filed": "2020-04-30",
                             "form": "10-Q", "accn": "0000021344-20-000018",
                             "fy": 2020, "fp": "Q1"},
                        ]
                    }
                }
            },
            "dei": dei_facts,
        },
    }


def test_dei_share_count_is_adopted_under_the_usgaap_name():
    """The share count is read from `dei` and written as the us-gaap concept.

    Renaming at the parser means no factor has to know which namespace a share
    count came from, and `attach_shares_outstanding` keeps working unchanged.
    The origin stays recoverable through `source_namespace`.
    """
    report = IngestReport(n_companies_requested=1)
    df = parse_companyfacts(_dei_payload(), report=report)

    shares = df[df["tag"] == "CommonStockSharesOutstanding"]
    assert len(shares) == 2
    assert set(shares["source_namespace"]) == {"dei"}
    assert sorted(shares["value"]) == [4_300_000_000.0, 4_310_000_000.0]
    assert report.n_shares_from_dei == 2

    # The rename is a rename, not a widening: the DEI spelling does not survive.
    assert "EntityCommonStockSharesOutstanding" not in set(df["tag"])
    # And a us-gaap row still reports its own origin.
    assert set(df.loc[df["tag"] == "Assets", "source_namespace"]) == {"us-gaap"}


def test_other_dei_tags_are_still_excluded_and_counted():
    """What was opened is one named tag, not the DEI namespace."""
    report = IngestReport(n_companies_requested=1)
    df = parse_companyfacts(_dei_payload(), report=report)

    assert "EntityPublicFloat" not in set(df["tag"])
    assert report.n_excluded_non_usgaap == 3  # the three EntityPublicFloat facts


def test_the_adopted_dei_tag_is_not_counted_as_an_exclusion():
    """The exclusion count must not include this parser's own intake.

    An earlier shape of this counter summed every fact outside us-gaap before
    the DEI tag was read, so the rows it went on to adopt were also reported as
    excluded -- a number that contradicted itself.
    """
    report = IngestReport(n_companies_requested=1)
    df = parse_companyfacts(_dei_payload(include_other_dei_tag=False), report=report)

    assert report.n_excluded_non_usgaap == 0
    assert report.n_shares_from_dei == 2
    assert len(df[df["tag"] == "CommonStockSharesOutstanding"]) == 2


def test_duration_contexts_with_the_same_end_are_not_collapsed():
    """Quarter, YTD and annual facts can share an end date and mean different things.

    The old key ignored ``start`` and ``frame``, then kept the first context. That
    turns arbitrary JSON order into an accounting convention. A magnitude check
    cannot catch the error because both values are physically ordinary.
    """
    payload = {
        "cik": 1,
        "facts": {
            "us-gaap": {
                "NetIncomeLoss": {
                    "units": {
                        "USD": [
                            {
                                "start": "2024-01-01",
                                "end": "2024-06-30",
                                "val": 25.0,
                                "filed": "2024-08-01",
                                "form": "10-Q",
                                "accn": "0001-24-000002",
                                "fy": 2024,
                                "fp": "Q2",
                                "frame": "CY2024Q2YTD",
                            },
                            {
                                "start": "2024-04-01",
                                "end": "2024-06-30",
                                "val": 15.0,
                                "filed": "2024-08-01",
                                "form": "10-Q",
                                "accn": "0001-24-000002",
                                "fy": 2024,
                                "fp": "Q2",
                                "frame": "CY2024Q2",
                            },
                        ]
                    }
                }
            }
        },
    }

    got = parse_companyfacts(payload, tags=("NetIncomeLoss",))

    assert len(got) == 2
    assert set(got["period_start"].astype(str)) == {"2024-01-01", "2024-04-01"}
    assert set(got["frame"]) == {"CY2024Q2YTD", "CY2024Q2"}
    assert set(got["duration_days"]) == {90, 181}
    assert set(got["fact_type"]) == {"duration"}


# ----------------------------------------------------------------------
# Unadjusted prices are reconstructed from the split history
# ----------------------------------------------------------------------
def _series(values, splits):
    """A split-adjusted close and its split column, indexed by trading day."""
    idx = pd.date_range("2020-01-01", periods=len(values), freq="D")
    return pd.Series(values, index=idx, dtype=float), pd.Series(splits, index=idx, dtype=float)


def test_one_split_lifts_only_the_prices_before_it():
    """The price printed ON the effective date is already in the new shares.

    This is the boundary the reconstruction gets wrong if the cumulative product
    is not shifted: Apple closed at 129.04 on the day of its 4:1 split, not 516.
    """
    close, splits = _series([100.0, 100.0, 25.0, 25.0], [0.0, 0.0, 4.0, 0.0])
    out = unadjust_close(close, splits)

    assert list(out) == [400.0, 400.0, 25.0, 25.0]


def test_two_splits_compound_for_the_earliest_prices():
    """A price before both splits carries the product of both, not the later one."""
    close, splits = _series(
        [1.0, 1.0, 1.0, 1.0, 1.0], [0.0, 0.0, 4.0, 0.0, 10.0]
    )
    out = unadjust_close(close, splits)

    assert list(out) == [40.0, 40.0, 10.0, 10.0, 1.0]


def test_without_splits_the_series_is_returned_unchanged():
    """No split means nothing to undo, and the reconstruction must not invent one."""
    close, splits = _series([10.0, 11.0, 12.0], [0.0, 0.0, 0.0])
    out = unadjust_close(close, splits)

    assert list(out) == [10.0, 11.0, 12.0]


def test_a_missing_split_column_yields_a_factor_of_one():
    """An absent or all-null split column leaves prices as the provider sent them.

    Stated as a test because the alternative -- treating a missing column as a
    reason to guess -- would put a fabricated price in the table. A factor of one
    is the honest answer, and the README records that this makes the split
    history a single point of dependence.
    """
    idx = pd.date_range("2020-01-01", periods=3, freq="D")
    close = pd.Series([10.0, 11.0, 12.0], index=idx)

    assert list(cumulative_split_factor(pd.Series([float("nan")] * 3, index=idx))) == [
        1.0, 1.0, 1.0,
    ]
    assert list(unadjust_close(close, pd.Series([float("nan")] * 3, index=idx))) == [
        10.0, 11.0, 12.0,
    ]
    assert list(cumulative_split_factor(pd.Series([0.0, 0.0, 0.0], index=idx))) == [
        1.0, 1.0, 1.0,
    ]


def _one_price_row_per(dates: list[str]) -> pd.DataFrame:
    """A minimal price frame for one company over the given trade dates."""
    n = len(dates)
    return pd.DataFrame(
        {
            "ticker": ["AAA"] * n,
            "cik": ["0000000001"] * n,
            "trade_date": pd.to_datetime(dates),
            "open": [1.0] * n,
            "high": [1.0] * n,
            "low": [1.0] * n,
            "close": [1.0] * n,
            "close_adj": [1.0] * n,
            "volume": [1.0] * n,
            "shares_out": [None] * n,
        }
    )


def _filings(dates: list[str], values: list[float]) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "cik": ["0000000001"] * len(dates),
            "tag": ["CommonStockSharesOutstanding"] * len(dates),
            "filed": pd.to_datetime(dates),
            "value": values,
        }
    )


def test_a_share_count_stops_being_carried_once_it_is_too_old():
    """The live failure: V, MA and BRK-B kept a 2010 count against a 2026 price.

    ``merge_asof`` carries the last filing forward with no bound, and for a
    multi-class issuer the DEI share-count tag simply stops being filed. The
    result was not a stale market cap, it was a fabricated one, and nothing
    downstream could see it -- see AI_NOTES incident 13.
    """
    from fza.ingest.prices import attach_shares_outstanding

    prices = _one_price_row_per(["2010-06-01", "2020-06-01"])
    out = attach_shares_outstanding(
        prices, _filings(["2010-05-01"], [1_000_000.0])
    ).sort_values("trade_date")

    assert out["shares_out"].iloc[0] == 1_000_000.0  # one month old
    assert pd.isna(out["shares_out"].iloc[1])  # ten years old


def test_the_staleness_bound_admits_a_late_annual_filer():
    """400 days, so a year plus slippage still counts and 401 does not.

    A tighter bound would null out every company that files late or changes its
    fiscal year end, which trades a known error for a silent loss of universe.
    """
    from fza.ingest.prices import MAX_SHARE_COUNT_STALENESS_DAYS, attach_shares_outstanding

    filed = pd.Timestamp("2010-05-01")
    inside = filed + pd.Timedelta(days=MAX_SHARE_COUNT_STALENESS_DAYS)
    outside = filed + pd.Timedelta(days=MAX_SHARE_COUNT_STALENESS_DAYS + 1)

    out = attach_shares_outstanding(
        _one_price_row_per([str(inside.date()), str(outside.date())]),
        _filings(["2010-05-01"], [1_000_000.0]),
    ).sort_values("trade_date")

    assert out["shares_out"].iloc[0] == 1_000_000.0
    assert pd.isna(out["shares_out"].iloc[1])


def test_a_company_that_keeps_filing_is_never_nulled():
    """The bound measures age since the last filing, not age since the first.

    A normal filer refreshes the clock every year, so the mitigation costs it
    nothing. Only a company whose tag stopped being reported loses rows.
    """
    from fza.ingest.prices import attach_shares_outstanding

    filings = _filings(
        ["2010-05-01", "2011-05-01", "2012-05-01", "2013-05-01"],
        [1e6, 2e6, 3e6, 4e6],
    )
    out = attach_shares_outstanding(
        _one_price_row_per(["2010-06-01", "2011-06-01", "2012-06-01", "2013-06-01"]),
        filings,
    ).sort_values("trade_date")

    assert out["shares_out"].notna().all()
    assert list(out["shares_out"]) == [1e6, 2e6, 3e6, 4e6]


# ----------------------------------------------------------------------
# Two coverage numbers, because one of them was measuring the wrong thing
# ----------------------------------------------------------------------
def _foreign_payload(form: str = "20-F", namespace: str = "us-gaap") -> dict:
    """A payload from a foreign private issuer: real tags, unusual form."""
    return {
        "cik": 937966,
        "facts": {
            namespace: {
                "Assets": {
                    "units": {
                        "USD": [
                            {"end": "2020-12-31", "val": 3.0e10, "filed": "2021-02-10",
                             "form": form, "accn": "x-1", "fy": 2020, "fp": "FY"},
                            {"end": "2021-12-31", "val": 3.4e10, "filed": "2022-02-09",
                             "form": form, "accn": "x-2", "fy": 2021, "fp": "FY"},
                        ]
                    }
                }
            }
        },
    }


def test_request_success_and_data_coverage_are_different_numbers():
    """The check that was measuring HTTP instead of data.

    On the first sixty-company run the reported coverage was 98.3% while twelve
    of the fifty-nine "covered" companies had produced zero rows. The rate was
    counting requests that returned 200. Both numbers are now reported, and this
    test is what keeps them from collapsing back into one.
    """
    from fza.ingest.sec import IngestReport

    rep = IngestReport(n_companies_requested=4, n_companies_fetched=4)
    rep.rows_per_company = {"A": 120, "B": 0, "C": 45, "D": 0}

    assert rep.request_success_rate == 1.0
    assert rep.data_coverage_rate == 0.5
    assert rep.n_companies_with_rows == 2


def test_a_company_that_parsed_to_nothing_names_itself():
    """Same rule as column_coverage: the empty thing has to say so.

    An aggregate cannot name the company that contributed nothing, and without
    the name the failure surfaces much later as a thin cross-section.
    """
    from fza.ingest.sec import IngestReport

    rep = IngestReport(n_companies_requested=3, n_companies_fetched=3)
    rep.rows_per_company = {"0000000002": 0, "0000000001": 10, "0000000003": 0}

    assert rep.companies_without_rows == ["0000000002", "0000000003"]


def test_a_failed_request_is_not_the_same_as_an_empty_one():
    """Absent from rows_per_company means it never answered; present with 0
    means it answered and gave nothing. The two need different fixes."""
    from fza.ingest.sec import IngestReport

    rep = IngestReport(n_companies_requested=2, n_companies_fetched=1, n_companies_failed=1)
    rep.rows_per_company = {"0000000001": 0}

    assert rep.companies_without_rows == ["0000000001"]
    assert rep.request_success_rate == 0.5
    assert rep.data_coverage_rate == 0.0


def test_the_coverage_gap_warning_names_the_tickers(capsys):
    """A warning that says '12 companies' and not which ones is not a warning."""
    from fza.ingest.run import _warn_on_coverage_gap
    from fza.ingest.sec import IngestReport

    rep = IngestReport(n_companies_requested=3, n_companies_fetched=3)
    rep.rows_per_company = {"0000000001": 50, "0000000002": 0, "0000000003": 0}
    rep.accounting_rows_per_company = {
        "0000000001": 40, "0000000002": 0, "0000000003": 0,
    }
    rep.standard_per_company = {
        "0000000001": "us-gaap", "0000000002": "ifrs", "0000000003": "unknown",
    }
    tickers = pd.DataFrame(
        {"ticker": ["AAA", "BBB", "CCC"],
         "cik": ["0000000001", "0000000002", "0000000003"]}
    )

    labels = _warn_on_coverage_gap(rep, tickers)
    assert labels == ["BBB (ifrs, no rows)", "CCC (unknown, no rows)"]

    out = capsys.readouterr().out
    assert "BBB (ifrs, no rows)" in out and "CCC (unknown, no rows)" in out
    assert "AAA" not in out
    assert "accounting series" in out


def test_no_warning_when_every_company_produced_rows(capsys):
    from fza.ingest.run import _warn_on_coverage_gap
    from fza.ingest.sec import IngestReport

    rep = IngestReport(n_companies_requested=2, n_companies_fetched=2)
    rep.rows_per_company = {"0000000001": 50, "0000000002": 3}
    rep.accounting_rows_per_company = {"0000000001": 45, "0000000002": 3}
    tickers = pd.DataFrame({"ticker": ["AAA", "BBB"],
                            "cik": ["0000000001", "0000000002"]})

    assert _warn_on_coverage_gap(rep, tickers) == []
    assert capsys.readouterr().out == ""


def test_both_rates_reach_the_report_json():
    """Reporting only the first is how twelve empty companies hid behind 98.3%."""
    from fza.ingest.sec import IngestReport

    rep = IngestReport(n_companies_requested=2, n_companies_fetched=2)
    rep.rows_per_company = {"0000000001": 5, "0000000002": 0}
    rep.accounting_rows_per_company = {"0000000001": 4, "0000000002": 0}
    d = rep.to_dict()

    assert d["request_success_rate"] == 1.0
    assert d["data_coverage_rate"] == 0.5
    assert d["accounting_coverage_rate"] == 0.5
    assert d["companies_without_rows"] == ["0000000002"]
    assert d["companies_without_accounting_rows"] == ["0000000002"]


# ----------------------------------------------------------------------
# 20-F: a change of contract, stated as one
# ----------------------------------------------------------------------
def test_a_twenty_f_annual_report_is_accepted():
    """Five of the first sixty companies were dropped whole for filing 20-F.

    ASML, BABA, ARM, MUFG and TM report under us-gaap with every tag this
    project reads; only the form differed. See AI_NOTES incident 14.
    """
    report = IngestReport()
    df = parse_companyfacts(_foreign_payload("20-F"), report=report)

    assert len(df) == 2
    assert set(df["form"]) == {"20-F"}
    assert report.n_excluded_form == 0


def test_a_six_k_is_still_excluded_and_counted():
    """6-K is a current report, not a periodic one.

    Its facts do not describe a completed accounting period the way a 10-Q's do,
    so admitting it would put two meanings of period_end in one column.
    """
    report = IngestReport()
    df = parse_companyfacts(_foreign_payload("6-K"), report=report)

    assert df.empty
    assert report.n_excluded_form == 2


# ----------------------------------------------------------------------
# The taxonomy a filer reports under, recorded rather than assumed
# ----------------------------------------------------------------------
def test_an_ifrs_filer_is_labelled_ifrs():
    from fza.ingest.sec import infer_accounting_standard

    payload = {"cik": 1, "facts": {"ifrs-full": {"Assets": {"units": {}}}, "dei": {}}}
    assert infer_accounting_standard(payload) == "ifrs"


def test_a_usgaap_namespace_without_the_tags_is_not_a_usgaap_filer():
    """BHP's shape: a us-gaap namespace carrying none of the tags read here,
    with the accounts themselves under ifrs-full. Testing for the namespace
    rather than the tags would have mislabelled it."""
    from fza.ingest.sec import infer_accounting_standard

    payload = {
        "cik": 1,
        "facts": {
            "us-gaap": {"SomeTagWeDoNotRead": {"units": {}}},
            "ifrs-full": {"Assets": {"units": {}}},
        },
    }
    assert infer_accounting_standard(payload) == "ifrs"


def test_a_filer_on_excluded_forms_is_still_a_usgaap_filer():
    """The taxonomy is a fact about the filer, not about this parser's filters.

    Labelling a company by what we happen to keep would blame the taxonomy for a
    decision made here.
    """
    from fza.ingest.sec import infer_accounting_standard

    assert infer_accounting_standard(_foreign_payload("6-K")) == "us-gaap"


def test_a_payload_with_neither_taxonomy_is_unknown_not_usgaap():
    from fza.ingest.sec import infer_accounting_standard

    assert infer_accounting_standard({"cik": 1, "facts": {"dei": {}}}) == "unknown"


def test_a_share_count_alone_does_not_count_as_coverage():
    """The hole the 20-F fix opened in the check built one step earlier.

    Accepting 20-F let five IFRS filers through on a DEI cover-page share count
    and nothing else. `data_coverage_rate` rose from 80% to 95% and the gap
    warning went quiet, while not one of those companies had become readable by
    a value factor. A check that a fix can silence without fixing anything is
    worse than no check.
    """
    from fza.ingest.sec import IngestReport

    rep = IngestReport(n_companies_requested=4, n_companies_fetched=4)
    rep.rows_per_company = {"A": 200, "B": 6, "C": 150, "D": 0}
    # B carries the cover-page share count and no accounting series.
    rep.accounting_rows_per_company = {"A": 180, "B": 0, "C": 140, "D": 0}

    assert rep.data_coverage_rate == 0.75  # B clears this bar
    assert rep.accounting_coverage_rate == 0.5  # and fails this one
    assert rep.companies_without_accounting_rows == ["B", "D"]


def test_the_warning_says_which_kind_of_empty_each_company_is(capsys):
    """'No rows' and 'share count only' need different fixes: one is a missing
    form or a 404, the other is a taxonomy this project cannot read."""
    from fza.ingest.run import _warn_on_coverage_gap
    from fza.ingest.sec import IngestReport

    rep = IngestReport(n_companies_requested=3, n_companies_fetched=3)
    rep.rows_per_company = {"0000000001": 90, "0000000002": 6, "0000000003": 0}
    rep.accounting_rows_per_company = {
        "0000000001": 80, "0000000002": 0, "0000000003": 0,
    }
    rep.standard_per_company = {
        "0000000001": "us-gaap", "0000000002": "ifrs", "0000000003": "unknown",
    }
    tickers = pd.DataFrame(
        {"ticker": ["AAA", "SHEL", "CYATY"],
         "cik": ["0000000001", "0000000002", "0000000003"]}
    )

    labels = _warn_on_coverage_gap(rep, tickers)
    assert labels == ["SHEL (ifrs, share count only)", "CYATY (unknown, no rows)"]
    assert "share count only" in capsys.readouterr().out


def test_companies_per_tag_counts_companies_not_rows():
    """One company filing quarterly for fifteen years can make a tag look
    universal. `tag_coverage` counts rows; this counts companies."""
    from fza.ingest.sec import SHARE_COUNT_TAG, IngestReport

    rep = IngestReport()
    rep.companies_per_tag = {"Assets": 48, SHARE_COUNT_TAG: 57}
    d = rep.to_dict()

    assert d["companies_per_tag"]["Assets"] == 48
    assert d["companies_per_tag"][SHARE_COUNT_TAG] == 57
