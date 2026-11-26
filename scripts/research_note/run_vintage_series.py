"""Timed single-factor vintage run that keeps the per-date IC series.

Read-only: opens the store with read_only=True and hashes it before and after.
Writes only --out and --log. Does not modify the repository: it imports the
repository's code (--repo, default: the checkout containing this script) and
wraps functions in memory to time them and capture ProtocolResult.ic_series
(which demo_run.json never serialises). One factor per process; DuckDB
memory_limit 1GB and threads 1.

    python -I -u scripts/research_note/run_vintage_series.py --db <store.duckdb>
        --factor bm_ratio --out <dir>/bm_ratio_series.json
        --log <dir>/bm_ratio_run.log [--expected-sha256 <hex>]

With --expected-sha256 the run aborts before computing if the store differs.

Layer spans are derived from call order in fza.pipeline.vintage.diagnostic_layers:
  original-process   = layers start -> 2nd outcome_identity call
  common-observation = 2nd outcome_identity -> 1st prepare_cross_sections
  common-support     = 1st prepare_cross_sections -> layers end
The small indexing/sample_report work between those markers is counted in the
earlier span.
"""

import argparse
import ctypes
import hashlib
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from time import perf_counter

LAYER_CALLS = [f"{layer}/{arm}" for layer in
               ("original-process", "common-observation", "common-support")
               for arm in ("pit", "restated")]

T0 = perf_counter()
EVENTS = []      # (name, start_s, end_s)
DEPTH = [0]


class Tee:
    encoding = "utf-8"

    def __init__(self, *streams):
        self.streams = streams

    def isatty(self):
        return False

    def write(self, s):
        for st in self.streams:
            st.write(s)
            st.flush()

    def flush(self):
        for st in self.streams:
            st.flush()


def now():
    return datetime.now().astimezone().isoformat(timespec="seconds")


def mem_mib():
    """(working set, peak working set) in MiB on Windows; None elsewhere."""
    try:
        from ctypes import wintypes as w

        class PMC(ctypes.Structure):
            _fields_ = [("cb", w.DWORD), ("PageFaultCount", w.DWORD)] + [
                (n, ctypes.c_size_t) for n in (
                    "PeakWorkingSetSize", "WorkingSetSize", "QuotaPeakPagedPoolUsage",
                    "QuotaPagedPoolUsage", "QuotaPeakNonPagedPoolUsage",
                    "QuotaNonPagedPoolUsage", "PagefileUsage", "PeakPagefileUsage")]
        k32, psapi = ctypes.windll.kernel32, ctypes.windll.psapi
        k32.GetCurrentProcess.restype = w.HANDLE
        psapi.GetProcessMemoryInfo.argtypes = [w.HANDLE, ctypes.POINTER(PMC), w.DWORD]
        c = PMC()
        c.cb = ctypes.sizeof(c)
        if not psapi.GetProcessMemoryInfo(k32.GetCurrentProcess(), ctypes.byref(c), c.cb):
            return None
        return round(c.WorkingSetSize / 2**20), round(c.PeakWorkingSetSize / 2**20)
    except Exception:
        return None


def begin(name):
    t = perf_counter() - T0
    print(f"{now()} {'  ' * DEPTH[0]}START {name}")
    DEPTH[0] += 1
    return t


def end(name, start):
    DEPTH[0] -= 1
    t = perf_counter() - T0
    EVENTS.append((name, start, t))
    m = mem_mib()
    mem = f" | WS {m[0]} MiB, peak {m[1]} MiB" if m else ""
    print(f"{now()} {'  ' * DEPTH[0]}END   {name} ({t - start:.1f}s){mem}")


def timed(fn, namer):
    calls = [0]

    def wrapper(*args, **kwargs):
        name = namer(calls[0], args, kwargs)
        calls[0] += 1
        start = begin(name)
        try:
            return fn(*args, **kwargs)
        finally:
            end(name, start)
    return wrapper


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", type=Path, required=True)
    ap.add_argument("--factor", required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--log", type=Path, required=True)
    ap.add_argument("--repo", type=Path, default=Path(__file__).resolve().parents[2])
    ap.add_argument("--expected-sha256")
    args = ap.parse_args()
    repo = args.repo.resolve()

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.log.parent.mkdir(parents=True, exist_ok=True)
    log = open(args.log, "w", encoding="utf-8")
    sys.stdout.reconfigure(errors="replace")
    sys.stdout = sys.stderr = Tee(sys.__stdout__, log)

    print(f"{now()} python {sys.version.split()[0]} at {sys.executable}")
    for cmd in (["rev-parse", "HEAD"], ["status", "--porcelain", "--", "src"]):
        r = subprocess.run(["git", "-C", str(repo), *cmd], capture_output=True, text=True)
        print(f"git {' '.join(cmd)}: {r.stdout.strip() or '(clean)'}")

    if not args.db.is_file():
        sys.exit(f"DB not found: {args.db}")
    s = begin("sha256 before")
    before = sha256(args.db)
    end("sha256 before", s)
    print(f"sha256 before: {before}")
    if args.expected_sha256 and before != args.expected_sha256.lower():
        sys.exit(f"ABORT: DB hash differs from --expected-sha256 {args.expected_sha256}")

    s = begin("load")
    sys.path.insert(0, str(repo / "src"))
    import fza
    if not Path(fza.__file__).resolve().is_relative_to(repo / "src"):
        sys.exit(f"ABORT: fza imported from {fza.__file__}, not {repo / 'src'}")
    print(f"fza imported from {fza.__file__}")
    import duckdb
    import numpy
    import pandas
    import scipy
    print(f"pandas {pandas.__version__} numpy {numpy.__version__} "
          f"scipy {scipy.__version__} duckdb {duckdb.__version__}")
    import fza.pipeline.run as R
    import fza.pipeline.vintage as V
    from fza.demo import signal_dates_for
    from fza.factors.registry import load_all
    from fza.store import Store

    store = Store(str(args.db), read_only=True)
    store.con.execute("SET memory_limit='1GB'")
    store.con.execute("SET threads=1")
    print("duckdb settings:", store.con.execute(
        "SELECT name, value FROM duckdb_settings() WHERE name IN ('memory_limit','threads')"
    ).fetchall())
    dates = signal_dates_for(store, min_history_months=15)
    factor = load_all()[args.factor]
    print(f"signal dates: {len(dates)} ({dates[0].date()} .. {dates[-1].date()}); "
          f"factor {factor.factor_id}, uses_fundamentals={factor.uses_fundamentals}")
    end("load", s)

    captured = {}

    def capture_protocol(fn):
        def wrapper(i, *a, **k):
            r = fn(*a, **k)
            captured[LAYER_CALLS[i]] = {
                "dates": [str(d.date()) for d in r.ic_series.index],
                "ic": [float(v) for v in r.ic_series.to_numpy()],
                "ic_mean": r.summary["ic_mean"],
                "n_dates": r.n_dates,
                "n_observations": r.n_observations,
            }
            return r
        calls = [0]

        def counted(*a, **k):
            i = calls[0]
            calls[0] += 1
            return wrapper(i, *a, **k)
        return counted

    R.historical_universe_membership = timed(
        R.historical_universe_membership, lambda i, a, k: "historical membership")
    R.compute_factor = timed(
        R.compute_factor, lambda i, a, k: f"compute_factor {k.get('vintage', '?').upper()}")
    R.run_protocol = timed(R.run_protocol, lambda i, a, k: "run_protocol (run.py)")
    V.run_protocol = timed(capture_protocol(V.run_protocol),
                           lambda i, a, k: f"layer run_protocol {LAYER_CALLS[i]}")
    V.outcome_identity = timed(V.outcome_identity, lambda i, a, k: f"outcome_identity #{i + 1}")
    V.prepare_cross_sections = timed(
        V.prepare_cross_sections, lambda i, a, k: f"common-support cleaning #{i + 1}")
    store.fundamentals_restated = timed(
        store.fundamentals_restated, lambda i, a, k: "restated read (fundamentals_restated)")

    original_layers = R.diagnostic_layers

    def layers_with_timed_labels(*a, **k):
        k["label_builder"] = timed(k["label_builder"],
                                   lambda i, a2, k2: f"common-support labels #{i + 1}")
        return original_layers(*a, **k)
    R.diagnostic_layers = timed(layers_with_timed_labels, lambda i, a, k: "diagnostic_layers")

    try:
        s = begin(f"compare_vintages {args.factor}")
        comp = R.compare_vintages(factor, store, dates, horizon_sessions=21,
                                  execution_lag_sessions=1, n_quantiles=5)
        end(f"compare_vintages {args.factor}", s)
    finally:
        store.con.close()
        s = begin("sha256 after")
        after = sha256(args.db)
        end("sha256 after", s)
        print(f"sha256 after:  {after} ({'UNCHANGED' if after == before else 'CHANGED'})")

    # Derived layer spans (see module docstring).
    ev = {name: (a, b) for name, a, b in EVENTS}
    layers_start, layers_end = ev["diagnostic_layers"]
    co_start = ev["outcome_identity #2"][0]
    cs_start = ev.get("common-support cleaning #1", (layers_end,))[0]
    print("\nSUMMARY (seconds)")
    rows = [("load", *ev["load"]),
            ("historical membership", *ev["historical membership"]),
            ("PIT compute_factor", *ev["compute_factor PIT"]),
            ("restated read", *ev["restated read (fundamentals_restated)"]),
            ("restated compute_factor", *ev["compute_factor RESTATED"]),
            ("layer original-process", layers_start, co_start),
            ("layer common-observation", co_start, cs_start),
            ("layer common-support", cs_start, layers_end),
            ("compare_vintages total", *ev[f"compare_vintages {args.factor}"])]
    for name, a, b in rows:
        print(f"  {name:26s} {b - a:10.1f}")
    m = mem_mib()
    if m:
        print(f"  peak working set: {m[1]} MiB")

    layer_gaps = {name: row.get("ic_gap") for name, row in comp.detail["layers"].items()}
    json.dump({
        "factor": args.factor,
        "generated_at": now(),
        "db": str(args.db),
        "db_sha256_before": before,
        "db_sha256_after": after,
        "fza_file": fza.__file__,
        "duckdb": {"memory_limit": "1GB", "threads": 1},
        "signal_dates": len(dates),
        "stage_seconds": {name: b - a for name, a, b in rows},
        "layer_ic_gap": layer_gaps,
        "series": captured,
    }, open(args.out, "w", encoding="utf-8"), indent=1)
    print(f"\nwrote {args.out}")
    if after != before:
        sys.exit("DB hash changed during the run")


if __name__ == "__main__":
    main()
