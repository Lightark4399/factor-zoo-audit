# B acceptance and qualification projection — 2026-09-07

Status: COMPUTATION SNAPSHOT VERIFIED; presentation corrections focused-tested;
post-correction full regression and upstream docs-quote reuse remain pending.
This is local validation, not hosted CI.
The verified computation source snapshot is commit `0bd03bf`.

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
- Full suites: 223 passed in each environment, including all fourteen original
  demo tests; zero failures, errors or skips. Locked 3932.242 s; minimum 4025.198 s.
  XML hashes are recorded below. No test was deleted or renamed.
- Full-grid selected-200 archive completed at 05:16:19 UTC, with all ten factors
  computed, all 185 configured dates retained and source database bytes unchanged.
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
archived as the full numeric report. The original archive is not rewritten to
hide this defect; it retains its actual generating source identity.

## Complete-suite evidence at `0bd03bf`

| Runtime | JUnit SHA-256 | Result |
|---|---|---|
| Python 3.12.14 / pandas 3.0.5 | `c5352a73c3f83c850d7188d7e07376038e82d665bb8ff657c2e5ce0c46b7d74a` | 223 passed |
| Python 3.10.21 / pandas 2.0.0 | `6e4aaf10915a241c030560656bc6d82544896c9ba0b4ef7b8b62086f00808d2f` | 223 passed |

The previous complete count was 201. This snapshot adds nine dataset-evidence,
seven real-store transport, three reporting and three qualification cases: +22.
All test-process exit codes and completed JUnit files were independently read.

## Expected changes versus observed changes

Compared yesterday's completed full-fixture bundles with today's full-fixture
bundles, separately within each matching runtime. These are one-off diagnostic
comparisons, not stored-output unit assertions. Both comparisons show identical
protocol statistics (including IC and LS Sharpe), configuration, roster,
denominator, vintage results and stage counts.

The locked comparison has no changed computational/report-detail fields.
The minimum comparison initially fails exact equality on six `naive_trap`
objects. Recursive inspection finds changes only in `sample`: different
examples occupy the first five rows. There is no final SQL ORDER BY before
`violations.head(5)`, so these examples are not deterministic. This is an
unexpected reporting defect, not evidence of changed investment statistics,
and is not silently waived. A separate correction defines canonical ordering.
Raw signal arrays and panel key hashes are not present in these bundles and
were not compared by this check.

## Immutable selected-200 diagnostic archive

Path: `examples/outputs/b_selected_200_20260907/`.
No max-dates subsampling, ingest, terminal-return rule or data expansion was used.
The full run lasted about 4 h 12 min, overlapping the two suites initially.
Artifact acceptance checked matching qualification in both JSON exits and text,
protocol column positions/rounded values against structured values, all ten
factor entries, stage-count identities, full date grid, roster and unresolved
research gates. The retained-percentage one-column layout defect is disclosed
above; protocol numeric columns passed. This is not a cross-commit real-data
numerical attribution run or a completed generic documentation scan.

| File | SHA-256 |
|---|---|
| `demo_report.txt` | `e0965bf644d8a4e15cea0ab00cf5ce2642a2313cc8f2d91ae07005c2934ce329` |
| `demo_evidence.json` | `93124a719f2f1757c09e9254f558c716a35c17cae8db7325de6eeea8797483ee` |
| `demo_run.json` | `e7c8744d7f8998eb4de1f719823e568cd37f4654a21a6ebbbb4ad37506459a42` |

The source implementation hash is the installed-artifact hash above. Hashes
identify exact bytes; checkout newline conversions can change a source hash
without changing its program logic. Database hash before and after:
`66c60785d1c085d4883f49796a33f20ad2bdf418072086fbfd938100666312d9`.
Qualification remains DIAGNOSTIC_ONLY / NOT_EVIDENCE for market-wide survival.

## Presentation follow-up

- `4968b1d`: both retained-percentage rows now share the headings' width.
- `e341991`: final naive-trap SQL result has an explicit ordering before its
  first-five examples are taken. No predicate, grouping, count or factor input
  was changed. A shuffled-input synthetic relation with eight known violations
  asserts canonical examples; a grace-window control asserts zero violations.
- `6bbd5d8`: supplied sentinel qualification also reaches factor records, with
  independent policy copies and unchanged computed payloads.

Both environments passed all 12 focused cases (two ordering, seven real-store
CLI, three qualification), zero failures/errors/skips. JUnit SHA-256:

- Locked, 78.580 s: `5fb8dbb3a7911c22a66fcbcc3e3bb7b25c06a9638956f34d8353ca545a89084e`
- Minimum, 86.220 s: `7762089d82e2a346e6409a66d213d4adcedec590e64038e34444de67974035ca`

The first two ordering-test attempts omitted required synthetic schema fields
and failed during fixture setup; neither is a valid bug reproduction. After
supplying complete instant-fact records, the old code produced one intended
ordering failure and one passing no-exposure control. Corrected code passes both.
The new total is 225 (+2 ordering cases, zero removals/renames). Full runs for
this source snapshot use `b-final-locked-20260907.xml` and
`b-final-minimum-20260907.xml`; until those finish, do not call it 225 passed.

The temporary isolation worktree was fast-forward merged into the existing work
branch. It is retained as a local review artifact; no user data was removed.

The corrected wheel was rebuilt and installed into a new target. Both isolated
runtime smoke checks passed with implementation hash
`07ec797b866b3c66f6e45ce04539f0678a85fecc7ff6ed5d68ab95e860215af1`.
This is deliberately distinct from the immutable selected-200 archive's source.

Within each environment, the corrected full-fixture bundle was compared with
the `0bd03bf` full-fixture bundle. All six fundamental-reading factors now have
the expected canonical `naive_trap.sample` selection. Every other compared
field is unchanged, including all saved protocol statistics, stage counts,
configuration, denominator and vintage comparisons. Qualification itself is
unchanged. These comparisons still do not include raw arrays or panel key
hashes. Local receipts: `b-final-comparison-reviewed-locked-20260907.log` and
`b-final-comparison-reviewed-minimum-20260907.log` under `.diagnostic-envs`.

Archive whitespace review found the original centred title's trailing padding
on line 2 of `demo_report.txt`. It was retained to preserve the generated bytes;
the archive diff therefore has that disclosed whitespace warning. Source/test
lint passed. No blanket whitespace-ignore rule was added.
