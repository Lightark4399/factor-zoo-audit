# Commit attribution ledger

Status: `DIAGNOSTIC_ONLY`  
Assertion status: `NOT_AN_ASSERTION`

This ledger attributes the numerical effects of commits `770a065..583d7e9` on
the synthetic fixture. It is an investigation record, not a set of regression
expectations. Regression tests continue to assert target invariants rather than
captured historical outputs.

The machine-readable and factor-level tables are:

- `examples/outputs/commit_attribution_locked.{json,md}` — Python 3.12.13,
  pandas 3.0.5, and the complete research lock.
- `examples/outputs/commit_attribution_minimum.{json,md}` — Python 3.10.21,
  pandas 2.0.0, and the direct minimum dependency set.

## Result

No commit changed a layer outside its declared scope in either environment.
This does not mean every environment claim passed: the minimum-version checkout
has two independent compatibility blockers described below.

| Commit | Intended change | Observed attribution |
|---|---|---|
| `770a065` | Characterization only | No numerical changes. |
| `0991a06` | Historical-universe gate | All ten factors lost ineligible raw keys before magnitude and cleaning. Surviving z-scores changed, but panel keys and rank-based IC/portfolio results did not. |
| `9a2a193` | Explicit `pct_change` gap semantics | No delta under pandas 3.0.5. Under pandas 2.0.0 only `idio_vol`'s raw value hash changed; the affected rows were outside the historical universe, so eligible and downstream layers were unchanged. |
| `e66ab5c` | Market-data freshness bounds | Raw output changed for `idio_vol`, `mom_12_1`, `mom_6_1`, and `rev_1m`. Every observed change was removed by the universe gate; the fixture did not exercise a turnover change. |
| `9e06d2b` | Label-attrition reporting | Only the new native outcome breakdown appeared. Counts, panels, IC, and Sharpe were unchanged. |
| `1d51a59` | Market-session date semantics | Raw, eligible, and cleaned layers were unchanged. Panel labels, IC, and Sharpe changed for all ten factors, as intended. |
| `583d7e9` | Definition documentation | No numerical changes. |

The universe gate changed 39 or 546 surviving z-scores per affected factor in
the locked environment, with a maximum absolute shift of `0.0698474`. In the
pandas 2.0 diagnostic the largest pre-fix shift was `0.861323` for `idio_vol`,
consistent with the old default `pct_change` padding making the pre-filter ghost
values version-sensitive. The gate left final rank-based results unchanged on
this fixture, but it removed contamination from the reported panel predictions
and from non-rank consumers.

The date-semantics commit had the largest IC movements in `mom_6_1`
(`-0.015293`), `mom_12_1` (`-0.015121`), and `rev_1m` (`-0.014076`). Its largest
Sharpe movement was `mom_12_1` (`-0.096461`). These are attributed changes, not
evidence for or against the factors.

## Minimum-version compatibility blocker

The unmodified checkout is not runnable under the declared Python 3.10 and
pandas 2.0 floor:

1. Source and tests use the newer `ME` and `QE` frequency aliases. Pandas 2.0
   accepts the equivalent older aliases `M` and `Q`.
2. Factor code passes `future_stack=True` to `DataFrame.stack`; pandas 2.0 does
   not have that argument.

The attribution driver records this as `UNEXPECTED_COMPATIBILITY_BLOCKER` and
uses an explicit compatibility shim (`ME -> M`, `QE -> Q`, and the equivalent
single-level `stack(dropna=False)`) only so that the independent commit effects
can still be measured. The shim is not used by the application or tests and is
not evidence that minimum-version CI passes.

This blocker should be fixed and verified in a separate correctness commit
before factor-definition changes are allowed to refresh any baseline.
