"""Check a run_vintage_series.py output against the archive, then t-statistics.

Stdlib only; reads two JSON files and writes nothing.

1. For each layer and arm: recomputed ic_mean / n_dates / IC date list vs
   examples/outputs/b_selected_200_rerun_20260909/demo_run.json
   (vintage_comparisons.<factor>.detail.layers.<layer>.{pit,restated}.ic_mean,
    .metrics.ic.{pit,restated}_dates), and recomputed ic_gap vs archived ic_gap.
2. For original-process and common-observation: per-date d_t = IC_restated - IC_pit
   on identical dates; simple t = mean / (s / sqrt(n)) with s using n-1;
   Newey-West t with Bartlett weights, lag 5, autocovariances divided by n;
   approximate minimum detectable difference MDE = 2.8 * s / sqrt(n)
   (two-sided 5%, 80% power; 2.8 ~ 1.96 + 0.84; ignores autocorrelation).

    python -I scripts/research_note/check_vintage_series.py <factor>_series.json
        [--archive <demo_run.json>] [--lag 5]
"""

import argparse
import json
import math
from pathlib import Path

ARCHIVE = (Path(__file__).resolve().parents[2] / "examples" / "outputs"
           / "b_selected_200_rerun_20260909" / "demo_run.json")
MDE_Z = 2.8
LAYERS = ("original-process", "common-observation", "common-support")
T_LAYERS = ("original-process", "common-observation")
EXACT = 1e-12


def simple_t(x):
    n = len(x)
    m = sum(x) / n
    s = math.sqrt(sum((v - m) ** 2 for v in x) / (n - 1))
    return m / (s / math.sqrt(n))


def newey_west_t(x, lag):
    n = len(x)
    m = sum(x) / n
    e = [v - m for v in x]
    gamma = [sum(e[t] * e[t - k] for t in range(k, n)) / n for k in range(lag + 1)]
    lrv = gamma[0] + 2 * sum((1 - k / (lag + 1)) * gamma[k] for k in range(1, lag + 1))
    return m / math.sqrt(lrv / n)


def selftest():
    x = [1.0, 2.0, 3.0, 4.0]  # hand-computed: gamma0 = 1.25, gamma1 = 0.3125
    assert abs(newey_west_t(x, 0) - 2.5 / math.sqrt(1.25 / 4)) < 1e-12
    assert abs(newey_west_t(x, 1) - 4.0) < 1e-12           # lrv = 1.5625
    assert abs(simple_t(x) - 2.5 / math.sqrt((5 / 3) / 4)) < 1e-12


def main():
    selftest()
    ap = argparse.ArgumentParser()
    ap.add_argument("run_json", type=Path)
    ap.add_argument("--archive", type=Path, default=ARCHIVE)
    ap.add_argument("--lag", type=int, default=5)
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

    print(f"\n2. Per-date IC gap d_t = IC_restated - IC_pit; NW lag {args.lag}")
    for layer in T_LAYERS:
        p, r = series[f"{layer}/pit"], series[f"{layer}/restated"]
        if p["dates"] != r["dates"]:
            print(f"  {layer}: PIT and restated IC dates differ "
                  f"({len(p['dates'])} vs {len(r['dates'])}); t-statistics withheld")
            continue
        d = [b - a for a, b in zip(p["ic"], r["ic"], strict=True)]
        n = len(d)
        mean = sum(d) / n
        sd = math.sqrt(sum((v - mean) ** 2 for v in d) / (n - 1))
        print(f"  {layer:19s} n {n} | mean {mean:+.6f} | sd {sd:.6f} | "
              f"simple t {simple_t(d):+.3f} | NW({args.lag}) t "
              f"{newey_west_t(d, args.lag):+.3f} | MDE {MDE_Z * sd / math.sqrt(n):.6f} | "
              f"mean vs recomputed ic_gap diff {mean - run['layer_ic_gap'][layer]:+.1e}")


if __name__ == "__main__":
    main()
