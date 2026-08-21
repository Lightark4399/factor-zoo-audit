# SPEC

What this project asks, what counts as done, and what would count as failure.

---

## The research question

> Of the equity return anomalies published in the academic literature, what
> fraction still survives once you pass them through four gates?

1. **Out of sample** — the post-publication period
2. **Multiple testing** — Deflated Sharpe and FDR control, given that dozens were
   tested
3. **Free baseline** — the part obtainable with no predictive insight at all
4. **Trading costs** — at a range of stated assumptions

The output is a single table: one row per factor, columns running left to right
as `raw Sharpe → out-of-sample → after baseline → after multiple testing → after
costs`, each column a subtraction from the one before.

**This project does not search for new factors.** It measures the survival rate
of old ones. That distinction is the point: a repository claiming a new alpha
cannot be verified by a reader, whereas a repository measuring attrition among
published claims can be checked line by line against the papers it cites.

---

## Why this framing, and not "I found a factor"

Every quantitative repository on GitHub asserts that some strategy works, and a
reader has no way to verify any of it, so the default response is to ignore all
of it. The way out is not a better assertion. It is to deliver something whose
correctness is checkable without trusting the author.

Two properties make this project checkable:

* **Every factor is a reimplementation of a published definition**, with the
  citation attached. A reader who doubts the result can compare against the
  paper.
* **Every result carries an audit report** produced by
  [`backtest-audit`](https://github.com/Lightark4399/backtest-audit), which was
  built for exactly this purpose. The deliverable is not "trust me" but "here is
  what happened when I attacked my own numbers".

---

## Where the leaks are, and which gate catches each

The four gates above map onto specific mechanisms. Naming them in advance is
what stops the project from becoming an undifferentiated worry about "leakage":

| Mechanism | Gate |
|---|---|
| Accounting data revised after publication | point-in-time `as-of` join on `filed` |
| Universe assembled from present survivors | universe reconstruction by listing/delisting |
| Score obtainable from persistent level differences | free-baseline decomposition |
| Autocorrelation inflating significance | Newey-West, effective sample size |
| Best of N factors reported as if it were one test | Deflated Sharpe, FDR |
| A signal traded at a price that did not exist yet | execution-timing decay |
| A parameter choice that only works at one grid point | parameter-neighbourhood scan |

The first is the one specific to this project and the one most often botched. It
is handled **in the data layer, not by an after-the-fact check**: the
`fundamentals` table stores both `period_end` (the accounting period) and `filed`
(the date the filing appeared), and every factor reads through a view that
enforces `filed <= signal_date`. A factor physically cannot see a restatement
that had not been filed yet, which is a stronger guarantee than testing for it
afterwards.

---

## Acceptance criteria

A factor ships when all six hold. Partial satisfaction is not partial credit.

**1. Reproducible from an empty directory.** `make data && make demo` completes
on one machine within four hours. Anything that cannot be rebuilt from raw
sources is not a result.

**2. Controls do not fire.** For synthetically constructed honest factors, every
audit module must pass; for synthetically constructed leaky ones, the
corresponding module must flag. Both directions are tested, because a check that
fires on correct input teaches its users to ignore it.

**3. Point-in-time is enforced, not requested.** No factor's construction path
may read a row with `filed > signal_date`. An automated check asserts this
against the query plan, not against author discipline.

**4. Every factor has a hypothesis card, written before implementation.** The
card states the economic mechanism, the precise definition including timing, and
the falsification criteria. Those criteria must be *actually tested* in the
report — a card whose falsification conditions are never checked is decoration.

**5. The multiple-testing correction demonstrably bites.** At least one factor
must be significant on its raw test and not significant after Deflated Sharpe.
If none is, the correction is probably not wired up.

**6. The conclusion fits on one screen.** Three findings, stated in the first
screenful of the README, each traceable to a row of the main table.

---

## What would count as failure

Stated in advance so the project can be judged rather than admired.

**The audit misreports a control.** If a synthetically honest factor shows a
non-zero point-in-time gap, or a synthetically leaky one passes, the tooling is
wrong and every downstream number is void.

**A factor cannot be rebuilt from raw data.** If any number in the final table
requires a manual step, an undocumented cleaning decision, or a file that only
exists on one machine, it is not a result.

**The conclusion cannot be stated in one table.** If the finding needs pages of
qualification, the analysis has not converged and the project should be narrowed
until it does.

**Survivorship bias is present but unquantified.** It cannot be eliminated with
free data — see the limitations section. Failing to eliminate it is acceptable;
failing to measure and state it is not.

---

## Explicit non-goals

- **Not new-factor discovery.** No claim of alpha is made, sought, or implied.
- **Not a trading system.** No execution, no live data, no capital.
- **Not a claim that the surviving factors work.** Surviving four gates on
  historical US equities is weak evidence about the future, and the README says
  so.
- **Not a replication of any single paper.** Definitions follow the literature
  where possible, and every divergence is recorded rather than smoothed over.

---

## Known limitations, stated up front

**Survivorship bias cannot be fully eliminated with free data.** Free price
sources do not carry delisted securities. The mitigation is a universe rebuilt
from SEC filing history — a company that stops filing 10-Ks has almost certainly
left the market — cross-checked against Ken French's portfolio returns, which are
CRSP-based and free of the bias. The residual gap is reported as an estimate, not
assumed away.

**Factor definitions diverge across papers.** Book-to-market alone has several
defensible constructions. Where a factor has a Ken French counterpart, the
monthly correlation between this implementation and the official series is
reported; below 0.9 indicates an implementation problem rather than a factor
failing.

**XBRL tag coverage is incomplete.** Companies file custom extension tags, so
restricting to the `us-gaap` namespace loses some firms. The exclusion rate is
reported rather than hidden by silent dropping.

---

## Scope discipline

The largest risk to this project is the factor count. **Twenty factors with a
complete pipeline beat sixty at 60% completion**, and the second is not a
milestone toward the first — it is a different, worse repository. The first
release covers two to three factors per category; the rest are issues.
