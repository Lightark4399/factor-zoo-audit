# B acceptance and qualification projection — 2026-09-07

Status: IN PROGRESS. No full-suite or selected-200 completion claim yet.

## Pre-run expectations

This stage changes serialization, provenance and qualification projections, not
factor calculations. Source implementation hashes, policy fields, the new run
bundle and the text qualification lines should change. Given identical source
data, environment and full signal grid, raw/eligible/cleaned/label counts, IC,
portfolio statistics, denominator decisions and vintage differences must not
change because of reporting. Comparing an abbreviated grid with a full grid
does not test that expectation. Any unexpected numeric difference requires
investigation rather than updating a stored-output assertion.

The existing selected-200 DB must remain byte-identical; the report must retain
all 185 monthly dates. It is DIAGNOSTIC_ONLY, not research evidence. Missing
membership and terminal outcomes remain UNRESOLVED. No sample expansion,
terminal-return implementation or backtest-audit bridge is included in this run.

## Current checks

- Lint passed after the qualification projection changes.
- Focused projection, dataset binding, real CLI transport and reporting suites:
  22 passed in each environment, zero failures/errors/skips (JUnit parsed).
  Locked runtime 122.809 s, minimum 117.756 s; concurrent elapsed times are not
  a performance comparison.
- Full suites and full-grid archive: pending.
- Generic docs-quote scanner: pending upstream implementation; not duplicated.

The previous 220 collected tests were never claimed here as a completed run.
Three qualification projection cases were added; no cases removed or renamed.
The README managed block is checked against the policy source. A sentinel-label
test exercises stdout, saved text and both JSON outputs through the actual CLI;
the populated real-store fixture separately covers factor records. These tests
guard projection, not the truth of the underlying qualification decision.

Focused XML SHA-256:

- Locked: `ac2b6018a6aae8c0d889abe39c6c42ca1a736d0dea254dd00ff900cfa5a3d960`
- Minimum: `b467d5f40f659917130137c7460dcf975cf37b8fa237dac6711a71894e6dd530`

## Installed artifact check

A newly built wheel was installed without dependency resolution into a fresh
target. Both runtimes imported that target under `-I` and exercised actual
empty-store CLI output, SQL/cards/lock, all three artifacts and unchanged DB
bytes. Both passed with implementation SHA-256
`2c46ced1046a48b86cc9108b74a733949054d452b8586393ede8439d6858f2dd`.
The locked environment correctly reports MATCHED; the minimum reports MISMATCH,
not an attempted claim of numerical parity. This is not hosted CI or a clean
dependency-resolution test. A setuptools license-table deprecation warning is
recorded as separate packaging maintenance, not a wheel failure.

## Manual documentation review

The README's original 30-company notes and the earlier output snapshot are now
explicitly historical, not current acceptance evidence. The old DB is absent;
the notes cannot establish the current selected-200 metrics. This is a scoped
review, not completion of the pending generic docs-quote scan.

A new layout reproduction failed as expected: retained-count table headings
end at column 63 but data rows end at 62. This is a one-column presentation
defect, not a numerical mismatch. The red run is `layout-red-20260907.xml`;
the property checks every retained-count table via the populated real-store
CLI. Its correction is intentionally separate from the source snapshot now
executing the full numeric report. No full acceptance is claimed while open.
