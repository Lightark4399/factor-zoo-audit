# Stored disclosure metrics and historical interpretation correction

## What the old percentage meant

The legacy `restatements` SQL view selects `(cik, tag, period_start, period_end)`
keys whose earliest and latest filing dates differ. It does not require a value
change. `data_summary.restatement_rate` divides that view's row count by all
fundamental record rows, not by fact keys. Therefore the archived 27.5% is not
the fraction of fundamental rows numerically revised. The same interpretation
must not be applied to earlier percentages produced by that formula.

Historical archives are retained. Their arithmetic is not being replaced with a
new result. Current rendering no longer labels the legacy ratio as revised-row
share; historical bundles without new counts explicitly report them unavailable.
Legacy JSON fields and the SQL view retain their behavior for compatibility;
new bundles mark `legacy_restatement_scope` and add `disclosure_summary`.

## New contract: stored_disclosures_v1

- The fact key is `(cik, tag, period_start, period_end)` throughout.
- Multiple-filing-date keys have more than one distinct `filed` date. Their share
  uses all fact keys as denominator; same-day duplicate records do not qualify.
- A repeated key is comparable only when all stored values are finite, all units
  are non-null and identical, fact types are identical and known, and no single
  filing date contains conflicting finite values. Other repeated keys are
  counted as uncomparable, not unchanged.
- Among comparable repeated keys, more than one distinct exact value means
  changed. A change subsequently reversed still counts. No rounding threshold,
  materiality test or claim of a verified accounting restatement is implied.
- The changed share divides changed comparable repeated keys by all comparable
  repeated keys. Empty denominators yield null, not zero. The repeated population
  partitions into changed, unchanged and uncomparable keys.

These metrics describe stored records, not provider completeness. They do not
recover revisions absent from the database or establish economic comparability
beyond the stated metadata checks.

## Scope check: roe 184/184

The archived `roe.naive_trap` reports 184 exposed dates out of 184 checked dates.
The pipeline supplies post-universe raw factor keys, before label eligibility,
to `Store.measure_naive_trap`. Duplicate `(ticker, signal_date)` inputs are removed.
For declared tags, the diagnostic chooses the latest filing per `(cik, tag,
period_end)`, requires `period_end <= signal_date`, and counts records with
`filed > signal_date + grace_days`. The date numerator is the number of distinct
signal dates with at least one such record; the denominator is distinct supplied
signal dates. Same-value repeated filings can also expose future disclosure.
The archived roe diagnostic records `grace_days=2`; its qualifying records are
therefore beyond signal date plus two calendar days, not merely later that day.

This is the implemented period-end naive comparator, not a reconstruction of
every possible naive query or the interval-aware TTM factor. It does not group
by period_start and does not resolve tied filing dates deterministically by
accession. These limitations must accompany stronger interpretations. The
184/184 archive field consistency and query semantics were inspected; this
review does not recreate the original raw key panel or certify a fresh real-data
reproduction. It is neither the share of future rows nor evidence that PIT reads
leaked. Read-path checks are separate.
