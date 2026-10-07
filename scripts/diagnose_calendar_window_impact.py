"""Calendar-window correction impact diagnostic -- synthetic verification only.

Purpose
-------
Compare ``mom_12_1``, ``mom_6_1`` and ``rev_1m`` as computed by the two
released source trees on one fixed database:

* v0.1.0 = 287be9b1a24d2d27b644b76cdfcae3b66b08c924 (row shifts of requests)
* v0.2.0 = 782d041db8438c6e957e5e4e3ba6c81a41f091c8 (calendar month anchors)

Both trees are exported from local git objects into the work directory and run
in separate subprocesses of the *current* interpreter, so each process imports
exactly one ``fza``. Actual outputs are checked against expectations computed
here, independently of the code under test:

S0  every anchor price used is positive and finite, and every formula result
    is finite (an experimental precondition, not a source-code filter);
S1  the database SHA-256 is unchanged from preparation through comparison;
S2  each version's raw keys equal the expected key set, with no duplicates;
S3  every raw value matches the independent anchor formula;
S4  version relations on common/new-only/old-only keys;
S5  labels on common scoring keys are exactly equal.

Descriptive Spearman IC per version (the version's own
``information_coefficient``) is reported with a request-date accounting.

Run
---
    python scripts/diagnose_calendar_window_impact.py synthetic --workdir DIR
        [--scenario positive|zero_latest|overflow] [--reference-sha256 HEX]

DIR must not exist; it should be a git-ignored location. This entry point only
creates and reads its own synthetic database. It has no real-database mode.

Evidence boundary
-----------------
A PASS here is evidence about the synthetic database only. It says nothing
about real-store values or coverage. ``compute_factor`` also runs the upstream
protocol; those results are not used. IC is descriptive: no baseline,
incremental signal, qualification or alpha claim.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import math
import os
import subprocess
import sys
import tarfile
import time
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[1]
VERSIONS = {
    "v0.1.0": "287be9b1a24d2d27b644b76cdfcae3b66b08c924",
    "v0.2.0": "782d041db8438c6e957e5e4e3ba6c81a41f091c8",
}
OLD, NEW = "v0.1.0", "v0.2.0"
BUILDER = NEW  # schema, Store, cleaning and labels are identical in both trees
FACTORS = ("mom_12_1", "mom_6_1", "rev_1m")
# (end lag, start lag) in calendar month ends before s; rev_1m is negated.
WINDOWS = {
    OLD: {"mom_12_1": (1, 13), "mom_6_1": (1, 7), "rev_1m": (0, 1)},
    NEW: {"mom_12_1": (1, 12), "mom_6_1": (1, 7), "rev_1m": (0, 1)},
}
OLD_WARMUP = {"mom_12_1": 13, "mom_6_1": 7, "rev_1m": 1}  # zero-based request row
STALE_DAYS = 10
PIPELINE = {"horizon_sessions": 21, "execution_lag_sessions": 1, "n_quantiles": 5}
IC_MIN_ROWS = 5
PASS, FAIL, NOT_RUN, EMPTY = "PASS", "FAIL", "NOT_RUN", "NO_COMPARABLE_SAMPLE"
CHECKS = ("S0", "S1", "S2", "S3", "S4", "S5", "IC")  # all must PASS for exit code 0


# ----------------------------------------------------------------------
# Synthetic data (pure pandas; no fza)
# ----------------------------------------------------------------------
def request_dates() -> list[pd.Timestamp]:
    """One ordered list of consecutive month ends, shared by both versions."""
    return list(pd.date_range("2019-01-31", "2021-06-30", freq=pd.offsets.MonthEnd()))


def synthetic_tables(scenario: str = "positive"):
    """Securities and prices. Deterministic; prices are daily business days."""
    days = pd.bdate_range("2017-10-02", "2021-08-31")
    rng = np.random.default_rng(20261007)

    def path():
        steps = rng.normal(0.0003, 0.015, len(days))
        return 100.0 * np.exp(np.cumsum(steps))

    frames = {f"T{i:02d}": pd.Series(path(), index=days) for i in range(30)}

    def drop(series, start, end):
        return series.loc[(series.index < start) | (series.index > end)]

    # 10 days of carry is allowed on 2020-07-31; 11 days is stale.
    frames["CARRY10"] = drop(pd.Series(path(), index=days), "2020-07-22", "2020-07-31")
    frames["STALE11"] = drop(pd.Series(path(), index=days), "2020-07-21", "2020-07-31")
    # No price within 10 days of 2019-11-30: removes s-13 for s=2020-12-31 and
    # s-12 for s=2020-11-30, so mom_12_1 can legitimately be new-only or old-only.
    frames["GAPM"] = drop(pd.Series(path(), index=days), "2019-11-16", "2019-11-30")
    frames["ALLNA"] = pd.Series(np.nan, index=days)
    if scenario == "zero_latest":
        zero = pd.Series(path(), index=days)
        zero.loc["2020-03-31"] = 0.0  # latest close at the anchor; earlier ones positive
        frames["ZERO"] = zero
    elif scenario == "overflow":
        frames["OVF"] = pd.Series(np.where(days <= "2019-12-31", 1e-300, 1e300), index=days)
    elif scenario != "positive":
        raise ValueError(f"unknown scenario {scenario!r}")

    prices = pd.concat(
        [pd.DataFrame({"ticker": t, "trade_date": s.index, "close_adj": s.to_numpy()})
         for t, s in frames.items()], ignore_index=True)
    prices["close"] = prices["close_adj"]
    securities = pd.DataFrame({
        "cik": [f"{i:010d}" for i in range(len(frames))],
        "ticker": list(frames),
        "first_filing": pd.Timestamp("2017-01-01"),
        "last_filing": pd.Timestamp("2022-12-31"),
    })
    return securities, prices


# ----------------------------------------------------------------------
# Independent expectations (never call the code under test)
# ----------------------------------------------------------------------
def month_back(s: pd.Timestamp, k: int) -> pd.Timestamp:
    return s if k == 0 else s - pd.offsets.MonthEnd(k)


class AnchorPrices:
    """Last non-missing close_adj on or before an anchor, at most STALE_DAYS old.

    Zero, negative and infinite values are observations, not gaps: the price is
    never sought further back past them.
    """

    def __init__(self, prices: pd.DataFrame):
        p = prices.loc[prices["close_adj"].notna(), ["ticker", "trade_date", "close_adj"]]
        p = p.assign(trade_date=pd.to_datetime(p["trade_date"])).sort_values(
            ["ticker", "trade_date"])
        self._by = {t: (g["trade_date"].to_numpy().astype("datetime64[ns]"),
                        g["close_adj"].to_numpy(float))
                    for t, g in p.groupby("ticker")}

    def at(self, ticker: str, anchor: pd.Timestamp) -> dict:
        dates, values = self._by.get(ticker, (np.array([], "datetime64[ns]"), np.array([])))
        i = int(np.searchsorted(dates, np.datetime64(anchor, "ns"), side="right")) - 1
        if i < 0:
            return {"anchor": anchor, "price": None, "obs_date": None, "age_days": None,
                    "reason": "no_history"}
        obs = pd.Timestamp(dates[i])
        age = int((anchor - obs).days)
        if age > STALE_DAYS:
            return {"anchor": anchor, "price": None, "obs_date": obs, "age_days": age,
                    "reason": "stale"}
        return {"anchor": anchor, "price": float(values[i]), "obs_date": obs,
                "age_days": age, "reason": "ok"}


def expectations(prices: pd.DataFrame, dates: list[pd.Timestamp]) -> dict:
    """Expected key sets and values per version and factor, plus S0 violations.

    The candidate domain is every ticker in the price table times the request
    list; it is never derived from factor output.
    """
    anchors = AnchorPrices(prices)
    tickers = sorted(prices["ticker"].unique())
    out = {"domain_tickers": tickers, "values": {}, "missing": {}, "s0_violations": []}
    for version, windows in WINDOWS.items():
        for factor, (end_lag, start_lag) in windows.items():
            values, missing = {}, {}
            for i, s in enumerate(dates):
                for t in tickers:
                    key = (t, s)
                    if version == OLD and i < OLD_WARMUP[factor]:
                        missing[key] = "warmup"
                        continue
                    end = anchors.at(t, month_back(s, end_lag))
                    start = anchors.at(t, month_back(s, start_lag))
                    violation = {"version": version, "factor": factor, "ticker": t,
                                 "signal_date": str(s.date()), "end": _jsonable(end),
                                 "start": _jsonable(start)}
                    # Every price that passed the staleness rule must be positive and
                    # finite, even when the other anchor is missing.
                    if any(x["price"] is not None
                           and not (math.isfinite(x["price"]) and x["price"] > 0)
                           for x in (end, start)):
                        out["s0_violations"].append({**violation,
                                                     "reason": "anchor_not_positive_finite"})
                        continue
                    if end["price"] is None or start["price"] is None:
                        gap = end if end["price"] is None else start
                        missing[key] = f"anchor_{gap['reason']}"
                        continue
                    a, b = end["price"], start["price"]
                    with np.errstate(all="ignore"):
                        ret = float(np.float64(a) / np.float64(b) - 1.0)
                    value = -ret if factor == "rev_1m" else ret
                    if not math.isfinite(value):
                        out["s0_violations"].append({**violation, "value": repr(value),
                                                     "reason": "result_not_finite"})
                        continue
                    values[key] = value
            out["values"][(version, factor)] = values
            out["missing"][(version, factor)] = missing
    out["anchors"] = anchors
    return out


def _jsonable(d):
    return {k: (str(v.date()) if isinstance(v, pd.Timestamp) else v) for k, v in d.items()}


# ----------------------------------------------------------------------
# Checks (pure; act on copies of collected observations)
# ----------------------------------------------------------------------
def close(a, b) -> bool:
    """|a-b| <= 1e-14 + 1e-12*|b|, and both finite (non-finite never passes)."""
    try:
        a, b = float(a), float(b)
    except (TypeError, ValueError):
        return False
    return math.isfinite(a) and math.isfinite(b) and abs(a - b) <= 1e-14 + 1e-12 * abs(b)


def combine(verdicts):
    verdicts = list(verdicts)
    if FAIL in verdicts:
        return FAIL
    if NOT_RUN in verdicts:
        return NOT_RUN
    if EMPTY in verdicts:
        return EMPTY
    return PASS


def _keys(rows):
    return [(t, pd.Timestamp(d)) for t, d, *_ in rows]


def check_s0(expect) -> dict:
    v = expect["s0_violations"]
    return {"verdict": PASS if not v else FAIL, "violations": v[:20], "n_violations": len(v)}


def check_s1(hashes: dict, reference: str | None = None) -> dict:
    seen = [h for h in hashes.values()]
    ok = len(seen) >= 2 and all(h == seen[0] for h in seen)
    if reference is not None:
        ok = ok and seen[0] == reference
    return {"verdict": PASS if ok else FAIL, "hashes": hashes, "explicit_reference": reference}


def check_s2(expect, raw) -> dict:
    detail, verdicts = {}, []
    for (version, factor), values in expect["values"].items():
        rows = raw[version][factor]
        keys = _keys(rows)
        actual, expected = set(keys), set(values)
        d = {"expected": len(expected), "actual_rows": len(keys), "actual_unique": len(actual),
             "duplicates": len(keys) - len(actual),
             "missing": sorted(map(_k, expected - actual))[:10],
             "n_missing": len(expected - actual),
             "extra": sorted(map(_k, actual - expected))[:10], "n_extra": len(actual - expected)}
        d["verdict"] = PASS if (actual == expected and d["duplicates"] == 0) else FAIL
        reasons = {}
        for reason in expect["missing"].get((version, factor), {}).values():
            reasons[reason] = reasons.get(reason, 0) + 1
        d["expected_missing_reasons"] = reasons
        detail[f"{version}:{factor}"] = d
        verdicts.append(d["verdict"])
    return {"verdict": combine(verdicts), "detail": detail}


def _k(key):
    return f"{key[0]}@{key[1].date()}"


def check_s3(expect, raw) -> dict:
    detail, verdicts = {}, []
    for (version, factor), values in expect["values"].items():
        rows = raw[version][factor]
        bad = []
        for t, d, v in rows:
            key = (t, pd.Timestamp(d))
            if key not in values or not close(v, values[key]):
                bad.append({"key": _k(key), "actual": repr(v), "expected": repr(values.get(key))})
        verdict = EMPTY if not rows else (PASS if not bad else FAIL)
        detail[f"{version}:{factor}"] = {"compared": len(rows), "n_bad": len(bad),
                                         "bad": bad[:10], "verdict": verdict}
        verdicts.append(verdict)
    return {"verdict": combine(verdicts), "detail": detail}


def check_s4(expect, raw, dates) -> dict:
    index = {s: i for i, s in enumerate(dates)}
    anchors = expect["anchors"]
    detail, verdicts = {}, []
    for factor in FACTORS:
        old = {(t, pd.Timestamp(d)): v for t, d, v in raw[OLD][factor]}
        new = {(t, pd.Timestamp(d)): v for t, d, v in raw[NEW][factor]}
        common = old.keys() & new.keys()
        new_only, old_only = new.keys() - old.keys(), old.keys() - new.keys()
        d = {"C": len(common), "N": len(new_only), "O": len(old_only)}
        sub = {}
        if factor == "mom_12_1":
            bad = []
            for t, s in sorted(common):
                p12 = anchors.at(t, month_back(s, 12))["price"]
                p13 = anchors.at(t, month_back(s, 13))["price"]
                ok = p12 is not None and p13 is not None and close(
                    1.0 + old[(t, s)], (1.0 + new[(t, s)]) * (p12 / p13))
                if not ok:
                    bad.append(_k((t, s)))
            sub["identity_on_C"] = EMPTY if not common else (PASS if not bad else FAIL)
            d["identity_failures"] = bad[:10]
            d["N_in_old_warmup"] = sum(index[s] < OLD_WARMUP[factor] for _, s in new_only)
            d["N_after_old_warmup"] = d["N"] - d["N_in_old_warmup"]
            d["N_after_old_warmup_keys"] = sorted(
                _k(k) for k in new_only if index[k[1]] >= OLD_WARMUP[factor])[:10]
            d["O_keys"] = sorted(map(_k, old_only))[:10]
        else:
            sub["O_empty"] = PASS if not old_only else FAIL
            late = [_k(k) for k in new_only if index.get(k[1], 10**9) >= OLD_WARMUP[factor]]
            sub["N_only_in_old_warmup"] = PASS if not late else FAIL
            bad = [_k(k) for k in common if not close(old[k], new[k])]
            sub["C_values_equal"] = EMPTY if not common else (PASS if not bad else FAIL)
            d["N_outside_warmup"], d["C_mismatch"] = late[:10], bad[:10]
            d["O_keys"] = sorted(map(_k, old_only))[:10]
        d["subchecks"], d["verdict"] = sub, combine(sub.values())
        detail[factor] = d
        verdicts.append(d["verdict"])
    return {"verdict": combine(verdicts), "detail": detail}


def check_s5(panels) -> dict:
    detail, verdicts = {}, []
    for factor in FACTORS:
        old = {(t, pd.Timestamp(d)): lab for t, d, _, lab in panels[OLD][factor]}
        new = {(t, pd.Timestamp(d)): lab for t, d, _, lab in panels[NEW][factor]}
        common = old.keys() & new.keys()
        bad = [_k(k) for k in common
               if not (isinstance(old[k], float) and isinstance(new[k], float)
                       and math.isfinite(old[k]) and old[k] == new[k])]
        verdict = EMPTY if not common else (PASS if not bad else FAIL)
        detail[factor] = {"common_scoring_keys": len(common), "n_bad": len(bad),
                          "bad": bad[:10], "verdict": verdict}
        verdicts.append(verdict)
    return {"verdict": combine(verdicts), "detail": detail}


def classify_dates(panel_rows, ic_by_date: dict, dates) -> dict:
    """Mutually exclusive request-date accounting, derived by this diagnostic.

    Order: no panel rows, fewer than IC_MIN_ROWS, constant cross-section,
    non-finite input -- the four cases the input itself shows to be undefined --
    then valid (IC returned and finite), then unexplained missing IC (the input
    allows an IC but none came back). Not a library export. Anomalies: an
    unexplained missing IC, an IC on any date not classified valid (including
    dates outside the request list), or a non-finite IC value.
    """
    by_date = {}
    for _, d, pred, lab in panel_rows:
        by_date.setdefault(pd.Timestamp(d), []).append((pred, lab))
    names = ("valid", "no_panel_rows", "lt_min_rows", "constant", "nonfinite_input",
             "unexplained_missing_ic")
    cats = {k: [] for k in names}
    n_per_date = {}
    for s in dates:
        rows = by_date.get(s, [])
        n_per_date[str(s.date())] = len(rows)
        ic = ic_by_date.get(str(s.date()))
        values = [float(v) for r in rows for v in r]
        if not rows:
            cats["no_panel_rows"].append(s)
        elif len(rows) < IC_MIN_ROWS:
            cats["lt_min_rows"].append(s)
        elif np.std([r[0] for r in rows]) <= 0 or np.std([r[1] for r in rows]) <= 0:
            cats["constant"].append(s)
        elif not all(math.isfinite(v) for v in values):
            cats["nonfinite_input"].append(s)
        elif ic is not None and math.isfinite(ic):
            cats["valid"].append(s)
        else:
            cats["unexplained_missing_ic"].append(s)
    valid = {str(s.date()) for s in cats["valid"]}
    anomalies = {
        "unexplained_missing_ic": [str(s.date()) for s in cats["unexplained_missing_ic"]],
        "unexplained_extra_ic": sorted(set(ic_by_date) - valid),
        "nonfinite_ic_value": sorted(d for d, v in ic_by_date.items() if not math.isfinite(v)),
    }
    complete = sum(len(v) for v in cats.values()) == len(dates)
    valid_ics = [ic_by_date[d] for d in sorted(valid)]
    if not complete or any(anomalies.values()):
        verdict = FAIL
    else:
        verdict = PASS if valid_ics else EMPTY
    return {
        "counts": {k: len(v) for k, v in cats.items()},
        "accounting_complete": complete,
        "anomalies": anomalies,
        "verdict": verdict,
        "valid_dates": sorted(valid),
        "mean_ic_equal_weight": (float(np.mean(valid_ics)) if valid_ics else None),
        "n_per_date": n_per_date,
    }


# ----------------------------------------------------------------------
# Orchestration (no fza import in this process)
# ----------------------------------------------------------------------
def git_commit(ref: str) -> str:
    return subprocess.run(["git", "-C", str(REPO), "rev-parse", "--verify", f"{ref}^{{commit}}"],
                          check=True, capture_output=True, text=True).stdout.strip()


def export_source(sha: str, dest: Path) -> Path:
    tar = subprocess.run(["git", "-C", str(REPO), "archive", "--format=tar", sha, "src"],
                         check=True, capture_output=True).stdout
    with tarfile.open(fileobj=io.BytesIO(tar)) as archive:
        archive.extractall(dest, filter="data")
    return dest / "src"


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def worker(mode: str, src: Path, args: list[str], log: Path) -> None:
    env = {**os.environ, "PYTHONPATH": str(src), "FZA_DIAG_EXPECTED_SRC": str(src)}
    with open(log, "w", encoding="utf-8") as out:
        proc = subprocess.run([sys.executable, str(Path(__file__).resolve()), mode, *args],
                              env=env, cwd=str(log.parent), stdout=out, stderr=subprocess.STDOUT)
    if proc.returncode != 0:
        raise RuntimeError(f"{mode} worker failed (exit {proc.returncode}); see {log}")


def collect(workdir: Path, scenario: str, reference: str | None = None) -> dict:
    """Prepare the synthetic database, run both versions, return observations."""
    # Absolute, because workers run with the work directory as cwd: a relative
    # PYTHONPATH would silently miss the export and fall back to an installed fza.
    workdir = Path(workdir).resolve()
    workdir.mkdir(parents=True, exist_ok=False)
    t0 = time.perf_counter()
    obs = {"scenario": scenario, "workdir": str(workdir), "interpreter": sys.executable,
           "python": sys.version.split()[0], "versions": {}, "timings_s": {}}
    tags = {}
    for label, sha in VERSIONS.items():
        tags[label] = git_commit(label)
        if tags[label] != sha:
            raise RuntimeError(f"{label} resolves to {tags[label]}, expected {sha}")
    obs["tag_commits"] = tags
    srcs = {label: export_source(sha, workdir / f"src-{label}") for label, sha in VERSIONS.items()}
    db = workdir / "synthetic.duckdb"
    worker("worker-build", srcs[BUILDER], ["--db", str(db), "--scenario", scenario],
           workdir / "build.log")
    if Path(str(db) + ".wal").exists():
        raise RuntimeError("write-ahead log left after build; database not closed cleanly")
    hashes = {"after_build": sha256(db)}
    import duckdb  # the orchestrator reads the synthetic file read-only, without fza

    con = duckdb.connect(str(db), read_only=True)
    try:
        prices = con.execute("SELECT ticker, trade_date, close_adj FROM prices").df()
    finally:
        con.close()
    dates = request_dates()
    expect = expectations(prices, dates)
    obs.update(expect=expect, dates=dates, builder=BUILDER)
    hashes["before_compare"] = sha256(db)
    obs["timings_s"]["prepare"] = round(time.perf_counter() - t0, 2)
    obs["hashes"], obs["reference"] = hashes, reference
    if expect["s0_violations"]:
        return obs
    # S1 gate: no compute worker runs against a file whose identity is in doubt.
    if check_s1(hashes, reference)["verdict"] != PASS:
        obs["s1_gate"] = "failed_before_compare"
        return obs
    dates_file = workdir / "request_dates.json"
    dates_file.write_text(json.dumps([str(s.date()) for s in dates]))
    raw, panels = {}, {}
    for label, src in srcs.items():
        t1 = time.perf_counter()
        out = workdir / f"compute-{label}.json"
        worker("worker-compute", src, ["--db", str(db), "--dates", str(dates_file),
                                       "--out", str(out)], workdir / f"compute-{label}.log")
        result = json.loads(out.read_text())
        obs["versions"][label] = {"sha": VERSIONS[label], **result["provenance"]}
        raw[label], panels[label] = result["raw"], result["panel"]
        obs["timings_s"][f"compute_{label}"] = round(time.perf_counter() - t1, 2)
    hashes["after_compare"] = sha256(db)
    obs.update(raw=raw, panels=panels)
    if check_s1(hashes, reference)["verdict"] != PASS:
        obs["s1_gate"] = "failed_after_compare"
        return obs  # no IC on outputs from a file that changed
    # Descriptive IC with each version's own function: own panel and common keys.
    ic = {}
    for label, src in srcs.items():
        payload = {}
        for factor in FACTORS:
            other = NEW if label == OLD else OLD
            common = ({(t, d) for t, d, *_ in panels[label][factor]}
                      & {(t, d) for t, d, *_ in panels[other][factor]})
            own = panels[label][factor]
            payload[factor] = {"own": own, "common": [r for r in own if (r[0], r[1]) in common]}
        inp, out = workdir / f"ic-in-{label}.json", workdir / f"ic-{label}.json"
        inp.write_text(json.dumps(payload))
        worker("worker-ic", src, ["--panels", str(inp), "--out", str(out)],
               workdir / f"ic-{label}.log")
        ic[label] = json.loads(out.read_text())
    obs["ic"] = ic
    obs["timings_s"]["total"] = round(time.perf_counter() - t0, 2)
    return obs


def evaluate(obs: dict) -> dict:
    """Verdicts S0-S5 and the IC accounting, from (copies of) observations."""
    expect, dates = obs["expect"], obs["dates"]
    report = {"S0": check_s0(expect), "S1": check_s1(obs["hashes"], obs.get("reference"))}
    if report["S0"]["verdict"] != PASS:
        blocked = "S0 failed; expectations undefined"
    elif report["S1"]["verdict"] != PASS:
        blocked = "S1 failed; database identity not established"
    elif "raw" not in obs or "ic" not in obs:
        blocked = "outputs not collected"
    else:
        blocked = None
    if blocked:
        for name in ("S2", "S3", "S4", "S5", "IC"):
            report[name] = {"verdict": NOT_RUN, "reason": blocked}
        return report
    report["S2"] = check_s2(expect, obs["raw"])
    report["S3"] = check_s3(expect, obs["raw"])
    report["S4"] = check_s4(expect, obs["raw"], dates)
    report["S5"] = check_s5(obs["panels"])
    ic = {}
    for label in (OLD, NEW):
        ic[label] = {}
        for factor in FACTORS:
            own = obs["panels"][label][factor]
            other = obs["panels"][NEW if label == OLD else OLD][factor]
            common_keys = {(t, d) for t, d, *_ in own} & {(t, d) for t, d, *_ in other}
            ic[label][factor] = {
                "own_sample": classify_dates(own, obs["ic"][label][factor]["own"], dates),
                "common_scoring_keys": classify_dates(
                    [r for r in own if (r[0], r[1]) in common_keys],
                    obs["ic"][label][factor]["common"], dates),
            }
    for factor in FACTORS:
        a = set(ic[OLD][factor]["common_scoring_keys"]["valid_dates"])
        b = set(ic[NEW][factor]["common_scoring_keys"]["valid_dates"])
        shared = sorted(a & b)
        means = {}
        for label in (OLD, NEW):
            vals = [obs["ic"][label][factor]["common"][d] for d in shared]
            means[label] = float(np.mean(vals)) if vals else None
        ic[f"shared_valid_dates:{factor}"] = {
            "note": "separate view on dates valid in both versions; not a paired test",
            "n_dates": len(shared), "mean_ic": means,
            "valid_date_sets_differ": a != b}
    ic["verdict"] = combine(ic[label][factor][sample]["verdict"] for label in (OLD, NEW)
                            for factor in FACTORS
                            for sample in ("own_sample", "common_scoring_keys"))
    report["IC"] = ic
    return report


def run_synthetic(workdir: Path, scenario: str = "positive", reference: str | None = None):
    obs = collect(workdir, scenario, reference)
    report = evaluate(obs)
    summary = {
        "scenario": scenario, "verdicts": {k: report[k]["verdict"] for k in CHECKS},
        "s1_gate": obs.get("s1_gate"),
        "versions": obs["versions"], "tag_commits": obs["tag_commits"],
        "interpreter": obs["interpreter"], "python": obs["python"], "builder": obs["builder"],
        "hashes": obs["hashes"], "timings_s": obs["timings_s"],
        "protocol_note": "compute_factor also ran run_protocol; its results are not used",
        "report": report,
    }
    (workdir / "report.json").write_text(json.dumps(summary, indent=2, default=str))
    return obs, report


# ----------------------------------------------------------------------
# Workers (run inside one version's subprocess; import fza here only)
# ----------------------------------------------------------------------
def _import_fza():
    import fza

    expected = Path(os.environ["FZA_DIAG_EXPECTED_SRC"]).resolve()
    actual = Path(fza.__file__).resolve()
    if expected not in actual.parents:
        raise RuntimeError(f"imported fza from {actual}, expected under {expected}")
    return fza


def _provenance(fza) -> dict:
    from importlib.metadata import version

    deps = {}
    for name in ("pandas", "numpy", "scipy", "duckdb", "statsmodels", "pyyaml"):
        try:
            deps[name] = version(name)
        except Exception as exc:  # recorded, not hidden
            deps[name] = f"unavailable: {type(exc).__name__}"
    return {"fza_file": str(Path(fza.__file__).resolve()), "executable": sys.executable,
            "python": sys.version.split()[0], "dependencies": deps}


def worker_build(db: str, scenario: str) -> None:
    _import_fza()
    from fza.store import Store

    securities, prices = synthetic_tables(scenario)
    with Store(db) as store:
        store.con.register("sec_df", securities)
        store.con.execute("INSERT INTO securities (cik, ticker, first_filing, last_filing) "
                          "SELECT cik, ticker, first_filing, last_filing FROM sec_df")
        store.con.register("px_df", prices)
        store.con.execute("INSERT INTO prices (ticker, trade_date, close, close_adj) "
                          "SELECT ticker, trade_date, close, close_adj FROM px_df")


def worker_compute(db: str, dates_file: str, out: str) -> None:
    fza = _import_fza()
    from fza.factors.registry import load_all
    from fza.pipeline.run import compute_factor
    from fza.store import Store

    dates = pd.DatetimeIndex(json.loads(Path(dates_file).read_text()))
    registry = load_all()
    result = {"provenance": _provenance(fza), "raw": {}, "panel": {}}
    store = Store(db, read_only=True)
    try:
        for factor in FACTORS:
            raw = registry[factor].compute(store, dates)
            result["raw"][factor] = [[t, str(pd.Timestamp(d).date()), float(v)] for t, d, v in
                                     zip(raw["ticker"], raw["signal_date"], raw["value"],
                                         strict=True)]
            run = compute_factor(registry[factor], store, dates, **PIPELINE)
            p = run.panel
            result["panel"][factor] = [
                [t, str(pd.Timestamp(d).date()), float(x), float(y)] for t, d, x, y in
                zip(p["ticker"], p["signal_date"], p["prediction"], p["label"], strict=True)]
    finally:
        store.close()
    Path(out).write_text(json.dumps(result))


def worker_ic(panels_file: str, out: str) -> None:
    _import_fza()
    from fza.pipeline.protocol import information_coefficient

    payload = json.loads(Path(panels_file).read_text())
    result = {}
    for factor, sets in payload.items():
        result[factor] = {}
        for name, rows in sets.items():
            frame = pd.DataFrame(rows, columns=["ticker", "signal_date", "prediction", "label"])
            frame["signal_date"] = pd.to_datetime(frame["signal_date"])
            series = information_coefficient(frame) if len(frame) else pd.Series(dtype=float)
            result[factor][name] = {str(pd.Timestamp(d).date()): float(v)
                                    for d, v in series.items()}
    Path(out).write_text(json.dumps(result))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    sub = ap.add_subparsers(dest="mode", required=True)
    s = sub.add_parser("synthetic", help="prepare a synthetic database and compare both versions")
    s.add_argument("--workdir", type=Path, required=True)
    s.add_argument("--scenario", default="positive",
                   choices=("positive", "zero_latest", "overflow"))
    s.add_argument("--reference-sha256", default=None)
    b = sub.add_parser("worker-build")
    b.add_argument("--db", required=True)
    b.add_argument("--scenario", required=True)
    c = sub.add_parser("worker-compute")
    c.add_argument("--db", required=True)
    c.add_argument("--dates", required=True)
    c.add_argument("--out", required=True)
    i = sub.add_parser("worker-ic")
    i.add_argument("--panels", required=True)
    i.add_argument("--out", required=True)
    args = ap.parse_args(argv)
    if args.mode == "worker-build":
        worker_build(args.db, args.scenario)
    elif args.mode == "worker-compute":
        worker_compute(args.db, args.dates, args.out)
    elif args.mode == "worker-ic":
        worker_ic(args.panels, args.out)
    else:
        _, report = run_synthetic(args.workdir, args.scenario, args.reference_sha256)
        verdicts = {k: report[k]["verdict"] for k in CHECKS}
        print(json.dumps(verdicts))
        return 0 if all(v == PASS for v in verdicts.values()) else 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
