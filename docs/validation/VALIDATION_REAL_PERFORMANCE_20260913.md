# Fixed-real-input timing and power-state evidence

## Outcome and limits

The six planned workers completed with exit 0. In every worker, the serialized
VintageComparison matched exactly between plain and wrapped execution. This
does not assert raw-panel identity or certify research claims. All six recorded
environments and input hashes match. Production factor/runner code is unchanged.

The historical 9.93x wall-time ratio is not a controlled algorithm-speed ratio.
Newly inspected Windows sleep/wake records overlap **106611.126393 seconds
(29.6142 hours)** of the newer 41.6791-hour run. Nine recorded intervals account
for this overlap; the earlier run window has no overlapping events of that class
in the queried log. This is positive evidence of a major wall-time confound,
not a complete accounting of process execution, overhead or all waiting time.
Do not label the remaining elapsed time after subtraction as active compute time.

## Frozen protocol and observations

See PERFORMANCE_REAL_INPUT_PLAN.md, written before measurement. First 20
us-gaap names ordered ticker/cik, all stored price and fundamental history,
ep_ratio, twelve 2018 month ends, locked environment. Source data hash:
`66c60785d1c085d4883f49796a33f20ad2bdf418072086fbfd938100666312d9`.
Subset hash: `26f45287116cd6004afadcbc095936e44cfe7b68ef47514a1e42d1b363c09603`.
Counts: 20 securities, 72893 prices, 23511 fundamental rows.

Each worker warmed up once, ran plain, then wrapped. Order was old/new,
new/old, old/new, with no replacement runs. All observed seconds are retained:

| Trial | Anchor | Plain wall | Plain CPU | Wrapped wall |
|---|---|---:|---:|---:|
| 0 | 0bd03bf | 22.4441 | 22.3281 | 24.2037 |
| 1 | de1e836 | 4061.3299 | 37.0938 | 28.1074 |
| 2 | de1e836 | 18.3669 | 18.4688 | 18.6456 |
| 3 | 0bd03bf | 17.3563 | 17.7500 | 21.7971 |
| 4 | 0bd03bf | 26.9527 | 27.0938 | 25.1215 |
| 5 | de1e836 | 28.1474 | 28.3281 | 37.2033 |

Trial 1 is power-state contaminated, NOT a valid code-speed observation:
Kernel-Power record 13952 reports Modern Standby entry at
2026-09-13T01:53:10.9807365+01:00 and record 13970 reports exit at
2026-09-13T03:00:23.1389159+01:00. It was retained, not silently discarded.
The roughly 67-minute interval is consistent with the anomalous wall/CPU gap.
Phase durations, not absolute phase timestamps, were captured by this harness;
future instrumentation should retain both. Do not infer exact suspended process
time from this interval or generalize one contaminated observation to all runs.

All-observation wall medians: old 22.4441 s, new 28.1474 s. Ranges:
old 17.3563–26.9527 s, new 18.3669–4061.3299 s. Paired new-minus-old:
4038.8859 s (contaminated), 1.0106 s, 1.1948 s. These three pairs do not
establish a stable speed ratio. No additional trials were selected post hoc.
Brief wrapper tests/static checks and read-only diagnostics also ran on the
host during the experiment; the host was not isolated from competing activity.

## Stages actually observed

All six traces record 331 TTM-value calls, with identical per-call input-row
count sequences (18732 input rows in aggregate). They do not hash the contents
of those intermediate frames; equal row counts do not establish equal work.
Each worker has two TTM-panel calls, not one per diagnostic layer.

Wrapped TTM-panel inclusive totals, in trial order:
23.4018, 26.9419, 17.4774, 21.1855, 24.3022, 35.6236 seconds.
They overlap compute_factor and history-read spans and must not be added to them.
The new diagnostic_layers spans are 0.4635, 0.4303, 0.6556 seconds. They include
new cleaning/label/scoring work and are not extra TTM formula invocations.
Wrapped timings retain instrumentation overhead and run-to-run variability;
they cannot supply causal production percentages. No namedtuple optimization
or cache was implemented on the basis of these observations.

The four shared top-level IC/Sharpe fields are identical across these six
outputs; both Sharpe fields are unavailable (null). Thus this small subset
does not exercise a fully populated long-short scoring workload. Full vintage
objects differ across versions because the newer code adds diagnostics.
This is one factor and one bounded grid, not the full selected-200 pipeline.

## Durable evidence

- PERFORMANCE_REAL_INPUT_RESULTS_20260913.json: all six timings, stage counts,
  environments, input/harness hashes and hashes of the underlying result files.
- PERFORMANCE_POWER_EVIDENCE_20260913.json: original run windows and the nine
  overlapping sleep/wake events with UTC times and Windows record IDs.
- Local detailed artifacts: .diagnostic-envs/real-stage-0913, including source
  exports, subset, inputs.json, six result JSONs, flushed traces and raw selected
  power-event records. No historical report file was overwritten.

Modern Standby 506/507 overlap was also counted (old 1117.502790 s; new
20809.925571 s). These are a different event class and may overlap sleep/wake
intervals: do not add the two totals. No absence-of-events claim proves the
absence of every kind of system suspension or resource contention.

## Verification and next step

Three new wrapper tests pass (zero failures/errors/skips), XML:
.diagnostic-envs/real-stage-tests.xml. Static checks pass for all four scripts
and this test module. The previous whole-suite 281-pass evidence is not a new
whole-suite run covering these additions. The scripts' comparisons are diagnostic
observations, not new regression assertions against historical outputs.

The legacy Windows PowerShell subprocess could not complete the event query;
the available pwsh runtime succeeded. No power settings were changed. No
commits or pushes were performed in this batch.

Next: retain phase UTC timestamps and power-state context in future measurements,
and separate elapsed waiting from compute diagnostics before selecting any
optimization. An explicitly controlled awake-host run could test remaining
uncertainty; it must not replace or sanitize the observations above. This batch
does not justify either claiming a tenfold code regression or claiming all
historical runtime differences are now explained.

## Subsequent checkpoint preparation — 2026-09-13

Before committing this accumulated work, the locked environment passed 14
targeted tests from test_stage_probe, test_real_stage_worker and test_render;
zero failures/errors/skips, XML at .diagnostic-envs/precommit-0913.xml.
This is not a new full-suite run. Static checks on diagnostic scripts and
their tests passed. The staged file list excludes data/, .diagnostic-envs/
and database files.

Because this checkout enables core.autocrlf, .gitattributes now disables text
conversion only for the six new archived JSON/TXT files. Their staged blobs
were compared byte-for-byte with disk and all matched. The two centered report
title lines intentionally retain their trailing spaces; trimming them to silence
diff --check would alter the archived evidence. Original archives are unchanged.
