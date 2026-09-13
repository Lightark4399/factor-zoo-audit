"""Demo: run the whole pipeline and print what it found.

Two modes, chosen automatically:

* **Real data**, when a store built by ``fza.ingest.run`` is present. Its
  statistics are diagnostic; opening a database does not certify evidence.
* **Fixtures**, otherwise. This is the mode CI runs in, and the numbers are not
  findings — the fixture is a random walk, so a factor cannot predict it and is
  not supposed to. What the fixture demonstrates is that the machinery behaves,
  which is a different claim and is labelled as one.

The dual mode exists because the repository has to be verifiable by someone who
has not downloaded anything. A demo that required a four-minute ingest before it
would run is a demo most readers never see, and CI could not run it at all.

Reading the output
------------------
The deliverable is the audit and its evidence limits. Vintage differences are
diagnostics of two reading pipelines, not isolated causal effects: samples and
cleaning inputs can differ even on shared dates. Read-path coverage and observed
key overlap must accompany the gap, not be inferred from a PASS label.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter

import pandas as pd

from .factors.registry import (
    load_all,
    published_anomaly_denominator,
    summary_table,
)
from .fixtures import FixtureSpec, load_fixture_into
from .pipeline.prepare import EmptyFactorError
from .pipeline.run import (
    ImplausibleMagnitudeError,
    compare_vintages,
    compute_factor,
)
from .provenance import (
    dataset_evidence,
    file_sha256,
    implementation_manifest,
    research_environment,
)
from .render import render_report
from .reporting import factor_record, json_safe, research_gate_ledger
from .store import Store

DEFAULT_DB = Path("data/fza.duckdb")
MONTH_END = pd.offsets.MonthEnd()

# Wide enough for the protocol table to carry a status column without
# truncating 'FAILED: magnitude' into something a reader has to guess at.
WIDTH = 84


def _rule(char: str = "-", width: int = WIDTH) -> str:
    return char * width


def _header(title: str) -> str:
    return f"\n{_rule('=')}\n{title}\n{_rule('=')}"


def _describe_failure(exc: Exception) -> tuple[str, list[str]]:
    """Turn an exception from ``compute_factor`` into a status and a reason.

    The status vocabulary is deliberately small and stable -- ``OK``,
    ``FAILED: magnitude``, ``FAILED: empty``, ``FAILED: <ExceptionName>`` -- so
    a reader can scan the column, and so a check that has never fired is still
    distinguishable from one that has.

    The reason is built from the exception's structured payload where there is
    one, not from its message. Reporting a failure by reprinting its English is
    how a report ends up saying something the code no longer does.
    """
    if isinstance(exc, ImplausibleMagnitudeError):
        d = exc.detail
        if "rule_id" in d:
            return "FAILED: magnitude", [
                f"{d['rule_id']}: {d['status']} ({d['n_outside']} raw-output violations)",
                d["rationale"],
            ]
        lo, hi = d.get("range", (float("nan"), float("nan")))
        reason = [
            f"{d.get('share_outside', float('nan')):.2%} of "
            f"{d.get('n_values', 0):,} raw values fall outside "
            f"[{lo:g}, {hi:g}] (tolerance {d.get('max_share', 0):.0%})"
        ]
        worst = d.get("worst") or []
        if worst:
            shown = ", ".join(f"{t} {dt} = {v:,.4g}" for t, dt, v in worst[:3])
            reason.append(f"most extreme: {shown}")
        reason.append("this is a data problem upstream of the factor definition")
        return "FAILED: magnitude", reason
    if isinstance(exc, EmptyFactorError):
        return "FAILED: empty", [
            "the factor produced no values at all; check the columns it reads"
        ]
    return f"FAILED: {type(exc).__name__}", [str(exc).splitlines()[0]]


def open_store(db_path: Path | None) -> tuple[Store, str]:
    """Open the real store if it exists, otherwise build one from fixtures."""
    if db_path is not None and db_path.exists():
        return Store(str(db_path), read_only=True), "real"
    store = Store()
    load_fixture_into(store)
    return store, "fixture"


def describe_data(store: Store, mode: str) -> dict:
    """Counts that determine how the rest of the output should be read."""
    con = store.con
    n_sec = con.execute("SELECT count(*) FROM securities").fetchone()[0]
    # Split by taxonomy, because the two numbers are not interchangeable. An
    # IFRS filer has prices and no fundamentals, so it counts towards the
    # universe a momentum factor sees and not towards the one a value factor
    # sees. Reporting only the total would overstate the second by the size
    # of the first, silently.
    by_standard = dict(
        con.execute(
            "SELECT accounting_standard, count(*) FROM securities GROUP BY 1"
        ).fetchall()
    )
    n_fun = con.execute("SELECT count(*) FROM fundamentals").fetchone()[0]
    n_px = con.execute("SELECT count(*) FROM prices").fetchone()[0]
    n_rev = len(store.restatements())

    dates = con.execute(
        "SELECT min(trade_date), max(trade_date) FROM prices"
    ).fetchone()

    return {
        "mode": mode,
        "securities": n_sec,
        "securities_by_standard": by_standard,
        "securities_usgaap": by_standard.get("us-gaap", 0),
        "fundamentals": n_fun,
        "prices": n_px,
        "restatements": n_rev,
        "restatement_rate": n_rev / n_fun if n_fun else float("nan"),
        "first_date": dates[0],
        "last_date": dates[1],
    }


def signal_dates_for(
    store: Store,
    freq: str | pd.DateOffset = MONTH_END,
    min_history_months: int = 15,
) -> pd.DatetimeIndex:
    """Month-end signal dates covered by the available price history.

    The first ``min_history_months`` are skipped because the momentum factor
    needs a twelve-month formation window plus a skip month before it can produce
    anything. Generating dates the factors cannot serve would fill the report with
    empty cross-sections and make the coverage look worse than it is.
    """
    first, last = store.con.execute(
        "SELECT min(trade_date), max(trade_date) FROM prices"
    ).fetchone()
    if first is None:
        return pd.DatetimeIndex([])

    start = pd.Timestamp(first) + pd.DateOffset(months=min_history_months)
    return pd.DatetimeIndex(pd.date_range(start, pd.Timestamp(last), freq=freq))


def failure_record(exc: Exception) -> dict:
    """Capture the same failure details consumed by the text renderer."""
    status, reasons = _describe_failure(exc)
    return {
        "exception_type": type(exc).__name__,
        "status": status,
        "message": str(exc),
        "display_reasons": reasons,
        "detail": json_safe(getattr(exc, "detail", None)),
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Run the factor pipeline and report.")
    ap.add_argument("--db", type=Path, default=DEFAULT_DB)
    ap.add_argument("--outdir", type=Path, default=None)
    ap.add_argument("--max-dates", type=int, default=0,
                    help="cap signal dates for a diagnostic run (0 = all)")
    args = ap.parse_args(argv)
    started = datetime.now(timezone.utc)
    clock_start = perf_counter()
    store, mode = open_store(args.db)
    try:
        info = describe_data(store, mode)
        evidence = dataset_evidence(args.db, mode)
        factors = load_all()
        environment = research_environment()
        presentation = {
            "database_display": str(args.db),
            "price_coverage": store.column_coverage("prices").to_dict("records"),
            "registered_factors": summary_table().to_dict("records"),
            "capture_method": "captured_during_this_run",
        }
        denominator = published_anomaly_denominator()
        dates = signal_dates_for(store, min_history_months=15)
        available_signal_dates = len(dates)
        if args.max_dates and len(dates) > args.max_dates:
            keep = range(0, len(dates), max(1, len(dates) // args.max_dates))
            dates = dates[list(keep)[:args.max_dates]]
        protocol_settings = {
            "horizon_sessions": 21, "execution_lag_sessions": 1, "n_quantiles": 5,
        }
        runs, failures, records, comparisons = {}, {}, {}, {}
        for factor_id, factor in factors.items():
            print(f"Computing PIT {factor_id}", file=sys.stderr, flush=True)
            try:
                runs[factor_id] = compute_factor(factor, store, dates, **protocol_settings)
            except Exception as exc:
                failures[factor_id] = failure_record(exc)
            if factor_id in runs:
                records[factor_id] = factor_record(runs[factor_id], evidence)
            else:
                records[factor_id] = {
                    "computation_status": failures[factor_id]["status"],
                    "statistics_status": "NOT_COMPUTED",
                    "protocol": None,
                    "failure": failures[factor_id],
                }
        for factor_id, factor in factors.items():
            if factor_id not in runs:
                comparisons[factor_id] = {
                    "status": "NOT_COMPUTED",
                    "reason": failures[factor_id]["status"],
                    "failure": failures[factor_id],
                }
                continue
            print(f"Computing vintage {factor_id}", file=sys.stderr, flush=True)
            try:
                comp = compare_vintages(factor, store, dates, **protocol_settings)
            except Exception as exc:
                comparisons[factor_id] = {
                    "status": "FAILED", "reason": type(exc).__name__,
                    "failure": failure_record(exc),
                }
                continue
            comparisons[factor_id] = {
                "status": evidence["statistics_status"] if comp.applicable else "NOT_APPLICABLE",
                "pit": comp.pit.to_dict(),
                "restated": comp.restated.to_dict() if comp.restated is not None else None,
                "ic_gap": comp.ic_gap if comp.applicable else None,
                "diagnostic_verdict": comp.verdict,
                "detail": comp.detail,
            }
        roster = store.con.execute(
            "SELECT cik, ticker, first_filing, last_filing, accounting_standard "
            "FROM securities ORDER BY ticker, cik"
        ).df().to_dict("records")
        roster_json = json.dumps(json_safe(roster), sort_keys=True, allow_nan=False)
        try:
            end_hash = file_sha256(args.db) if mode == "real" else None
        except OSError:
            end_hash = None
        finished = datetime.now(timezone.utc)
        bundle = {
            "schema_version": 2,
            "artifact_role": evidence["statistics_status"] + " / NOT_AN_ASSERTION",
            "generated_at_utc": finished.isoformat(),
            "evidence": evidence,
            "environment": environment,
            "implementation": implementation_manifest(),
            "presentation": presentation,
            "runtime": {
                "started_at_utc": started.isoformat(),
                "computation_finished_at_utc": finished.isoformat(),
                "elapsed_seconds": perf_counter() - clock_start,
                "scope": "start_through_computation_and_manifest_excludes_render_and_write",
                "clock": "perf_counter",
            },
            "data_summary": info,
            "fixture_spec": asdict(FixtureSpec()) if mode == "fixture" else None,
            "selected_roster": roster,
            "selected_roster_sha256": hashlib.sha256(roster_json.encode()).hexdigest(),
            "roster_scope": "stored_selection_not_verified_historical_membership",
            "database_sha256_after_run": end_hash,
            "database_bytes_unchanged": (
                end_hash == evidence["database_sha256"] if end_hash is not None else None
            ),
            "configuration": {
                "signal_dates": [str(value.date()) for value in dates],
                "max_dates": args.max_dates,
                "available_signal_dates": available_signal_dates,
                "subsampled_signal_grid": len(dates) < available_signal_dates,
                "min_history_months": 15,
                **protocol_settings,
                "ls_sharpe_units": "per_observation_not_annualised",
            },
            "denominator": denominator,
            "factors": records,
            "vintage_comparisons": comparisons,
            "research_gates": research_gate_ledger(),
        }
        bundle = json_safe(bundle)
        report = render_report(bundle)
        print(report, flush=True)
        if args.outdir:
            args.outdir.mkdir(parents=True, exist_ok=True)
            for name, content in (
                ("demo_report.txt", report),
                ("demo_evidence.json", json.dumps(evidence, indent=2, allow_nan=False)),
                ("demo_run.json", json.dumps(bundle, indent=2, allow_nan=False)),
            ):
                (args.outdir / name).write_text(content, encoding="utf-8", newline="\n")
            print(f"report written to {args.outdir / 'demo_report.txt'}")
        return 0
    finally:
        store.close()


if __name__ == "__main__":
    raise SystemExit(main())
