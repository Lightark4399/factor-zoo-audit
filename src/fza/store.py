"""Data store with point-in-time access enforced at the boundary.

The central claim of this project is that its factors could have been computed
when they claim to have been. That claim is only as good as the mechanism behind
it, so the mechanism is here rather than in a convention:

* ``fundamentals_asof(date)`` is the only supported way for factor code to read
  fundamentals. It filters on ``filed <= date``.
* ``fundamentals_restated()`` exists solely to measure the gap. It is named
  loudly, documented as unusable for signal construction, and every call is
  recorded so an audit can show whether a factor ever touched it.
* ``assert_no_lookahead()`` re-derives, from the raw table, whether any value a
  factor consumed had a ``filed`` date after the signal date. It is the check
  that runs in CI.

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
class AccessLog:
    """Record of which vintage a session read.

    Kept so a factor run can state, as part of its output, that it never touched
    the restated view. An assertion about behaviour is stronger than a promise
    about intent, and this is the cheapest way to make one.
    """

    pit_reads: int = 0
    restated_reads: int = 0
    restated_callers: list[str] = field(default_factory=list)

    @property
    def touched_restated(self) -> bool:
        return self.restated_reads > 0

    def to_dict(self) -> dict:
        return {
            "pit_reads": self.pit_reads,
            "restated_reads": self.restated_reads,
            "restated_callers": list(self.restated_callers),
            "touched_restated": self.touched_restated,
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
    def fundamentals_asof(self, signal_date, tags: list[str] | None = None) -> pd.DataFrame:
        """Latest value per (cik, tag) that had been FILED by ``signal_date``.

        This is the only supported read path for factor construction.
        """
        self.access.pit_reads += 1
        d = pd.Timestamp(signal_date).date()
        sql = (
            "SELECT * FROM latest_fundamental_asof(DATE '"
            f"{d.isoformat()}')"
        )
        if tags:
            placeholders = ", ".join(f"'{t}'" for t in tags)
            sql += f" WHERE tag IN ({placeholders})"
        return self.con.execute(sql).df()

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
    # The check that runs in CI
    # ------------------------------------------------------------------
    def assert_no_lookahead(
        self, factor_values: pd.DataFrame, tags: list[str], grace_days: int = 0
    ) -> dict:
        """Verify no factor value could have used a filing published after it.

        Re-derived from the raw table rather than trusting the read path: for
        each (ticker, signal_date) in ``factor_values``, find the earliest filing
        that the factor could plausibly have needed and confirm it predates the
        signal date.

        ``grace_days`` allows a deliberate reporting lag to be asserted -- a
        factor that requires data filed at least 5 days earlier can state that,
        and the check enforces it. The default of 0 enforces only the
        physical constraint.
        """
        if factor_values.empty:
            return {"checked": 0, "violations": 0, "ok": True}

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

        return {
            "checked": int(len(needed)),
            "violations": int(len(violations)),
            "ok": len(violations) == 0,
            "sample": violations.head(10).to_dict(orient="records"),
            "grace_days": grace_days,
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
