# Selected-200 rerun: prospective expectations

Prepared before launching the new real-data computation. Commit this document
before running. Results must be appended in a separate record, not substituted
for these predictions. This is an acceptance/diagnostic plan, not a statistical
preregistration or a test oracle made from old results.

## Preconditions and comparison anchor

- Full regression must finish in BOTH environments with no failures/errors/skips,
  including all fourteen demo tests. At preparation, locked full regression had
  271 tests with one failure: a retained explicit disclaimer phrase was absent.
  The phrase is restored without deleting or weakening the assertion. Minimum
  regression was still running and had displayed a failure. Neither is accepted.
- Compare to immutable `examples/outputs/b_selected_200_20260907/demo_run.json`,
  produced from `0bd03bf`. Do not overwrite its three artifacts.
- Local database: `data/fza_200.duckdb`, SHA-256
  `66c60785d1c085d4883f49796a33f20ad2bdf418072086fbfd938100666312d9`.
  This hash was rechecked while preparing this plan. Require the same hash after
  the run. No download, ingestion, write-back or roster expansion.
- Expected selected-roster hash:
  `66182cefc38d2f0291444d66d1fad828ed6d9797c212b6b3ef2b9e679b0d3af3`.
- Use all 185 monthly signal dates, 2011-04-30 through 2026-08-31; compare the
  entire ordered date list, not just endpoints. `max_dates=0`, minimum history
  15 months, horizon 21 sessions, execution lag 1, five quantiles. Never substitute
  a subsampled run. LS Sharpe remains per observation, not annualised.
- Locked environment: Python 3.12.14, pandas 3.0.5, NumPy 2.5.2, SciPy 1.18.1,
  statsmodels 0.15.0; lock hash
  `3014091ea5f7c2b51f3a1d867a674a65be84bf2d8e27348ad6b7b7e512df99f3`.
  Compare recorded provenance. Matching these fields alone does not establish
  identical hardware, reduction order or every unrecorded dependency.

## Expected numerical invariants

For all ten successful original PIT runs, expect identical observation/date
counts, universe/cleaning/label-loss counts, breadth summaries, IC, LS Sharpe,
monotonicity and other protocol outputs. Formula, preparation and scoring
algorithms have not intentionally changed since the archive. The new turnover
sign guard is expected not to reject valid existing outputs; if it rejects,
investigate the input, do not relax the guard to recover the old report.

Compare JSON values exactly first (nulls as nulls), separately from formatted
text. Report every changed numerical path, old/new value and absolute/relative
difference. No automatic tolerance grants acceptance. A difference is an
unexplained discrepancy until traced: it could be floating-point reduction/order,
changed eligibility, configuration or a defect, not automatically improvement or
automatically an algorithmic bug. Counts, roster and configuration must agree
exactly. Do not manufacture raw-key equality evidence: the old archive did not
record every raw intermediate required to prove it.

## Expected additions and changed interpretation

| Surface | Prospective expectation | What would require investigation |
|---|---|---|
| log_mktcap / turnover vintage | NOT_APPLICABLE, null comparison gaps; unchanged original PIT statistics | A research PASS or treating null as an observed zero |
| Four price-only vintage paths | Remain NOT_APPLICABLE; layers explicitly unexercised | New earned-looking PASS |
| bm_ratio / ep_ratio / roe / asset_growth original-process | Old shared-date, arm-specific scoring retained; compatible outcome identity expected to match | New blocked gap or changed original scores must be explained |
| Three-layer diagnostics | New common-observation/support scores, sample/key disclosures, outcome/holding-period checks and reasons | No numeric prediction for new layers; they are not components of a causal decomposition |
| Legacy economic guards | Same four intervals, counts, tolerance and blocking behavior; new structured rule metadata | Changed counts/thresholds or promotion to physical law |
| log_mktcap rule | DECLARED_UNBOUNDED, not PASS; no finite output-bound assertion | Invented finite bounds or claimed input verification |
| turnover rule | Nonpositive output check; expected zero violations | Positive values trigger investigation, not a blanket turnover <= 1 rule |
| mom_12_1 / mom_6_1 / rev_1m / total_vol_60d | UNDECLARED rule status; six legacy ranges still undefined is a different count | An undefined rule treated as passed |
| Research qualification | Historical membership and terminal outcomes remain UNRESOLVED; other four gates NOT_IMPLEMENTED | Any promotion merely because this rerun completed |

## Breadth markers, predicted from the OLD archive

The marker uses minimum retained date-by-quantile group size, not the entire
cross-section. Based on unchanged PIT breadth summaries, expect `[B]` only on
asset_growth (minimum 3). Expect no `[B?]`: all ten had retained quantile dates.
The other minima are mom_12_1 27, mom_6_1 27, rev_1m 26, log_mktcap 21,
total_vol_60d 26, turnover 21, bm_ratio 18, ep_ratio 17, roe 17. No marker means
only no low-group flag, not adequate power. These are prospective display
predictions from observed data, not newly predeclared scientific thresholds.

## Presentation and provenance

Expect all three newly generated artifact files to differ in bytes; do not call
that a numerical change. Code/rule manifest changes, generation time and new
sections are expected; dataset hash, selected roster, configuration, qualification
policy and runtime/lock identity should remain unchanged. Inspect actual fields
rather than assuming each artifact has a timestamp.

Retained-percentage alignment and disclaimer wording differ from the old archive.
Naive-trap example selection was made deterministic: individual examples may
change, while exposure-date and row counts are expected unchanged. An exposure
rate of 100% means every inspected date has at least one hazardous naive read,
not that all rows are future data or that the actual PIT pipeline leaked.

Read the new text report, including standard protocol, all vintage layers,
breadth, plausibility rationale and research gates. Check column alignment and
wrapping, not only maximum line width. Cross-check statuses/counts against JSON.
No README numerical headline is approved in advance. In particular, do not
preselect roe as an "unearned advantage" or select whichever new gap looks best.

## Execution and acceptance record

After the full-suite gate, use the locked Python to run `python -m fza.demo`
with the existing database and a NEW output directory. Record actual command,
source commit, start/end time, input/output hashes and runtime. Produce a separate
expected-versus-observed record with each item marked matched, unexpected or
not checked. An unexplained discrepancy blocks acceptance. Full regression plus
report generation alone is not completion: discrepancy review, artifact QA and
README consistency must also pass. None of these steps closes research gates.
