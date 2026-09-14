# README diagnostic examples — scoped document verification

The existing headline and generated qualification policy remain unchanged.
Three examples now precede the detailed report links. No computation, archive,
research gate, threshold or verdict was changed.

The selected source is the archived de1e836 demo_run.json under
examples/outputs/b_selected_200_rerun_20260909, SHA-256:
4bcefb562c17971de93604dd952ba1e61781d29c1dbf57722d26f29e404c4f34.

| Example | Exact source fields | Scope retained |
|---|---|---|
| asset_growth gap | vintage_comparisons.asset_growth.detail.layers.original-process.ic_gap and common-observation.ic_gap | Restated minus PIT; shared scoring keys do not undo arm-specific cleaning; sensitivity, not decomposition; original FAIL unchanged |
| Research gates | research_gates, each named status | This archive: two unresolved, four unimplemented; neither category implies passed research |
| roe naive exposure | factors.roe.naive_trap.n_dates_exposed and n_signal_dates | Dates with at least one exposed record, not share of rows or a PIT leakage diagnosis |

scripts/readme_examples.py projects this reviewed text and its numeric fields.
It refuses changed comparison scopes, unmatched outcome status, absent sign
reversal, altered original verdict, changed gate statuses or inconsistent
date-exposure counts. Changing the selected source requires renewed review.
The script prints a Markdown block; it does not silently rewrite the README.

tests/test_readme_examples.py checks exact block consistency and mutations of
numbers, PASS/DIAGNOSTIC_ONLY wording, causal interpretation, date/row scope,
comparison scope, outcome status and a promoted research gate. These checks
guard the reviewed mapping and wording; they do not prove the interpretation
or underlying calculations scientifically correct. They are documentation
projection tests, not factor tests using old output as a correctness oracle.

The selected suite is test_readme_examples, test_qualification and
test_documented_contracts: 15 tests in each environment, with no overlaps
summed as additional coverage. Full-suite and CI status are not inferred.
Results are recorded in .diagnostic-envs/readme-locked.xml and
.diagnostic-envs/readme-minimum.xml; final rerun after wording/style edits uses
readme-final-locked.xml and readme-final-minimum.xml.

Final reruns completed with exit 0 in both environments: 15 tests, zero
failures/errors/skips in each XML. Static checks and git diff --check passed.
The archived source SHA-256 was checked again and remains unchanged. This
batch changes only the README, its projection/checks, and this validation note;
no factor recomputation, verdict change, whole-suite run or CI claim is made.

## Subsequent release-candidate preparation

Byte inspection found mixed README line endings (288 CRLF and 142 bare LF).
The editable README is now 430 LF lines, zero CRLF; its text is unchanged by
normalization. A README-only text/eol=lf attribute preserves this convention.
Historical JSON/TXT archive bytes were not rewritten. Full src/tests/scripts
lint passes. Complete dual-environment regression and CI for the candidate
commit are still required before requesting permission to merge; the earlier
targeted results do not substitute for those checks.
