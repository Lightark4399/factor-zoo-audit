# Cross-repository audit results

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
