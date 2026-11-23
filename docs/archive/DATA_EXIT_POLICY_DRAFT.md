# Historical membership and exit policy — review draft

Status: `OPTIONAL_RESEARCH_EXTENSION / NOT_IMPLEMENTED / OUTSIDE_B_DELIVERY`
Scope update 2026-09-08: no source acquisition, rights enquiry or exit-policy
decision is a pending prerequisite of B. The proposals below are retained for
context, not active implementation tasks. Reopening this extension would require
new approval and data acceptance. The two substantive data gaps remain UNRESOLVED.
Review update 2026-09-06: agreed conceptual corrections incorporated below.
AS-03 and the B diagnostic delivery are authorised; historical source selection,
any numerical exit-estimation rule and exit-policy implementation were not approved.
Policy ID: `historical_membership_exit_v1_draft`
Prepared: 2026-09-05. Source verification means the specific material described
below was checked, not that a vendor subscription or dataset was obtained.

This document is a proposal. It does not authorize an ingest, a purchase, a
source migration, an imputation, or promotion of an existing diagnostic report.
The user requested review before implementation.

## Decisions proposed for review

| Decision | Recommended policy | Approval still needed |
|---|---|---|
| Historical source | Prefer licensed CRSP security history and event/return data if accessible; evaluate Norgate as a conditional alternative. | Source and actual access entitlement. Neither is established in this workspace. |
| No licensed source | Build a bounded historical cohort from contemporaneous archived membership and primary event records; retain all selected securities through exit. | Named archive, snapshot date, population, follow-up dates, and sampling rule. Until completeness is demonstrated, this remains a case study/diagnostic. |
| Terminal return | `actual`, `estimated`, `undetermined`, with separate actual and estimate storage. Default to `undetermined` when support is absent. | Approve the rule set below; no universal numeric fallback. |
| Estimates | Disable estimates in the primary result initially; permit explicitly named sensitivity scenarios after calibration and approval. | Any particular estimate rule and its applicable event/exchange/date population. |
| Existing 200-company store | May produce a new diagnostic run with its original provenance intact. | It cannot be promoted by flipping `research_evidence`. |
| Evidence | Evaluate qualification per claim, metric, cohort and period; unresolved required outcomes block those claims. | Approve the dependency and reporting rules below. |

Increasing the sample from 200 to 500 is not a prerequisite. A larger
present-survivor sample cannot repair historical membership or terminal outcomes.
An archived fixed cohort answers a fixed-cohort question, not a market-wide
anomaly survival question. Sample size and statistical power remain limitations.

## 1. Source options and what has actually been verified

| Source | Supported by material checked | Access in this task | Remaining acceptance condition |
|---|---|---|---|
| CRSP US Stock Databases | Active/inactive securities, daily/monthly data, corporate actions, permanent security IDs; licensed delivery. [S1] | Product documentation accessible; licensed data access unverified. | Obtain permitted extract including historical identity, trading status, corporate events, return flags and format/version. Inspect actual exit cases. |
| Nasdaq Daily List | Nasdaq listings, delistings, name/symbol changes; history advertised from 1999, subscription access. [S2] | Public documentation accessible; historical files not obtained. | Useful event source, not complete US-market coverage or a terminal-return dataset. Check effective-date and announcement-date fields. |
| Norgate Platinum/Diamond US stocks | Delisted securities and historical index membership; the vendor expressly does not claim complete delisted coverage. A move to OTC is not necessarily in its "Delisted" category. [S3] | Public documentation accessible; entitlement/export not tested. | Confirm stable security IDs, exact dates, event settlements, adjusted-price semantics and membership API export. An index constituent series is not the full exchange universe. |
| SEC historical indexes/submissions + event filings | Public historical filing indexes and filer submission histories can find issuers absent from today's ticker map. CIK identifies a filer, not a share class. [S4, S5] | Documentation accessible; full historical reconstruction not performed. | Join archived listing records to securities; distinguish issuer and security. Filings alone cannot establish complete traded-security membership or exit consideration. |
| Existing `data/fza_200.duckdb` | Local sidecar records `diagnostic_scale`, `research_evidence: false`, 200 yfinance sources, zero Stooq sources and `survivorship_prone_share: 1.0`. | Already local. | Diagnostic-only for the declared project question. No automatic promotion. |

The current code starts with `SECClient.fetch_ticker_map()` then `head(limit)` or
a requested ticker subset (`src/fza/ingest/run.py`). `derive_filing_history`
uses the minimum/maximum **ingested fundamental filing dates**. The SQL
`universe_asof` treats those as membership boundaries. Neither date is verified
as the first/last trading session. New filings or a different set of retained
XBRL tags can therefore alter a putative exit boundary. Wiring this predicate
into the pipeline proved enforcement, not the economic validity of the predicate.

### Free-data fallback and bias disclosure

Start from a timestamped historical security roster, not today's ticker map or
a list of famous bankruptcies. Select the cohort before reading subsequent
returns. Record the complete roster and any deterministic sampling rule, then
track every selected security, including failures to obtain data. Do not replace
a missing name with a survivor or require eventual data availability to enter.

Use historical filings and exchange/issuer announcements to resolve identities
and events. Maintain a reconciliation ledger for every roster member. If an
archive has no completeness guarantee, explicitly narrow the claim; a filing
index is a discovery aid, not proof of a complete securities roster. [S4, S5]

Bias direction is `UNDETERMINED` unless established for the precise estimand.
Missing outcomes can change factor ranks, long and short exposures, weighting,
and the dates/companies entering IC. The signed effect on an arbitrary factor's
IC or long-short portfolio cannot be inferred from a count of missing names.
An event-selected case study can validate mechanics but cannot estimate an
unconditional anomaly survival rate. These are design deductions, not results
of a new empirical experiment.

## 2. Identity, information time, and membership

Proposed records use `security_id` (e.g. PERMNO where licensed), `issuer_id`,
`share_class`, and timestamped ticker/exchange aliases. Retain the source ID
and effective mapping interval. Do not treat ticker reuse as continuity or
duplicate issuer-level equity across classes without an explicit allocation.
CRSP documents permanent security-level identifiers for historical continuity. [S1]

Keep distinct fields for announcement/availability time, exchange-effective
membership, last executable session, final valuation date, and payment date.
Retain source, locator, acquisition timestamp, dataset release/hash, timezone,
correction history and whether the record was reconstructed retrospectively.

Membership governs formation; execution eligibility is checked again at entry.
A name may be eligible when a signal is formed but suspended before entry.
Exchange transfer, temporary suspension, cash acquisition, stock exchange offer,
bankruptcy and legal cancellation are separate event types. Exchange departure
does not by itself mean economic extinction. Subsequent event information may
be used to measure an outcome, never to select the earlier signal universe.

Use an independent exchange-session calendar for the proposed research universe.
The current union of observed quote dates cannot certify that a market-wide
missing data day was a holiday. Freshness is not a listing/delisting classifier.

Unknown membership remains a separate unresolved eligibility record; do not
relabel an unknown boundary as an observed exit or silently drop the security.
It blocks claims requiring a complete universe until resolved or explicitly
limited to a separately defined, disclosed cohort.

## 3. Terminal outcomes: structure and consumption

| Outcome state | `terminal_return_actual` | Estimate storage | Required evidence |
|---|---|---|---|
| `actual` | Finite observed/reconciled value | Empty in the primary record | Source event/price/payment record, units, reference valuation, effective and availability dates; adjustments reconciled. |
| `estimated` | Null | One or more rows keyed by `(event_id, rule_id, scenario_id)` with `terminal_return_estimated` | Approved rule/version, applicable population, literature locator, inputs, assumptions and sensitivity results. |
| `undetermined` | Null | No selected approved estimate | Explicit reason, missing fields, affected positions/claims and follow-up state. |

This table qualifies the **terminal component**, not the whole holding-period
return. `actual` denotes documented measurement rather than infallible truth. A vendor
may itself estimate a delisting payment; the adapter must preserve such flags.
An undocumented vendor convention is not sufficient to label a value actual.

Store estimates in a separate relation. Actual-only consumers receive only
actual values plus the unresolved-position manifest. Scenario consumers must
request a `scenario_id`, retain actual/estimated contributions separately and
label their combined output. Never use unconditional
`COALESCE(terminal_return_actual, terminal_return_estimated, 0)`.
Separate columns alone do not prevent misuse; explicit consumer contracts and
end-to-end rejection tests are part of the proposed implementation.

### Treatment by event

1. **Cash acquisition:** reconcile the received cash per share and any already
   accounted-for distributions to the last reference valuation. An announced
   deal price is not an actual completed settlement. Track the effective date
   and payment/availability date separately.
2. **Stock or mixed consideration:** retain conversion ratio, cash component and
   successor security ID. A transparent continuing-wealth series may follow
   successor shares; it is not a purchase selected using future returns. An
   assumed sale at a chosen price is an execution assumption, not observed cash.
3. **Transfer to OTC/another exchange:** use a verified continuous identity and
   supported observable prices if the holding policy permits them. Delisting
   alone is not grounds to set the value to zero.
4. **Bankruptcy/cancellation:** a verified zero recovery can produce an actual
   -100% terminal component; the words "bankrupt" or "delisted" alone cannot.
   Unknown recovery stays undetermined.
5. **Suspension/unavailable quote:** keep the open-position obligation and reason.
   The next available quote cannot be silently substituted for the scheduled
   horizon. A later final recovery does not establish an earlier horizon price.
6. **No entry execution:** label the signal as non-executable separately from a
   position established and subsequently lost. Track both; neither is an
   unexplained row deletion.

For disjoint intervals only, a price-path return `r` and terminal component `d`
combine as `(1 + r) * (1 + d) - 1`; this follows multiplication of wealth ratios.
Example: reference wealth 100 -> 80 -> cash 40 gives -20%, then -50%, and a
combined -60%, not -70%. Require reference prices/currencies/adjustments to agree.
Unknown `r` remains unknown even if `d` is observed.

Do not append a separate event loss to a total-return series that already
incorporates it. CRSP's SIZ-to-CIZ guide documents changed return conventions
and event placement; CIZ return/event flags must be inspected for the chosen
release. "CRSP" without a format and release is not a return specification. [S6]

Preserve the predeclared holding horizon and separate `terminal_component`
(actual/estimated/undetermined) from `horizon_extension_convention` (named rule).
For nonoverlapping intervals, the full wealth ratio is
`(1 + price_path_return) * (1 + terminal_return) * (1 + extension_return)`.
An actual payment alone does not establish an actual full-horizon return.

Two proposed scenarios, neither implemented or selected as the primary result:

- `CASH_ZERO`: retain verified available proceeds as non-interest-bearing cash.
- `PIT_EW_REINVESTMENT`: reinvest in a precisely defined equal-weight basket
  eligible and executable at the reinvestment time, not names later known to
  survive the sample. Basket scope, weighting, rebalancing, execution costs,
  subsequent exits and empty-basket treatment require an explicit contract.

Choose the primary convention with a reason before inspecting its comparative
performance; show the other as sensitivity analysis once both are executable.
Neither is inherently conservative or unbiased. The claim that the latter is
the usual Beaver–McNichols–Price convention remains UNVERIFIED; no checked
reference relationship is added on the basis of recollection.

Convention-extended full-horizon returns must retain a `CONVENTION_EXTENDED`
basis and scenario ID, not inherit `actual` from the terminal event. This alone
does not invalidate a claim about a strategy that explicitly defines that
convention; the proposition being tested must match it. Do not manufacture an
estimated event value simply because a portfolio strategy has a convention.

No early reinvestment at an assumed payment time. If proceeds arrive after the
horizon and no valid horizon valuation exists, that horizon's outcome is
undetermined even when eventual cash is known. Censoring does not grant a free
exit at the last quote.

## 4. Literature and estimates

Shumway (1997) documents missing delisting returns and omitted losses. The
publisher abstract supports the existence of the problem; it does not by
itself establish a universal -30% rule. Full calibration/method details for a
-30% proposal have **not** been verified here. Such a rule remains
`UNVERIFIED / NOT_APPROVED`. [S7]

Shumway and Warther (1999), publisher abstract, explicitly give -55% for
missing performance-related Nasdaq delisting returns in their study. This is
`VERIFIED_ABSTRACT` for that claim only. It does not justify applying -55% to
mergers, all exchanges, today's sample, or an arbitrary missing daily quote.
Application to this project still requires the full method, sample/event-code
mapping and user approval. [S8]

Default proposal: no constant imputation in the primary result. A future
approved sensitivity analysis must retain the same formation cohort, report
actual/estimated/unknown counts and weights by date, and show IC and portfolio
results for each explicit rule. Do not choose the scenario that best preserves
a factor's significance. A stress loss of -100% is not an estimate of truth;
zero is not a justified upper bound on every event's return. Without defensible
bounds report conditional scenarios, not a confidence interval.

## 5. Evidence propagation and headline eligibility

`actual / estimated / undetermined` describe an outcome record. They are not
interchangeable with a metric verdict or a factor's definition eligibility.

Each unresolved record must reference its formation key, holding key,
`affected_factors`, `affected_metrics`, `affected_claims`, severity, `blocking`,
and an `inconclusive_reason` such as `terminal_outcome_missing`,
`membership_unresolved`, `security_mapping_ambiguous` or `horizon_value_missing`.
Compatible words across repositories do not imply an implemented shared API.

For a predeclared cohort and period, while a necessary outcome affecting the
full-cohort IC claim is unknown, do not publish that point estimate as an
evidentiary conclusion. A
complete-case IC may still be printed as `DIAGNOSTIC_ONLY` with its selection
loss visible. For a portfolio claim, track formation weights before the label
join. Loss of an invested security cannot renormalise the remaining weights and
make the unresolved investment disappear. Unknown membership can affect
cross-sectional ranking even without a known portfolio weight.

This is a deliberate strict gate, not a missingness-percentage exemption. It
does not assert that every real dataset is incomplete forever. A bounded cohort
may be fully reconciled; unknown records may later be resolved. Paid data does
not automatically pass, and lack of CRSP does not logically preclude a valid
bounded study. The current 200-company selection does not meet the market-wide
claim's requirements. B is the diagnostic delivery, not a relabelled survival
headline. Signed bias assertions remain UNDETERMINED unless justified for the
particular estimand and assumptions; this does not override proven arithmetic.

Report dependency-specific qualification: an unaffected statistic may retain
its own status; an unresolved exit is not proof that every other metric failed.
Counts and universe diagnostics remain reportable. A factor survival numerator
cannot silently omit a factor with blocked outcomes. Keep definition eligibility
and outcome qualification separately visible, with pending/blocked counts.

All report entry points (stdout, saved report, real-store mode, fixture mode,
future exports) must preserve these qualifications. AS-03 was fixed on
2026-09-06: the demo reads source declarations and propagates diagnostic status
to all current outputs, without a research-promotion path. Outcome-dependent
qualification and future exporters still require implementation and tests.
See `ASSERTION_SCOPE_AUDIT.md`.

## 6. Implementation acceptance after approval

- Freeze source entitlement, dataset/format, dates, membership rule, security
  class and estimate policies in a versioned manifest before interpreting IC.
- Reconcile the complete historical roster: retained, unresolved and excluded
  with reasons. Price availability must not define membership retrospectively.
- Exercise cash, stock/mixed, exchange transfer, suspension, cancellation,
  missing event, entry failure and payment-after-horizon examples.
- Verify disjoint return compounding and prevent double counting a preintegrated
  return; a vendor estimate must never enter the actual-only field.
- Verify actual-only consumers reject an unresolved required position, and a
  scenario result names the rule in both structured output and every report.
- Verify an undetermined terminal event changes the dependent claim's
  qualification, never quietly the sample/weights.
- Keep property tests over supported input classes plus regression tests through
  `compute_factor`, `compare_vintages`, label construction and demo output.
- Publish diagnostics before/after any new policy without attributing a dataset
  replacement to a code change. Do not recompute the old 30-company report from
  a different dataset and call it the same baseline.

## Sources and verification scope

- **S1 — primary vendor documentation:** [CRSP US Stock Databases, Morningstar](https://indexes.morningstar.com/research-data-products/crsp-us-stock-databases), sections "Access Over 100 Years", "Permanent Identifiers" and subscription information; checked 2026-09-05. Capability/access description only, not a data audit.
- **S2 — primary exchange documentation:** [Nasdaq Daily List](https://www.nasdaqtrader.com/Trader.aspx?id=DailyListPD), Benefits & Features and Access Options; checked 2026-09-05. History, event scope, subscription; not terminal-return coverage.
- **S3 — primary vendor documentation:** [Norgate Data Content Tables](https://norgatedata.com/data-content-tables.php), "US Delisted" and "US Historical Index Constituents"; checked 2026-09-05. Explicit coverage limitations retained.
- **S4 — primary regulator documentation:** [SEC Accessing EDGAR Data](https://www.sec.gov/search-filings/edgar-search-assistance/accessing-edgar-data), historical indexes and CIK sections; checked 2026-09-05. Discovery and issuer identity only.
- **S5 — primary regulator documentation:** [SEC EDGAR APIs](https://www.sec.gov/search-filings/edgar-application-programming-interfaces), submissions and bulk-data sections; checked 2026-09-05. Public access and historical filing retrieval; not official trading dates.
- **S6 — primary vendor documentation:** [CRSP SIZ-to-CIZ cross-reference guide](https://www.crsp.org/crsp_pdf/crsp-us-stock-indexes-databases-siz-to-ciz-cross-reference-guide/), Chapter 1, "Monthly holding period returns" and "Daily primary data"; retrieved text checked 2026-09-05. Format differences and event-placement warning, not a tested adapter.
- **S7 — primary paper, abstract only checked:** [Shumway (1997), The Delisting Bias in CRSP Data](https://onlinelibrary.wiley.com/doi/10.1111/j.1540-6261.1997.tb03818.x). The -30% calibration is not certified by this review.
- **S8 — primary paper, abstract checked:** [Shumway & Warther (1999), The Delisting Bias in CRSP's Nasdaq Data](https://onlinelibrary.wiley.com/doi/10.1111/0022-1082.00192). Supports the -55% statement for missing performance-related Nasdaq returns in that study; project applicability not approved.
