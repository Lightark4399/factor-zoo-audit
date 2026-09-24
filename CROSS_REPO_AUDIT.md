# Cross-repository audit results

## Observation-subset follow-up — 2026-09-08

| Failure class | Origin / pointer | Local result | Next gate |
|---|---|---|---|
| Concrete repair shape substitutes for the full abstract comparison constraint | backtest-audit AI_NOTES incident 6 at locally inspected `2e4b2b0`; full local narrative: [incident 18](AI_NOTES.md#incident-18--a-repairs-shape-displaced-its-broader-constraint) | `defect-found`: dates aligned, securities not intersected despite docstring promise; no-call embedded-share paths mislabelled as PASS | First correction adds sample/coverage disclosure; common-observation and common-support diagnostics remain separate work, not checked-clean |

No sibling file was edited. Claude Code owns its local verification result and
pointer back to incident 18. This observation does not establish a systematic
failure rate or a defect in the sibling's current release.

2026-09-09: common-observation and common-support diagnostics are now wired into
the local runner and report. Outcome/timing and metric-date checks accompany
the key checks; mismatch withholds dependent gaps. Synthetic controls and the
actual pipeline/CLI were verified in both supported environments. See
[validation](docs/validation/VALIDATION_20260909.md). This is not a new real-data comparison or
completion of the full regression / remaining delivery work.

Keep the original incident narrative in its originating repository. Each local
row records what was actually inspected here; links alone are not a result.

| Failure class | Origin | Factor-zoo result | Date | Evidence / next gate |
|---|---|---|---|---|
| Assertions scoped to the last failing artifact instead of the property | backtest-audit; new audit item supplied in the user's message (not present in the local sibling checkout) | `defect-found` | 2026-09-05 | [AS-01..AS-07](ASSERTION_SCOPE_AUDIT.md): matched-only environment assertions, missing runtime locator validation, real-store diagnostic provenance gap, release-smoke coverage and unsupported demo frequency default. See each item's disposition; this is not checked-clean. |
| Unknown required quantity replaced by an apparently observed number | Shared principle, user-supplied DSR comparison | `pending` — exit policy not implemented | 2026-09-05 | [Policy draft](DATA_EXIT_POLICY_DRAFT.md) separates actual/estimated/undetermined outcomes and blocks dependent claims. Outcome/DSR schemas have not been integrated. |

The backtest-audit checkout is owned by the other implementation task and was
not edited. This file does not claim that its latest remote commits, new audit
item or DSR implementation were independently reviewed. Its owner can link this
record and record their own result without duplicating this narrative.

## Follow-up verification — 2026-09-06

Local backtest-audit HEAD inspected: `2e4b2b024b9a6b27ae764d63b57c4e821063c75e`.
`src/audit/ingest/duckdb_store.py` defines `universe`; source/test search found
calls only in two assertions in `tests/test_pit.py`, not production consumers.
`src/audit/audits/survivorship.py` uses presence in the panel's final dates,
and the no-attrition branch returns `passed=None` with an explicit warning that
never-loaded delisted entities would be invisible. These specific observations
are independently checked, not the sibling owner's reported newer doc changes.

The reusable failure class is **a defined/tested historical-membership helper
does not establish its integration into delivered output**. The methods have
different names (`universe` and `universe_asof`), and the sibling panel audit
explicitly requires an already-correct input universe. It must not be described
as automatically reconstructing missing history. Factor-zoo's gate is wired,
but its filing proxy still does not validate historical membership. AS-03's
analogous disconnected qualification has now been wired into all demo outputs.
No sibling code, incident document or API was modified here.

## Projection and documentation follow-up — 2026-09-07

| Failure class | Origin / upstream pointer | Local result | Next gate |
|---|---|---|---|
| Copied documentation output outlives its generated source | backtest-audit, user-reported docs-quote scanner; [upstream tests](https://github.com/Lightark4399/backtest-audit/tree/main/tests) | `pending`: generic scanner not yet received or reviewed; no independent implementation added | Reuse the upstream implementation once its committed path/ref is supplied, then record actual local findings |
| Qualification facts independently copied across delivery surfaces | Same upstream review; AS-03 local transport failure | `defect-found`: centralised in `fza.qualification`; dataset evidence, text, both JSON exits and README managed block project this policy | Projection tests include sentinel changes; tests cannot validate the truth of the policy itself |

Remote release independently checked using the GitHub connection: annotated
`v0.2.0` tag object `6f51943c49be5f7f1487f620c8621a9e0bdf8b3c` resolves to
`bdb62503b9d993f113e1979242d9501a2865ded1`.
[CI run 15](https://github.com/Lightark4399/backtest-audit/actions/runs/34045330621)
reports success for that commit. The complete tagged `MIGRATION.md` was read.
This verifies release identity and upstream CI status, not local integration.
The single-trial selection exception does not justify declaring one trial when
the search history is unknown. No bridge or dependency change is included yet.

Local follow-up found two concrete output defects: retained-percentage headings
and data differed by one column (`4968b1d`), and unordered SQL made naive-trap
examples change across matching-environment runs (`e341991`). The latter altered
example selection, not IC, LS Sharpe or counts. Both have synthetic/actual-CLI
regressions and passed the 12-case focused suite in both environments. See
`docs/validation/VALIDATION_20260907.md` for the failed reproductions, scope and pending full run.
The upstream default-branch tree was rechecked: still `bdb6250`; the generic
docs-quote implementation/ref has not yet been received. That audit item stays
pending, not checked-clean. No duplicate scanner or sibling edit was made.

## Current-interface documentation check — 2026-09-09

The user supplied the sibling's documentation-contract follow-up (`4cacd5d`);
that new commit and its reported 238 passes were not independently verified in
this pass. Local read-only inventory covered 19 tracked Markdown files and ten
cards: no file:line or #L source references were found. Twenty card locators
were retained (14 populated, six explicitly UNVERIFIED/null); this was not a
fresh verification of their papers. The 162 distinct candidate inline tokens
include paths and historical names, not 162 interfaces or defects.

Local result: **defect-found, corrected**. The bridge preflight named
`formation_date` although actual label output uses `formation_session`. The
current timing-field list is now an ordinary table checked against datetime
columns in generated labels; the existing vintage-layer table is checked against
the executable layer registry. Historical/proposed names and unstructured prose
are outside these tests. No sentence-specific regex or duplicate upstream
docs-quote scanner was added. Field existence does not establish semantic truth;
the separate label/holding-period controls remain necessary.


## Four-class wording and verdict check — 2026-09-23

Source: four audit classes supplied in the user's 2026-09-23 message. Their
originating sibling incidents were not inspected; backtest-audit was not read or
edited. Base: `c015b68`; locations below are path plus function at that commit.
Scope: `src/`, tracked Markdown outside `examples/outputs`, and the named tests.
Archived outputs and rendered bundles were not inspected. No verdict behavior,
serialized field or Python name changed.

| Class | Call path inspected | Local result | Evidence / not checked |
|---|---|---|---|
| Fixed threshold called a noise bound | `src/fza/demo.py::main` → `src/fza/pipeline/run.py::compare_vintages` (constant `MATERIAL_GAP`, verdict branches); `src/fza/render.py` vintage section; `src/fza/reporting.py::breadth_diagnostic`; `src/fza/pipeline/run.py::_check_legacy_magnitude` docstring | `no-defect-found` in inspected paths | Constant comment, verdict text, `threshold_kind` and renderer disclaim noise/significance; breadth cutoff is marked post-observation. Markdown hits are the incident-18 correction record only. |
| Heuristic called another estimator | `src/fza/pipeline/protocol.py::run_protocol` → `::fama_macbeth`; grep of `estimat`, `power`, `tstat`, `deflat` in `src` | `no-defect-found` | `tstat` is statsmodels HAC OLS with the Newey-West lag rule; `tstat_naive` is separately named. Display after a statsmodels failure (NaN `tstat`/`pvalue`) is a follow-up, not checked. |
| Non-finite result reported as PASS | `src/fza/pipeline/run.py::compare_vintages` branch order; `src/fza/pipeline/vintage.py::diagnostic_layers` (inner `evaluate`) and `::outcome_identity`; `src/fza/factors/plausibility.py::evaluate_rule`; `src/fza/pipeline/run.py::check_plausible_magnitude` | `no-defect-found`; test gap closed | Not-exercised, no-shared-date, unscorable-layer and non-finite-gap cases return `passed=None` before threshold comparisons. `evaluate_rule` never reports within-tolerance when nothing finite is bounded; with some finite values, non-finite rows are excluded from the share and counted in `n_nonfinite_or_missing`. The legacy guard counts ±inf as outside. New `tests/test_vintage_scope.py::test_exercised_shared_dates_with_unscorable_ic_is_inconclusive` covers an exercised path with a shared date and unscorable IC. |
| Arm name implies unverified qualification | `src/fza/pipeline/run.py::compute_factor` (`vintage="pit"`/`"restated"`), `::compare_vintages` (inner `leaking_asof`, `leaking_history_asof`); `src/fza/store.py::Store.fundamentals_restated`; `src/fza/demo.py::main` comparison keys; `src/fza/render.py` section title | `naming-ambiguity`; compatibility names retained | The `restated` arm is a **latest-filed comparison**: for each key it reads the latest-filed stored value with `period_end <= signal_date` and the `filed <= signal_date` constraint removed. It does not require that any value changed and is not a verified accounting restatement (the incident-19 population issue). The renderer already says the gap is not pure revision. Python/JSON names are kept for compatibility, by instruction. `pit` is backed by `assert_read_path_respected` only when the factor declares tags. |

The added test exposed a misattributed reason. In
`src/fza/pipeline/vintage.py::diagnostic_layers` (inner `evaluate`), the reason
expression tested date equality before finiteness. In the tested single-date case
the unscorable arm had no IC dates, so the verdict read `INCONCLUSIVE: metric_dates_differ.`.
Corrected in a follow-up by instruction: non-finite metrics now report
`metric_unscorable`; finite metrics on different dates keep `metric_dates_differ`.
Eligibility, INCONCLUSIVE status, threshold and finite gaps are unchanged; only
the reason string differs. `tests/test_vintage_layers.py` had asserted the old
reason for a constant-prediction (unscorable) case. It now asserts
`metric_unscorable` in both scored layers, and a separate two-date case with
finite ICs on different dates asserts `metric_dates_differ`. The comparator test
asserts the full verdict. Against the pre-fix `vintage.py`, the two unscorable
tests fail and the date-misalignment test passes. Archived bundles are not
regenerated and may carry the old reason.

Follow-ups, deliberately not changed here:

- `compare_vintages` inner `leaking_asof` sorts by `period_end` only before
  `.last()`; keys sharing a period end with different `period_start` have no
  stated interval choice (compare the naive-trap limitation in
  `docs/DISCLOSURE_METRICS.md`).
- `fama_macbeth` HAC failure: how NaN `tstat`/`pvalue` are displayed.
- Share-count candidates and interval ties: evidence, counts and options in
  [VALIDATION_SELECTION_EVIDENCE_20260923](docs/validation/VALIDATION_SELECTION_EVIDENCE_20260923.md);
  no selection rule changed.

### Read-only disclosure reasons on the available store — 2026-09-23

`src/fza/disclosure.py::uncomparable_reason_counts` adds multi-label reasons for
repeated keys that `disclosure_summary` cannot compare: non-finite or missing
value (NULL, NaN, ±inf), missing unit, mixed units, mixed fact types, unknown
fact type and same-date conflict. Reason counts may overlap and must not be
summed; their union must equal `uncomparable_repeated_keys`. It is not wired into
demo bundles. Fixture tests in `tests/test_disclosure.py` check hand-derived
reason counts, the overlap and union agreement.

`scripts/disclosure_readonly_summary.py` opens the store read-only with
`threads=1` and a DuckDB memory limit (script default 512 MB; this run passed
`--memory-limit 256MB`), checks the fundamentals schema first and
prints aggregates only. It exits 2 when `fundamentals` is absent, a required
column is missing, or a required non-null column is nullable; it does not
validate every schema constraint. It exits 1 when either consistency check
fails, still printing the counts and `failed_checks`. Tests
cover success and each deliberately broken check. On `data/fza_200.duckdb` (SHA-256 `66c60785…12d9`,
unchanged before and after; 201,112 fundamental rows; key columns and
`fact_type` NOT NULL):

| Quantity | Keys |
|---|---|
| Fact keys | 91,641 |
| Multiple-filing-date keys | 55,240 (60.3% of fact keys) |
| Comparable, changed | 5,947 |
| Comparable, unchanged | 49,219 |
| Not comparable | 74, all with the same-date conflict reason; no other reason fired |

Changed share of comparable repeated keys: 10.8%. The three classes sum to
55,240, and the reason union equals 74. The 55,240 equals the legacy
repeat-date count in the archived selected-200 reports. That is consistent with
the same key definition, but this run does not establish that the store is
byte-identical to the one behind those archives. These counts describe stored
exact-value differences, not verified accounting restatements or provider
completeness. The store is labelled diagnostic, not evidence-eligible.

### Location of the 74 same-date conflicts — 2026-09-23

Read-only aggregate on the same store, hash unchanged before and after; only
counts printed. The population is the 74 uncomparable multiple-filing-date
keys; every row of the table below uses that denominator. A conflict key is a
repeated fact key with at least one filing date carrying more than one distinct
finite value. "Latest" means the key's
maximum `filed`. Two tag scopes are reported. Read-path tags are those passed to
the substituted fundamental read methods at the `src/fza/factors/library.py`
call sites: `Assets`, `NetIncomeLoss`, `StockholdersEquity`. Declared tags add
`CommonStockSharesOutstanding`, which `log_mktcap`/`turnover` declare but read
through the embedded price-table share count (read path not exercised).

| Quantity | Keys |
|---|---|
| Conflict keys | 74 |
| Conflict on the key's latest filing date | 0 |
| Conflict only on earlier filing dates | 74 |
| Keys with more than one conflict date | 0 |
| In read-path tags | 0 |
| In declared tags | 72, all `CommonStockSharesOutstanding`, none on the latest date |

Outside that population, one single-filing-date key also has conflicting
finite values on its only filing date (`CommonStockSharesOutstanding`, not a
read-path tag). It is not repeated, so it is neither among the 74 nor in the
changed/unchanged/uncomparable partition; it appears only in the total fact-key
count.

Zero on the latest date does not mean no point-in-time exposure: an as-of read
at a signal date between the conflicting filing and the next one would meet that
tie. That window, the effect on the embedded share count and how the price
ingest derives it were not traced. The SQL selection rule was not changed.
