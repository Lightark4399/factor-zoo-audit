# Validation record — 2026-09-05

Status: `COMPLETE / LOCAL_VALIDATION`; research release remains blocked.
Branch: `codex/fza-universe-wiring`; review baseline `0a2dde0`.
Implementation commits: `052d696` (demo/minimum-environment validation) and
`82b2e55` (assertion boundary and entry-point coverage).

## Test count reconciliation

| Point | demo | ingest | library | packaging | pipeline | registry contracts | store | Total |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Original main `361c3a9` | 14 | 49 | 45 | 1 | 27 | 0 | 23 | 159 |
| Prior-stage head `0a2dde0` | 14 | 49 | 55 | 2 | 37 | 0 | 23 | 180 |
| This review | 14 | 49 | 55 | 7 | 37 | 16 | 23 | 201 |

The previously reported 166 was `180 - 14`: five test files, excluding demo.
No test was deleted in this review. Five controlled provenance cases and
sixteen registry acceptance cases were added. Existing all-factor tests gained
membership/count assertions. The fourteen demo test names remain unchanged.

The demo tests share fresh executions within one pytest invocation (one full
window and two distinct six-date configurations). They do not read committed
output snapshots or mock factor computations. The full report also exercises
`--outdir`; its disclaimer and saved/console consistency are asserted.

## Reproductions and intermediate checks

- Original minimum packaging reproduction: **1 passed, 1 failed**; failure was
  the test requiring MATCHED from an intentionally mismatched environment.
- Corrected packaging tests: **7 passed** in each environment.
- Adversarial registry tests before correction: **15 failed, 1 passed**.
  The failures were all the intended rejection cases; the unverified-origin
  control passed. The runtime loader was corrected after the standalone demo
  run completed.
- Standalone locked demo: **14 passed in 741.93 s**. Full-window report setup
  took 527.32 s; the original 33 signal dates were retained.
- Locked complete run before the final demo frequency correction: **201 passed
  in 785.16 s**. This does not verify the later source edit.
- Minimum demo date test reproduced `ValueError: Invalid frequency: ME`.
  Corrected the remaining default argument to `pd.offsets.MonthEnd()` and
  extended its existing date test. Aborted the earlier minimum full run once
  this defect was isolated; that interrupted run is not counted as passing.
- Final `ruff check src tests` and `git diff --check` passed after the frequency
  default was extracted into the module constant.

## Final validation

Both complete test directories passed after the demo frequency correction.
There are no exit-policy changes in this source tree. Neither run had failures,
errors, or skipped tests; both include the original fourteen demo cases.

| Environment | Python | pandas | Command scope | Result |
|---|---|---|---|---|
| Research lock | 3.12.14 | 3.0.5 | `pytest tests -v --durations=10` | **201 passed**, 1343.33 s |
| Minimum supported | 3.10.21 | 2.0.0 | `pytest tests -v --durations=10` | **201 passed**, 1305.96 s |

Commands use a fresh, explicitly named `--basetemp` under `.diagnostic-envs`
and a `--junitxml` file for each run. The locked run sets numerical thread
variables `OPENBLAS_NUM_THREADS`, `OMP_NUM_THREADS`, and `MKL_NUM_THREADS` to 1.
After PowerShell startup stalled, the final minimum run was launched directly
through cmd.exe with its inherited thread settings. Neither run installs a
pandas compatibility shim. Stalled commands that never collected tests were
terminated; they are not counted as completed runs.

The final lint-only extraction of the MonthEnd default into a module constant
was checked with the existing date test in both environments (one pass each).
It does not change the offset or date calculation used by the full runs.

The two runs overlapped on this machine. Their elapsed times are validation
records, not a performance comparison between pandas versions.

Local JUnit captures (ignored diagnostic artifacts, not expected-value fixtures):

| Environment | Path under `.diagnostic-envs/` | SHA-256 |
|---|---|---|
| Research lock | `all-locked-final-20260905.xml` | `f256f89b674d4401ca5a5b3afed12603bfb18c95803f2fc79ed6705aa52002fe` |
| Minimum supported | `all-minimum-cmd-20260905.xml` | `ae93e9d5934d34ea262788daf2d00f0d73d53f62a7e4b09953c5befff2c0dc16` |

The lock environment now reports Python 3.12.14, not the previous run's
3.12.13. Python's observed version is recorded independently; the existing
MATCHED indicator compares the four numerical packages, not Python itself.
It must not be interpreted as a full environment identity check.

## Release and evidence limits

The final wheel was built and installed with `pip --no-index --no-deps --target`
into a new local directory. Both interpreters invoked a smoke script with `-I`,
explicitly adding only that installed package directory, and verified that
`fza` and `fza.demo` were imported from it. SQL, ten cards, the denominator,
research lock and the empty-store demo date path all passed. The locked runtime
reported MATCHED; the minimum runtime correctly reported all four mismatches.
Dependencies came from the two existing environments; this was an isolated
installed-package smoke, not a fresh dependency installation.

The installed `demo.py` SHA-256 was
`33ad18e0981a55a64eb53204e685834bf51b1c0fe371601fd23d1ff3ca9afcdd`.
CI now exercises these resource consumers in its clean-venv smoke as well.
No successful hosted CI run is claimed by this record.

Even a passing complete suite leaves AS-03 open: real-store demo output does
not yet consume diagnostic dataset provenance. The exit-policy draft remains
`AWAITING_USER_REVIEW`; no source subscription, historical ingest, terminal
return imputation, policy aggregation or backtest-audit bridge was implemented.

See [assertion audit](../../ASSERTION_SCOPE_AUDIT.md) and
[data/exit policy draft](../../DATA_EXIT_POLICY_DRAFT.md).
