-- Schema for factor-zoo-audit.
--
-- The design decision that matters is in the `fundamentals` table: it stores
-- both the accounting period the number describes AND the date the filing
-- appeared. Every factor reads through a view that enforces `filed <=
-- signal_date`, so a factor physically cannot see a restatement that had not
-- been published yet.
--
-- That is a stronger guarantee than testing for look-ahead afterwards. An
-- after-the-fact check can only find leakage the author thought to look for; a
-- data layer that cannot express the leaking query removes the possibility.
--
-- Prices are stored without a knowledge dimension, deliberately. Daily OHLCV is
-- revised rarely and unsystematically, while fundamentals are revised routinely
-- and in a direction correlated with the outcome -- a company that restates
-- earnings downward is a different company than the one whose original filing
-- suggested. Carrying a knowledge dimension on prices would double the storage
-- and complicate every query to guard against a mechanism that barely operates.
-- The limitation is recorded in DATA_DICTIONARY.md rather than silently assumed.

-- ---------------------------------------------------------------------------
-- Securities and universe
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS securities (
    cik            VARCHAR NOT NULL,   -- SEC central index key, the stable identifier
    ticker         VARCHAR NOT NULL,
    name           VARCHAR,
    sic            VARCHAR,            -- SEC industry classification
    -- first_filing / last_filing are derived from EDGAR submission history and
    -- are how the universe is reconstructed without survivorship bias: a company
    -- that stopped filing has almost certainly left the market, whether or not a
    -- free price source still carries its ticker.
    first_filing   DATE,
    last_filing    DATE,
    -- Which accounting taxonomy the filer publishes under: 'us-gaap', 'ifrs' or
    -- 'unknown'. An IFRS filer reports under `ifrs-full`, whose tag names do not
    -- overlap the ones read here, so it has no rows in `fundamentals` at all.
    -- Without this column that is indistinguishable from a us-gaap filer whose
    -- ingest failed, and the fundamental universe would silently be smaller than
    -- the security count suggests.
    accounting_standard VARCHAR DEFAULT 'unknown',
    PRIMARY KEY (cik, ticker),
    CHECK (last_filing IS NULL OR first_filing IS NULL OR last_filing >= first_filing)
);

-- ---------------------------------------------------------------------------
-- Prices
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS prices (
    ticker       VARCHAR NOT NULL,
    trade_date   DATE    NOT NULL,
    open         DOUBLE,
    high         DOUBLE,
    low          DOUBLE,
    close        DOUBLE,
    -- close_adj carries splits and dividends. Factors that compare prices across
    -- time must use it; factors that use a price level at a point in time (a
    -- market cap, a 52-week-high ratio) must be explicit about which they mean.
    close_adj    DOUBLE,
    volume       DOUBLE,
    shares_out   DOUBLE,
    PRIMARY KEY (ticker, trade_date),
    CHECK (high IS NULL OR low IS NULL OR high >= low)
);

-- ---------------------------------------------------------------------------
-- Fundamentals, bitemporal
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS fundamentals (
    cik          VARCHAR NOT NULL,
    tag          VARCHAR NOT NULL,   -- us-gaap concept, e.g. 'StockholdersEquity'
    -- The accounting interval the value describes. Instant facts use the same
    -- date for start and end. Keeping start is mandatory for duration facts:
    -- quarterly, year-to-date and annual income can share an end date while
    -- representing different quantities.
    period_start DATE    NOT NULL,
    period_end   DATE    NOT NULL,
    fiscal_year  INTEGER,
    fiscal_period VARCHAR,           -- FY, Q1..Q4
    -- The date the filing containing this value became public. This is an
    -- ORIGINAL FIELD in the SEC data, not a derived estimate -- which is the main
    -- reason this project uses XBRL rather than a scraped alternative.
    filed        DATE    NOT NULL,
    value        DOUBLE,
    unit         VARCHAR,
    form         VARCHAR NOT NULL,   -- 10-K, 10-Q, 8-K...
    accession    VARCHAR NOT NULL,   -- the filing this came from, for provenance
    -- Which XBRL namespace the fact was taken from. Almost always 'us-gaap'.
    -- Shares outstanding is the exception: it is a cover-page fact that us-gaap
    -- does not define, so it comes from 'dei' and is written under the us-gaap
    -- name the rest of the codebase asks for. Recording the origin keeps that
    -- rename auditable -- `WHERE source_namespace = 'dei'` shows exactly which
    -- rows were renamed, instead of the rename being visible only in a comment.
    source_namespace VARCHAR DEFAULT 'us-gaap',
    frame        VARCHAR NOT NULL DEFAULT '', -- SEC calendrical context, when supplied
    fact_type    VARCHAR NOT NULL CHECK (fact_type IN ('instant', 'duration', 'unknown')),
    duration_days INTEGER,

    -- A restatement is a NEW ROW with a later `filed`, never an update. Without
    -- this, the historical record becomes the current view of the past and no
    -- query can reconstruct what was knowable at the time.
    PRIMARY KEY (cik, tag, period_start, period_end, filed, form, accession, frame),

    -- A filing cannot predate the period it reports on.
    CHECK (filed >= period_end),
    CHECK (period_end >= period_start),
    CHECK (duration_days IS NULL OR duration_days >= 0)
);

CREATE INDEX IF NOT EXISTS fundamentals_pit_idx
    ON fundamentals (cik, tag, period_start, period_end, filed);

CREATE INDEX IF NOT EXISTS fundamentals_filed_idx ON fundamentals (filed);

-- ---------------------------------------------------------------------------
-- The two views, and why both exist
-- ---------------------------------------------------------------------------

-- RESTATED: the final value for each (cik, tag, period). This is what a naive
-- query against a fundamentals database returns, and what most published factor
-- research implicitly uses. It must NOT be used to construct a signal -- it is
-- here so the point-in-time gap can be measured, which is one of this project's
-- headline numbers.
CREATE OR REPLACE VIEW fundamentals_restated AS
SELECT DISTINCT ON (cik, tag, period_start, period_end)
    cik, tag, period_start, period_end, fiscal_year, fiscal_period, filed, value,
    unit, form, accession, source_namespace, frame, fact_type, duration_days
FROM fundamentals
ORDER BY cik, tag, period_start, period_end, filed DESC;

-- POINT-IN-TIME: for a given signal date, the most recent filing for each
-- (cik, tag, period) that had actually been published by then.
--
-- The two conditions do different jobs and both are required:
--   filed <= signal_date       the filing existed
--   period_end <= signal_date  the period had ended
-- Dropping the first is the classic error: it returns today's restated value for
-- a historical date, which looks like history and is not.
--
-- ASOF is reserved in DuckDB (it has a native ASOF JOIN), so the parameter is
-- named `signal_date`.
CREATE OR REPLACE MACRO fundamentals_asof(signal_date) AS TABLE
    SELECT DISTINCT ON (cik, tag, period_start, period_end)
        cik, tag, period_start, period_end, fiscal_year, fiscal_period, filed,
        value, unit, form, accession, source_namespace, frame, fact_type, duration_days
    FROM fundamentals
    WHERE filed <= signal_date
      AND period_end <= signal_date
    ORDER BY cik, tag, period_start, period_end, filed DESC;

-- The single most recent value known at a signal date, per (cik, tag) -- the
-- form a factor usually wants, since it asks "what was the latest reported book
-- value when I formed this portfolio".
CREATE OR REPLACE MACRO latest_fundamental_asof(signal_date) AS TABLE
    SELECT DISTINCT ON (cik, tag)
        cik, tag, period_start, period_end, fiscal_year, fiscal_period, filed,
        value, unit, form, accession, source_namespace, frame, fact_type, duration_days
    FROM fundamentals
    WHERE filed <= signal_date
      AND period_end <= signal_date
    ORDER BY cik, tag, period_end DESC, filed DESC;

-- Universe membership by filing activity rather than present existence. A
-- company that stopped filing is out of the universe from that point, and IN it
-- for every date it was still filing -- which is what keeps the failures in the
-- sample.
CREATE OR REPLACE MACRO universe_asof(signal_date) AS TABLE
    SELECT cik, ticker, name, sic
    FROM securities
    WHERE (first_filing IS NULL OR first_filing <= signal_date)
      AND (last_filing IS NULL OR last_filing >= signal_date);

-- ---------------------------------------------------------------------------
-- Restatement diagnostics
-- ---------------------------------------------------------------------------

-- Every (cik, tag, period) that was ever revised, with the size and lag of the
-- revision. If nothing was ever revised, the point-in-time and restated views
-- coincide and this channel of look-ahead is absent -- which the report states
-- explicitly rather than letting a zero read as an all-clear.
CREATE OR REPLACE VIEW restatements AS
WITH first_filing AS (
    SELECT DISTINCT ON (cik, tag, period_start, period_end)
        cik, tag, period_start, period_end, filed AS first_filed, value AS first_value
    FROM fundamentals
    ORDER BY cik, tag, period_start, period_end, filed ASC
),
last_filing AS (
    SELECT DISTINCT ON (cik, tag, period_start, period_end)
        cik, tag, period_start, period_end, filed AS last_filed, value AS last_value
    FROM fundamentals
    ORDER BY cik, tag, period_start, period_end, filed DESC
)
SELECT
    f.cik, f.tag, f.period_start, f.period_end,
    f.first_filed, l.last_filed,
    f.first_value, l.last_value,
    l.last_value - f.first_value AS revision,
    CASE WHEN f.first_value IS NULL OR f.first_value = 0 THEN NULL
         ELSE (l.last_value - f.first_value) / abs(f.first_value)
    END AS revision_pct,
    date_diff('day', f.first_filed, l.last_filed) AS revision_lag_days
FROM first_filing f
JOIN last_filing l USING (cik, tag, period_start, period_end)
WHERE f.first_filed <> l.last_filed;

-- ---------------------------------------------------------------------------
-- Factor output
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS factor_values (
    factor_id    VARCHAR NOT NULL,
    ticker       VARCHAR NOT NULL,
    -- The date the signal was formed, using only information available before
    -- it. Execution happens no earlier than the next trading day; the
    -- execution-timing audit measures what that delay costs.
    signal_date  DATE    NOT NULL,
    value        DOUBLE,
    -- Which data vintage produced this value, so a run can be attributed. The
    -- same factor computed both ways is how the point-in-time gap is measured.
    vintage      VARCHAR NOT NULL DEFAULT 'pit'
        CHECK (vintage IN ('pit', 'restated')),
    PRIMARY KEY (factor_id, ticker, signal_date, vintage)
);

CREATE TABLE IF NOT EXISTS factor_runs (
    run_id       VARCHAR PRIMARY KEY,
    factor_id    VARCHAR NOT NULL,
    config_hash  VARCHAR NOT NULL,
    git_commit   VARCHAR,
    vintage      VARCHAR NOT NULL,
    started_at   TIMESTAMP,
    finished_at  TIMESTAMP,
    n_values     BIGINT,
    n_dates      BIGINT,
    status       VARCHAR DEFAULT 'running'
        CHECK (status IN ('running', 'ok', 'failed'))
);
