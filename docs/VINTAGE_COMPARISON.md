# Three-layer vintage diagnostic contract

All layers are diagnostic. Differences between layers reflect sensitivity to
sample selection and processing, not a decomposition into value and sample
effects. A common set is selected; it does not represent the original cohort.

| Layer | Fixed scope | Remaining limitation |
|---|---|---|
| original-process | Shared signal dates; the historical-membership input | Arm-specific effective observations and cleaning inputs; even metric-eligible dates can differ and are disclosed |
| common-observation | Intersection of the already-cleaned scoring observation keys | Effects of arm-specific upstream cleaning remain in the values |
| common-support | Intersection of finite, post-membership, pre-cleaning observation keys | The common support itself is selected; this is not a market-wide result |

The common-support layer cleans the two raw inputs independently using the same
cleaning configuration and industry mapping, then rebuilds labels using the
requested horizon and execution lag. It does not reconstruct raw signals from
z-scores or use cleaned-panel keys as its raw-input selection rule. Finite raw
support selection, small-cross-section cleaning losses and label losses are
distinct; both cleaning reports and label-join reports are retained.

## Fail-closed conditions

Every row carries its scope, status, reason, outcome-identity result, and nullable
IC/LS-Sharpe gaps. The text shows scope and identity beside the IC gap; the run
bundle and library serialization also contain input/output key counts/hashes,
metric-date lists and metric-specific reasons when those checks were reached.

- The declared price-only branch and an unexercised substituted path are
  NOT_APPLICABLE, not zero-gap evidence. Invocation is not proof of influence.
- Shared keys must be unique and non-null. Outcome identity compares actual label,
  formation session, entry date and exit date exactly on those keys. Missing
  columns are NOT_CHECKED; missing/nonfinite outcomes do not match each other.
  Identically invalid holding-period ordering cannot pass.
- Missing or mismatched required outcomes block dependent gaps. Original-process
  identity covers its shared keys only; it does not certify arm-exclusive outcomes.
  Original per-arm scores remain available, but no valid comparison is implied.
- Rebuilding common-support labels cannot erase a missing/failed original outcome
  identity check. Its source check and newly rebuilt check are both visible.
- If common-support processing produces different final keys, do not silently
  take another intersection: withhold its gaps and report the discrepancy.
- Common-observation/support metrics require identical eligible metric dates.
  For example, equal keys with a constant signal in one arm can still yield
  different IC date sets. Unscorable IC and LS Sharpe remain unavailable,
  independently; an available IC does not certify an LS-Sharpe comparison.

All scoring paths use the requested number of quantiles. The original-process
legacy directional threshold remains a diagnostic trigger, not a significance,
equivalence or research-qualification test. Additional layers do not inherit a
research PASS from that threshold. Do not add/subtract layer gaps as causal parts.

## Regressions and delivery limits

Synthetic controls explicitly construct an additional extreme security that
changes industry neutralisation before final sample intersection. Common-support
re-cleaning restores a zero gap when its two raw inputs are identical. Separate
controls change each outcome field, use invalid/missing outcomes, remove metric
eligibility, omit common raw support, and request a non-default quantile count.
The actual pipeline and actual CLI are exercised in addition to pure helpers.

No archived real-data statistic is used as a test oracle. The original selected-200
report remains unchanged; it predates these layers and cannot supply their values.
No new full-grid selected-200 computation is implied by these implementation tests.
