# Documentation contracts and plausibility-rule checkpoint

Documentation correction commit: `027b65a`. Parent before this work: `d9c203b`.
This checkpoint does not replace the archived selected-200 report.

## Changes and numerical expectations

- Correct formation_date to formation_session in the bridge preflight. Two
  contract tests compare explicit tables to generated label columns and the
  executable vintage-layer registry. No arbitrary prose-token existence scan.
- Introduce immutable PlausibilityRule declarations, unique per-factor IDs,
  kind/severity validation, inclusive nullable bounds and required rationale.
  Report all evaluated rules in text and magnitude_check.rules JSON.
- Preserve all four legacy economic ranges, their tolerance and extreme-row
  ordering. They are now structurally reported as economic guards, not universal
  physical limits. Compatibility fields refer only to the legacy range.
- Add log_mktcap's DECLARED_UNBOUNDED output declaration and turnover's
  nonpositive construction rule. The latter intentionally rejects positive raw
  outputs before cleaning; it does not cap underlying turnover at one. Existing
  valid outputs are not transformed. Four other factors remain UNDECLARED.
- No factor formula, cleaning, label or scoring calculation is changed. Neither
  scale checks nor declarations certify freshness, semantics or research claims.

## Completed focused verification

Python 3.12.14 / pandas 3.0.5 and Python 3.10.21 / pandas 2.0.0 each passed:

| Suite | Tests | Locked seconds | Minimum seconds |
|---|---|---|---|
| Rule boundaries, docs, registry, actual CLI, packaging, reporting, qualification | 52 | 25.585 | 27.228 |
| Legacy magnitude and ghost-universe regressions | 5 | 18.077 | 19.411 |

The two final suites cover 57 distinct tests per environment, with zero failures,
errors or skips. Earlier 37/5 runs and the two standalone documentation tests
overlap and are not added. Fourteen rule tests and two documentation tests were
added, none removed. Collection is 271, not a claim of 271 passes.

| Local JUnit path under .diagnostic-envs | SHA-256 |
|---|---|
| rules-final-locked-0909.xml | dc589be5cd57a5e5921794ba413b3cbbe34c0d8f3032a60c7c1e92143fc91209 |
| rules-final-minimum-0909.xml | 621fa7a1e7166e9f9f014f87081b8d514d74f8e40de8e915a3a3776fb98ecbd2 |
| rules-final-legacy-locked-0909.xml | 75a6cbbb1202e8602f3ade1e007b1929fe7c074619a379043998227daa6fa8d3 |
| rules-final-legacy-minimum-0909.xml | 55dbf2b71b9d66c0d73a425865605bf1435ea3a573dad2437ac93d0fc1511da0 |

The populated synthetic CLI report was read: unbounded, undeclared, construction
and economic statuses are visible alongside rationale and bounds. Actual CLI
tests compare every emitted rule's status against stdout and saved text. The
three-date transport fixture is not a full-grid research run. Ruff initially
fixed three import-order findings; subsequent lint and whitespace checks passed.

## Outstanding acceptance

Full tests were launched in both environments, including all fourteen demo
tests, with intended XML paths full-rules-locked-0909.xml and
full-rules-minimum-0909.xml. No completed full-suite XML was available when this
checkpoint was written. Collection or ongoing dots are not acceptance evidence.
After full regression, the selected-200 report must be regenerated on its full
signal grid into a new archive, with expected/observed changes disclosed. That
run has not started. No historical archive, research claim or WRDS gate was
promoted; no dependency bridge, data acquisition or sibling modification occurred.

## Subsequent full-suite outcome and repair

Both initial full runs have now finished: 271 tests each, 270 passed and one
failed, zero errors/skips. Locked elapsed 2242.848 seconds; minimum 20492.925
seconds. The same test failed in both:
`test_an_undeclared_range_is_printed_as_undefined_not_as_a_pass`, because its
required explicit phrase "NOT that the factor passed" had been replaced by
different wording. This was not a numerical assertion failure. These failed
full runs are retained, not overwritten or presented as successful regression.

JUnit SHA-256: full-rules-locked-0909.xml:
`9b0f2c58d9d6e1948a1c41b55e9ff1f03e321de7f8f4022bad528ab7d12a65b1`;
full-rules-minimum-0909.xml:
`39bf7121398c1e72402add36c3c8a9bf66b58d82ced4414f34022cafc735c117`.

Commit `51627f9` restores the phrase while retaining its legacy-only scope;
no assertion was deleted or weakened. All fourteen demo tests were then launched
again in each environment, targeting demo-disclaimer-locked-0909.xml and
demo-disclaimer-minimum-0909.xml. Those repair runs are not yet certified here;
even successful module XMLs must be described as module runs, not new 271-case
single-invocation full passes.

The same commit freezes `SELECTED_200_RERUN_EXPECTATIONS.md` BEFORE any new
selected-200 computation. The database hash was rechecked and matches the old
archive. New real-data generation remains unstarted pending regression acceptance.
