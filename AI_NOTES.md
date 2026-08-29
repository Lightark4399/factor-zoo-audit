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

## Incident 10 — the same lesson, reintroduced by the fix for it

**What happened.** The fix for incident 9 added `ReadRecord.signal_date` to log
what each point-in-time read returned. On real data every one of 184 signal
dates reported a violation.

**Diagnosis.** The field held two different quantities depending on who was
reading it. `book_to_market` subtracts its declared two-day lag before calling
`fundamentals_asof`, so what got logged was the date actually asked for.
`assert_read_path_respected` then subtracted `grace_days` again, requiring
filings to predate a date two days earlier still. The lag was applied twice.

**Why it matters more than an off-by-two.** Incident 9's constraint was that a
check's name, its docstring and its implementation must describe the same thing.
This was that same failure one level down: a single field name carried both "the
day the factor wants to predict" and "the day it actually queried", and the
recorder and the checker each read it as the one they meant. The fix for a
naming failure contained a naming failure.

**The fix.** Two fields where there was one. `requested_asof` is what was passed
to the view; `intended_signal_date` is the day the factor is forecasting.
`respects_asof` uses the first, which is the read path's own contract;
`assert_read_path_respected(grace_days)` uses the second, so a declared lag is
subtracted exactly once.

**What this bought beyond removing a false alarm.** `filing_lag_days` was
previously decoration — nothing verified that a factor declaring a two-day lag
actually applied one. It is now enforced: a test constructs a read where the
factor forgot the subtraction, confirms the read path itself is clean, and
confirms the check fails only once the declared lag is taken into account.

**Constraint added.** When one name is ambiguous between two quantities, the
ambiguity will be resolved differently by each reader. Splitting the field is
cheaper than any amount of documentation, and the second quantity usually turns
out to be the one that makes a declared invariant enforceable.

---

## Incident 11 — one null column, four factors, and an error that named the wrong thing

**What happened.** The first run of the full factor library against real data
produced results for six factors and nothing for four. Each of the four reported
`factor produced no values`.

**Diagnosis.** The four were exactly the four that read `close_adj`, and that
column was null for every row in the store. Recent `yfinance` versions drop
`Adj Close` unless the request is shaped a particular way, and the fallback was
written as a dictionary `.get()` default that did not fire under the shape the
library actually returned.

**Why the error was unhelpful.** The pipeline's refusal to pass an empty factor
along — added in incident 1, and correct — reports the factor that produced
nothing. Here the factor was fine. Finding the shared cause required lining up
which factors read which column and noticing that the split was exactly along
`close` versus `close_adj`.

**The fix, in three places.** The ingestion fallback is now explicit rather than
a `.get()` default. `_wide` raises when a requested column is entirely null,
saying so and pointing at the diagnostic. And `Store.column_coverage` reports the
non-null rate of every column, printed by the ingest as a warning and by the demo
as a section.

**Constraint added.** A silent null column is the ingestion equivalent of a
silent exclusion, and this project already refuses to allow those. Coverage is
now reported at the point of load, before anything downstream can fail in a way
that names the wrong component.

**A note on where the error surfaced.** Incident 1's constraint — an empty result
must be rejected where it happens — was doing its job. It localised the failure
to the factor layer, which was as far as it could see. Localisation is not
diagnosis: a check can only name the layer it guards, and pointing one layer
further up requires a check at that layer too. Hence the coverage report.

---

## Incident 12 — a broken quantity that produced the expected result

**What happened.** On real data `bm_ratio` returned an IC of +0.0365 with a
monotonicity of +0.70 — a value factor behaving the way the value literature
says it should. `log_mktcap` returned +0.0831 and +0.90, the strongest row in the
table. Both were computed from a market capitalisation that was wrong for every
company on every date.

**How it was found, which is the part worth recording.** Not by looking at those
ICs. They were unremarkable in the direction that invites no scrutiny. It came
out of a diagnostic written for an unrelated question — whether `bm_ratio`'s
unearned advantage of -0.0013 was a real measurement or an inert leaking path
— which happened to print the five largest raw factor values on its way to
answering. The top row read `AAPL 2014-06-30  5752.68`. A book-to-market ratio
lives between roughly 0.1 and 3. The IC computed from that column was reported to
four decimal places and looked fine.

**Root cause (a): both price columns held adjusted prices.** Recent `yfinance`
versions adjust `Close` as well as dropping `Adj Close`. Incident 11 fixed the
missing column and did not ask what had happened to the one that remained. All
three call shapes were probed across Apple's 2020 split — `yf.download`,
`Ticker().history()`, and `Ticker().history(actions=True)` — and
`auto_adjust=False` restores the `Adj Close` column in every one of them without
restoring a raw series. There is no call that returns the unadjusted price, so it
is now reconstructed from the split history.

**Root cause (b): shares outstanding was read from the wrong namespace.** Eleven
of thirty companies had no share count at all. The number is a cover-page fact
that `us-gaap` does not define: Coca-Cola's `us-gaap` namespace carries 724 tags
and `CommonStockSharesOutstanding` is not among them, while
`dei:EntityCommonStockSharesOutstanding` carries 71 facts spanning 2009-2026. The
ingest was looking in the wrong place. The data had never been missing.

**What the fix did to the results.** `bm_ratio` went from +0.0365 to **-0.0336**.
`ep_ratio` went from +0.0169 to **-0.0382**. Both value factors changed sign. The
pre-fix signs agreed with the literature and the post-fix signs do not — and
the pre-fix numbers came from a market capitalisation off by a factor of about
four thousand. On the row that gave it away, the implied market cap was $20.9
million against an actual $80.0 billion. Had nobody asked about the 5752, this
table would have entered the README carrying two value factors that agreed with
expectations.

**An additional irony.** `_market_cap`'s docstring, at the time, read: *"The
unadjusted close is deliberate. Market capitalisation is a level at a point in
time, and the adjusted series has been rescaled by every subsequent split —
using it would make a firm's historical market cap depend on corporate actions
that had not happened yet."* The code described the error it was there to prevent
and then committed it. A docstring is a statement of intent, and nothing had ever
checked that the column it named held what it claimed.

**Constraints added.**

* **A result agreeing with expectations is not evidence that it is correct.**
  Agreement lowers the probability that anyone looks, which is precisely what
  makes it dangerous. The four factors that were wrong all looked reasonable; the
  one number that did not look reasonable was never printed by the demo.
* **Every factor needs a plausible-magnitude assertion.** Book-to-market between
  0.01 and 100, market cap between 1e6 and 1e13, returns between -1 and 10. A
  value outside physical range must raise, not yield a credible-looking IC. An
  out-of-range value is the only signal that survives a broken input, because
  every downstream statistic is rank-based or standardised and will happily
  report four decimal places on nonsense.
* **A change in an external API can move several fields at once.** Incident 11
  fixed "this column is empty" without asking whether the meaning of the
  neighbouring column had also changed. The question to ask of a provider change
  is not "which field broke" but "which fields moved".

### The magnitude check, and what it is known not to cover

The constraint above was implemented rather than filed: `plausible_range` on the
factor registry, checked in `compute_factor` before any cleaning, raising when
more than 1% of a factor's raw values fall outside it. Four factors declare a
range; six declare `None`, which the report renders as **undefined** and not as
passing — the same distinction the store keeps between a null share count and a
zero one. A guessed bound would be worse than the gap, because a range set too
wide never fires while making the table look guarded. That is the shape of
incident 9's failure, where a check's name and its behaviour had come apart.

Its coverage, stated so nobody has to infer it:

* **Caught:** a quantity wrong by orders of magnitude — the 5752 above, and
  anything else produced by a unit error, a mis-scaled column or a wrong
  denominator. A regression test reproduces incident 12's market cap and asserts
  the check refuses it.
* **Not caught:** a value that is wrong but physically ordinary, and any fault
  affecting fewer rows than the tolerance. Both live cases are below.

### Still open (1): share counts carried forward for a decade

*(Mitigated in incident 13 by a staleness bound. The account below is what
was known when this was written; the fault itself is not fixed.)*

Found by the magnitude check on its first run against real data, which is the
strongest argument for it. `bm_ratio` exceeded its range on 4.67% of rows and
`ep_ratio` on 4.01%, all from a single company.

**What it is.** SEC's own `companyfacts` stops reporting
`dei:EntityCommonStockSharesOutstanding` for multi-class issuers once they begin
reporting per class: Visa has 2 facts ending 2010-02-03, Mastercard 4 ending
2010-11-02, Berkshire 7 ending 2011-05-06. `attach_shares_outstanding` joins
as-of with no staleness bound, so `merge_asof` carries the last value forward
indefinitely — fifteen years, in Berkshire's case. Worse, the value carried is
941,481, the Class A count, while the price is Class B's. Berkshire's market cap
comes out at $141m in 2014.

**Scope.** Three of thirty companies. Every other company's share counts run to
2026.

**Why it is not fixed here.** It is a different fault from the two this commit
addresses, and the right fix is a design question rather than a correction: cap
how long a share count may be carried, and drop the row past that; or resolve
share classes properly, which needs a source the consolidated DEI tag does not
provide. Choosing between those decides what the universe contains, so it is not
a change to make in passing.

**What holds until then.** The magnitude check refuses to score the affected
factors rather than reporting a plausible number from them. That is the intended
behaviour: a run that stops is better than a table that is quietly wrong.

The first of those two options was taken. See incident 13.

### Still open (2): a split separates the price from the share count

The reconstruction fixed the price but not its counterpart. `shares_out` is the
last count *filed* as of the signal date, while the price is the one *quoted*
that day, and a split moves the two out of step until the next filing reports the
new count. Apple's 7:1 split took effect on 2014-06-09; at the 2014-06-30 signal
date the store pairs a post-split price of 92.93 with the pre-split count of
861,381,000, giving a market cap of $80.0bn against an actual $560bn — low by
exactly seven.

**Why the check above does not catch this one.** The resulting `bm_ratio` is
1.50. It is seven times wrong and sits in the middle of any honest range. The fix
is to rescale a filed share count by any split effective between its filing date
and the signal date, using the split history already downloaded for the prices
— which is tractable, and is the same data the reconstruction depends on.

That is the lesson of this incident recurring one level down: the number that
looks reasonable is the one that does not get checked.

---

## Incident 13 — the assertion caught something nobody was looking for

Incident 12 ended with a magnitude assertion and an argument for building one: a
constraint that cannot catch an accident that has already happened is decoration.
The assertion was written against incident 12's market cap and a regression test
proves it rejects it. Then it ran against real data for the first time and
stopped the demo on a fault this project did not know it had.

**What it caught.** `bm_ratio` left its plausible range on 4.67% of rows and
`ep_ratio` on 4.01%, every one of them the same company. Following it back:
SEC's `companyfacts` stops publishing `dei:EntityCommonStockSharesOutstanding`
once an issuer begins reporting per share class, so the tag ends at 2010-02-03
for Visa, 2010-11-02 for Mastercard and 2011-05-06 for Berkshire Hathaway B.
`attach_shares_outstanding` joined as-of with no staleness bound, so `merge_asof`
carried the last value forward — fifteen years, for Berkshire. And the value it
carried is 941,481, the **Class A** count, standing next to the **Class B**
price. Berkshire's market capitalisation came out at $141m in 2014.

**Why this one is more dangerous than incident 12.** Incident 12 was wrong for
every company by the same ~4000x, which is the kind of error that eventually
trips over something. This one is wrong for 3 companies out of 30 and exactly
right for the other 27, and every aggregate in the report absorbed it:

* The IC table was unremarkable. `log_mktcap` +0.0329, `bm_ratio` −0.0336 — the
  signs and magnitudes the size and value literature would predict.
* Winsorising clips the affected values back to the 99th percentile before any
  statistic sees them, and standardising then erases the units the error is
  denominated in.
* Every statistic downstream is rank-based, and a rank cannot tell 5,752 from 3.
  Three names out of thirty do not move a cross-sectional average enough to
  notice.

So the error was not merely undetected, it was *undetectable* by anything in the
pipeline except a check placed on the raw values before cleaning — which is
precisely where the magnitude assertion sits, and the reason it sits there.

**What was done: a 400-day staleness bound.** A count more than 400 days old is
written as null rather than carried forward. 400 is a year plus room for a late
filer or a changed fiscal year end; past that, a share count that has not been
refiled is not stale data, it is a number that is known to be wrong. An undefined
market cap is a smaller lie than a confidently wrong one, which is the same rule
that keeps an unknown share count out of a zero.

**The bound did not hold on its first attempt, because the same carry-forward
existed one layer down.** With `attach_shares_outstanding` fixed, the demo still
rejected `bm_ratio` — 4.96% of values outside the range, worst case BRK-B at
9,493 in 2026. The ingest was correctly writing null, and `_at_signal_dates` in
the factor library was forward-filling the null away: it fills a wide panel to
the end of the index with no limit, so the last defined market capitalisation
(June 2012) was carried to 2026, and the value drifted *further* out of range
every year as book equity grew against a frozen denominator.

That is incident 6 again — the same bug in a second place — and it is worth
naming precisely, because the two fills look identical and mean opposite things.
Filling a price across a day the stock did not trade bridges a *missing
observation*. Filling a share count across the years it was not filed
manufactures one. `_at_signal_dates` now takes an optional
`max_staleness_days`; it defaults to None so a price still carries as before,
and `_market_cap` and `turnover` pass 10 days, which covers a month end on a
holiday weekend and nothing else. `bm_ratio` fell to 0.88% out of range and
`ep_ratio` to 0.49%, both inside the 1% tolerance, and BRK-B's last market cap
is now 2012-05-31.

`turnover` had the identical fault and no plausible range declared, so nothing
would have reported it. It was fixed because the cause was understood, not
because anything caught it — which is the argument for declaring the remaining
six ranges rather than leaving them undefined.

**This is a mitigation, and the distinction matters.** It treats the symptom.
Berkshire's count was not wrong because it aged — it was a Class A count against
a Class B price on the day it was filed, and the bound only stops it once it gets
old. A real fix needs per-class share counts, which the consolidated DEI tag
cannot supply and which would take another source. Recording the bound as a fix
would leave the next reader believing the market caps are sound.

**The cost, measured, because it changes the sample.** The bound nulls 11,166 of
113,216 price rows and takes `shares_out` coverage from 85.5% to 75.6%. All
11,166 belong to the same three companies — their last usable count is
2011-03-10 (V), 2011-12-07 (MA) and 2012-06-08 (BRK-B) — so those three leave
every market-cap factor from then to 2026 and stay in the price-only factors
throughout. No other company loses a row, which is worth stating: the bound is
not quietly thinning the universe everywhere, it is removing exactly the rows
that were fabricated.

The cost shows up in the width of each cross-section and not in the number of
signal dates: the mean number of names carrying a market capitalisation falls
from 23.4 to 20.6, and all 184 dates still produce one. A count of dates — the
obvious thing to look at — would have shown this change as nothing at all. It is
in the README's limitations section for the same reason.

**What was also done: the report now has somewhere to put a failure.** Before
this, a factor whose magnitude check fired took the whole demo down with it, and
the obvious repair — catch the error and move on — would have deleted the row.
Both are wrong in the same way: the first hides nine working factors behind one
broken one, the second hides the broken one. The protocol table now carries a
`status` column (`OK`, `FAILED: magnitude`, `FAILED: empty`, `FAILED: <error>`),
a failed row keeps its place with its numbers withheld rather than invented, the
reason is printed underneath it from the exception's structured payload rather
than its prose, and the vintage section names the factor it could not compare
instead of silently omitting it. Catching an error and reporting it is not the
same as catching it and swallowing it; a check whose failure leaves no mark on
the report is the same decoration this incident was supposed to be about.

The factor table gained a `plausible range` column for the same reason. Six of
the ten factors have no declared range, and that is printed as `undefined` — not
blank, not omitted. An unchecked magnitude and a checked one must not look alike
on the page, for the same reason an unknown share count is null and not zero.

**The lesson, which is the one from incident 12 confirmed rather than repeated.**
The assertion was justified on the argument that a check earns its place by
catching a known accident. It did that, in a test. Its first contact with real
data then produced a finding — and the finding was of exactly the shape the
argument predicted: a quantity that was wrong in a way every downstream statistic
was structurally incapable of showing.

---

## What the live data changed

The first thirty companies produced facts, not assumptions:

* **SEC coverage was complete** — 30 of 30, 33,599 rows. The `us-gaap` restriction
  costs less than the SPEC's caution implied, at least among large filers.
* **Impossible filing dates are real**, not a hypothetical. The exclusion count is
  now part of every run's report.
* **Free price sources are the fragile link**, not SEC. The fundamentals arrived
  on the first attempt and have been stable since, failing once on a filer's
  typo. Prices have now taken five fixes — a missing User-Agent, an undeclared
  dependency, a default window of one month, a provider returning 404 to its own
  documented format, and a silently null adjusted-close column — and still
  depend on a source that drops delisted securities.

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
failure costs four minutes. Incidents 3 through 8 came from two such runs, the
first and second live ingests; incidents 9 and 10 came from the first demo
executed against that data; incidents 11 and 12 from the first demo run with
the full factor library. In every case the code had passed its full test suite
immediately beforehand — and incident 12 would have passed any test suite that
did not assert on magnitudes, because every number in it was finite, plausibly
scaled and wrong.

Incident 13 is the exception that says something about the arrangement: it was
found by a check rather than by a run that failed. The check was added because
incident 12 argued for it, and it repaid the argument on its first contact with
real data. That is the only failure in this list that was caught before it had
produced a number anyone believed.
