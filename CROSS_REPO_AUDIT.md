# Cross-repository audit results

## Observation-subset follow-up — 2026-09-08

| Failure class | Origin / pointer | Local result | Next gate |
|---|---|---|---|
| Concrete repair shape substitutes for the full abstract comparison constraint | backtest-audit AI_NOTES incident 6 at locally inspected `2e4b2b0`; full local narrative: [incident 18](AI_NOTES.md#incident-18--a-repairs-shape-displaced-its-broader-constraint) | `defect-found`: dates aligned, securities not intersected despite docstring promise; no-call embedded-share paths mislabelled as PASS | First correction adds sample/coverage disclosure; common-observation and common-support diagnostics remain separate work, not checked-clean |

No sibling file was edited. Claude Code owns its local verification result and
pointer back to incident 18. This observation does not establish a systematic
failure rate or a defect in the sibling's current release.

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
`VALIDATION_20260907.md` for the failed reproductions, scope and pending full run.
The upstream default-branch tree was rechecked: still `bdb6250`; the generic
docs-quote implementation/ref has not yet been received. That audit item stays
pending, not checked-clean. No duplicate scanner or sibling edit was made.
