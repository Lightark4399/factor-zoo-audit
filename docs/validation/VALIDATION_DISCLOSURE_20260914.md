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
