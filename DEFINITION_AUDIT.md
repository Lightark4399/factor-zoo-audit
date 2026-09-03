# Factor definition and citation audit

**Status: DECISION REQUIRED / no factor values changed by this audit.**

This audit checks two independent edges of each research contract:

1. executable implementation ↔ hypothesis-card definition;
2. hypothesis-card definition ↔ the object measured by the cited literature.

An accurate card does not repair a citation to a different characteristic. A
relevant mechanism paper is also not automatically the origin of a definition.
The status vocabulary proposed for the registry is:

- `EXACT_REPLICATION`: formula, timing and portfolio construction match a cited
  definition;
- `DOCUMENTED_VARIANT`: the lineage is valid and every material departure is
  stated;
- `RELATED_MECHANISM_ONLY`: the source supports the rationale, not the formula;
- `UNSUPPORTED_LINEAGE`: no cited source measures the implemented object;
- `UNVERIFIED`: no primary-source locator has yet been checked.

## Results

| factor | executable formula | card ↔ code | cited object and locator | proposed lineage |
|---|---|---|---|---|
| `asset_growth` | `-(AT_latest / AT_closest-to-(latest-1y) - 1)` over every visible XBRL interval | **DIVERGES.** The card says two annual filings; the code permits quarterly contexts and refreshes monthly. | Cooper–Gulen–Schill use annual percentage growth in total assets and form portfolios each June. Fama–French define investment from fiscal year *t−2* to *t−1* (2015, Table A4 note). Titman–Wei–Xie study capital investment, not total-asset growth. | `UNSUPPORTED_LINEAGE` until code is annual-only; Titman belongs as `RELATED_MECHANISM_ONLY`. |
| `bm_ratio` | latest PIT positive `StockholdersEquity / (close × shares)` at each month end | **AGREES.** | Fama–French use fiscal-year book equity with December market equity, matched to July–June returns (1992, data construction); their book-equity numerator also adjusts deferred taxes and preferred stock. | `DOCUMENTED_VARIANT`; monthly PIT timing and simplified numerator must be explicit structured departures. |
| `ep_ratio` | positive PIT TTM net income / contemporaneous market cap | **AGREES.** | Basu sorts on P/E built from annual earnings available before portfolio formation and year-end market value (1977, method); Fama–French likewise test an annual E/P characteristic. | `DOCUMENTED_VARIANT`; TTM PIT refresh and loss exclusion are material departures, not an exact Basu replication. |
| `idio_vol` | negative 60-session standard deviation of total daily returns | **AGREES, with the simplification disclosed.** | Ang–Hodrick–Xing–Zhang estimate volatility of residuals from a Fama–French three-factor regression (2006, variable construction). Bali–Cakici–Whitelaw measure the maximum daily return in the prior month (2011, abstract/Section 2). Neither defines total volatility. | `UNSUPPORTED_LINEAGE`. Rename to `total_vol_60d`; both current citations become mechanism/comparator roles, not definition origins. |
| `log_mktcap` | `-log(close × shares)` at the signal date | **AGREES.** | Banz tests market value of common equity; Fama–French's SMB is a portfolio factor formed on June market equity rather than a monthly single-stock z-score. | `DOCUMENTED_VARIANT`; Banz is the definition origin, Fama–French is a comparator/portfolio-construction source. |
| `mom_12_1` | adjusted-close cumulative return from *t−12* to *t−1*, negating neither side | **AGREES.** | Asness–Moskowitz–Pedersen explicitly use cumulative months 2–12 return (`MOM2–12`, data section). Jegadeesh–Titman test 3/6/9/12-month formation and holding grids, with either no lag or a one-week lag. | `DOCUMENTED_VARIANT`; signal matches AMP, while this repository's holding and portfolio protocol is its own. |
| `mom_6_1` | adjusted-close cumulative return from *t−6* to *t−1* | **AGREES.** | Jegadeesh–Titman include six-month formation strategies but not this exact one-month skip convention. | `DOCUMENTED_VARIANT`. |
| `rev_1m` | negative prior-month adjusted-close return | **AGREES.** | Jegadeesh documents negative first-order serial correlation in monthly returns (1990, abstract and tests). Nagel supports the liquidity-provision interpretation, not the variable's origin. | `DOCUMENTED_VARIANT`; Jegadeesh is definition origin, Nagel is mechanism. |
| `roe` | PIT TTM net income / latest positive stockholders' equity | **AGREES.** | Novy-Marx defines gross profits/assets (2013, abstract/data); Fama–French define annual operating profitability/book equity (2015, Table A4 note). Neither is this ROE. Hou–Xue–Zhang do define ROE, but as latest quarterly income before extraordinary items divided by one-quarter-lagged book equity (2015, factor construction). | Current citations: `UNSUPPORTED_LINEAGE`. Replace definition origin with Hou–Xue–Zhang, then classify the TTM/latest-equity implementation as `DOCUMENTED_VARIANT`. |
| `turnover` | negative 21-session mean daily share volume / PIT shares outstanding | **AGREES.** | Datar–Naik–Radcliffe define turnover as shares traded divided by shares outstanding (1998, abstract). Miller is a disagreement/short-sale mechanism source. | `DOCUMENTED_VARIANT`; Datar is definition origin, Miller is mechanism. |

No row is labelled `EXACT_REPLICATION`: even where the characteristic formula
matches, the repository uses a common monthly PIT signal, cleaning and holding
protocol rather than reproducing the cited paper's complete portfolio design.

## Decisions proposed before implementation

1. Fix `asset_growth` code to select the latest two annual fiscal-year contexts
   roughly one year apart. Do not relabel the current quarterly-capable path as
   the published Cooper characteristic.
2. Rename `idio_vol` to `total_vol_60d`. Keep it outside the denominator of
   “published anomalies tested” until a valid total-volatility definition source
   is added. Add residual `idio_vol_ff3_1m` only after an external market/FF3
   series exists.
3. Keep `roe`, but replace its definition citations with Hou–Xue–Zhang and state
   the TTM/latest-equity departures. Novy-Marx and Fama–French may remain only as
   competing profitability definitions, not lineage.
4. Add structured citation entries with `role`, `locator`, and `verification`;
   default new entries to `UNVERIFIED`. A factor-level `lineage_status` is then
   derived from those entries rather than hand-set.
5. Do not present an `UNSUPPORTED_LINEAGE` factor's IC as evidence about the
   named published anomaly. The row remains visible with numbers withheld or
   explicitly marked `NOT_EVIDENCE`.

## Primary sources checked

- [Cooper, Gulen & Schill (2008), annual asset growth](https://onlinelibrary.wiley.com/doi/10.1111/j.1540-6261.2008.01370.x).
- [Fama & French (1992), pp. 429–432 data construction](https://onlinelibrary.wiley.com/doi/10.1111/j.1540-6261.1992.tb04398.x).
- [Basu (1977), Journal of Finance 32, 663–682](https://onlinelibrary.wiley.com/doi/10.1111/j.1540-6261.1977.tb01979.x).
- [Ang, Hodrick, Xing & Zhang (2006), variable construction](https://www.ruf.rice.edu/~yxing/AHXZ_011906.pdf).
- [Bali, Cakici & Whitelaw (2011), MAX definition](https://pages.stern.nyu.edu/~rwhitela/papers/max%20jfe11.pdf).
- [Jegadeesh & Titman (1993), formation/holding strategies](https://www.smallake.kr/wp-content/uploads/2015/01/Jegadeesh_Titman_1993.pdf).
- [Asness, Moskowitz & Pedersen (2013), `MOM2–12`](https://spinup-000d1a-wp-offload-media.s3.amazonaws.com/faculty/wp-content/uploads/sites/3/2019/09/ValueandMomentumEverywhere.pdf).
- [Jegadeesh (1990), monthly first-order reversal](https://onlinelibrary.wiley.com/doi/10.1111/j.1540-6261.1990.tb05110.x).
- [Datar, Naik & Radcliffe (1998), turnover definition](https://www.sciencedirect.com/science/article/pii/S1386418197000049).
- [Novy-Marx (2013), gross profitability definition](https://www.nber.org/papers/w15940.pdf).
- [Fama & French (2015), Table A4 definition note](https://www.sciencedirect.com/science/article/pii/S0304405X14002323).
- [Hou, Xue & Zhang (2015), ROE factor construction](https://academic.oup.com/rfs/article/28/3/650/1574802).

The user-supplied quantitative research guides were used as background for
terminology and workflow discipline. They do not replace the primary papers for
formula attribution.
