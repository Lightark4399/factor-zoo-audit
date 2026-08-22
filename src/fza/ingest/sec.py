"""SEC XBRL ingestion.

Why XBRL rather than a scraped alternative
------------------------------------------
The ``companyfacts`` endpoint carries a ``filed`` field on every value: the date
the filing containing that number became public. It is an original field, not an
estimate derived from a period end plus an assumed reporting lag. That single
property is what makes an honest point-in-time backtest possible on free data,
and it is the reason this project is built around SEC filings.

Structure of this module
------------------------
Network access is confined to ``fetch_companyfacts`` and ``fetch_ticker_map``.
Everything else — tag selection, unit handling, the flattening of the nested JSON
into rows, the derivation of filing history — is a pure function of a response
body, and is tested against recorded fixtures.

That split exists because the development environment had no route to sec.gov, so
the parsing had to be verifiable without a download. It turned out to be the
better arrangement anyway: a test that hits the network tests SEC's uptime as
much as this code, and it cannot run in CI.

Constraints SEC imposes, and how they are handled
-------------------------------------------------
* **A declared User-Agent is mandatory.** Requests without one are refused. The
  fair-access policy asks for a contact address, so the caller must supply one
  rather than inheriting a default that would misattribute the traffic.
* **Ten requests per second.** Enforced here by a minimum interval between calls
  rather than by retry-on-429, because being throttled after the fact still
  counts as abuse of a free service.
* **Custom extension tags.** Companies define their own concepts, so the same
  economic quantity lands on different tags across filers. The scope is pinned to
  the ``us-gaap`` namespace and a fixed tag list; anything else is excluded, and
  the exclusion rate is reported rather than silently absorbed.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pandas as pd

SEC_BASE = "https://data.sec.gov"
SEC_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"

# The tags this project reads. Kept short and standard on purpose: every addition
# widens the set of filers whose custom tagging causes a silent gap, and a factor
# built on a tag only half the universe reports is a factor about which half.
CORE_TAGS: tuple[str, ...] = (
    "Assets",
    "Liabilities",
    "StockholdersEquity",
    "Revenues",
    "NetIncomeLoss",
    "OperatingIncomeLoss",
    "GrossProfit",
    "CashAndCashEquivalentsAtCarryingValue",
    "CommonStockSharesOutstanding",
    "PaymentsToAcquirePropertyPlantAndEquipment",
)

# Only annual and quarterly reports and their amendments. Anything else (8-K, S-1)
# carries values that are not comparable across the panel.
ACCEPTED_FORMS: tuple[str, ...] = ("10-K", "10-Q", "10-K/A", "10-Q/A")

MIN_REQUEST_INTERVAL = 0.11  # seconds; SEC allows 10 requests per second


class SECError(RuntimeError):
    """Raised when SEC returns something the parser cannot use."""


@dataclass
class IngestReport:
    """What was ingested and, more importantly, what was not.

    The exclusion counts are the point. A silent drop is indistinguishable from
    an absence in the source, and the difference matters: one is a bug in this
    code, the other is a fact about the filer.
    """

    n_companies_requested: int = 0
    n_companies_fetched: int = 0
    n_companies_failed: int = 0
    n_rows: int = 0
    n_excluded_non_usgaap: int = 0
    n_excluded_form: int = 0
    n_excluded_no_filed: int = 0
    n_excluded_unit: int = 0
    n_excluded_filed_before_period: int = 0
    failures: list[str] = field(default_factory=list)
    tag_coverage: dict[str, int] = field(default_factory=dict)

    @property
    def coverage_rate(self) -> float:
        if not self.n_companies_requested:
            return float("nan")
        return self.n_companies_fetched / self.n_companies_requested

    def to_dict(self) -> dict:
        return {
            "n_companies_requested": self.n_companies_requested,
            "n_companies_fetched": self.n_companies_fetched,
            "n_companies_failed": self.n_companies_failed,
            "coverage_rate": self.coverage_rate,
            "n_rows": self.n_rows,
            "n_excluded_non_usgaap": self.n_excluded_non_usgaap,
            "n_excluded_form": self.n_excluded_form,
            "n_excluded_no_filed": self.n_excluded_no_filed,
            "n_excluded_unit": self.n_excluded_unit,
            "n_excluded_filed_before_period": self.n_excluded_filed_before_period,
            "tag_coverage": dict(self.tag_coverage),
            "failures": list(self.failures[:20]),
        }


# ----------------------------------------------------------------------
# Network layer -- thin on purpose, and the only part that cannot be tested here
# ----------------------------------------------------------------------
class SECClient:
    """Minimal client for the SEC data APIs."""

    def __init__(self, user_agent: str, session: Any | None = None):
        if not user_agent or "@" not in user_agent:
            raise ValueError(
                "SEC requires a User-Agent identifying you, including a contact "
                "address, e.g. 'Your Name your.email@example.com'. Supplying one "
                "is a condition of the fair-access policy, not a formality."
            )
        self.user_agent = user_agent
        self._last_request = 0.0

        if session is None:
            try:
                import requests
            except ImportError as exc:  # pragma: no cover
                raise ImportError(
                    "requests is needed for ingestion: pip install -e '.[ingest]'"
                ) from exc
            session = requests.Session()
        self.session = session
        self.session.headers.update({"User-Agent": user_agent, "Accept-Encoding": "gzip, deflate"})

    def _throttle(self) -> None:
        elapsed = time.monotonic() - self._last_request
        if elapsed < MIN_REQUEST_INTERVAL:
            time.sleep(MIN_REQUEST_INTERVAL - elapsed)
        self._last_request = time.monotonic()

    def _get_json(self, url: str) -> dict:
        self._throttle()
        resp = self.session.get(url, timeout=30)
        if resp.status_code == 404:
            raise SECError(f"not found: {url}")
        resp.raise_for_status()
        return resp.json()

    def fetch_ticker_map(self) -> pd.DataFrame:
        """CIK-to-ticker mapping for all SEC filers."""
        data = self._get_json(SEC_TICKERS_URL)
        return parse_ticker_map(data)

    def fetch_companyfacts(self, cik: str) -> dict:
        """Raw companyfacts payload for one CIK."""
        cik10 = str(cik).zfill(10)
        return self._get_json(f"{SEC_BASE}/api/xbrl/companyfacts/CIK{cik10}.json")


# ----------------------------------------------------------------------
# Parsing -- pure functions, tested against recorded fixtures
# ----------------------------------------------------------------------
def parse_ticker_map(payload: dict) -> pd.DataFrame:
    """Flatten the ticker file into ``cik, ticker, name``.

    The payload is a dict keyed by row index rather than a list, which is a
    detail worth handling explicitly: iterating ``.values()`` is correct, while
    treating it as a list silently yields nothing.
    """
    rows = []
    for entry in payload.values():
        cik = str(entry.get("cik_str", "")).zfill(10)
        ticker = entry.get("ticker")
        if not cik or not ticker:
            continue
        rows.append({"cik": cik, "ticker": ticker, "name": entry.get("title")})
    return pd.DataFrame(rows, columns=["cik", "ticker", "name"])


def parse_companyfacts(
    payload: dict,
    tags: tuple[str, ...] = CORE_TAGS,
    forms: tuple[str, ...] = ACCEPTED_FORMS,
    report: IngestReport | None = None,
) -> pd.DataFrame:
    """Flatten companyfacts into one row per (tag, period, filing).

    The nested structure is ``facts → namespace → tag → units → unit → [facts]``.
    Each fact carries ``end`` (period end), ``filed``, ``val``, ``form`` and
    ``accn``. Restatements appear as **separate entries with the same ``end`` and
    a later ``filed``**, which is exactly the shape the bitemporal table wants —
    no reconstruction required, the source already records it.

    Facts without ``filed`` are dropped rather than assigned an estimated date.
    An assumed reporting lag would fabricate the one field the entire
    point-in-time guarantee rests on.
    """
    rep = report if report is not None else IngestReport()

    cik = str(payload.get("cik", "")).zfill(10)
    facts = payload.get("facts", {})

    # Only us-gaap. Custom extension namespaces are counted and excluded: a tag
    # one filer invented is not comparable with anything else in the panel.
    for namespace in facts:
        if namespace != "us-gaap":
            rep.n_excluded_non_usgaap += sum(
                len(unit_facts)
                for tag_data in facts[namespace].values()
                for unit_facts in tag_data.get("units", {}).values()
            )

    usgaap = facts.get("us-gaap", {})
    rows = []

    for tag in tags:
        tag_data = usgaap.get(tag)
        if tag_data is None:
            continue

        units = tag_data.get("units", {})
        for unit, entries in units.items():
            # Monetary values in USD and share counts are the only units these
            # tags should carry. Anything else (a foreign currency, a per-share
            # figure) is not comparable and is excluded with a count.
            if unit not in ("USD", "shares"):
                rep.n_excluded_unit += len(entries)
                continue

            for e in entries:
                form = e.get("form")
                if form not in forms:
                    rep.n_excluded_form += 1
                    continue
                filed = e.get("filed")
                if not filed:
                    rep.n_excluded_no_filed += 1
                    continue
                end = e.get("end")
                val = e.get("val")
                if end is None or val is None:
                    continue

                rows.append(
                    {
                        "cik": cik,
                        "tag": tag,
                        "period_end": end,
                        "fiscal_year": e.get("fy"),
                        "fiscal_period": e.get("fp"),
                        "filed": filed,
                        "value": float(val),
                        "unit": unit,
                        "form": form,
                        "accession": e.get("accn"),
                    }
                )
                rep.tag_coverage[tag] = rep.tag_coverage.get(tag, 0) + 1

    frame = pd.DataFrame(
        rows,
        columns=[
            "cik", "tag", "period_end", "fiscal_year", "fiscal_period",
            "filed", "value", "unit", "form", "accession",
        ],
    )

    if not frame.empty:
        # The same (cik, tag, period, filed, form) can appear more than once when
        # a filing reports a figure in several contexts. They agree, so the first
        # is kept -- but the primary key would reject the duplicate, so it is
        # resolved here where the reason can be stated.
        frame = frame.drop_duplicates(
            subset=["cik", "tag", "period_end", "filed", "form"], keep="first"
        )

        # A filing cannot predate the period it reports on, and the schema
        # enforces that. Real XBRL nonetheless contains rows that violate it:
        # filers mistype period ends, and nothing in the submission process
        # catches a date typo. Measured on the first thirty companies ingested,
        # such rows exist in the live data.
        #
        # The constraint stays. What changes is where the violation is handled:
        # dropping these rows here, with a count, keeps a data-entry error in one
        # filing from aborting an ingest of thirty thousand rows. Relaxing the
        # constraint instead would let a fact with an impossible date into the
        # table, where a point-in-time query would happily return it.
        filed = pd.to_datetime(frame["filed"], errors="coerce")
        period = pd.to_datetime(frame["period_end"], errors="coerce")
        valid = filed.notna() & period.notna() & (filed >= period)
        rep.n_excluded_filed_before_period += int((~valid).sum())
        frame = frame.loc[valid]

    rep.n_rows += len(frame)
    return frame


def derive_filing_history(fundamentals: pd.DataFrame) -> pd.DataFrame:
    """First and last filing date per company, for universe reconstruction.

    A company that stops filing has, with few exceptions, left the market —
    acquired, delisted, or wound up. That inference is the only route to a
    survivorship-free universe on free data, since no free price source carries
    securities that no longer exist.

    It is an inference, not a fact, and it has a known failure mode: a company
    that goes private continues to exist while ceasing to file. The README states
    this rather than leaving the reader to assume the universe is exact.
    """
    if fundamentals.empty:
        return pd.DataFrame(columns=["cik", "first_filing", "last_filing"])

    f = fundamentals.copy()
    f["filed"] = pd.to_datetime(f["filed"])
    out = f.groupby("cik")["filed"].agg(["min", "max"]).reset_index()
    out.columns = ["cik", "first_filing", "last_filing"]
    return out


def ingest_companies(
    client: SECClient,
    ciks: list[str],
    tags: tuple[str, ...] = CORE_TAGS,
    on_progress=None,
) -> tuple[pd.DataFrame, IngestReport]:
    """Fetch and parse several companies, collecting failures rather than raising.

    One company's malformed payload must not abort a run of five hundred. The
    failures are counted and listed, so a coverage rate can be reported instead
    of a partial dataset silently passing for a complete one.
    """
    report = IngestReport(n_companies_requested=len(ciks))
    frames = []

    for i, cik in enumerate(ciks):
        try:
            payload = client.fetch_companyfacts(cik)
            frame = parse_companyfacts(payload, tags=tags, report=report)
            if not frame.empty:
                frames.append(frame)
            report.n_companies_fetched += 1
        except Exception as exc:
            report.n_companies_failed += 1
            report.failures.append(f"{cik}: {type(exc).__name__}: {exc}")
        if on_progress is not None:
            on_progress(i + 1, len(ciks))

    combined = (
        pd.concat(frames, ignore_index=True)
        if frames
        else pd.DataFrame(
            columns=[
                "cik", "tag", "period_end", "fiscal_year", "fiscal_period",
                "filed", "value", "unit", "form", "accession",
            ]
        )
    )
    return combined, report


def save_fixture(payload: dict, path: Path, max_facts_per_tag: int = 12) -> None:
    """Trim a real payload to a fixture small enough to commit.

    Keeps the structure exactly and truncates the fact lists, so the parser is
    tested against the real shape rather than against an idealised one — the
    quirks (a dict keyed by index, restatements as repeated ``end`` values,
    unexpected units) are precisely what a hand-written fixture would omit.
    """
    trimmed: dict[str, Any] = {
        "cik": payload.get("cik"),
        "entityName": payload.get("entityName"),
        "facts": {},
    }
    for namespace, tags in payload.get("facts", {}).items():
        trimmed["facts"][namespace] = {}
        for tag, tag_data in tags.items():
            if tag not in CORE_TAGS:
                continue
            units = {
                unit: entries[:max_facts_per_tag]
                for unit, entries in tag_data.get("units", {}).items()
            }
            trimmed["facts"][namespace][tag] = {**tag_data, "units": units}

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(trimmed, indent=2), encoding="utf-8")
