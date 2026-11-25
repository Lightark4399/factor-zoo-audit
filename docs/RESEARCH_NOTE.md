# Research note: vintage layers for the four fundamental factors

DIAGNOSTIC_ONLY. Every number below is read from an archived run; nothing here
was recomputed. The archive labels its statistics "NOT findings".

## Question and answer

TODO (author).

## Data and settings

- **Source run.** [`examples/outputs/b_selected_200_rerun_20260909/demo_run.json`](../examples/outputs/b_selected_200_rerun_20260909/demo_run.json)
  (SHA-256 `4bcefb56…4c4f34`), `generated_at_utc` 2026-09-11T10:51:10Z. The
  presentation replay
  [`b_selected_200_presentation_20260912_final/replay_input.json`](../examples/outputs/b_selected_200_presentation_20260912_final/replay_input.json)
  carries an identical `vintage_comparisons` object (checked 2026-11-24).
- **Store.** `data/fza_200.duckdb`, SHA-256 `66c60785…12d9`
  (`database_sha256_after_run`; `database_bytes_unchanged` is `true`).
- **Companies.** 200 stored securities (`selected_roster`, 200 rows; 161
  `us-gaap` in `data_summary.securities_usgaap`). `roster_scope` is
  `stored_selection_not_verified_historical_membership`.
- **Dataset status.** `evidence.declared_run_purpose` = `diagnostic_scale`;
  `evidence.declared_research_evidence` = `false`;
  `evidence.declared_survivorship_prone_share` = `1.0`;
  `evidence.statistics_status` = `DIAGNOSTIC_ONLY`.
- **Grid and protocol** (`configuration`). 185 month-end signal dates,
  2011-04-30 to 2026-08-31, not subsampled; 21-session labels; execution lag 1
  session; 5 quantiles; `ls_sharpe_units` = `per_observation_not_annualised`.
  IC is the per-date Spearman rank correlation between signal and forward
  return (`src/fza/pipeline/protocol.py`, `information_coefficient`);
  `ic_mean` is its mean over dates. For each of the four factors and each layer
  below, PIT and restated IC are computed on 183 dates, and the two date lists
  are identical (`…metrics.ic.identical_metric_dates` = `true`).
- **Environment** (`environment`). Python 3.12.14, pandas 3.0.5, numpy 2.5.2,
  scipy 1.18.1; `lock_status` = `MATCHED`.
- **Arms.** PIT reads fundamentals through the point-in-time path. The restated
  arm substitutes a read that keeps `period_end <= signal date` and drops the
  filing-visibility constraint (`src/fza/pipeline/run.py`, `compare_vintages`).
  IC gap = restated IC − PIT IC.
- **Layers.** Defined in [VINTAGE_COMPARISON.md](VINTAGE_COMPARISON.md):
  original-process (shared dates, arm-specific observations and cleaning
  inputs), common-observation (intersection of the cleaned scoring keys),
  common-support (intersection of finite, post-membership, pre-cleaning keys,
  re-cleaned per arm). All three are diagnostic; differences between layers are
  sensitivities, not a value/sample decomposition.
- **Cleaning setting.** The common-support cleaning reports record
  `neutralised: false` for both arms of all four factors
  (`…layers.common-support.cleaning[0..1].neutralised`).
- **Code version.** The run predates commit `0ce7911` (2026-09-26), which
  changed the restated arm's latest-row read from `groupby().last()` to
  whole-row selection. A bounded read-output comparison on 24 of 185 signal dates
  found no differing cell; factor outputs were not recomputed
  ([VALIDATION_SELECTION_EVIDENCE_20260923.md](validation/VALIDATION_SELECTION_EVIDENCE_20260923.md)).
  The 0.2.0 window correction applies to `mom_12_1`, `mom_6_1` and `rev_1m`
  only ([CHANGELOG.md](../CHANGELOG.md)).

## Four-factor table

All rows: status `DIAGNOSTIC_ONLY`, label/holding-period identity `MATCHED`.

| factor | layer | PIT IC | restated IC | IC gap | restated-only share |
|---|---|---|---|---|---|
| bm_ratio | original-process | −0.01400 | −0.01493 | −0.00092 | 0.96% (195 / 20,346) |
| bm_ratio | common-observation | −0.01430 | −0.01465 | −0.00035 | — |
| ep_ratio | original-process | −0.01058 | −0.00823 | +0.00235 | 2.17% (439 / 20,215) |
| ep_ratio | common-observation | −0.00880 | −0.00715 | +0.00165 | — |
| roe | original-process | −0.00471 | −0.00112 | +0.00360 | 2.58% (553 / 21,463) |
| roe | common-observation | −0.00470 | −0.00205 | +0.00265 | — |
| asset_growth | original-process | −0.01166 | −0.00351 | +0.00815 | 42.59% (9,643 / 22,642) |
| asset_growth | common-observation | −0.01120 | −0.01306 | −0.00187 | — |

Field paths, with `<f>` the row's factor and `<layer>` the row's layer, all
under `vintage_comparisons.<f>.detail` in the source run:

| column | field path |
|---|---|
| PIT IC | `layers.<layer>.pit.ic_mean` |
| restated IC | `layers.<layer>.restated.ic_mean` |
| IC gap | `layers.<layer>.ic_gap` |
| restated-only share | `sample_comparison.restated_only_observations` / `sample_comparison.restated_observations` |

Common-observation scores only the shared keys, so it has no restated-only
observations by construction.

Observation counts (`sample_comparison`):

| factor | PIT | restated | shared | PIT-only | restated-only |
|---|---|---|---|---|---|
| bm_ratio | 20,186 | 20,346 | 20,151 | 35 | 195 |
| ep_ratio | 19,908 | 20,215 | 19,776 | 132 | 439 |
| roe | 20,970 | 21,463 | 20,910 | 60 | 553 |
| asset_growth | 13,404 | 22,642 | 12,999 | 405 | 9,643 |

## asset_growth

The original-process directional trigger fired: `diagnostic_verdict` begins
`FAIL`, with `detail.material_gap_threshold` 0.005 and `detail.threshold_kind`
`PRECONFIGURED_DIAGNOSTIC_NOT_SIGNIFICANCE_TEST`. Universe rows excluded:
PIT 213, restated 236 (`detail.universe_rows_excluded_pit`, `…_restated`).

Each arm, by layer (`detail.layers.<layer>.<arm>.*`):

| arm | layer | observations | IC mean | IC std | avg names per quantile |
|---|---|---|---|---|---|
| PIT | original-process | 13,404 | −0.01166 | 0.1878 | 14.7 |
| PIT | common-observation | 12,999 | −0.01120 | 0.1911 | 14.3 |
| restated | original-process | 22,642 | −0.00351 | 0.1614 | 24.7 |
| restated | common-observation | 12,999 | −0.01306 | 0.1877 | 14.3 |

- PIT arm: from original-process to common-observation, the 405 PIT-only
  observations leave the scored sample; IC mean is −0.01166 and then −0.01120.
- Restated arm: from original-process to common-observation, the 9,643
  restated-only observations leave the scored sample; IC mean is −0.00351 and
  then −0.01306.
- IC gap by layer: original-process +0.00815; common-observation −0.00187.
  LS-Sharpe gap by layer (`ls_sharpe_gap`, per observation): +0.1094; +0.0534.

The two layers' gaps are reported side by side; they are not combined.

## Common-support versus common-observation

For all four factors the common-support IC gap agrees with the
common-observation IC gap to four decimal places (bm_ratio −0.00036,
ep_ratio +0.00163, roe +0.00265, asset_growth −0.00188 at
`layers.common-support.ic_gap`), and the stored LS-Sharpe gaps of the two layers
are equal, in a run where neutralisation was off (`neutralised: false`).

## Conclusion

TODO (author).

## What this cannot show

- **Significance.** The archive stores no per-date IC series, only date lists
  and summaries, so no standard error or t-statistic can be computed from it.
  The 0.005 threshold is a preconfigured diagnostic trigger, not a test.
- **A decomposition.** Layer gaps are not value and sample parts and are not
  added or subtracted ([VINTAGE_COMPARISON.md](VINTAGE_COMPARISON.md)).
- **A pure restatement effect.** The restated arm relaxes filing visibility, so
  the gap mixes value, availability and processing changes.
- **A cohort or market-wide result.** The common set is selected. The store is
  `diagnostic_scale` with `declared_research_evidence: false` and
  `declared_survivorship_prone_share: 1.0`; the roster is not verified
  historical membership. Research gates (`research_gates`):
  historical membership and terminal outcomes `UNRESOLVED`; post-publication
  out-of-sample, multiple testing, free baseline and trading costs
  `NOT_IMPLEMENTED`.
- **Industry-neutralised behaviour.** Neutralisation was off in this run.
- **The current code's output.** The run predates `0ce7911`; equality of
  factor outputs under the current restated read is not observed.
- **Generality across factors.** There are four fundamental factors; the other
  six are `NOT_APPLICABLE` on every layer.

## Reproduction fields

Source run: `examples/outputs/b_selected_200_rerun_20260909/demo_run.json`.

| item | field path |
|---|---|
| per-layer PIT / restated summaries | `vintage_comparisons.<f>.detail.layers.<layer>.{pit,restated}` |
| per-layer gaps | `vintage_comparisons.<f>.detail.layers.<layer>.{ic_gap,ls_sharpe_gap}` |
| per-layer status and reason | `vintage_comparisons.<f>.detail.layers.<layer>.{status,reason}` |
| outcome identity | `vintage_comparisons.<f>.detail.layers.<layer>.outcome_identity.status` |
| IC date lists | `vintage_comparisons.<f>.detail.layers.<layer>.metrics.ic.{pit_dates,restated_dates,identical_metric_dates}` |
| layer sample counts | `vintage_comparisons.<f>.detail.layers.<layer>.sample.*` |
| common-support cleaning and labels | `vintage_comparisons.<f>.detail.layers.common-support.{cleaning_input_sample,cleaning,label_join}` |
| arm sample comparison | `vintage_comparisons.<f>.detail.sample_comparison.*` |
| verdict and threshold | `vintage_comparisons.<f>.diagnostic_verdict`, `….detail.{material_gap_threshold,threshold_kind}` |
| universe exclusions | `vintage_comparisons.<f>.detail.universe_rows_excluded_{pit,restated}` |
| store identity | `database_sha256_after_run`, `database_bytes_unchanged`, `evidence.*` |
| grid and protocol | `configuration.*` |
| environment | `environment.*` |
| research gates | `research_gates.*` |

`<f>` ∈ {`bm_ratio`, `ep_ratio`, `roe`, `asset_growth`}; `<layer>` ∈
{`original-process`, `common-observation`, `common-support`}.
