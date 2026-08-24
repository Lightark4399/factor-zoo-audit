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

## Incident 6 — the same bug in a second place

**What happened.** The second live ingest crashed in `merge_asof` with
`incompatible merge keys dtype('<M8[s]') and dtype('<M8[us]')`.

**Diagnosis.** pandas infers different datetime resolutions depending on how a
frame was built, and `merge_asof` raises on a mismatch rather than coercing. The
identical failure had been found and fixed during the pipeline work, in
`build_panel`. It was fixed there and nowhere else.

**The fix.** Both keys normalised at the join. More usefully: the other join
sites were audited, which is what should have happened the first time.

**Constraint added.** A fix applied at one call site is not a fix. When a defect
turns out to be a property of a library rather than of one line, the response is
a search for the other instances, not a patch.

---

## Incident 7 — a default that truncated the data and looked like success

**What happened.** After the price fixes, the run downloaded 690 rows across
thirty tickers and reported success.

**Diagnosis.** That is about 23 trading days each. `yfinance.download` returns
roughly one month when no start date is given, and the code passed none. No
error, no warning — just a dataset too short for any factor in the project.

**The fix.** An explicit default start of 2010-01-01, and a `--start` flag. The
parameter is no longer optional in the sense that matters: omitting it now
produces fifteen years, not one month.

**Constraint added.** A default that silently truncates is worse than an error.
Where a library's default is a quiet subset of what the caller means, the wrapper
states its own.

---

## Incident 8 — a provider that answers 404 to a documented request

**What happened.** Stooq returned `404 Not Found` for `aapl.us`, `nvda.us`,
`googl.us` — the documented symbol format, over a plain residential connection,
with a browser User-Agent already set from incident 4.

**Why it was not simply fixed.** The development environment cannot reach Stooq
at all, so the correct request could not be determined empirically. Guessing at a
URL format and shipping it would have been a change with no evidence behind it.

**What was done instead.** The source order became a parameter, defaulting to
Stooq for the survivorship reason but overridable with `--price-source
yfinance,stooq`. The run report records which source supplied each ticker and
what share came from the survivorship-prone one.

**Constraint added.** When a dependency's behaviour cannot be verified from
here, the response is to make the choice visible and recorded rather than to
guess and hard-code. The report already carried `survivorship_prone_share` for
exactly this situation.

---

## Incident 9 — the guarantee was asserted by a check that did not test it

**What happened.** The first run on real data reported `VIOLATION` for the
book-to-market factor in one section and `PASS` in the next. The two sections
disagreed about the same factor in the same run.

**Diagnosis.** `assert_no_lookahead` did not do what its name, its docstring, or
the comment at its call site said. Those said it verified that no factor value
had used a filing published after it. What it actually did was re-derive, from
the raw table, how many rows a *naive* query would have read early — a fact about
the data, computed without reference to what this code had read.

So it flagged a violation while the point-in-time path was working correctly, and
`compare_vintages` said so. The counts gave it away: 12,844 violations against
3,010 checks, a ratio that cannot mean anything because the two numbers were
counted at different granularities.

**Why it mattered more than a mislabelling.** The project's central claim is that
its factors could have been computed when they claim to have been, and the
evidence offered for that claim was a check that never examined a single read.
Nothing was verifying the guarantee. Worse, the number it produced — the size of
the trap, which is the strongest finding here — was being reported as a failure
of the code that avoids the trap.

**How it was caught.** Not by a test. All of them passed, because they asserted
the behaviour the implementation had rather than the behaviour the name promised.
The coding agent noticed the contradiction between two sections of the demo
output and traced it back rather than reporting the run as successful.

**The fix.** Two functions where there was one.

`assert_read_path_respected` logs what `fundamentals_asof` actually returns — the
maximum filing date in each result — and checks it against the date that was
asked for. It is evidence rather than intention, and it fails if someone bypasses
the view, which the old implementation could not detect.

`measure_naive_trap` keeps the hazard measurement, renamed, with its counts
reported at consistent granularity. On the fixture it reads: 33 signal dates, 31
exposed, 899 trap rows, 93.9%. That is a finding — it is the reason the
bitemporal store exists.

**Constraint added.** A check's name, its docstring, and its implementation must
describe the same thing. When they diverge, the check does not merely fail to
help — it supplies false assurance, and the tests written against it lock that in.
For a project about false assurance this was a fitting place to find one.

---

## What the live data changed

The first thirty companies produced facts, not assumptions:

* **SEC coverage was complete** — 30 of 30, 33,599 rows. The `us-gaap` restriction
  costs less than the SPEC's caution implied, at least among large filers.
* **Impossible filing dates are real**, not a hypothetical. The exclusion count is
  now part of every run's report.
* **Free price sources are the fragile link**, not SEC. The fundamentals arrived
  on the first attempt and have been stable since. Prices have now taken four
  fixes across two runs — a missing User-Agent, an undeclared dependency, a
  default window of one month, and a provider returning 404 to its own documented
  format — and still depend on a source that drops delisted securities.

  That asymmetry is itself a finding worth stating: the point-in-time guarantee
  this project is built around rests on SEC data, which is well-formed and
  complete. The survivorship guarantee rests on price data, which is neither.

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
