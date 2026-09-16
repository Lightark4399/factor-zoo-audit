# Disclosure metric correction — scoped validation

Base: `f9f5638` (documentation-layout commit, following `d00c656`).
This is a new reporting contract, not a new selected-200 numerical run.

## Changes and migration

The legacy repeat-date view and JSON fields keep their behavior, with an explicit
scope field in new summaries. New `disclosure_summary` fields use fact-key
denominators and separate changed, unchanged and uncomparable repeated keys.
The current renderer suppresses the misleading legacy percentage and explicitly
marks changed-value counts unavailable for old bundles. This intentionally changes
future rendering of old inputs; original text/JSON/manifests are not overwritten.
See [the contract](../DISCLOSURE_METRICS.md) for definitions and limitations.

Tests use explicit histories, not historical outputs as correctness oracles.
They cover unchanged repetition, numerical change, reversal, missing values,
unit conflicts, same-date conflicts, empty denominators, demo-summary transport,
legacy rendering and date-level naive exposure with duplicate input keys.
Store, existing renderer and README projection tests also ran.

## Results

Both locked and minimum-supported environments completed 47 focused tests:
zero failures/errors/skips, exit code 0. XML files are ignored local artifacts:
`.diagnostic-envs/disclosure-locked-0914-final.xml` and
`.diagnostic-envs/disclosure-minimum-0914-final.xml`.
The import-order lint failure was fixed without changing assertions; final lint
passes. Subsequent changes to the legacy SQL/store descriptions are comments and
a docstring, not query semantics. No full-repository pass or hosted CI is claimed
for this batch. This does not extend an earlier full-suite result to new code.
After documentation updates, 14 navigation, README-projection and documented-field
checks also passed in the locked environment. They overlap the 47-test selection;
these counts must not be added as if disjoint. Archive output files have no Git diff.

The original roe archive's date counts and the implemented query were inspected;
no real-data factor construction was repeated. In particular, no raw-key identity
or exact reproduction of 184/184 is claimed by the new synthetic query test.
Neither a corrected counting contract nor these tests promote research status.

## 2026-09-16 follow-up: bounded old/new execution

The query now documents its schema-enforced fact_type constraint beside the SQL;
the report explains whole-key exclusion and changes later reversed. No grouping,
denominator or comparability rule changed. The locked environment's 28 relevant
checks passed, as did Ruff and whitespace checks. An initial test attempt hit
system-temp permission errors in two setup fixtures; rerunning with a fresh
workspace basetemp passed without assertion changes.

`scripts/check_disclosure_ab.py` runs actual old/new demos in fresh processes,
with the same interpreter, fixture and date grid. Old source was exported from
`d00c656`; new source is `2dc9123` plus the three explanatory-file edits. Expected
differences were written before execution: runtime/generated timestamp,
implementation provenance, and two added data-summary fields. All other bundle
fields and every legacy summary field must match; all ten factors must complete.

The first six-date run matched the compared fields but failed the all-completed
requirement: both momentum windows produced empty factors in both arms. Its
outputs remain in `.diagnostic-envs/disclosure-ab-20260916`. The requirement was
not relaxed. A second, prospectively fixed 16-date run completed in both arms,
and the comparison exited 0. All ten factors have non-null IC and LS Sharpe.
Full serialized factor records, vintage comparisons, evidence, research gates,
denominator, configuration and roster matched exactly. New disclosure counts
were 2400 fact keys, 13 repeated keys, 13 changed-comparable keys, zero unchanged
and zero uncomparable keys. These are synthetic diagnostics, not research findings.

Second-run artifacts are under `.diagnostic-envs/disclosure-ab-20260916-16dates`:

| File | SHA-256 |
|---|---|
| comparison.json | 95d99a4fcd9c777d312d3c81b7d625d2de979012569937a9b5551872b8784967 |
| old/demo_run.json | 9aaa71757fb4291e218de06abbd919c0e37a81148e365a4e412ecab84c00d381 |
| new/demo_run.json | a34db5e6584411ccf032381607f937a05a96acc0fa6a11a9835a567f53392059 |

This is a one-off diagnostic, not a stored-output correctness test. It covers
serialized results, not raw-panel identity; a 16-date subsample is not the full
grid or selected-200 data. README projection checks still only establish its
consistency with the named historical archive. This run separately supports
unchanged computed outputs on the stated synthetic scope, not a new reproduction
of the README's real-data numbers. No performance claim is made.
