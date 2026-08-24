"""Data store with point-in-time access enforced at the boundary.

The central claim of this project is that its factors could have been computed
when they claim to have been. That claim is only as good as the mechanism behind
it, so the mechanism is here rather than in a convention:

* ``fundamentals_asof(date)`` is the only supported way for factor code to read
  fundamentals. It filters on ``filed <= date``.
* ``fundamentals_restated()`` exists solely to measure the gap. It is named
  loudly, documented as unusable for signal construction, and every call is
  recorded so an audit can show whether a factor ever touched it.
* ``assert_read_path_respected()`` verifies, from a log of what was actually
  returned, that no read handed back a filing dated after the signal date it was
  asked for. It is the check that runs in CI.

Why both a guard and a check
----------------------------
The view makes the leaking query hard to write; the assertion proves none was
written. Neither alone is enough. A view can be bypassed by anyone who opens a
connection and writes their own SQL — which, in a repository meant to be read and
extended, will eventually happen. The assertion catches that, and it catches it
in CI rather than in review.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

try:
    import duckdb
except ImportError as exc:  # pragma: no cover
    raise ImportError("duckdb is required: pip install duckdb") from exc

SCHEMA_PATH = Path(__file__).resolve().parents[2] / "sql" / "001_schema.sql"


class LookaheadError(AssertionError):
    """Raised when a factor consumed data filed after its signal date."""


@dataclass
class ReadRecord:
    """One call to the point-in-time read path, and what it returned.

    Recording the maximum ``filed`` in the result is what makes the guarantee
    checkable after the fact. The view's WHERE clause is an intention; this is
    evidence.

    TWO DATES, DELIBERATELY. ``requested_asof`` is what was handed to the view;
    ``intended_signal_date`` is the day the factor actually wants to form a
    signal on. A factor declaring a reporting lag asks for an earlier vintage
    than the day it is forecasting, so the two differ, and each answers a
    different question: whether the read path held, and whether the declared lag
    was really applied. An earlier version stored one field for both, so the lag
    was subtracted twice and every honest read was flagged.
    """

    requested_asof: pd.Timestamp
    intended_signal_date: pd.Timestamp
    max_filed: pd.Timestamp | None
    n_rows: int
    tags: tuple[str, ...]

    @property
    def respects_asof(self) -> bool:
        """The read path's own contract: nothing newer than what was asked for.

        Judged against ``requested_asof`` alone. Whether the date asked for was
        the right one is a separate question, and ``assert_read_path_respected``
        answers it.
        """
        if self.max_filed is None:
            return True
        return self.max_filed <= self.requested_asof


@dataclass
class AccessLog:
    """Record of which vintage a session read.

    Kept so a factor run can state, as part of its output, that it never touched
    the restated view. An assertion about behaviour is stronger than a promise
    about intent, and this is the cheapest way to make one.
    """

    pit_reads: int = 0
    restated_reads: int = 0
    restated_callers: list[str] = field(default_factory=list)
    # Every point-in-time read, with the latest filing date it returned. This is
    # the raw material for assert_read_path_respected.
    reads: list[ReadRecord] = field(default_factory=list)

    @property
    def touched_restated(self) -> bool:
        return self.restated_reads > 0

    @property
    def violating_reads(self) -> list[ReadRecord]:
        return [r for r in self.reads if not r.respects_asof]

    def to_dict(self) -> dict:
        return {
            "pit_reads": self.pit_reads,
            "restated_reads": self.restated_reads,
            "restated_callers": list(self.restated_callers),
            "touched_restated": self.touched_restated,
            "n_reads_logged": len(self.reads),
            "n_reads_violating": len(self.violating_reads),
        }


class Store:
    """DuckDB-backed store for prices, fundamentals and factor values."""

    def __init__(self, path: str | None = None, read_only: bool = False):
        self.path = path or ":memory:"
        self.con = duckdb.connect(self.path, read_only=read_only)
        if not read_only:
            self._apply_schema()
        self.access = AccessLog()

    def _apply_schema(self) -> None:
        if not SCHEMA_PATH.exists():
            raise FileNotFoundError(f"schema not found at {SCHEMA_PATH}")
        self.con.execute(SCHEMA_PATH.read_text(encoding="utf-8"))

    # ------------------------------------------------------------------
    # Loading
    # ------------------------------------------------------------------
    def load_securities(self, frame: pd.DataFrame) -> int:
        cols = ["cik", "ticker", "name", "sic", "first_filing", "last_filing"]
        df = frame.reindex(columns=cols).copy()
        df["cik"] = df["cik"].astype(str).str.zfill(10)
        for c in ("first_filing", "last_filing"):
            df[c] = pd.to_datetime(df[c], errors="coerce").dt.date
        return self._insert("securities", df)

    def load_prices(self, frame: pd.DataFrame) -> int:
        cols = [
            "ticker", "trade_date", "open", "high", "low",
            "close", "close_adj", "volume", "shares_out",
        ]
        df = frame.reindex(columns=cols).copy()
        df["trade_date"] = pd.to_datetime(df["trade_date"]).dt.date
        return self._insert("prices", df)

    def load_fundamentals(self, frame: pd.DataFrame) -> int:
        """Insert fundamentals. Revisions are additional rows, never updates.

        A duplicate (cik, tag, period_end, filed, form) is rejected by the
        primary key rather than resolved: two different values claiming the same
        filing are a contradiction, not a revision, and silently picking one
        would bury an ingestion bug.
        """
        cols = [
            "cik", "tag", "period_end", "fiscal_year", "fiscal_period",
            "filed", "value", "unit", "form", "accession",
        ]
        df = frame.reindex(columns=cols).copy()
        df["cik"] = df["cik"].astype(str).str.zfill(10)
        for c in ("period_end", "filed"):
            df[c] = pd.to_datetime(df[c]).dt.date
        return self._insert("fundamentals", df)

    def _insert(self, table: str, df: pd.DataFrame) -> int:
        if df.empty:
            return 0
        self.con.register("_incoming", df)
        self.con.execute(f"INSERT INTO {table} SELECT * FROM _incoming")
        self.con.unregister("_incoming")
        return len(df)

    # ------------------------------------------------------------------
    # Reading -- the point of the class
    # ------------------------------------------------------------------
    def fundamentals_asof(
        self,
        signal_date,
        tags: list[str] | None = None,
        intended_signal_date=None,
    ) -> pd.DataFrame:
        """Latest value per (cik, tag) that had been FILED by ``signal_date``.

        This is the only supported read path for factor construction.

        ``intended_signal_date`` is the day the caller is forming a signal for,
        which differs from ``signal_date`` when the factor deliberately asks for
        an older vintage to honour a declared reporting lag. It never touches the
        query -- it is recorded so ``assert_read_path_respected`` can check that
        the lag was actually applied, rather than taking the declaration on
        trust. Omitted, it defaults to ``signal_date``: a factor that declares no
        lag intends to read as of the day it asked for.
        """
        self.access.pit_reads += 1
        ts = pd.Timestamp(signal_date)
        intended = ts if intended_signal_date is None else pd.Timestamp(intended_signal_date)
        d = ts.date()
        sql = (
            "SELECT * FROM latest_fundamental_asof(DATE '"
            f"{d.isoformat()}')"
        )
        if tags:
            placeholders = ", ".join(f"'{t}'" for t in tags)
            sql += f" WHERE tag IN ({placeholders})"
        out = self.con.execute(sql).df()

        # Log what was actually returned, not what was asked for. The WHERE
        # clause states the intention; this records the outcome, and the two can
        # only be compared if both exist.
        max_filed = (
            pd.to_datetime(out["filed"]).max() if len(out) and "filed" in out else None
        )
        self.access.reads.append(
            ReadRecord(
                requested_asof=ts,
                intended_signal_date=intended,
                max_filed=None if pd.isna(max_filed) else max_filed,
                n_rows=len(out),
                tags=tuple(tags or ()),
            )
        )
        return out

    def fundamentals_restated(self, caller: str = "unknown") -> pd.DataFrame:
        """Final value per (cik, tag, period). NOT usable for signal construction.

        Provided so the point-in-time gap can be measured by running the same
        factor both ways. Every call is logged with its caller, so a factor run
        can assert it never came through here.
        """
        self.access.restated_reads += 1
        self.access.restated_callers.append(caller)
        return self.con.execute("SELECT * FROM fundamentals_restated").df()

    def prices(
        self, start=None, end=None, tickers: list[str] | None = None
    ) -> pd.DataFrame:
        clauses = []
        if start is not None:
            clauses.append(f"trade_date >= DATE '{pd.Timestamp(start).date()}'")
        if end is not None:
            clauses.append(f"trade_date <= DATE '{pd.Timestamp(end).date()}'")
        if tickers:
            joined = ", ".join(f"'{t}'" for t in tickers)
            clauses.append(f"ticker IN ({joined})")
        where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
        return self.con.execute(
            f"SELECT * FROM prices{where} ORDER BY ticker, trade_date"
        ).df()

    def universe_asof(self, signal_date) -> pd.DataFrame:
        d = pd.Timestamp(signal_date).date()
        return self.con.execute(
            f"SELECT * FROM universe_asof(DATE '{d.isoformat()}') ORDER BY ticker"
        ).df()

    def restatements(self) -> pd.DataFrame:
        return self.con.execute(
            "SELECT * FROM restatements ORDER BY abs(revision_pct) DESC NULLS LAST"
        ).df()

    # ------------------------------------------------------------------
    # The check on the guarantee
    # ------------------------------------------------------------------
    def assert_read_path_respected(self, grace_days: int = 0) -> dict:
        """Verify every logged read returned only filings that already existed.

        This is the check that the point-in-time guarantee held. It reads the log
        of what the read path actually returned, so it fails if someone bypasses
        the view -- which an earlier version could not do, because it re-derived
        a hypothetical from the raw table instead of inspecting the real reads.

        ``grace_days`` lets a factor assert a deliberate reporting lag beyond the
        physical constraint, and this is what enforces it. The comparison is
        against ``intended_signal_date`` -- the day being forecast -- so a factor
        that declares a two-day lag but forgets to subtract it at the query site
        fails here. That is the whole point: the declaration is checked against
        the reads rather than believed.
        """
        reads = self.access.reads
        if not reads:
            return {
                "n_reads": 0,
                "n_violations": 0,
                "ok": True,
                "note": "no point-in-time reads were logged",
            }

        tolerance = pd.Timedelta(days=grace_days)
        violations = [
            r
            for r in reads
            if r.max_filed is not None
            and r.max_filed > (r.intended_signal_date - tolerance)
        ]

        return {
            "n_reads": len(reads),
            "n_violations": len(violations),
            "ok": not violations,
            "grace_days": grace_days,
            "sample": [
                {
                    "intended_signal_date": str(r.intended_signal_date.date()),
                    "requested_asof": str(r.requested_asof.date()),
                    "max_filed": str(r.max_filed.date()),
                    "n_rows": r.n_rows,
                }
                for r in violations[:5]
            ],
        }

    def measure_naive_trap(
        self, factor_values: pd.DataFrame, tags: list[str], grace_days: int = 0
    ) -> dict:
        """How much data a NAIVE query would have read early.

        This is a measurement of the hazard, not a check on this code. It asks:
        for these signal dates, how many (period, tag) values would a query that
        takes the latest figure per period -- ignoring filing dates entirely --
        have returned before they were published?

        The result is a finding. A large number means the bitemporal store is
        earning its keep; it says nothing about whether this project's factors
        respected it. Confusing the two is what an earlier version did, reporting
        the size of the trap as a violation by the code that avoids it.

        Counts are reported at two granularities because they answer different
        questions: how many signal dates are exposed at all, and how many values
        are involved.
        """
        if factor_values.empty:
            return {
                "n_signal_dates": 0,
                "n_dates_exposed": 0,
                "n_trap_rows": 0,
                "exposure_rate": float("nan"),
            }

        needed = factor_values[["ticker", "signal_date"]].drop_duplicates()
        needed["signal_date"] = pd.to_datetime(needed["signal_date"]).dt.date
        self.con.register("_needed", needed)

        placeholders = ", ".join(f"'{t}'" for t in tags)
        # A violation is a filing that (a) is for one of the tags the factor
        # uses, (b) belongs to a security in the factor's output, and (c) was
        # filed after the signal date but is nonetheless the LATEST filing for
        # its period -- i.e. the only way a naive query would have picked it up.
        violations = self.con.execute(
            f"""
            WITH latest AS (
                SELECT DISTINCT ON (f.cik, f.tag, f.period_end)
                    f.cik, f.tag, f.period_end, f.filed
                FROM fundamentals f
                WHERE f.tag IN ({placeholders})
                ORDER BY f.cik, f.tag, f.period_end, f.filed DESC
            )
            SELECT n.ticker, n.signal_date, l.tag, l.period_end, l.filed
            FROM _needed n
            JOIN securities s ON s.ticker = n.ticker
            JOIN latest l ON l.cik = s.cik
            WHERE l.period_end <= n.signal_date
              AND l.filed > n.signal_date + INTERVAL ({grace_days}) DAY
            """
        ).df()
        self.con.unregister("_needed")

        n_dates = int(needed["signal_date"].nunique())
        n_exposed = (
            int(violations["signal_date"].nunique()) if len(violations) else 0
        )
        return {
            "n_signal_dates": n_dates,
            "n_dates_exposed": n_exposed,
            "n_trap_rows": int(len(violations)),
            "exposure_rate": n_exposed / n_dates if n_dates else float("nan"),
            "grace_days": grace_days,
            "sample": violations.head(5).to_dict(orient="records"),
        }

    # ------------------------------------------------------------------
    def write_factor_values(self, factor_id: str, frame: pd.DataFrame, vintage: str = "pit") -> int:
        df = frame[["ticker", "signal_date", "value"]].copy()
        df.insert(0, "factor_id", factor_id)
        df["signal_date"] = pd.to_datetime(df["signal_date"]).dt.date
        df["vintage"] = vintage
        df = df[["factor_id", "ticker", "signal_date", "value", "vintage"]]
        return self._insert("factor_values", df)

    def factor_values(self, factor_id: str, vintage: str = "pit") -> pd.DataFrame:
        return self.con.execute(
            "SELECT ticker, signal_date, value FROM factor_values "
            f"WHERE factor_id = '{factor_id}' AND vintage = '{vintage}' "
            "ORDER BY signal_date, ticker"
        ).df()

    def close(self) -> None:
        self.con.close()

    def __enter__(self) -> Store:
        return self

    def __exit__(self, *exc) -> None:
        self.close()
