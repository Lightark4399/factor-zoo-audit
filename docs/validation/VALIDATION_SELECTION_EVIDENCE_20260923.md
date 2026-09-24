# Share-count and interval selection — evidence for review

Base: `bb92bc1` on `claude/disclosure-readme-audit`, plus uncommitted files.
Recorded 2026-09-23 and extended 2026-09-24. This is evidence for review, not a
correction, an algorithm fix or a stage pass. No selection algorithm, database,
historical archive or verdict behavior was changed. No factor, demo or
selected-200 run was executed.

## Environment and commands

Locked environment `.diagnostic-envs/locked`, Python 3.12.14, pandas 3.0.5, ruff
0.16.6. About 390–650 MB of physical memory was free during the probes.

```
python scripts/probe_share_candidates.py data/fza_200.duckdb --memory-limit 256MB
python scripts/probe_share_candidates.py data/fza_200.duckdb --memory-limit 256MB --samples
python -m pytest tests/test_selection_evidence.py -rxX
python -m pytest tests/test_selection_evidence.py --runxfail   # shows the gap values
```

The probe sets DuckDB `threads=1` and hashes the file before and after. For
`data/fza_200.duckdb`, SHA-256 was
`66c60785d1c085d4883f49796a33f20ad2bdf418072086fbfd938100666312d9` before and
after every run in this record. The store is opened read-only with in-memory TEMP
tables. Count mode prints aggregates plus the rows of the nine undefined-ratio
groups. `--samples` prints the candidate rows of eight chosen groups. Count mode
reports `checks` and `failed_checks` in the same way as
`disclosure_readonly_summary.py`. It exits non-zero if any check fails or the
hash changes. The mapping rules mirror the production code named below. The probe
is an audit replica checked on synthetic fixtures, not against a factor run. The
store is labelled diagnostic, not evidence-eligible.

## Where share counts come from

`dei:EntityCommonStockSharesOutstanding` is the cover-page count in SEC's DEI
taxonomy; `us-gaap:CommonStockSharesOutstanding` is common shares outstanding in
the FASB's US GAAP taxonomy. The tag does not fix a fact's presentation or date.
Observed stored us-gaap rows carry the current period end and earlier comparative
dates (AAPL 2026-06-27 and 2025-09-27; CAT 2025-06-30 and 2024-06-30). The CAT
DEI row shares the 2025-06-30 date. Exact XBRL contexts were not parsed.
`ingest/sec.py` collects the us-gaap rows, current and comparative, then the DEI
rows under the same tag name. When a DEI and a us-gaap
row share the same stored de-duplication key, the us-gaap row is kept. That key
is `(cik, tag, period_start, period_end, filed, form, accession, frame)`; it
contains no XBRL class dimension. Rows with different keys are all kept. Of 178
companies with a share-count row, 116 have us-gaap rows, 170 DEI rows and 108
both. `ingest/prices.py::attach_shares_outstanding` then selects by `(cik, filed)`
only: it ignores `period_end`, accession and namespace, sorts on `filed` alone,
and `merge_asof` takes whichever tied row is last.

## Counts, each with its unit and denominator

| Unit | Denominator | Count |
|---|---|---|
| Share-tag fact keys `(cik, tag, period_start, period_end)` | 12,387 keys | 1,690 multiple-filing-date; 72 of those with a same-date conflict; 1 single-filing-date key with a conflict |
| `(cik, filed)` disclosure groups | 8,622 groups | 4,374 multi-row; **4,334 with more than one distinct finite value**; 0 mixing non-finite with finite |
| Multi-value groups | 4,334 | 119 companies; 4,325 one accession; all 4,334 span several `period_end`s; 3,859 mix DEI and us-gaap, 471 us-gaap only, 4 DEI only; 73 contain a conflict within one fact key |
| Same | 4,334 | Latest `period_end` has one distinct finite value: 4,261 (105 of them on several rows); several values: 73; none: 0 |
| Same, max/min ratio (defined only when every finite candidate is positive) | 4,334 | <1.01: 1,893; 1.01–1.1: 2,142; 1.1–2: 247; ≥2: 43; **undefined: 9** (all with a zero candidate; none negative). The five bins sum to 4,334 |
| Stored price rows `(ticker, trade_date)` | 768,082 rows | 581,033 with a group within 400 days, all of them with a stored share count; **272,334 exposed** to a multi-value group (119 tickers) |
| Price rows with a stored share count | 581,033 | **1,022 store `shares_out = 0`**, across 9 tickers: BRK-B, CRWD, HOOD, ICE, KO, MS, NEE, SHOP, T. Not all come from the nine undefined-ratio groups; KO, NEE and BRK-B have none |
| Exposed price rows with stored `shares_out` | 272,334 | Every stored value equals a candidate. Equals the unique latest-period value: 104,390. **Differs from it: 161,580.** Latest period not unique: 6,364 |
| Historical-universe signal keys `(ticker, signal_date)` | 31,027 keys (185 month ends) | 25,654 with a market-cap row within 10 days; **12,173 exposed** (115 tickers, 184 dates); **42** use a zero-share row, across 6 tickers (CRWD, HOOD, ICE, MS, SHOP, T), all among the 9 above |
| Exposed signal keys | 12,173 | Ratio ≥1.01: 6,803; ≥1.1: 763; undefined: 62. Equals the unique latest-period value: 4,690. **Differs: 7,193.** Latest period not unique: 290 |

Consistency checks on the real store, all `true`, `failed_checks` empty:

- the ratio bins sum to the multi-value groups;
- the listed undefined groups equal the undefined count;
- the exposed price-row split sums;
- the exposed signal-key split sums;
- the zero-share signal tickers are a subset of the zero-share price tickers.

### Reading the counts

- **161,580 rows / 7,193 keys** are observations that the stored count differs
  from the unique latest-period value in its group. They are not the maximum
  impact of any strategy, and not proof of error: the latest-period value may be
  the wrong context too.
- **6,364 rows / 290 keys** are listed separately. For these the latest period
  already carries several values.
- **12,173** signal keys are exposed to an ambiguous choice. That is not the
  number that would lose a market cap under refusal, because the ten-day carry
  can substitute an earlier row, and that has not been simulated. **290** is
  likewise residual exposure, not a demonstrated loss.
- "Unique latest-period value" requires exactly one distinct finite value at the
  latest `period_end`; the row count there is reported separately.
- The nine undefined-ratio groups were previously missing from every bin because
  the ratio used `nullif(min, 0)`. A zero share count gives a zero market cap. The
  replica, like `_market_cap`, treats that as a value.
- Signal keys follow `demo.signal_dates_for`, the securities first/last-filing
  gate and the ten-day `_market_cap` carry. They are counted before
  factor-specific eligibility and cleaning, and exclude `turnover`.

## The nine undefined-ratio groups, row by row

Candidate rows as stored (`CommonStockSharesOutstanding` rows, unit `shares`).
**Filings not opened**, except HOOD 2022-02-24, which is covered in the source
table below.

| cik | Ticker | filed | Accession | Form | Rows: namespace, period_end → value |
|---|---|---|---|---|---|
| 0000895421 | MS | 2015-08-04 | 0001193125-15-276529 | 10-Q | dei 2015-07-31 → 1,953,385,490; us-gaap 2015-06-30 → **0**; us-gaap 2014-12-31 → **0** |
| 0001535527 | CRWD | 2019-09-06 | 0001558370-19-008521 | 10-Q | us-gaap 2019-07-31 → **0**; us-gaap 2019-01-31 → 47,421,000 |
| 0001535527 | CRWD | 2019-12-06 | 0001535527-19-000011 | 10-Q | us-gaap 2019-10-31 → **0**; us-gaap 2019-01-31 → 47,421,000 |
| 0001535527 | CRWD | 2020-03-23 | 0001535527-20-000006 | 10-K | us-gaap 2020-01-31 → **0**; us-gaap 2019-01-31 → 47,421,000 |
| 0001571949 | ICE | 2015-05-05 | 0001571949-15-000007 | 10-Q | dei 2015-05-01 → 111,309,558; us-gaap 2015-03-31 → **0**; us-gaap 2014-12-31 → 113,000,000 |
| 0001571949 | ICE | 2018-10-31 | 0001571949-18-000014 | 10-Q | dei 2018-10-26 → 569,583,956; us-gaap 2018-09-30 → **0**; us-gaap 2017-12-31 → 583,000,000 |
| 0001594805 | SHOP | 2016-02-17 | 0001594805-16-000019 | 20-F | us-gaap 2015-12-31 → **0**; us-gaap 2014-12-31 → 39,310,446 |
| 0001783879 | HOOD | 2021-10-29 | 0001783879-21-000054 | 10-Q | us-gaap 2021-09-30 → **0**; us-gaap 2020-12-31 → 229,031,546 |
| 0001783879 | HOOD | 2022-02-24 | 0001783879-22-000044 | 10-K | us-gaap 2021-12-31 → **0**; us-gaap 2020-12-31 → 229,031,546 |

## Representative groups: Store observation, filing text, what stays undetermined

Filings were read with a web fetch through an extracting summarizer on
2026-09-24, not downloaded and parsed. Quotations below are the summarizer's
quotations of the pages. For all eight samples, `--samples` confirmed the
attribution: the first price row on or after `filed` has the listed group as its
as-of group, 0 days old, inside the 400-day window, and its stored value is one
of the group's candidates. Links marked "candidate" were generated from the
accession and not opened.

| Ticker, filing | Store observation | Filing text confirms | Still undetermined |
|---|---|---|---|
| **AAPL** 10-Q filed 2026-07-31, [index](https://www.sec.gov/Archives/edgar/data/320193/000032019326000020/0000320193-26-000020-index.htm) (opened), `aapl-20260627.htm` | dei 2026-07-17 → 14,594,180,000; us-gaap 2026-06-27 → 14,608,963,000; us-gaap 2025-09-27 → 14,773,260,000. Price row 2026-07-31 stores 14,773,260,000 | Cover: "14,594,180,000 shares of common stock were issued and outstanding as of July 17, 2026." Balance sheet (in thousands): "14,608,963 and 14,773,260 shares issued and outstanding" at June 27, 2026 and September 27, 2025. **The stored value agrees in amount and date with the prior fiscal-year-end comparative; the XBRL context mapping remains unverified** | None for class (single class on the cover). Which count a market cap should use is a policy question |
| **HOOD** 10-K filed 2022-02-24, [index](https://www.sec.gov/Archives/edgar/data/1783879/000178387922000044/0001783879-22-000044-index.htm) (opened), `hood-20211231.htm` cover, [R4 parenthetical](https://www.sec.gov/Archives/edgar/data/1783879/000178387922000044/R4.htm) | us-gaap 2021-12-31 → 0; 2020-12-31 → 229,031,546. Price row 2022-02-24 stores **0**, attributed to this group | **Listed class, confirmed from the filing.** The cover's Section 12(b) table registers "Class A Common Stock - $0.0001 par value per share" under trading symbol "HOOD" on Nasdaq. The cover counts, as of February 18, 2022, are Class A 740,034,469 and Class B 127,955,246. R4: Class A outstanding 735,957,367 and Class B 127,955,246 at Dec. 31, 2021, as class-qualified rows; the unqualified old "Common stock, shares outstanding" line is 0 then and 229,031,546 at Dec. 31, 2020. **The stored zero agrees in value and date with that old unqualified line; the context mapping is unproven. It is not the listed Class A count** | **Not established from the Store:** the Store keeps no class axis or member, and the XBRL instance was not parsed. That the stored 0 row is the fact behind R4's unqualified line is a value-and-date match, not a checked context mapping. No correct market cap is computed or claimed here; that needs the target-quantity decision below |
| **BRK-B** 10-Q filed 2011-05-06, [index](https://www.sec.gov/Archives/edgar/data/1067983/000115752311002891/0001157523-11-002891-index.html) (the `.html` form opened; the generated `-index.htm` form was reported broken for this filing and was not retried here), `a6706198.htm` | dei 2011-04-29 → 941,481 (only candidate). Price row 2011-05-06 stores 941,481 | Cover: "Number of shares of common stock outstanding as of April 29, 2011: Class A — 941,481; Class B — 1,061,009,224". **The stored value is the Class A count; the ticker is Class B** | Which XBRL context carried 941,481 (the instance could not be read in full). Any Class A/B conversion rule is not in the Store |
| **CAT** 10-Q filed 2025-08-06, [index](https://www.sec.gov/Archives/edgar/data/18230/000001823025000040/0000018230-25-000040-index.htm) (opened), `cat-20250630.htm`, [R5](https://www.sec.gov/Archives/edgar/data/18230/000001823025000040/R5.htm), [R41](https://www.sec.gov/Archives/edgar/data/18230/000001823025000040/R41.htm) | dei 2025-06-30 → 468,478,923; us-gaap 2025-06-30 → 468,500,000 (frame empty); us-gaap 2024-06-30 → 484,900,000. Price row 2025-08-06 stores 484,900,000 | Cover: "At June 30, 2025, 468,478,923 shares of common stock of the registrant were outstanding." R5: issued 814,894,624 less treasury 346,415,701 = 468,478,923. R41 ("Profit Per Share (Tables)"): "Shares outstanding as of June 30, (in millions)", 2025 → 468.5, 2024 → 484.9. That is where the displayed values come from. **The stored 484,900,000 matches R41's 2024 display value, a prior-year comparative** | R41 is a rendered statement, not a checked mapping from an XBRL context to these Store rows. The instance was not parsed, so the context, decimals and whether the us-gaap rows are the facts behind R41 are unverified. 468,500,000 and 468,478,923 are kept as distinct literal values; no economic conflict is claimed and no tolerance is introduced |
| GOOGL 10-Q filed 2026-07-23, candidate [link](https://www.sec.gov/Archives/edgar/data/1652044/000165204426000071/0001652044-26-000071-index.htm) | us-gaap 2026-06-30 → 12,230,000,000; 2025-12-31 → 12,088,000,000; no DEI row. Stored 12,230,000,000 | **Filing not opened** | Class coverage |
| JPM 10-Q filed 2012-08-09, candidate links [264](https://www.sec.gov/Archives/edgar/data/19617/000001961712000264/0000019617-12-000264-index.htm), [262](https://www.sec.gov/Archives/edgar/data/19617/000001961712000262/0000019617-12-000262-index.htm) | dei 2012-07-31 → 3,798,753,657 (10-Q); dei 2012-04-30 → 3,806,666,475 (10-Q/A). Stored 3,798,753,657 | **Filings not opened** | — |
| PLTR 10-K filed 2021-02-26, candidate [link](https://www.sec.gov/Archives/edgar/data/1321655/000119312521060650/0001193125-21-060650-index.htm) | us-gaap 2020-12-31 → 1,792,139,544; 2019-12-31 → 581,497,116. Stored 581,497,116 | **Filing not opened** | Class coverage; whether 581,497,116 is a prior-year comparative is inferred from its stored date only |
| V 10-Q filed 2010-02-03, candidate [link](https://www.sec.gov/Archives/edgar/data/1403161/000119312510020834/0001193125-10-020834-index.htm) | dei 2010-01-27 → 469,280,842 (only candidate). Stored 469,280,842 | **Filing not opened** | Class coverage |

"Multi-class issuer" for GOOGL, PLTR and V is general knowledge, not verified here.

## Interval ties on the tags factors actually read

| Tag / read path | `fundamentals_restated` `(cik, period_end)` groups with several `period_start`s | `(cik, period_end, filed)` groups with several rows / different values |
|---|---|---|
| StockholdersEquity — `fundamentals_asof`, `leaking_asof` in the restated arm | 0 of 8,367 | 19 / 0 of 21,861 |
| NetIncomeLoss — `fundamentals_history_asof` | 5,274 of 8,776 (5,233 with differing values) | 9,643 / 9,625 of 23,394 |
| Assets — `fundamentals_history_asof` | 0 of 9,096 | 15 / 0 of 19,152 |

In this store the only tag on the latest path (`StockholdersEquity`) has no
multi-interval groups and no value-changing ties, so neither the PIT tie-break
nor `leaking_asof` changes a value used by the current factors. The gaps are
latent for any factor reading a duration tag through the latest path.

## Scope of a later whole-row selection fix (not in this batch)

| Site | Current selection | Gap |
|---|---|---|
| `src/fza/sql/001_schema.sql` view `fundamentals_restated` | `DISTINCT ON (cik, tag, period_start, period_end) ORDER BY … filed DESC` | Whole rows, but same-date ties within a fact key have no ordering |
| same file, macro `fundamentals_asof(signal_date)` (history path) | Same key and order, filtered by `filed` and `period_end` | Same-date ties unordered |
| same file, macro `latest_fundamental_asof(signal_date)` | `DISTINCT ON (cik, tag) ORDER BY … period_end DESC, filed DESC` | Ties across `period_start`, and same-date ties, fall to storage order; observed in a scratch run to follow insertion order |
| `src/fza/pipeline/run.py::compare_vintages`, inner `leaking_asof` | View rows (no `ORDER BY`) sorted by `cik, tag, period_end`, then `groupby().last()` | Not a whole row: last non-null value per column; interval ties resolved by frame order, differently from PIT |
| same function, inner `leaking_history_asof` | View rows returned whole | Inherits the view's same-date ties |

Share-count selection in `ingest/prices.py::attach_shares_outstanding` is a
separate site with its own policy question.

## Tests (`tests/test_selection_evidence.py`)

The three strict xfails (`raises=AssertionError`) record **known gaps**. They are
not a pass or a stage acceptance:

| Test | Invariant | Observed with `--runxfail` |
|---|---|---|
| `test_attached_share_count_does_not_depend_on_input_row_order` | Same input rows in reverse order give the same `shares_out` | 90 vs 100 |
| `test_both_arms_select_the_same_row_when_filing_visibility_is_equal` | Two intervals, same end and filing date, both filed before the signal: PIT and restated arms read the same row | PIT 9-month 90 (accession 0); restated 3-month 30 (accession 1) |
| `test_restated_arm_returns_a_whole_stored_row` | The restated arm returns a stored row | `(2020-07-01, 90, accession 1)`, which does not exist |

The ordinary passing tests are:

- **probe fixture test:** units, latest-period classification, the undefined bin
  and its row listing, and the checks;
- **exit test:** a failed check makes the probe exit 1 while it still prints the
  counts;
- **attribution test:** a sample price row whose as-of group is a later filing is
  not attributed to the listed group.

## Decision boundary: what the share count is supposed to measure

A choice between A and B presupposes a target quantity, and none has been
chosen. The candidates are:

- **Issuer total common shares outstanding, all classes.** This is a conditional
  across-class candidate. If `StockholdersEquity` and `NetIncomeLoss` are
  company-level amounts attributable to common holders, an all-class market
  value is one candidate denominator for book-to-market and earnings-to-price.
  That attribution is unverified. The value would also need a price for each
  class, or a stated conversion between classes; the Store has neither.
- **Listed-class shares outstanding.** This is consistent with the one price
  series the Store holds, but values only part of the equity where there are
  several classes. If the numerator is company-level, the resulting ratio is not
  like-for-like for multi-class issuers.
- **Timing.** The DEI cover count's date may be later than or equal to the period
  end. Stored us-gaap rows include the current period end and earlier comparative
  dates; their exact XBRL mapping is unverified. This is a separate
  choice from the class question.

What the Store lacks for any of these:

- share class or series axis and member on share rows;
- a ticker-to-class mapping;
- prices for unlisted classes;
- conversion ratios;
- class-qualified counts, such as HOOD's Class A and B;
- the XBRL context identifier and `decimals` of each stored row.

It keeps `frame`, `form`, accession and namespace only.

**Scope of A and B.** Both address a group with several candidate values: which
to pick, or whether to refuse. Neither resolves a group with one candidate of the
wrong class. BRK-B has one stored candidate, the Class A count, beside a Class B
price. Neither option would change it, and a latest-period rule would not detect
it. A zero candidate is not resolved by ordering either. For HOOD 2022-02-24 the
latest-period candidate is the 0; a latest-period rule would keep it, while B
would refuse the group. The Store lacks class identifiers, so whether a stored
count is of the right class cannot be reliably identified or verified. This
record states the boundary only; no policy is implemented.

### By consumer (read-only code review, `src/fza/factors/library.py` at `9f6dfe6`)

Shared inputs:

- **Price.** `prices.close` is the price for the security's one ticker. For
  yfinance rows it is `Close` × the cumulative later split factor; that
  reconstruction depends on the split records yfinance supplies. For Stooq rows
  it is Stooq's `Close`, which the code comment says is already split- and
  dividend-adjusted.
- **Volume.** `prices.volume` is the ticker's volume. For yfinance rows it is
  `Volume` ÷ the same split factor, so it depends on the same split records.
- **Shares.** `prices.shares_out` is written at ingest by
  `attach_shares_outstanding`. It is an as-of join on `filed ≤ trade_date` with
  no filing lag, nulled beyond 400 days, and resolves same-date candidates by row
  order.

The Store does not record which source supplied a price row: **UNKNOWN** per
row. A local companion ingest report, `data/fza_200.report.json` (gitignored, not
archived), shows `n_stooq=0`, `n_yfinance=200` and `n_rows=768082` for prices.
It is not bound to the Store hash, so it is not row-level provenance.

| Consumer | Formula in code | Price / volume | Shares | Fundamentals | Consistent target (policy, not chosen) | Store lacks | A/B can / cannot |
|---|---|---|---|---|---|---|---|
| `_market_cap` (shared) | `close × shares_out` per ticker-day, pivoted, carried ≤ 10 days to each signal date | ticker `close` | `shares_out` | — | Depends on the consumer below | Class of `shares_out`; which source supplied `close` | Can: pick or refuse among one group's candidates. May pick the right class by chance, but cannot guarantee or show it; the Store lacks class identifiers |
| `log_mktcap` | `−log(mktcap)` where `mktcap > 0` | via `_market_cap` | via `_market_cap` | none (declares `CommonStockSharesOutstanding`, `filing_lag_days=2`) | **Policy**: issuer-total equity value or listed-class value — see below | Class counts, unlisted-class prices, conversion ratios | Same as `_market_cap` |
| `bm_ratio` | `StockholdersEquity / mktcap`; both `> 0` | via `_market_cap` | via `_market_cap` | Latest filed `StockholdersEquity`, read at signal date − 2 days | **Conditional candidate**: an across-class (issuer-total) value, if the numerator is company-level; common-only attribution of `StockholdersEquity` is unverified | As `log_mktcap`; also whether each filer's `StockholdersEquity` includes preferred or other non-common equity (**UNKNOWN**) | May select a count of the right class by chance, but cannot guarantee or verify class alignment with the numerator |
| `ep_ratio` | TTM `NetIncomeLoss / mktcap`; both `> 0` | via `_market_cap` | via `_market_cap` | TTM `NetIncomeLoss` from history reads at signal date − 2 days | As B/M: **conditional** across-class candidate; common-only attribution of `NetIncomeLoss` is unverified | As B/M; whether income is attributable to common only (**UNKNOWN**) | As B/M |
| `turnover` | `−(21-day rolling mean volume) / shares_out` where `shares_out > 0`; the mean needs at least 10 non-null observations (`min_periods = window // 2`); both carried ≤ 10 days separately | ticker `volume` | `shares_out` direct, not via `_market_cap` | none (declares the share tag, `filing_lag_days=2`) | Volume and shares in the same class terms: **listed-class shares** if the volume is listed-class only. Which class `volume` covers is **UNKNOWN** | Listed-class share counts; the class of the provider's volume | Can: stabilise the within-group pick. May match the volume's class by chance, but cannot guarantee or verify it |

**B/M and E/P.** The numerators are company-level fundamentals (the
`StockholdersEquity` and `NetIncomeLoss` tags) and the denominator is one
ticker's price times a stored count of undetermined class. Whether those tags are
attributable to common shareholders only is unverified. If they are company-level
amounts attributable to common holders, one candidate denominator is the market
value of all classes. For a single-class issuer the class question falls away, but other
questions remain besides the within-group pick and timing. These include common
attribution, the price source and split terms. For a multi-class issuer the
Store cannot reliably form or verify the across-class candidate: it has one price
series per security and lacks class identifiers, class counts and conversions. BRK-B's stored Class A count times the
Class B price is neither issuer total nor listed class. The code docstring for
`bm_ratio` says "common equity". The tag is not restricted to common equity, and
whether a filer's figure includes preferred is **UNKNOWN** from the Store.

**Turnover.** The numerator is the ticker's volume as the provider reports it.
Whether that covers the listed class only is **UNKNOWN** from code and sources
here, and is not inferred. Where it is listed-class volume, the matching
denominator is listed-class shares. The Store lacks class identifiers, so for
multi-class issuers it cannot reliably identify or verify a listed-class count.
For HOOD's 10-K filed 2022-02-24, the only filing checked, the Class A counts on
the cover and in R4 are not among the stored rows. A/B changes which stored count
is used. It might pick one of the right class by chance, but cannot guarantee or
show that.

**log_mktcap.** No numerator constrains the target. There are two candidate
definitions: whole-company equity value (issuer total) and the traded line's
value (listed class). This is a **policy choice not yet made**, and each needs
data the Store lacks for multi-class issuers.

Code observations that bear on the choice, recorded without a fix:

- **Zero shares.** A zero share count is a non-null value, so the ten-day carry
  does not replace it with an earlier row. The 42 zero-share signal keys were
  counted on the `_market_cap` path. On that path `log_mktcap`, `bm_ratio` and
  `ep_ratio` (`mktcap > 0`) drop the key, so it yields no value there rather than
  a wrong one. `turnover` selects its own `shares_at` and excludes a key when that
  value is 0. What it does at these 42 keys was not checked.
- **Filing lag.** The fundamentals numerators are read 2 days before the signal
  date. The share count is attached at ingest with no lag, from the filing date
  onward. `log_mktcap` and `turnover` declare `filing_lag_days=2`, but that
  declaration does not reach the embedded share count. These factors make no
  fundamentals read, so the read-path check has nothing to test and cannot verify
  that delay. Whether a same-day attachment is later than the filing time is
  **UNKNOWN** (no time of day is stored). No leak is asserted.
- **Split terms.** `close` is un-split and `volume` is re-split per yfinance row,
  subject to the split records available. For Stooq rows the stored `close` is
  adjusted according to the code comment. If that holds and a Stooq row is used,
  `close × shares_out` could mix adjusted and point-in-time terms. This is a
  conditional risk, not an observed mismatch. The ingest code stores Stooq
  `Volume` as delivered, and whether its split and class terms match the share
  count used is likewise unverified. Row-level source is **UNKNOWN** from the
  Store. The companion report above shows Stooq = 0 for this batch but is not
  bound to the Store hash, so no mismatch is shown here.
- **CIK to ticker.** `_fundamental_panel` and `_fundamental_history` build
  `dict(zip(cik, ticker))`, which keeps one ticker when a CIK has several.
  Whether the current sample has any such CIK was not checked. This is a code
  boundary, not an observed sample error.

**Bounded recommendation.**

1. Before choosing A or B, declare a target per consumer. The candidates above
   are:
   - for `bm_ratio` and `ep_ratio`, an across-class value, conditional on the
     numerators' attribution;
   - for `turnover`, same-class volume and shares;
   - for `log_mktcap`, an explicit choice between the two definitions.
2. Treat the class data as a prerequisite, not something A/B can supply. Without
   a ticker-to-class mapping and class counts, the Store cannot tell single-class
   from multi-class issuers. Those keys can only be labelled as class-unverified,
   not corrected.
3. Only then use A/B for within-group selection or refusal, where it still
   applies.

The filing-lag asymmetry and the conditional price-source terms are separate
decisions from the class question.

**Unresolved choices:**

- target for `log_mktcap`;
- whether `bm_ratio` and `ep_ratio` should exclude or flag multi-class issuers
  until issuer-total value is available;
- turnover pairing, pending the class of provider volume;
- whether the share count should carry the declared filing lag;
- whether price-source adjustment terms need row-level provenance;
- common-only attribution of `StockholdersEquity` and `NetIncomeLoss`;
- the source for class counts and ticker-to-class mapping (XBRL instance
  dimensions or another dataset);
- only after these, A versus B.

## Options for review (not chosen)

**A. Select on stated grounds.** Define an explicit order inside `(cik, filed)`,
for example latest `period_end` first, then a deterministic tie-break, and refuse
whatever still differs. Any namespace preference is a policy decision. The current
de-duplication keeps us-gaap on a shared stored key, and preferring DEI would
reverse that; this is not proposed without a separate decision. Rules for zero
candidates (HOOD's stored zero agrees in value and date with the old unqualified
common-stock line; the context mapping is unproven) and for share
classes (BRK-B) need decisions, and the Store cannot support a class rule. A would
also order the SQL paths above and make `leaking_asof` select whole rows. Price
rows affected by any A variant need `prices.shares_out` rebuilt and new archives.

**B. Refuse on ambiguity.** A multi-value `(cik, filed)` group yields a null
share count with a counted reason. Exposure: 12,173 signal keys if applied to
every multi-value group, or 290 as a residual after a latest-period rule. Actual
market-cap loss would be lower wherever the carry supplies an earlier row; not
simulated. B alone does not address single-candidate class mismatches such as
BRK-B.

## Not done

- No choice between the options.
- The XBRL instances were not parsed, so the axis and member of the class rows
  are unread.
- CAT's displayed 468.5 and 484.9 were located in R41. Their mapping to XBRL
  contexts and to the Store rows is unverified.
- No target quantity (issuer total, listed class or other) has been chosen.
- GOOGL, JPM, PLTR, V and eight of the nine undefined-ratio groups were not
  checked against the filings.
- No change to ingest selection, SQL, `leaking_asof`, the store or archives.
- No factor, demo or selected-200 run.
- The carry-adjusted loss under B was not simulated, and `turnover` exposure was
  not counted.
- The minimum environment and the full suite were not run.
