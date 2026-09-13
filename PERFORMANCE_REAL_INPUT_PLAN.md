# Fixed-real-input comparison — frozen before measurement, 2026-09-13

DIAGNOSTIC_ONLY. This is not a reproduction of the historical 9.93x ratio.

- Anchors: 0bd03bf (old archive) and de1e836 (new archive), exported without
  changing the working tree. Same locked Python environment for both.
- Source: existing selected-200 database, opened read-only. Select the first
  20 us-gaap securities ordered by ticker, cik, without inspecting returns or
  timings. Retain all their price and filing history, including later revisions.
- Evaluation grid: the twelve calendar month ends of 2018. Factor: ep_ratio,
  chosen from the previously sampled TTM path, not from a return ranking.
- Defaults: no industry neutralisation, 21-session labels, execution lag 1,
  five quantiles. This subset is diagnostic, not an equivalent full-grid report.
- Snapshot the source DB hash, selected roster, subset DB hash, row counts,
  source commit and harness hash. No network acquisition or data-policy change.
- Six separate sequential workers: old/new, new/old, old/new. Each warms up
  once, then runs plain and stage-instrumented passes in that order. Three
  observations per version. Fixed pass order is a limitation; no causal estimate
  of instrumentation overhead is claimed.
- Use coarse function wrappers instead of the global Python profiling hook.
  Capture actual called stages, wall/process CPU, nesting and TTM call counts.
  JSONL entry/exit records flush immediately. Wrapper overhead remains present.
  A worker failure is recorded, not silently replaced by another selection.
- Within each worker, serialized comparison results must match plain versus
  instrumented. Between versions, added diagnostics are expected; no blanket
  result equality assertion. Raw-panel equivalence is not established here.

## Analysis rules

Report every repetition, medians and ranges, paired new-minus-old differences.
Do not sum inclusive parent and child times. Compare top-level elapsed times
separately from comparable stage times; stages absent in old code are identified
as added work. A ratio to a near-zero or sign-unstable total increment is not
interpretable. No post-hoc threshold will turn a noisy difference into a binary
attribution. Counts do not establish equal work per call. A stage association
does not isolate its cause. These measurements may fail to reproduce the old
slowdown; that outcome must be retained rather than optimized away.

No optimization, full 200-company rerun, historical-archive rewrite or research
qualification upgrade is included. Licensed-data access remains outside scope.
