"""Check a run_vintage_series.py output against the archive, then t-statistics.

Stdlib only; reads two JSON files and writes nothing.

1. For each layer and arm: recomputed ic_mean / n_dates / IC date list vs
   examples/outputs/b_selected_200_rerun_20260909/demo_run.json
   (vintage_comparisons.<factor>.detail.layers.<layer>.{pit,restated}.ic_mean,
    .metrics.ic.{pit,restated}_dates), and recomputed ic_gap vs archived ic_gap.
2. For original-process and common-observation: per-date d_t = IC_restated - IC_pit
   on identical dates; simple t = mean / (s / sqrt(n)) with s using n-1;
   Newey-West t with Bartlett weights, autocovariances divided by n, at lags
   0, 3, 5 and 12 (main lag 5); SE_NW = sqrt(long-run variance / n) at lag 5
   (= |mean| / |NW(5) t|); p-values from NW(5) t under a standard normal
   approximation, two-sided and one-sided (H1: mean > 0); approximate minimum
   detectable difference MDE = 2.8 * SE_NW (two-sided 5%, 80% power;
   2.8 ~ 1.96 + 0.84; normal approximation).

    python -I scripts/research_note/check_vintage_series.py <factor>_series.json
        [--archive <demo_run.json>]
"""

import argparse
import json
import math
from pathlib import Path
from statistics import NormalDist

ARCHIVE = (Path(__file__).resolve().parents[2] / "examples" / "outputs"
           / "b_selected_200_rerun_20260909" / "demo_run.json")
MDE_Z = 2.8
LAGS = (0, 3, 5, 12)
MAIN_LAG = 5
N_TESTS = 8  # four factors x two layers (original-process, common-observation)
ALPHA = 0.05
LAYERS = ("original-process", "common-observation", "common-support")
T_LAYERS = ("original-process", "common-observation")
EXACT = 1e-12
Z = NormalDist()


def simple_t(x):
    n = len(x)
    m = sum(x) / n
    s = math.sqrt(sum((v - m) ** 2 for v in x) / (n - 1))
    return m / (s / math.sqrt(n))


def newey_west_se(x, lag):
    n = len(x)
    m = sum(x) / n
    e = [v - m for v in x]
    gamma = [sum(e[t] * e[t - k] for t in range(k, n)) / n for k in range(lag + 1)]
    lrv = gamma[0] + 2 * sum((1 - k / (lag + 1)) * gamma[k] for k in range(1, lag + 1))
    return math.sqrt(lrv / n)


def newey_west_t(x, lag):
    return (sum(x) / len(x)) / newey_west_se(x, lag)


def p_two_sided(t):
    return 2 * (1 - Z.cdf(abs(t)))


def p_one_sided_positive(t):
    return 1 - Z.cdf(t)


def gap_stats(series, layer):
    """Per-date gap statistics for one layer, or None if the date lists differ."""
    p, r = series[f"{layer}/pit"], series[f"{layer}/restated"]
    if p["dates"] != r["dates"]:
        return None
    d = [b - a for a, b in zip(p["ic"], r["ic"], strict=True)]
    n = len(d)
    mean = sum(d) / n
    se = newey_west_se(d, MAIN_LAG)
    t = mean / se
    return {
        "n": n, "mean": mean,
        "sd": math.sqrt(sum((v - mean) ** 2 for v in d) / (n - 1)),
        "simple_t": simple_t(d),
        "nw_t": {lag: newey_west_t(d, lag) for lag in LAGS},
        "se_nw": se, "mde": MDE_Z * se,
        "p_two": p_two_sided(t), "p_one": p_one_sided_positive(t),
    }


def selftest():
    x = [1.0, 2.0, 3.0, 4.0]  # hand-computed: gamma0 = 1.25, gamma1 = 0.3125
    assert abs(newey_west_t(x, 0) - 2.5 / math.sqrt(1.25 / 4)) < 1e-12
    assert abs(newey_west_t(x, 1) - 4.0) < 1e-12           # lrv = 1.5625
    assert abs(newey_west_se(x, 1) - 0.625) < 1e-12        # sqrt(1.5625 / 4)
    assert abs(simple_t(x) - 2.5 / math.sqrt((5 / 3) / 4)) < 1e-12
    assert abs(p_two_sided(-1.959963984540054) - 0.05) < 1e-12
    assert abs(p_one_sided_positive(1.6448536269514722) - 0.05) < 1e-12
    assert abs(p_one_sided_positive(-1.6448536269514722) - 0.95) < 1e-12


def main():
    selftest()
    ap = argparse.ArgumentParser()
    ap.add_argument("run_json", type=Path)
    ap.add_argument("--archive", type=Path, default=ARCHIVE)
    args = ap.parse_args()

    run = json.load(open(args.run_json, encoding="utf-8"))
    factor = run["factor"]
    arch = json.load(open(args.archive, encoding="utf-8"))
    layers = arch["vintage_comparisons"][factor]["detail"]["layers"]
    series = run["series"]
    print(f"factor {factor}; run {args.run_json.name}")
    print(f"db sha256 before/after: {run['db_sha256_before'][:12]} / {run['db_sha256_after'][:12]}")
    print(f"archive {args.archive.parent.name}/{args.archive.name}\n")

    print("1. Recomputed vs archive (diff = recomputed - archived; "
          f"'exact' means |diff| <= {EXACT:g})")
    for layer in LAYERS:
        a = layers[layer]
        for arm in ("pit", "restated"):
            r = series[f"{layer}/{arm}"]
            archived = a[arm]["ic_mean"]
            diff = r["ic_mean"] - archived
            dates_same = r["dates"] == a["metrics"]["ic"][f"{arm}_dates"]
            print(f"  {layer:19s} {arm:8s} archived {archived:+.10f} recomputed "
                  f"{r['ic_mean']:+.10f} diff {diff:+.3e} "
                  f"{'exact' if abs(diff) <= EXACT else 'DIFFERS'} | n_dates "
                  f"{a[arm]['n_dates']}->{r['n_dates']} | n_obs "
                  f"{a[arm]['n_observations']}->{r['n_observations']} | "
                  f"IC dates identical to archive: {dates_same}")
        gap_diff = run["layer_ic_gap"][layer] - a["ic_gap"]
        print(f"  {layer:19s} ic_gap   archived {a['ic_gap']:+.10f} recomputed "
              f"{run['layer_ic_gap'][layer]:+.10f} diff {gap_diff:+.3e} "
              f"{'exact' if abs(gap_diff) <= EXACT else 'DIFFERS'}")

    a_b = ALPHA / N_TESTS
    print(f"\n2. Per-date IC gap d_t = IC_restated - IC_pit; main lag {MAIN_LAG}; "
          "p from NW(5) t, normal approximation; one-sided H1: mean > 0")
    print(f"   Bonferroni over {N_TESTS} tests: p < {a_b:g}; "
          f"|t| > {Z.inv_cdf(1 - a_b / 2):.3f} two-sided, t > {Z.inv_cdf(1 - a_b):.3f} one-sided")
    for layer in T_LAYERS:
        s = gap_stats(series, layer)
        if s is None:
            print(f"  {layer}: PIT and restated IC dates differ; t-statistics withheld")
            continue
        nw = " ".join(f"NW({lag}) t {s['nw_t'][lag]:+.3f} |" for lag in LAGS)
        print(f"  {layer:19s} n {s['n']} | mean {s['mean']:+.6f} | sign "
              f"{'+' if s['mean'] > 0 else '-' if s['mean'] < 0 else '0'} | sd {s['sd']:.6f} | "
              f"simple t {s['simple_t']:+.3f} | {nw} SE_NW(5) {s['se_nw']:.6f} | "
              f"MDE {s['mde']:.6f} | p two-sided {s['p_two']:.4f} | "
              f"p one-sided {s['p_one']:.4f} | mean vs recomputed ic_gap diff "
              f"{s['mean'] - run['layer_ic_gap'][layer]:+.1e}")


if __name__ == "__main__":
    main()
