# Assertion scope audit

Date: 2026-09-05. Baseline inspected: `0a2dde0`.
Scope: factor-zoo tests, registry boundary, pipeline entry points, demo stdout
and file output, provenance, and release checks. No backtest-audit code changed.

The user supplied the sibling audit principle: scope an assertion to the
property, not only to the file or report where it last failed. The local sibling
checkout did not contain the quoted new audit item. Its four-instance incident
is therefore attributed to the supplied message, not claimed independently
verified here. This document records this repository's own checks and results.

## Findings

| ID | Property and relevant entry points | Observed scope before review | Result and disposition |
|---|---|---|---|
| AS-01 | Provenance must accurately distinguish a matched lock and any mismatch: runtime, packaging test, both CI environments, demo | Packaging and demo tests hard-coded `MATCHED`; the minimum environment is intentionally different. | **DEFECT_FOUND, test correction implemented.** Minimum packaging run reproduced `MISMATCH != MATCHED`. Tests now compare installed versions with the lock; synthetic cases vary every numerical dependency independently. |
| AS-02 | `VERIFIED` needs a nonblank locator at the card-loading boundary, for every reference role | `test_every_reference_has_role_locator_and_verification` loops over current cards, but `HypothesisCard.from_yaml` only requires that the key exists. | **DEFECT_FOUND, runtime correction implemented.** Fifteen null/empty/whitespace cases across all five reference roles failed before the correction. Loader now rejects them; the honestly unverified origin remains PENDING. Current cards did not change status. |
| AS-03 | A diagnostic dataset must remain diagnostic in every report path | Fixture disclaimer checked on stdout; real-store mode only printed the DB path and never read `research_evidence` from the ingest sidecar. | **FIXED 2026-09-06.** Dataset declarations now reach stdout, saved text and `demo_evidence.json`. Missing/malformed/unreadable/unbound metadata cannot promote evidence; even hash-matched `true` is not certification. Six real-store transport cases plus a populated, unmocked pipeline case and nine provenance boundary cases passed in both environments. Research eligibility itself remains unimplemented. |
| AS-04 | Eligibility must precede magnitude/cleaning for all registered factors and PIT/restated entry points | Strong `asset_growth` ghost/magnitude incident tests; all-factor smoke tests did not assert the membership subset or count conservation. | **COVERAGE_EXTENDED.** Incident tests preserved; all ten factor path tests now assert membership and stage-count conservation. Source inspection confirms both vintage arms route through `compute_factor`; existing shared-membership integration tests retained. This is not exhaustive adversarial coverage of every possible future entry point. |
| AS-05 | Release resources must work without the checkout | CI's installed-wheel smoke instantiates Store and loads ten cards; source tests also check the denominator file and lock. | **COVERAGE_EXTENDED.** CI wheel smoke now calls denominator/provenance consumers, uses the job's constraints and isolated Python imports. Local wheel verification and hosted-CI status are distinguished in the validation record. |
| AS-06 | Diagnostic classifications survive output transport | Several tests regenerate identical reports and inspect stdout only; file test checks only existence/title. | **COVERAGE_GAP, narrowed.** A freshly computed full-window report is now shared within this pytest invocation and its saved contents checked against stdout, including `NOT findings`. This covers fixture transport, not the missing real-store policy in AS-03. |
| AS-07 | Every supported pandas environment can enter through the demo, not just factor/fixture helpers | The earlier frequency-alias fix missed `signal_dates_for(..., freq="ME")`. The 14 demo tests were not completed in the earlier minimum-version verification. | **DEFECT_FOUND, correction implemented.** The minimum-environment date test reproduced `ValueError: Invalid frequency: ME`. Default now uses `pd.offsets.MonthEnd()`. The original date test also checks month ends and explicit/default frequency equivalence. Source/test scan found no other `ME`/`QE`/`YE` string literals or `future_stack` uses. |

`DEFECT_FOUND` means a concrete counterexample or an inspected missing
implementation, not a claim that every existing numerical report is wrong.
`COVERAGE_GAP` does not claim a production bug without a counterexample.

## Reproductions and controls

### AS-01: mismatched runtime is not a packaging failure

The baseline minimum environment (Python 3.10.21/pandas 2.0.0) ran
`pytest tests/test_packaging.py`: one pass, one failure. The failure was the
test's unconditional `environment['lock_status'] == 'MATCHED'`.
The application correctly returned `MISMATCH`.

The revised test derives expected mismatches from actual distribution versions
and the shipped pins. Five independent controlled cases cover all matched and
each of pandas/NumPy/SciPy/statsmodels unavailable. They assert the status and
the exact mismatch keys and installed/locked values. Both environments passed
all seven packaging cases after the correction.

The demo test now expects the runtime's reported status, while the independent
packaging tests verify that status calculation. This is not permission to
accept either word without checking which is warranted.

### AS-02: accepted unsupported verification label

Read-only probe: deep-copy the loaded `bm_ratio` YAML data, replace the
definition-origin locator with null, and feed it via an in-memory resource to
`HypothesisCard.from_yaml`. Baseline output:

```text
accepted=True
lineage=DOCUMENTED_VARIANT
eligibility=INCLUDED
```

The intended property is independent of factor ID, filename and citation role:
a verified reference must have a nonblank locator. An unverified relation may
have no locator and must not thereby be silently promoted. A nonblank locator
is a structural prerequisite, not proof that a human actually verified a paper.

### AS-03: report provenance is not enforced by an example README

At the inspected baseline, `open_store` returned `real` for any existing database. `main` printed the
fixture warning only for `mode == 'fixture'`; the real branch prints the path.
Neither path loads the ingest report's research flag. The real-mode footer
interprets the vintage gap. Tests all pass a nonexistent DB path.

This is the same scope failure in a different transport: the example-output
README labelled `fza_200` diagnostic, but opening that DB directly did not
propagate the label. Following user approval, the real-store report now prints
DIAGNOSTIC_ONLY / NOT findings at the beginning, beside the statistics and in
the conclusion. The machine-readable evidence artifact carries claim-relative
statuses. AS-03 is closed for the current demo outputs, not for hypothetical
future exporters. A successful run still cannot authorize a research headline.

Focused verification on 2026-09-06: Python 3.12/pandas 3.0.5 and Python
3.10/pandas 2.0 each passed all 16 new cases (no failures or skips). The first
attempt used a denied system temp directory and never reached an assertion;
successful runs used separate workspace-local basetemp directories.

## Tests are properties plus incident regressions

Keep the asset-growth/TST07 counterfactual tests and the concrete magnitude
outlier displacement example. Supplement them with assertions on every factor
actually traversing the pipeline. Similarly, retain the named denominator
reclassification assertions while checking partition/count identities over
the dynamically discovered registry. Do not substitute a helper-only test for
an actual CLI/pipeline call.

The 14 demo test names and their original behavioral assertions are retained.
Repeated identical executions share fresh in-process module fixtures: one full
33-date normal report (including `--outdir`), one six-date injected-magnitude
report and one six-date normal/empty-factor report. No saved historical output
is used as an expected value. No production factor, date window, label rule or
exit behavior is changed by this test refactoring.

## Evidence limits

- Source-level full tests do not prove that a clean installed wheel works.
- Matched numerical dependencies do not imply a complete historical dataset.
- Universe wiring does not validate filing-history dates as official exits.
- Finite cleaned values do not prove that no invalid raw rows were discarded.
- Shared PIT/restated membership does not imply identical label samples or
  cancellation of common biases.
- This bounded audit does not certify every assertion in every sibling repo.

The standalone 14-test demo run passed in 741.93 seconds, retaining the full
window (527.32 seconds for its single normal report). Its XML capture is under
the ignored `.diagnostic-envs` directory. Full runs and final counts are recorded
separately in `docs/validation/VALIDATION_20260905.md`. The earlier 166 passes remain a five-file
subset, not a full-suite claim.
