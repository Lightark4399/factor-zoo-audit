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
The headline is the point-in-time gap. Every other number in this project is a
conventional factor statistic that a reader could compute elsewhere; the gap is
the one that requires the bitemporal store, and it answers a question most factor
research does not ask: *how much of this result depends on data that had not been
published when the signal was formed?*
"""

from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

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
from .qualification import qualification_lines
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


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Run the factor pipeline and report.")
    ap.add_argument(
        "--db",
        type=Path,
        default=DEFAULT_DB,
        help=f"path to an ingested store (default {DEFAULT_DB}); falls back to fixtures",
    )
    ap.add_argument("--outdir", type=Path, default=None)
    ap.add_argument(
        "--max-dates",
        type=int,
        default=0,
        help="cap the number of signal dates, for a quick run (0 = all)",
    )
    args = ap.parse_args(argv)

    store, mode = open_store(args.db)
    info = describe_data(store, mode)
    evidence = dataset_evidence(args.db, mode)
    factors = load_all()

    lines: list[str] = []

    def emit(text: str = "") -> None:
        print(text, flush=True)
        lines.append(text)

    emit(_rule("="))
    emit("FACTOR ZOO AUDIT".center(WIDTH))
    emit(_rule("="))
    emit()

    if mode == "fixture":
        emit("  DATA: synthetic fixtures (no ingested store found)")
        emit()
        emit("  The numbers below are NOT findings. Fixture prices are a random")
        emit("  walk, so no factor can predict them and none is meant to. What")
        emit("  this run demonstrates is that the machinery behaves: the")
        emit("  point-in-time view returns the pre-restatement value, the")
        emit("  look-ahead check fires when it should, and the vintage comparison")
        emit("  isolates the filing constraint.")
        emit()
        emit("  For real numbers, ingest first:")
        emit("    python -m fza.ingest.run --user-agent 'Name you@example.com'")
    else:
        emit(f"  DATA: {args.db}")
    emit()
    for line in qualification_lines(evidence):
        emit("  " + line)
    emit(f"  reasons: {', '.join(evidence['reasons'])}")
    if mode == "real":
        emit(f"  sidecar binding: {evidence['sidecar_binding']}")
        emit("  declared research_evidence: " + json.dumps(evidence['declared_research_evidence']))
        emit("  declared run purpose: " + json.dumps(evidence['declared_run_purpose']))
        emit(f"  database SHA-256: {evidence['database_sha256']}")
        emit(f"  sidecar SHA-256: {evidence['sidecar_sha256']}")
        emit("  declared survivorship-prone source share: " +
             json.dumps(evidence['declared_survivorship_prone_share']))
        emit("  Source share is NOT the magnitude or direction of survivorship bias.")
        emit("  Sidecar declarations, even true or hash-matched, do not certify research.")
    emit()
    emit(f"  securities     {info['securities']:>10,}")
    emit(
        f"  with us-gaap   {info['securities_usgaap']:>10,}   "
        f"(fundamental factors see only these)"
    )
    other = {
        k: v for k, v in info['securities_by_standard'].items() if k != 'us-gaap'
    }
    if other:
        detail = ", ".join(f"{v} {k}" for k, v in sorted(other.items()))
        emit(f"  excluded       {detail:>10}   "
             f"(prices only -- no readable fundamentals)")
    emit(f"  fundamentals   {info['fundamentals']:>10,}")
    emit(f"  prices         {info['prices']:>10,}")
    emit(f"  restatements   {info['restatements']:>10,}   "
         f"({info['restatement_rate']:.1%} of fundamental rows)")
    emit(f"  price history  {info['first_date']} .. {info['last_date']}")

    environment = research_environment()
    emit(_header("RESEARCH ENVIRONMENT"))
    emit()
    emit(f"  {'Python':<14}{environment['python']}")
    for package in ("pandas", "numpy", "scipy", "statsmodels"):
        emit(f"  {package:<14}{environment[package]}")
    emit(f"  {'lock':<14}{environment['lock_file']}")
    emit(f"  {'lock SHA-256':<14}{environment['lock_sha256']}")
    emit(f"  {'lock status':<14}{environment['lock_status']}")
    if environment["lock_mismatches"]:
        for package, versions in environment["lock_mismatches"].items():
            emit(
                f"    {package}: installed {versions['installed']}, "
                f"locked {versions['locked']}"
            )
    emit()
    emit("  These are the versions that produced this report. MATCHED means the")
    emit("  four numerical libraries equal the exact shipped research lock;")
    emit("  MISMATCH keeps the report diagnostic and prints every difference.")

    coverage = store.column_coverage("prices")
    thin = coverage.loc[coverage["coverage"] < 0.99]
    if len(thin):
        emit(_header("DATA QUALITY"))
        emit()
        emit("  Price columns that are not fully populated. A column at 0.0%")
        emit("  empties every factor that reads it, and the failure surfaces as")
        emit("  'factor produced no values' -- naming the factor, not the column.")
        emit()
        emit(f"  {'column':<16}{'non-null':>12}{'coverage':>12}")
        for _, row in thin.iterrows():
            emit(
                f"  {row['column']:<16}{int(row['non_null']):>12,}"
                f"{row['coverage']:>11.1%}"
            )

    emit(_header("REGISTERED FACTORS"))
    emit()
    table = summary_table()
    emit(
        f"  {'factor':<14}{'category':<14}{'fundamentals':<14}"
        f"{'falsification':>14}{'plausible range':>20}"
    )
    for _, row in table.iterrows():
        emit(
            f"  {row['factor_id']:<14}{row['category']:<14}"
            f"{'yes' if row['uses_fundamentals'] else 'no':<14}"
            f"{row['n_falsification_criteria']:>14}"
            f"{row['plausible_range']:>20}"
        )
    emit()
    emit("  Every factor carries a hypothesis card stating an economic mechanism,")
    emit("  the conditions under which it should persist, and what would falsify")
    emit("  it. Registration fails without one.")
    emit()
    emit("  'plausible range' is the interval the factor's raw values are checked")
    emit("  against before any cleaning. 'undefined' means no range has been")
    emit("  declared -- NOT that the factor passed. An undeclared range is an")
    emit("  unchecked magnitude, and the two states are printed differently for")
    emit("  the same reason an unknown share count is null and not zero.")

    denominator = published_anomaly_denominator()
    emit(_header("PUBLISHED-ANOMALY DENOMINATOR"))
    emit()
    emit(f"  claim             {denominator['claim_id']}")
    emit(
        f"  current base      {denominator['current_n']} included "
        f"(baseline {denominator['baseline_n']}, delta {denominator['delta_n']:+d})"
    )
    emit(f"  included          {', '.join(denominator['current_included'])}")
    emit(f"  excluded          {', '.join(denominator['excluded']) or 'none'}")
    emit(f"  pending           {', '.join(denominator['pending']) or 'none'}")
    emit(
        "  removed vs base   "
        f"{', '.join(denominator['removed_since_baseline']) or 'none'}"
    )
    for factor_id in denominator["excluded"] + denominator["pending"]:
        emit(f"    {factor_id}: {denominator['reasons'][factor_id]}")
    emit()
    emit("  INCLUDED requires a verified definition-origin citation. PENDING means")
    emit("  the proposed origin has not been checked at a primary-source locator;")
    emit("  EXCLUDED means the implemented quantity is not the published anomaly.")
    emit("  Definition eligibility is separate from outcome evidence; no survival rate")
    emit("  follows from this denominator or from a completed computation.")

    dates = signal_dates_for(store, min_history_months=15)
    available_signal_dates = len(dates)
    protocol_settings = {"horizon_sessions": 21, "execution_lag_sessions": 1, "n_quantiles": 5}
    if args.max_dates and len(dates) > args.max_dates:
        idx = pd.Index(range(len(dates)))
        keep = idx[:: max(1, len(dates) // args.max_dates)][: args.max_dates]
        dates = dates[keep]

    emit(_header("STANDARD PROTOCOL"))
    emit()
    emit("  " + qualification_lines(evidence)[0])
    emit(f"  {len(dates)} signal dates from the monthly grid, "
         f"{dates[0].date() if len(dates) else 'n/a'} .. "
         f"{dates[-1].date() if len(dates) else 'n/a'}")
    if len(dates) < available_signal_dates:
        emit("  SUBSAMPLED diagnostic grid: formation shifts count selected dates.")
        emit("  This is not definition-equivalent to the full monthly run.")
    emit()
    emit(
        f"  {'factor':<14}{'IC':>10}{'LS Sharpe':>11}"
        f"{'monotone':>10}{'dates':>7}{'as-of held':>11}  status"
    )

    runs = {}
    failures: dict[str, str] = {}
    for factor_id, factor in factors.items():
        try:
            run = compute_factor(factor, store, dates, **protocol_settings)
        except Exception as exc:
            # A factor that fails a check must stay in the table. Catching the
            # error keeps the other nine computable; dropping the row would make
            # the failure disappear, which is the opposite of what the check is
            # for. So the row is printed with its numbers withheld -- they were
            # never computed -- and the reason underneath it.
            status, reason = _describe_failure(exc)
            failures[factor_id] = status
            emit(
                f"  {factor_id:<14}{'--':>10}{'--':>11}"
                f"{'--':>10}{'--':>7}{'--':>11}  {status}"
            )
            for line in reason:
                emit(f"      {line}")
            continue
        runs[factor_id] = run
        s = run.protocol.summary
        emit(
            f"  {factor_id:<14}{s['ic_mean']:>+10.4f}{s['ls_sharpe']:>+11.4f}"
            f"{run.protocol.monotonicity_rho:>+10.2f}{run.protocol.n_dates:>7}"
            f"{('yes' if run.read_path_check['ok'] else 'VIOLATION'):>11}  OK"
        )

    emit()
    emit("  'as-of held' is a check on this code: did every read return only")
    emit("  filings that were already public on the day being forecast, including")
    emit("  any reporting lag the factor declared? A VIOLATION here would void")
    emit("  every number in the row.")
    emit()
    emit("  'status' is whether the factor produced a result at all. OK means the")
    emit("  run completed; it does not mean the factor works. A FAILED row has no")
    emit("  numbers because none were computed -- the run stopped at the check")
    emit("  named in the status, and that row is excluded from every table below.")

    emit(_header("HISTORICAL UNIVERSE GATE"))
    emit()
    emit("  Membership is applied to raw factor rows before magnitude checks,")
    emit("  winsorisation and standardisation. An excluded row therefore cannot")
    emit("  alter the score of a security that was eligible on the same date.")
    emit()
    emit(
        f"  {'factor':<14}{'raw rows':>12}{'eligible':>12}"
        f"{'excluded':>12}{'retained':>11}"
    )
    for factor_id, run in runs.items():
        u = run.universe_filter
        emit(
            f"  {factor_id:<14}{u.n_input:>12,}{u.n_output:>12,}"
            f"{u.n_excluded_outside_universe:>12,}{u.retention:>10.1%}"
        )
    emit()
    emit("  'excluded' is reported independently from missing-value cleaning and")
    emit("  label attrition: outside the historical universe is an eligibility")
    emit("  decision, not a missing observation.")
    emit("  For ingested data this is a filing-activity proxy, not verified exchange")
    emit("  membership. It cannot recover securities missing from the initial selection.")

    emit(_header("FACTOR-CONSTRUCTION SAMPLE FILTERS"))
    emit()
    emit("  These are definition-level eligibility rules applied inside a factor,")
    emit("  before the common universe gate and missing-value cleaning.")
    emit()
    emit(f"  {'factor':<14}{'filter':<38}{'input':>9}{'excluded':>11}")
    any_filter = False
    for factor_id, run in runs.items():
        for construction_filter in run.construction_filters:
            any_filter = True
            emit(
                f"  {factor_id:<14}{construction_filter['filter_id']:<38}"
                f"{construction_filter['n_input']:>9,}"
                f"{construction_filter['n_excluded']:>11,}"
            )
            sample = construction_filter.get("excluded_keys", [])[:5]
            if sample:
                shown = ", ".join(
                    f"{row['signal_date']} {row['ticker']} ({row['equity']:g})"
                    for row in sample
                )
                emit(f"      excluded keys: {shown}")
    if not any_filter:
        emit("  none")

    emit(_header("FORWARD-LABEL ATTRITION"))
    emit()
    emit("  Every cleaned signal is left-joined to its realised return before")
    emit("  invalid rows are removed, so an absent label cannot disappear without")
    emit("  a counted reason.")
    emit()
    emit(
        f"  {'factor':<14}{'signals':>12}{'labelled':>12}"
        f"{'dropped':>12}{'retained':>11}"
    )
    for factor_id, run in runs.items():
        label = run.label_join
        emit(
            f"  {factor_id:<14}{label.n_input:>12,}{label.n_output:>12,}"
            f"{label.n_dropped_without_label:>12,}{label.retention:>10.1%}"
        )
        reasons = {
            reason: count
            for reason, count in label.outcome_counts.items()
            if reason != "matched" and count
        }
        if reasons:
            rendered = ", ".join(
                f"{reason}={count:,}" for reason, count in sorted(reasons.items())
            )
            emit(f"    {rendered}")

    emit(_header("CROSS-SECTION BREADTH"))
    emit()
    emit("  Names per quantile are reported as a distribution. The average alone")
    emit("  can hide a month whose portfolios nearly disappeared.")
    emit()
    emit(
        f"  {'factor':<14}{'avg':>7}{'min':>7}{'p10':>7}{'median':>9}"
        f"{'p90':>7}{'max':>7}{'dropped':>10}"
    )
    for factor_id, run in runs.items():
        s = run.protocol.summary
        emit(
            f"  {factor_id:<14}{s['names_per_quantile_avg']:>7.1f}"
            f"{s['names_per_quantile_min']:>7}{s['names_per_quantile_p10']:>7.1f}"
            f"{s['names_per_quantile_median']:>9.1f}{s['names_per_quantile_p90']:>7.1f}"
            f"{s['names_per_quantile_max']:>7}"
            f"{s['n_dates_dropped_insufficient_cross_section']:>10}"
        )
    emit()
    emit("  'dropped' counts signal dates present in the aligned panel but absent")
    emit("  from quantile portfolios because the cross-section was too small or")
    emit("  ties prevented all five groups from being formed.")

    emit(_header("THE TRAP, MEASURED"))
    emit()
    emit("  How much would a naive query have read early? This is the hazard the")
    emit("  bitemporal store exists to avoid -- a diagnostic count, not an alpha finding.")
    emit()
    emit(f"  {'factor':<14}{'signal dates':>14}{'exposed':>10}{'trap rows':>12}{'rate':>9}")
    for factor_id, run in runs.items():
        t = run.naive_trap
        if not t.get("n_signal_dates"):
            emit(f"  {factor_id:<14}{'n/a -- reads no fundamentals':>45}")
            continue
        emit(
            f"  {factor_id:<14}{t['n_signal_dates']:>14,}{t['n_dates_exposed']:>10,}"
            f"{t['n_trap_rows']:>12,}{t['exposure_rate']:>9.1%}"
        )

    emit(_header("POINT-IN-TIME VS RESTATED"))
    emit()
    emit("  " + qualification_lines(evidence)[0])
    emit("  Within-sample comparison; shared defects need not cancel.")
    emit("  Could this result have been obtained when the signal was formed?")
    emit()

    comparisons = {}
    for factor_id, factor in factors.items():
        if factor_id not in runs:
            # Named rather than skipped. A factor absent from this section
            # because its run failed looks identical to one that was never
            # registered, and the two mean very different things.
            emit(f"  {factor_id}")
            emit(f"    not compared -- {failures.get(factor_id, 'run failed')};")
            emit("    see the status column above")
            emit()
            comparisons[factor_id] = {"status": "NOT_COMPUTED", "reason": failures[factor_id]}
            continue
        try:
            comp = compare_vintages(factor, store, dates, **protocol_settings)
        except Exception as exc:
            emit(f"  {factor_id}: comparison failed: {type(exc).__name__}: {exc}")
            comparisons[factor_id] = {"status": "FAILED", "reason": type(exc).__name__}
            continue

        comparisons[factor_id] = {
            "status": evidence["statistics_status"] if comp.applicable else "NOT_APPLICABLE",
            "pit": comp.pit.to_dict(),
            "restated": comp.restated.to_dict() if comp.restated is not None else None,
            "ic_gap": comp.ic_gap if comp.applicable else None,
            "diagnostic_verdict": comp.verdict,
            "detail": comp.detail,
        }

        emit(f"  {factor_id}")
        if not comp.applicable:
            emit("    not applicable -- this factor reads no fundamentals, so the")
            emit("    two vintages are identical by construction. That is not")
            emit("    evidence it is free of look-ahead.")
        else:
            emit(f"    point-in-time IC   {comp.pit.summary['ic_mean']:>+10.4f}")
            emit(f"    restated IC        {comp.restated.summary['ic_mean']:>+10.4f}")
            emit(f"    restated minus PIT {comp.ic_gap:>+10.4f}")
            verdict = comp.verdict.split(":")[0]
            emit(f"    verdict            {verdict:>10}")
        emit()

    gates = research_gate_ledger()
    emit(_header("RESEARCH CLAIM GATES"))
    for gate, state in gates.items():
        emit(f"  {gate}: {state['status']} -- {state['reason']}")
    emit("  UNRESOLVED is not a measured bias size; NOT_IMPLEMENTED is not passed.")

    emit(_rule("="))
    for line in qualification_lines(evidence):
        emit("  " + line)
    emit("  The vintage gap is conditional on the selected data and label samples;")
    emit("  it does not establish a market-wide effect or cancel shared data defects.")
    emit("  Ingest alone does not qualify research evidence.")
    emit(_rule("="))
    emit()

    if args.outdir:
        roster = store.con.execute(
            "SELECT cik, ticker, first_filing, last_filing, accounting_standard "
            "FROM securities ORDER BY ticker, cik"
        ).df().to_dict("records")
        roster_json = json.dumps(json_safe(roster), sort_keys=True, allow_nan=False)
        records = {}
        for factor_id in factors:
            completed = factor_id in runs
            records[factor_id] = factor_record(runs[factor_id], evidence) if completed else {
                "computation_status": failures[factor_id],
                "statistics_status": "NOT_COMPUTED",
                "protocol": None,
                "reason": "see_text_failure_details; no_zero_imputed_for_missing_result",
            }
        try:
            end_hash = file_sha256(args.db) if mode == "real" else None
        except OSError:
            end_hash = None
        bundle = {
            "schema_version": 1,
            "artifact_role": evidence["statistics_status"] + " / NOT_AN_ASSERTION",
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "evidence": evidence,
            "environment": environment,
            "implementation": implementation_manifest(),
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
            "research_gates": gates,
        }
        args.outdir.mkdir(parents=True, exist_ok=True)
        (args.outdir / "demo_report.txt").write_text("\n".join(lines), encoding="utf-8")
        (args.outdir / "demo_evidence.json").write_text(
            json.dumps(evidence, indent=2, allow_nan=False), encoding="utf-8"
        )
        (args.outdir / "demo_run.json").write_text(
            json.dumps(json_safe(bundle), indent=2, allow_nan=False), encoding="utf-8"
        )
        print(f"report written to {args.outdir / 'demo_report.txt'}")

    store.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
