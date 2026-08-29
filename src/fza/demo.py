"""Demo: run the whole pipeline and print what it found.

Two modes, chosen automatically:

* **Real data**, when a store built by ``fza.ingest.run`` is present. This is the
  interesting mode, and the numbers it prints are findings.
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
from pathlib import Path

import pandas as pd

from .factors.registry import load_all, summary_table
from .fixtures import load_fixture_into
from .pipeline.prepare import EmptyFactorError
from .pipeline.run import (
    ImplausibleMagnitudeError,
    compare_vintages,
    compute_factor,
)
from .store import Store

DEFAULT_DB = Path("data/fza.duckdb")

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
    n_fun = con.execute("SELECT count(*) FROM fundamentals").fetchone()[0]
    n_px = con.execute("SELECT count(*) FROM prices").fetchone()[0]
    n_rev = len(store.restatements())

    dates = con.execute(
        "SELECT min(trade_date), max(trade_date) FROM prices"
    ).fetchone()

    return {
        "mode": mode,
        "securities": n_sec,
        "fundamentals": n_fun,
        "prices": n_px,
        "restatements": n_rev,
        "restatement_rate": n_rev / n_fun if n_fun else float("nan"),
        "first_date": dates[0],
        "last_date": dates[1],
    }


def signal_dates_for(
    store: Store, freq: str = "ME", min_history_months: int = 15
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
    emit(f"  securities     {info['securities']:>10,}")
    emit(f"  fundamentals   {info['fundamentals']:>10,}")
    emit(f"  prices         {info['prices']:>10,}")
    emit(f"  restatements   {info['restatements']:>10,}   "
         f"({info['restatement_rate']:.1%} of fundamental rows)")
    emit(f"  price history  {info['first_date']} .. {info['last_date']}")

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

    dates = signal_dates_for(store)
    if args.max_dates and len(dates) > args.max_dates:
        idx = pd.Index(range(len(dates)))
        keep = idx[:: max(1, len(dates) // args.max_dates)][: args.max_dates]
        dates = dates[keep]

    emit(_header("STANDARD PROTOCOL"))
    emit()
    emit(f"  {len(dates)} monthly signal dates, "
         f"{dates[0].date() if len(dates) else 'n/a'} .. "
         f"{dates[-1].date() if len(dates) else 'n/a'}")
    emit()
    emit(
        f"  {'factor':<14}{'IC':>10}{'LS Sharpe':>11}"
        f"{'monotone':>10}{'dates':>7}{'as-of held':>11}  status"
    )

    runs = {}
    failures: dict[str, str] = {}
    for factor_id, factor in factors.items():
        try:
            run = compute_factor(factor, store, dates)
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

    emit(_header("THE TRAP, MEASURED"))
    emit()
    emit("  How much would a naive query have read early? This is the hazard the")
    emit("  bitemporal store exists to avoid -- a finding, not a failure.")
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
    emit("  Could this result have been obtained when the signal was formed?")
    emit()

    for factor_id, factor in factors.items():
        if factor_id not in runs:
            # Named rather than skipped. A factor absent from this section
            # because its run failed looks identical to one that was never
            # registered, and the two mean very different things.
            emit(f"  {factor_id}")
            emit(f"    not compared -- {failures.get(factor_id, 'run failed')};")
            emit("    see the status column above")
            emit()
            continue
        try:
            comp = compare_vintages(factor, store, dates)
        except Exception as exc:
            emit(f"  {factor_id}: comparison failed: {type(exc).__name__}: {exc}")
            continue

        emit(f"  {factor_id}")
        if not comp.applicable:
            emit("    not applicable -- this factor reads no fundamentals, so the")
            emit("    two vintages are identical by construction. That is not")
            emit("    evidence it is free of look-ahead.")
        else:
            emit(f"    point-in-time IC   {comp.pit.summary['ic_mean']:>+10.4f}")
            emit(f"    restated IC        {comp.restated.summary['ic_mean']:>+10.4f}")
            emit(f"    unearned advantage {comp.ic_gap:>+10.4f}")
            verdict = comp.verdict.split(":")[0]
            emit(f"    verdict            {verdict:>10}")
        emit()

    emit(_rule("="))
    if mode == "real":
        emit("  The gap above is the value of reading a filing before it existed.")
        emit("  It is measurable here only because revisions are stored as rows")
        emit("  rather than updates -- a database that overwrote them could not")
        emit("  produce this number at all.")
    else:
        emit("  Run the ingest for numbers that mean something.")
    emit(_rule("="))
    emit()

    if args.outdir:
        args.outdir.mkdir(parents=True, exist_ok=True)
        (args.outdir / "demo_report.txt").write_text("\n".join(lines), encoding="utf-8")
        print(f"report written to {args.outdir / 'demo_report.txt'}")

    store.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
