# Three-layer comparison checkpoint

Base: `f3bce92`. Contract: [VINTAGE_COMPARISON.md](../../VINTAGE_COMPARISON.md).
Three diagnostic layers are implemented, with post-universe raw-input capture,
shared outcome/timing checks, common metric-date checks, and withheld gaps on
failed required checks. Text and structured outputs retain scope/reasons. They
do not present sensitivities as a causal decomposition.

## Expected changes and verification scope

- Original-process scores remain arm-specific on shared dates. Invalid outcome
  identity now withholds the gap and verdict. Synthetic source mismatch tests
  cover this intentional change; no historical data was used as a test oracle.
- Common-observation and common-support results are new. A synthetic extra
  industry member changes upstream neutralisation; re-cleaning identical common
  raw support restores an exactly zero gap, unlike merely intersecting scores.
- All re-scoring propagates requested quantiles. This fixes the old fallback to
  five when a caller requested a different count; the two-quantile runner and
  layer tests cover it. The default five-quantile setting does not change.
- The existing actual pipeline test verifies delivery of all layers and matched
  common-support outcomes. The populated actual CLI checks all layer scopes and
  statuses in stdout/saved text/JSON. Its three-date synthetic transport run is
  not a definition-equivalent full-grid research run. The rendered vintage
  section was read as well, including N/A factors and a computed three-row case.
- Additional controls cover each outcome field, missing labels/columns, invalid
  holding-period ordering, re-labeling that would hide invalid source outcomes,
  asymmetric IC eligibility and empty common raw support.

## Completed verification

Locked: Python 3.12.14 / pandas 3.0.5. Minimum: Python 3.10.21 / pandas 2.0.0.
All XMLs report zero failures, errors and skips. The union of testcase IDs is
80 distinct tests per environment, NOT the sum of the overlapping suite counts.

| Suite | Locked | Minimum |
|---|---|---|
| Pipeline, scope/layer controls, CLI evidence, qualification, reporting | 70 passed / 663.972 s | 70 passed / 736.272 s |
| Final layer/scope controls, CLI evidence, packaging | 34 passed / 182.977 s | 34 passed / 174.823 s |
| Added non-default runner-configuration regression | 1 passed / 71.181 s | 1 passed / 28.268 s |

The 34-case suite includes the last source-outcome guard tests and final output
projections; the 1-case run covers the subsequent runner-configuration test.
Initial 18-case unit verification passed; lint initially found one long line,
which was corrected. Final lint and whitespace checks passed.

Local JUnit files under `.diagnostic-envs/` and SHA-256:

| File | SHA-256 |
|---|---|
| layers-locked-0909.xml | `1c26032fb414e70ccf1a4e98fe8a1d9c13afe889bd428f887cfea35610e3f561` |
| layers-minimum-0909.xml | `5fe0f122782be189bd5f2029cd201a7034b9b393928dbb5e2f72029541fa8257` |
| layers-final-locked-0909.xml | `76965207523fd373363dcc71412ca08a22440a6ad5a54fdc6482a718caa25996` |
| layers-final-minimum-0909.xml | `2bf3cc7e99cc95b31325556828cfa99caa7be3ec15074cc01cffa4a01e4ab45f` |
| layers-config-locked-0909.xml | `f6ef67f96df0e208cada95573d73cf3f687fe0960e95da3899ca473b7a0613f0` |
| layers-config-minimum-0909.xml | `4f434d4ab36e2f42782b5dec3920cccc10d441f8f7d956c8a7233d195e80621d` |

Collection: 248 tests (236 + 11 layer controls + 1 runner-setting case). Zero
removed/renamed tests. Existing synthetic scope panels now supply explicit
holding-period metadata, and the old NOT_CHECKED assertion expects MATCHED for
those generated valid outcomes. Full regression, including the entire 14-case
demo module, has NOT been rerun for this snapshot. Do not claim 248 full passes.

## Not done here

No selected-200 rerun, archive replacement, numerical claim upgrade, provider
acquisition, exit-return implementation, OSAP integration, sibling edit or email.
The archived 200-company report predates these layers. Its former IC gap is not
a substitute for their as-yet-uncomputed real-data values. Breadth messaging and
PlausibilityRule remain separate work after this checkpoint.

## Subsequent breadth-display checkpoint

Base: `796e6c4` (the three-layer checkpoint above). Added a group-scoped
`breadth_diagnostic` projection to structured factor records and standard-protocol
text rows. Its post-observation display rule does not modify any numerical
protocol, input sample, score or vintage verdict. Retained date-by-quantile
distributions are explicitly distinguished from total cross-section sizes and
from dropped dates. Absence of a warning is not a power certificate.

Both environments passed 27 tests, zero failures/errors/skips: breadth policy,
reporting, qualification, all seven CLI-evidence tests and packaging. There are
seven new breadth tests and zero deleted tests. Collection is now 255; this is
NOT a claim of 255 passes. These suites overlap the preceding checkpoint and
their counts must not be added as distinct tests. Full 14-case demo-module
regression and a full-grid selected-200 rerun remain outstanding.

| Local JUnit file | Tests | Seconds | SHA-256 |
|---|---|---|---|
| `.diagnostic-envs/breadth-locked-0909.xml` | 27 | 63.342 | `596225b071e40e3d806ae5e41468ae68b857221728cd6cd8e992038410e62f17` |
| `.diagnostic-envs/breadth-minimum-0909.xml` | 27 | 65.909 | `894e76830254b5458dd00060c375dadd4ac3c6a8bbbc7f310fee8e82ab3845b4` |

The generated populated synthetic CLI report was read: columns remain aligned,
and its undersized cross-sections correctly show `[B?]` rather than a successful
breadth check. Unit cases cover low-group, unflagged and missing-group states.
Existing protocol summary zero/NaN placeholders are preserved, not redefined as
new numerical results. Lint and whitespace checks passed. PlausibilityRule is
still the next implementation item; no old archive or evidence claim was upgraded.
