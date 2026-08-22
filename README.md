# factor-zoo-audit

**How many published equity anomalies survive contact with an honest test?**

Not a search for new factors. A measurement of the attrition rate among old ones,
as they pass four gates: out-of-sample, multiple-testing correction, free-baseline
decomposition, and trading costs.

The output is one table. One row per factor, columns running left to right:

```
raw Sharpe  →  out-of-sample  →  after baseline  →  after multiple testing  →  after costs
```

Each column is a subtraction from the one before.

---

## Why this framing

There is a genre of tooling that generates factors in bulk and reports the best
ones. **This project does the opposite: it counts the attempts and discounts the
result accordingly.** Reporting the maximum of forty noisy estimates as though it
were a single test is the mechanism that makes factor zoos look productive, and
the correction for it is the point of the exercise.

Every result carries an audit report from
[backtest-audit](https://github.com/Lightark4399/backtest-audit), built for this
purpose. The deliverable is not "trust me" but "here is what happened when I
attacked my own numbers".

---

## The design decision that matters

Accounting data is revised. A company files an earnings figure, then amends it
months later — and the amended figure is systematically different from the
original in ways correlated with what happened next. A backtest reading a
fundamentals database sees the amended value for every historical date, and has
therefore been handed information nobody had.

**This is handled in the data layer, not by an after-the-fact check.** The
`fundamentals` table stores both the accounting period and the filing date:

```sql
CREATE TABLE fundamentals (
    cik         VARCHAR,
    tag         VARCHAR,
    period_end  DATE,      -- the accounting period
    filed       DATE,      -- when the filing became public
    value       DOUBLE,
    ...
    PRIMARY KEY (cik, tag, period_end, filed, form),
    CHECK (filed >= period_end)
);
```

A revision is a **new row**, never an update. Factor code reads through
`fundamentals_asof(signal_date)`, which enforces `filed <= signal_date`, so a
factor physically cannot see an amendment that had not been published yet.

The fixture makes this checkable. One company's equity is filed, then revised to
60% of the original 180 days later:

```
  restatement lands on 2019-08-13, revision -40%

  as-of 2019-08-12   →  $1,026,000,000    (the original filing)
  as-of 2019-08-14   →    $615,600,000    (after the amendment)
  restated view      →    $615,600,000    (always, at every date)
```

The gap between running a factor on the first and on the third is the quantified
value of the look-ahead — one of this project's headline numbers.

**Both a guard and a check.** The view makes a leaking query hard to write;
`assert_no_lookahead()` re-derives from the raw table whether any consumed value
was filed after its signal date, and runs in CI. Neither alone is enough: in a
repository meant to be read and extended, someone will eventually open a
connection and write their own SQL.

---

## Every factor carries a hypothesis card

Registration fails without one. The card is written **before** the
implementation, because falsification criteria composed with the results already
in view are not criteria.

```yaml
factor_id: mom_12_1
category: momentum

economic_rationale: >
  Investors underreact to news, and information diffuses gradually, so past
  winners continue to outperform over intermediate horizons. The most recent
  month is skipped because short-horizon reversal is a distinct and opposite
  effect; including it contaminates the signal with a mechanism that works the
  other way.

persistence_conditions: >
  Expected to weaken in high-volatility regimes and to reverse sharply after
  crashes. Expected to decay post-publication if the effect is behavioural
  rather than compensation for risk.

falsification:
  - Decile returns show no monotonic pattern
  - The effect is concentrated in a single sub-period
  - The effect disappears after industry neutralisation
  - Performance at execution lag 1 is indistinguishable from zero
```

The two prose fields answer the question a BlackRock job description puts
directly: *why an alpha idea should work, what mechanism supports it, and under
what conditions it persists.* They are what separates research from search.

---

## Status

Early. The data layer, the registry, and the fixtures are built and tested; the
factor library and the audit pipeline are in progress.

```
✓ SPEC.md — research question, six acceptance criteria, falsification standard
✓ Point-in-time schema with restatement history
✓ Store with enforced as-of access, access logging, look-ahead assertion
✓ Universe reconstruction from filing activity
✓ Factor registry requiring a hypothesis card to register
✓ Synthetic fixtures with a known restatement and a delisting
✓ Cross-sectional pipeline: winsorise, neutralise, standardise, forward returns
✓ Standard protocol: quantiles, long-short, IC, monotonicity, Fama-MacBeth, sub-periods
✓ Point-in-time vs restated vintage comparison
✓ 35 tests, CI green
○ Ingestion from SEC XBRL and price sources
○ Factor library (20 to start, across eight categories)
○ Audit layer wired to backtest-audit
○ Style orthogonalisation, factor structure (PCA), costs
```

See [PLAN.md](PLAN.md) for the build order and [SPEC.md](SPEC.md) for what would
count as failure.

---

## Running it

The test suite and the demo need no network and no credentials — everything runs
on fixtures, so the correctness argument is verifiable by anyone who clones the
repository.

```bash
pip install -e ".[dev]"
make test
```

Ingestion is the only step that reaches the internet:

```bash
pip install -e ".[ingest]"
make data     # SEC XBRL + prices into data/fza.duckdb
```

---

## License

MIT
