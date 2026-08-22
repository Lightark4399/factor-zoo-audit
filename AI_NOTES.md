# AI_NOTES

How this repository was built with AI assistance, what went wrong, and the
constraints added in response.

Every incident below actually happened. The sibling project
[backtest-audit](https://github.com/Lightark4399/backtest-audit) carries fourteen
more, and the pattern that dominates both is the same: a formula or an assumption
that was defensible on paper and wrong in contact with data, found by running it
rather than by reading it.

---

## Incident 1 — a shift in the wrong unit, failing silently

**What happened.** The momentum factor resampled prices to signal dates, then
shifted by 21 rows to mean "one month". On a month-end frame, 21 rows is
twenty-one months. The factor returned zero rows.

**Why it took a while.** The emptiness propagated. An empty factor produced an
empty cleaned frame, which produced an empty forward-return frame, whose columns
defaulted to object dtype, which finally failed four layers later as a merge type
error — pointing at the join rather than at the factor.

**The fix.** Windows are expressed in rows of the resampled frame, with the unit
stated in the code. `prepare_cross_sections` now raises on an empty factor: an
empty factor is always a bug, and it should surface where it happened.

**Constraint added.** A pipeline stage that cannot legitimately produce an empty
result must reject one rather than pass it along.

---

## Incident 2 — a comparison that varied two things at once

**What happened.** The point-in-time versus restated comparison substitutes a
leaking read path to simulate a naive query. The first version relaxed two
constraints: it ignored the filing date *and* allowed accounting periods that had
not ended yet.

**Diagnosis.** The second leak is cruder and swamped the first. The company whose
filing had been restated by 40% saw its factor value move 1.85%, because most of
the difference was coming from reading a future period rather than from reading
the revised value.

**The fix.** The substitution relaxes only the filing constraint — which is
exactly what a query against a mutable fundamentals table does. The gap then
measures restatement leakage and nothing else.

**Constraint added.** A comparison must vary exactly one thing, and a test
asserts the two arms score the same number of observations.

---

## Incident 3 — the constraint was right and the error handling was wrong

**What happened.** The schema enforces `filed >= period_end`: a filing cannot
predate the period it reports on. The first ingest of real SEC data — thirty
companies, 33,599 rows, 100% coverage — aborted on that constraint.

**Diagnosis.** Real XBRL contains impossible dates. Filers mistype period ends
and nothing in the submission process catches it. The constraint was correct; what
was wrong was that a data-entry error in one filing could abort an ingest of
thirty thousand rows.

**The fix.** Rows violating the constraint are dropped at parse time and counted
as `n_excluded_filed_before_period`. The constraint stays: relaxing it would let a
fact with an impossible date into the table, where a point-in-time query would
return it.

**Constraint added.** A validity rule belongs in the schema; handling its
violation belongs at the boundary. Enforcing one without the other means either
bad data gets in or good runs die.

---

## Incident 4 — a silent dependency and a silent refusal

**What happened.** The same live run downloaded **zero price rows for all thirty
tickers**, and reported it as thirty per-ticker failures.

**Two causes, both invisible from the output.** Stooq refuses requests without a
browser-like User-Agent and returns an HTML page with a 200 status — which fails
to parse as CSV, several frames from the cause. And `yfinance`, the fallback, was
referenced in the code but never added to the `ingest` extra, so every fallback
raised `ImportError`, which was caught and counted as "no data".

**The fix.** A User-Agent on the price session, an explicit check for an HTML
body, and `yfinance` declared where it is used.

**Constraint added.** A dependency referenced in an import must appear in the
dependency list, and a test now reads `pyproject.toml` to assert it. A per-item
failure handler must record *why*, not only *that*.

---

## Incident 5 — diagnostics that only survive success

**What happened.** The run in incidents 3 and 4 crashed inside the store. The
diagnostic report was written after the store load, so a four-minute download
produced no report at all — including the failure list that would have explained
the price problem immediately.

**The fix.** The report is written before the database and enriched afterwards.

**Constraint added.** Diagnostics are written as soon as they exist. A report
that only survives a successful run is a report for the case that needs it least.

---

## What the live data changed

The first thirty companies produced facts, not assumptions:

* **SEC coverage was complete** — 30 of 30, 33,599 rows. The `us-gaap` restriction
  costs less than the SPEC's caution implied, at least among large filers.
* **Impossible filing dates are real**, not a hypothetical. The exclusion count is
  now part of every run's report.
* **Free price sources are the fragile link**, not SEC. The fundamentals arrived
  first try; the prices needed two fixes and still depend on a source that refuses
  unfamiliar clients.

---

## Workflow constraints

**Every parser is tested against a recorded payload, not a live download.** The
development environment had no route to sec.gov, which forced the split between
network access and parsing. It is the better arrangement regardless: a test that
hits the network tests the provider's uptime as much as the code, and cannot run
in CI.

**Fixtures keep the source's quirks.** The recorded payload is a dict keyed by
index, carries restatements as repeated period ends, a custom namespace, an
unexpected unit, and a fact with no filing date. Those are what a hand-written
fixture omits and what breaks a parser.

**Live runs are expected to find bugs, and are run small for that reason.**
Thirty companies is enough to hit real data quirks and cheap enough that a
failure costs four minutes. All five incidents above came from one such run.
