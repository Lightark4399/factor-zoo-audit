# Selection contracts for the two remaining strict xfails — draft for review

Status: `DESIGN_DRAFT`, not implemented. Drafted 2026-09-26 against `51103b7`
on `claude/disclosure-readme-audit`. No production code, Store, archive,
qualification status or share A/B strategy was changed. Evidence and counts
come from [the selection evidence](validation/VALIDATION_SELECTION_EVIDENCE_20260923.md)
and from the read-only script `scripts/estimate_share_refusal.py`. That script's
real-store run has not completed (see §2.4).

Each contract fixes what must hold before an implementation is chosen. Both
offer two options: a **unified selection** that always returns one whole
stored record by a stated total order, and an **explicit refusal** that returns
nothing, with a counted reason, when candidates disagree.

---

## 1. Interval tie — `test_both_arms_select_the_same_row_when_filing_visibility_is_equal`

### 1.1 Sites (as of `51103b7`)

| Id | Site | Current selection | Tie that falls to storage or frame order |
|---|---|---|---|
| S1 | `001_schema.sql` macro `latest_fundamental_asof` (PIT latest; `bm_ratio` and `roe` equity) | `DISTINCT ON (cik, tag) ORDER BY … period_end DESC, filed DESC` | Rows equal on `(period_end, filed)`: different `period_start`, or same-date rows within one fact key |
| S2 | macro `fundamentals_asof` (PIT history; TTM income, asset growth) | `DISTINCT ON (cik, tag, period_start, period_end) ORDER BY … filed DESC` | Same-date rows within one fact key (different form, accession, frame or value) |
| S3 | view `fundamentals_restated` | as S2, without the `filed` cutoff | as S2 |
| S4 | `pipeline/run.py::compare_vintages`, inner `leaking_asof` (restated latest) | S3 frame (no `ORDER BY`) → `sort_values([cik, tag, period_end])` → `drop_duplicates(keep="last")` | Rows equal on `period_end`; frame order comes from S3's unordered output |
| S5 | same, inner `leaking_history_asof` | S3 rows returned whole | Inherits S3 |
| S6 | `factors/library.py::_ttm_value` | `sort_values("filed")` → `drop_duplicates([period_start, period_end], keep="last")` | Only if two rows for one exact interval reach it. S2 already returns one per fact key, so this arises only when several CIKs map to one ticker (unverified in the sample) |
| S7 | `factors/library.py` asset-growth annual pick | `sort_values([fiscal_year, period_end, filed])` → `drop_duplicates(fiscal_year, keep="last")` | Rows equal on `(fiscal_year, period_end, filed)` with different `period_start` or value. Same class of tie; the xfail does not cover it |

The strict xfail exercises S1 against S4. S2, S3, S5 and S7 are the same class of
tie. The contract below states them explicitly so that a fix to S1/S4 alone is
not mistaken for a fix to the class.

Store exposure measured on `data/fza_200.duckdb` (unchanged SHA-256 `66c60785…`),
from the evidence record, all as `(cik, period_end)` or `(cik, period_end, filed)`
groups:

- **`StockholdersEquity`**, the only tag on the latest path: 0 of 8,367
  restated groups have several `period_start`s; 19 of 21,861 same-date groups
  have several rows, and none of them differ in value.
- **`NetIncomeLoss`** and **`Assets`** use the history path, where several
  intervals per end date are intended and are not a tie.
- **Same-date conflicts within one fact key:** 74 repeated keys and 1 single-date
  key; none are on a tag the factors read.

On this Store, therefore, the tie is latent for current consumers. The contract
is prospective.

### 1.2 Option U — unified selection

1. **Total order.** Every site in scope selects by an order that extends to the
   full stored primary key `(cik, tag, period_start, period_end, filed, form,
   accession, frame)`, so the result cannot depend on insertion or frame order.
   - Latest read (S1, S4): `period_end DESC, filed DESC, <interval rule>,
     accession DESC, form, frame`.
   - Per-key reads (S2, S3, S5): `filed DESC, accession DESC, form, frame`.
2. **Interval rule (decision required).** One of: latest `period_start`
   (shortest interval), earliest `period_start` (longest interval), or a
   duration band matching the tag's `fact_type`. The contract only requires that
   the rule be written down and identical in both arms.
3. **Same order in both arms.** S1 and S4 use the same order. The only permitted
   difference between the arms is the `filed` cutoff.
4. **Whole record.** The returned row equals one stored row on every returned
   column. This already holds for S4 since `0ce7911`.
5. **Limit.** A total order makes the selection reproducible, not correct. An
   accession tie-break is arbitrary.

### 1.3 Option R — explicit refusal

1. **Refusal.** At the top rank (S1/S4: equal `period_end` and `filed`; S2/S3:
   equal `filed` within a key):
   - **more than one distinct interval** (`period_start`) → refuse with reason
     `interval_tie`, **even if the values are equal**. Equal values do not make
     two different accounting intervals the same fact;
   - within one interval, more than one distinct finite value, or a finite value
     mixed with a null → refuse with reason `same_date_conflict`;
   - one interval and one value, repeated only by form, accession or frame → a
     whole stored row chosen by Option U's total order, so record identity stays
     deterministic.
2. **Detect before `DISTINCT ON`.** `DISTINCT ON` keeps one row and discards the
   rest, so the conflict must be counted over the full top-rank candidate set
   first, for example with a window count in the same query. A check run on the
   output of S1–S3 cannot see what was already dropped. The same applies to the
   pandas sites: count before `drop_duplicates`.
3. **Same rule in both arms.** One arm refuses and the other does not only when
   their candidate sets differ, which happens only through filing visibility.
4. **Surface.** Refusal counts are reported next to the vintage comparison, and
   the read-path check is unchanged. Where the rule is enforced is a decision:
   SQL (`QUALIFY` with window counts over the tie rank), or a post-filter shared
   by the Python read methods, fed with the pre-`DISTINCT ON` candidates.

### 1.4 Test matrix

Every case also stores an **untied control key**, a different `(cik, tag)` with
one candidate. Every test asserts that the control key is returned, identically,
in both arms. A result in which both arms are empty therefore fails.

| # | Fixture | Option U expects | Option R expects |
|---|---|---|---|
| T1 | Two intervals, same `period_end` and `filed`, values 90 and 30, both filed before the signal | Both arms return the same accession, chosen by the written interval rule | Both arms refuse this key with reason `interval_tie`; the control is returned |
| T2 | T1 inserted in reverse order | The same accession as T1 | Same as T1 |
| T3 | T1 with the rule-preferred row's `value` NULL | The rule-preferred row, whole, with a null value (the consumer then drops it); no splicing | Refuse (finite value mixed with null) |
| T4 | Two different intervals with identical values | The same accession in both arms, chosen by the interval rule | **Refused** with reason `interval_tie`; equal values do not let different intervals through |
| T5 | Future-disclosure control, built **after** the interval rule is fixed: interval X filed before the signal; interval Y, same `period_end`, filed after the signal, and constructed so that the written rule ranks Y above X | PIT returns exactly X (Y is invisible); restated returns exactly Y. Both assert the accession, and the control key is returned in both arms | PIT returns exactly X (no tie in its candidates); restated refuses the key with reason `interval_tie`. The control key is returned in both arms, so an empty result fails |
| T6 | Same-date conflict within one fact key (S2/S3): same interval and `filed`, different accession and value | One row by `accession DESC`, the same in both arms | Refuse with reason `same_date_conflict` |
| T7 | S7: two FY rows with equal `(fiscal_year, period_end, filed)` and different values | The same row whatever the insertion order | Refuse; the factor yields no value for that key and reports the reason |
| T8 | All of the above | Each returned row equals a stored row on every column (the existing `as_rows` identity check) | Same, for the rows returned |

The existing strict xfail becomes T1/T2 under the chosen option. Until an option
is chosen, it stays a strict xfail.

---

## 2. Share-count row order — `test_attached_share_count_does_not_depend_on_input_row_order`

### 2.1 Target quantity per consumer, and what the Store lacks

| Consumer | Numerator | Candidate target for the share count (not chosen) | Missing from the Store |
|---|---|---|---|
| `bm_ratio` | `StockholdersEquity`; common-only attribution unverified | Conditional: an all-class value, if the numerator is company-level common equity | Class identifiers, class counts, unlisted-class prices, conversion ratios |
| `ep_ratio` | TTM `NetIncomeLoss`; common-only attribution unverified | Same conditional candidate as `bm_ratio` | Same as `bm_ratio` |
| `turnover` | Ticker `volume`; the class it covers is UNKNOWN | Shares of the same class as the volume | Listed-class counts; the class of the provider's volume |
| `log_mktcap` | None | Policy choice: issuer total or listed class | Either way, the class data above for multi-class issuers |

The Store cannot identify or verify share class for any row. No selection rule,
unified or refusing, can guarantee a class-correct count. BRK-B, a single
candidate of the wrong class, is untouched by either option.

### 2.2 Option U-shares — unified selection within a `(cik, filed)` group

Two orderings are kept separate.

**Policy ordering.** It decides which candidate *should* be used, and each step
is a decision:

1. latest `period_end`;
2. then the interval, `period_start` (share counts are instants, so normally
   `period_start = period_end`, but the rule must state what happens otherwise);
3. then a **namespace rule**. The current de-duplication keeps us-gaap on a
   shared stored key; preferring DEI would reverse that.

Candidates still differing in value after the policy ordering are the residual:
refused, or resolved by a further written rule.

**Deterministic tie-break.** It only makes the choice reproducible among
candidates the policy ordering treats as equivalent. It runs over the rest of
the full stored key, `(cik, tag, period_start, period_end, filed, form,
accession, frame)`, for example `accession DESC, form, frame`. It carries no
economic meaning and must never decide between different values.

**Pending policies** — these are not chosen here:

- a finite value mixed with a NULL candidate in one group: ignore the NULL,
  refuse, or treat as residual;
- a zero mixed with positive candidates, as in the nine undefined-ratio groups
  such as HOOD: exclude the zero, refuse, or treat as residual;
- whether a refusal may be bridged by the ten-day carry (§2.4).

### 2.3 Option R-shares — refuse any multi-value group

Every price row whose as-of `(cik, filed)` group has more than one distinct
finite value gets a null share count, with a counted reason.

### 2.4 Conservative-refusal sample loss (read-only estimate)

Method (`scripts/estimate_share_refusal.py`):

1. Build the refusal mask from the as-of share group within 400 days, the same
   semantics as `attach_shares_outstanding`.
2. Run the real library code for `log_mktcap`, `bm_ratio`, `ep_ratio` and
   `turnover` on the unchanged read-only Store, with only `prices()`
   substituted.
3. Count finite factor keys after the historical-universe gate, before the
   magnitude check and cleaning.

Two substitutions:

- **`zeroed_no_carry`** (refused count → 0). Every consumer drops non-positive
  values, and a non-null zero stops the carry. Its metric,
  `simulated_key_loss_zeroed_no_carry`, is the simulated key loss when no carry
  across a refusal is allowed. It is not a count of all exposure and not an error
  count.
- **`null_with_carry`** (refused count → NULL). The real ten-day carry may reuse
  an earlier row, whose share count comes from the previous filing. Whether that
  is acceptable is a decision, not an assumption. Its metrics are
  `simulated_key_loss_null_with_carry` and `kept_by_carry_value_changed`.

Input invariants are checked before counting. The script raises rather than
counting if one fails:

- tickers are unique in `securities`;
- price rows are unique per `(ticker, trade_date)`;
- the mask has exactly one row per price row, and the one-to-one merge keeps the
  row count;
- every price row has a refusal flag;
- universe keys are unique;
- each factor's output keys are unique.

Two report checks come afterwards: the carry adds no keys, and the zeroed keys
are a subset of the null keys.

Two refusal rules:

- all multi-value groups;
- only groups whose latest `period_end` is itself not unique.

The second is only the refusal half of a combined U + R rule. It does not
simulate the value changes that rule U would make elsewhere.

**Status: the real-store run is pending.** It was stopped by the host on
2026-09-26 because the machine ran critically low on memory (about 450 MB free
at start). It produced no output, and the Store hash was unchanged afterwards. It
was not restarted.

Fixture tests (`tests/test_share_refusal_estimate.py`) pass:

- **Exact-key test.** One ticker, a clean group filed 2019-12-15 and a two-value
  group filed 2020-02-25, checked for both `log_mktcap` and `turnover`:
  - 2020-01-31 is unaffected;
  - 2020-02-29 is lost when zeroed, but kept by the carry from row 2020-02-24,
    with the older 100-share value in place of 110;
  - 2020-03-31 is lost in both variants.
- **Duplicate-ticker test.** A repeated ticker is rejected.
- **Bounded control.** A bounded run on the synthetic fixture store, which also
  checks that the numerator memo is restored.

**Memory.** The real run holds the full `prices` frame in pandas (768,082 rows).
It copies that frame for each variant, and every factor pivots it into wide
panels. With four factors, two rules and three price variants, that is 24 factor
passes in one process, which is where free memory ran out. The script now takes
`--factor` and `--rule`, both repeatable, so one factor and one rule can run per
process. That is three passes, and the process exits between runs. The expected
bounded sequence is four separate processes, one per factor, starting with
`--rule refuse_multi_value`. Each would still load the prices frame once; the
peak was not measured. Only small fixtures were run in this batch.

| Factor | Current keys | Simulated loss, zeroed, no carry | Simulated loss, null with 10-day carry | Kept by carry, value changed |
|---|---|---|---|---|
| `log_mktcap` | pending | pending | pending | pending |
| `bm_ratio` | pending | pending | pending | pending |
| `ep_ratio` | pending | pending | pending | pending |
| `turnover` | pending | pending | pending | pending |

The only real-store figures already measured are from the evidence record.
There, 12,173 of 25,654 universe signal keys with a market-cap row use a row
from a multi-value group, with the latest end not unique for 290. That is
`_market_cap`-level exposure, before carry. It does not include `turnover`, it
does not include the numerator filters of `bm_ratio` and `ep_ratio`, and it is
**not an error count**.

### 2.5 Test matrix

| # | Fixture | U-shares expects | R-shares expects |
|---|---|---|---|
| S1 | The existing row-order case (two candidates, same `filed`) | Same count in both input orders, by the written order | Null in both orders, with a reason |
| S2 | Same values, different contexts | The same count; not refused | Not refused (one distinct value) |
| S3 | Zero candidate in the group | Per the pending zero policy | Refused (several values), unless the pending zero policy says otherwise |
| S3b | Finite value and NULL in one group | Per the pending NULL policy | Per the pending NULL policy |
| S3c | Same `period_end`, different `period_start`, different values | The written `period_start` step decides; not the tie-break | Refused |
| S4 | Single wrong-class candidate (BRK-B shape) | Unchanged. The test records this limit and does not assert correctness | Unchanged; same note |
| S5 | Refused group followed within 10 days by a signal date | Not applicable | Asserts the chosen carry policy: either the earlier row is used or the key is null |
| S6 | Group older than 400 days | Nulled by staleness in both options, as now | Same |
| S7 | Control ticker with a single-value group | Returned unchanged | Returned unchanged |

## 3. Decisions needed before implementation

1. Interval tie: U or R, and under U the interval rule.
2. Whether S7 (asset-growth annual) is in scope for the same change.
3. Share count: U-shares or R-shares; the namespace rule, the `period_start`
   step, the NULL-mix policy and the zero-mix policy.
4. Whether a refusal may be bridged by the ten-day carry.
5. A target quantity per consumer (§2.1) and a class-data source. Without them
   neither option is class-correct.
6. Whether and when to allow the real-store estimate. If allowed, run it
   bounded, for example `python scripts/estimate_share_refusal.py
   data/fza_200.duckdb --memory-limit 256MB --factor log_mktcap --rule
   refuse_multi_value`, one factor per process, to fill §2.4.
