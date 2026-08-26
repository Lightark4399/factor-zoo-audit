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
`assert_read_path_respected()` inspects what the reads actually returned and
confirms none was filed after its signal date, and runs in CI. Neither alone is enough: in a
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

Early. The data layer, the registry, the fixtures, and the factor library are
built and tested; the audit pipeline is in progress.

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
✓ SEC XBRL and price ingestion, parsers tested against recorded payloads
✓ Demo entry point: real store when present, fixtures otherwise
✓ Read-path verification distinct from hazard measurement
✓ Factor library: ten factors across eight categories, each with a hypothesis card
✓ Column coverage reported at load — an entirely null column names itself
✓ 110 tests, CI green
○ Audit layer wired to backtest-audit
○ Style orthogonalisation, factor structure (PCA), costs
```

See [PLAN.md](PLAN.md) for the build order and [SPEC.md](SPEC.md) for what would
count as failure.

---

## First real ingest

Thirty companies, run as the first live test of the ingestion layer:

```
securities         30
fundamentals   33,598
prices        121,341
restatements    8,999      (27% of fundamental rows)
coverage         100%
of prices, 100% came from a source that drops delisted tickers
```

Two things in that table shaped what came next.

**Nearly a third of fundamental rows were revised after first publication.** The
point-in-time machinery was built on the assumption that restatements matter; it
is now built on the observation that they are pervasive. A backtest reading a
mutable fundamentals table is reading revised figures for a large share of its
history.

**Every price row came from a source that drops delisted securities.** Stooq,
which retains them, returned 404 for its own documented symbol format from an
ordinary connection. The run reports that share rather than letting it pass, and
it is the project's largest known gap — quantified in the output of every run.

Getting to that table took seven fixes across three runs; they are recorded in
[AI_NOTES.md](AI_NOTES.md).

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
python -m fza.ingest.run --user-agent "Your Name you@example.com" --limit 30
```

SEC requires a User-Agent identifying you, with a contact address — it is a
condition of the fair-access policy, and requests without one are refused. The
run is throttled to ten requests per second for the same reason.

Start small. Thirty companies makes a failure cheap and legible; scaling up is a
flag change, not a different code path. The run writes a report alongside the
database recording coverage, exclusion counts by reason, and what share of the
prices came from a source that drops delisted tickers.

---

## License

MIT
