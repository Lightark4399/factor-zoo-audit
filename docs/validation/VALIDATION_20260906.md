# Validation — AS-03 and B diagnostic delivery

Status: INTERRUPTED; no final full-suite XML or selected-200 report was produced.
Focused checks below are prior-snapshot results, not current full acceptance.
See `VALIDATION_20260907.md` for the replacement run. This is not hosted CI.
Baseline: `2bf5aa0`; AS-03 isolated fix: `36071e9`.

## Counts and scope

The previous complete suite had 201 cases. This stage collects 220: nine dataset
qualification cases, seven real-store demo cases, and three serialization/gate
cases were added. No tests were deleted or renamed. The original 14 demo cases
remain, with structured-output assertions added to the saved-report case.

| Check | Research lock (Python 3.12.14 / pandas 3.0.5) | Minimum (Python 3.10.21 / pandas 2.0.0) |
|---|---|---|
| AS-03 focused cases | 16 passed, 17.641 s | 16 passed, 25.070 s |
| B focused cases | 19 passed, 13.251 s | 19 passed, 14.862 s |
| Final `pytest tests -v --durations=5` | Pending | Pending |
| Installed-wheel report smoke, isolated imports | Passed | Passed |

The first AS-03 attempt failed at pytest's default system temporary directory,
before running an assertion. It is not a red reproduction or a passing run.
All successful tests used new named basetemp directories under `.diagnostic-envs`.
Full-run captures are `b-full-locked-20260906.xml` and
`b-full-minimum-20260906.xml` there. The two full suites and real report overlap;
their elapsed times are not a pandas performance comparison.

## What was verified

- Real-store stdout and saved text stay diagnostic for missing, malformed,
  wrongly typed and explicitly false/true declarations. A populated synthetic
  SQL store exercises genuine factor calculations and vintage comparisons;
  transport tests do not substitute a helper for the real CLI entry point.
- Binding/mismatch/WAL and unreadable-sidecar cases cannot promote research.
  Current sidecars have no DB hash and are explicitly UNVERIFIED bindings.
- Completed structured records preserve stage-count identities and existing
  metrics; failed factors retain null protocols, not fabricated zero results.
- Fixture specifications, stored roster, explicit date/configuration choices,
  source byte hashes, implementation hashes and runtime travel with the bundle.
- Nonfinite numbers serialize to JSON null; observed zero remains zero.
- Unimplemented research gates are explicit and never marked passed.

Final source lint and whitespace checks are recorded at completion. No factor,
membership, missing-price or terminal-return formula was changed in this stage.
Explicit protocol settings equal the existing defaults. The quick max-dates
option still subsamples; its output now warns that formation shifts then count
selected dates, so it is not definition-equivalent to the full grid.

## Installed artifact

Built a wheel without network/build isolation, installed it into a fresh local
target with `--no-index --no-deps`, and invoked both runtimes with `-I`. The smoke
asserted imports from that installed target, then ran a real empty-store report
through all three output artifacts. It exercised SQL/cards/lock and the new
reporting module. Existing environment dependencies were reused; this was not a
fresh dependency resolution or a hosted CI run.

Both installed runs reported implementation hash
`7a1bd22a3d0922a9f3f7f60f47c17bcaa36015874e61b76224f8d5f9101849f8`.
The lock run correctly reports MATCHED; the minimum correctly reports MISMATCH.
The four-package lock hash is
`3014091ea5f7c2b51f3a1d867a674a65be84bf2d8e27348ad6b7b7e512df99f3`.
Python itself is observed separately, not part of that MATCHED comparison.

## Selected 200-company report

The run uses existing `data/fza_200.duckdb` read-only, all 185 available monthly
signal dates (2011-04-30 through 2026-08-31), no max-dates subsampling. No ingest
or provider access was attempted. The runtime needed a local editable install
(`--no-index --no-deps --no-build-isolation`) because pytest's source-path setup
alone did not make `python -m fza.demo` importable; the first CLI import failure
produced no report and is not counted as a successful run.

Database SHA-256 before the run:
`66c60785d1c085d4883f49796a33f20ad2bdf418072086fbfd938100666312d9`.
Sidecar SHA-256:
`718a03dd30f80a20366623ebdaeea237a2141230f9eef1123aa52545914790b4`.
The source declares diagnostic_scale, research_evidence false, and a
survivorship-prone source share of 1.0. That is not a quantified bias magnitude.
Final report/artifact integrity checks will be recorded at completion.

## Remaining boundaries

AS-03 closes qualification propagation for current demo exits. It does not
validate historical membership, resolve terminal outcomes, certify any factor
survival claim, or integrate backtest-audit. Exit-component and horizon-extension
design revisions are documented only. Data entitlement remains a user decision.
Sibling checks are scoped to the local revision recorded in CROSS_REPO_AUDIT.md.
