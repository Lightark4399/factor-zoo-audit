# Vintage scope correction — first implementation checkpoint

Base: `0199040`, branch `codex/fza-universe-wiring`. Scope: explanations,
observation-key disclosure, actual substituted-read invocation coverage,
fail-closed undefined comparisons, and the B delivery decision. This is not
completion of the three-layer numerical diagnostics or the entire backlog.

## Expected changes, and what was checked

- On valid shared dates with exercised reads, preserve the original-process
  protocol inputs and computations. New synthetic runner tests compare its IC
  series and quantile returns with direct protocol evaluation of the exact
  generated arm-specific panels. This is not a cross-commit real-data attribution
  run; raw real-data arrays and the 200-company ICs were not recomputed.
- Expose PIT/restated/common/exclusive counts and canonical scoring-key hashes.
  Equal dates/counts with different securities must not imply equal keys.
  Row permutations must leave disclosure unchanged; null/duplicate keys fail.
  Key equality does not verify labels or holding periods: explicitly NOT_CHECKED.
- Change log_mktcap/turnover comparison status from an unearned PASS to
  NOT_APPLICABLE because neither calls the substituted read methods. Existing
  per-arm protocol statistics remain available; comparison gap becomes unavailable.
  Invocation counting does not prove that a returned value influenced a result.
- With no shared dates, report zero scored observations, unavailable statistics
  and INCONCLUSIVE instead of using two unmatched original scores. This is an
  intentional fail-closed numerical-availability change, not a wording-only fix.
- PASS/FAIL retains the preconfigured directional 0.005 rule when applicable;
  remove claims about causal information value, equivalence or estimation noise.
- The populated actual CLI checks every emitted comparison in stdout, saved text
  and the run bundle. Its 12-security, three-selected-date fixture is only an
  output-transport check, not a definition-equivalent full-grid research run.
  The newly generated vintage section was also read for labels and alignment.

No factor formula, cleaning primitive, price-label rule, dependency or research
gate was changed. The three original selected-200 artifact hashes match the
2026-09-07 record; an accompanying README correction does not rewrite artifacts.

## Completed tests (JUnit inspected)

| Suite | Locked Python 3.12.14 / pandas 3.0.5 | Minimum Python 3.10.21 / pandas 2.0.0 |
|---|---|---|
| Entire test_pipeline + test_vintage_scope + test_demo_evidence | 55 passed / 519.588 s | 55 passed / 578.940 s |
| test_demo_evidence + test_qualification + test_reporting + test_packaging + test_vintage_scope | 29 passed / 43.576 s | 29 passed / 46.932 s |

All four XMLs report zero failures, errors and skips. Suites overlap: 68 distinct
tests ran in each environment, not 84. The second suite ran after the final two
report clarification lines were added. Lint and `git diff --check` passed.

Local JUnit receipts under `.diagnostic-envs/`:

| File | SHA-256 |
|---|---|
| scope-locked-20260908.xml | `388af7e5901712377c5af2235540fb67cee0ce303e41a6fdabd681f9b8ff6bca` |
| scope-minimum-20260908.xml | `6eb9bfad47620dd1a966886b78b9eac6f5cb31310c86787383364e1e73eb5afe` |
| scope-surfaces-locked-20260908.xml | `ced6aed0c69de75676a5f20fc6d2fc2d470fd8a696a8aed9851c607405bebee0` |
| scope-surfaces-minimum-20260908.xml | `6b1f137508c5da83c737dd05c3a4ebc61e591424092b6c68a2b7c5c9f761e422` |

Collection is now 236: prior 225 + nine synthetic scope cases + two actual
embedded-share pipeline cases. Zero tests removed or renamed; an existing demo
assertion now expects the actual uppercase NOT APPLICABLE label, and the existing
populated-CLI test checks all comparison records. The 14-case full demo module
was not rerun at this checkpoint. The previous 225-case complete dual-environment
results are documented separately and do not establish 236 current passes.

## Remaining gates for subsequent work

1. Implement common-observation scoring and common-support re-cleaning, check
   label/holding-period identity and metric eligibility, and preserve the exact
   requested protocol settings in every scoring path. Contrasts are sensitivities,
   not a pure value/sample decomposition. No common-support results exist yet.
2. Breadth clarification/warnings, then multi-rule PlausibilityRule.
3. Complete regression and suitable full-grid diagnostic verification after the
   numerical changes. Do not silently overwrite the existing real-data archive.

OSAP integration, licensed-data acquisition, terminal-return implementation,
sibling edits and email sending were not performed. Data-access enquiries are
not substitutes for the unresolved membership and outcome evidence gates.
