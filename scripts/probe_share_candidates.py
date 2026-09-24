"""Read-only probe: same-date share-count candidates and interval ties.

Output is mainly aggregate counts. Two parts list keys and candidate rows: every
undefined-ratio group in count mode (``ratio_undefined_groups``: cik, ticker,
filed, accession, values; nine in the selected-200 store), and every group printed by
``--samples``. Every count block names its counting unit and denominator: share
fact keys, (cik, filed) disclosure groups, stored price rows, or
historical-universe signal keys. These units are not interchangeable.

Opens the store read-only; TEMP tables live in memory. No factor run, demo or
write. The mapping rules mirror, but do not call, the production code named
beside each block; they are an audit replica, not a second implementation.
"""

import argparse
import hashlib
import json
from pathlib import Path

import duckdb
import pandas as pd

SHARES = "CommonStockSharesOutstanding"
READ_TAGS = {"StockholdersEquity": "fundamentals_asof (latest; leaking_asof in restated arm)",
             "NetIncomeLoss": "fundamentals_history_asof",
             "Assets": "fundamentals_history_asof"}


def sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def one(con, sql, params=()):
    cur = con.execute(sql, params)
    names = [c[0] for c in cur.description]
    return dict(zip(names, cur.fetchone(), strict=True))


def counts(con, sql, params=()):
    return {k: v for k, v in con.execute(sql, params).fetchall()}


def selected(where="TRUE"):
    """Stored count against the unique latest-period value, where one exists.

    A difference is an observation, not a proven error or a strategy's impact.
    """
    return f"""
        count(*) FILTER (WHERE {where} AND n_values_at_latest_end = 1
                         AND shares_out = latest_end_value)
          AS stored_equals_unique_latest_end_value,
        count(*) FILTER (WHERE {where} AND n_values_at_latest_end = 1
                         AND shares_out <> latest_end_value)
          AS stored_differs_from_unique_latest_end_value,
        count(*) FILTER (WHERE {where} AND n_values_at_latest_end <> 1)
          AS latest_end_not_unique
    """


def probe(con, staleness_days=400, carry_days=10, history_months=15):
    out = {}

    # Fact keys of the share tag, as disclosure_summary defines them.
    out["fact_keys"] = {
        "unit": "share-tag fact keys (cik, tag, period_start, period_end)",
        "denominator": "all share-tag fact keys",
        **one(con, f"""
            WITH d AS (
                SELECT cik, period_start, period_end, filed,
                       count(DISTINCT value) FILTER (WHERE isfinite(value)) > 1 AS conflict
                FROM fundamentals WHERE tag = '{SHARES}' GROUP BY ALL
            )
            SELECT count(*) AS keys,
                   count(*) FILTER (WHERE n_filed > 1) AS multiple_filing_date_keys,
                   count(*) FILTER (WHERE n_filed > 1 AND conflict)
                     AS same_date_conflict_multiple_filing_date_keys,
                   count(*) FILTER (WHERE n_filed = 1 AND conflict)
                     AS same_date_conflict_single_filing_date_keys
            FROM (SELECT count(DISTINCT filed) AS n_filed, bool_or(conflict) AS conflict
                  FROM d GROUP BY cik, period_start, period_end)"""),
    }

    # Disclosure groups as attach_shares_outstanding sees them: every row of the
    # tag keyed by (cik, filed) only; period, accession and namespace are ignored.
    con.execute(f"""
        CREATE TEMP TABLE g AS
        SELECT cik, filed, count(*) AS n_rows,
               count(DISTINCT value) FILTER (WHERE isfinite(value)) AS n_values,
               bool_or(value IS NULL OR NOT isfinite(value)) AS has_nonfinite,
               count(DISTINCT accession) AS n_accessions,
               count(DISTINCT form) AS n_forms,
               count(DISTINCT period_end) AS n_period_ends,
               string_agg(DISTINCT form, '+' ORDER BY form) AS forms,
               string_agg(DISTINCT coalesce(source_namespace, 'NULL'), '+'
                          ORDER BY coalesce(source_namespace, 'NULL')) AS namespaces,
               min(value) FILTER (WHERE isfinite(value)) AS min_value,
               -- Undefined (NULL) unless every finite candidate is positive.
               CASE WHEN min(value) FILTER (WHERE isfinite(value)) > 0
                    THEN max(value) FILTER (WHERE isfinite(value))
                         / min(value) FILTER (WHERE isfinite(value)) END AS ratio,
               bool_or(key_conflict) AS conflict_inside_one_fact_key,
               count(*) FILTER (WHERE period_end = max_end) AS n_rows_at_latest_end,
               count(DISTINCT value) FILTER (WHERE period_end = max_end AND isfinite(value))
                 AS n_values_at_latest_end,
               -- Meaningful only when n_values_at_latest_end = 1.
               min(value) FILTER (WHERE period_end = max_end AND isfinite(value))
                 AS latest_end_value
        FROM (SELECT *,
                     count(DISTINCT value) FILTER (WHERE isfinite(value)) OVER (
                         PARTITION BY cik, tag, period_start, period_end, filed) > 1
                       AS key_conflict,
                     max(period_end) OVER (PARTITION BY cik, filed) AS max_end
              FROM fundamentals WHERE tag = '{SHARES}')
        GROUP BY cik, filed
    """)
    out["disclosure_groups"] = {
        "unit": "(cik, filed) share-tag disclosure groups",
        "denominator": "all groups",
        **one(con, """SELECT count(*) AS groups,
                             count(*) FILTER (WHERE n_rows > 1) AS multi_row,
                             count(*) FILTER (WHERE n_values > 1) AS multi_value,
                             count(*) FILTER (WHERE has_nonfinite AND n_values > 0)
                               AS nonfinite_mixed_with_finite
                      FROM g"""),
        "multi_value_context": {
            "denominator": "multi_value groups",
            **one(con, """
                SELECT count(*) AS groups,
                       count(DISTINCT cik) AS companies,
                       count(*) FILTER (WHERE n_accessions = 1) AS one_accession,
                       count(*) FILTER (WHERE n_forms > 1) AS mixed_forms,
                       count(*) FILTER (WHERE n_period_ends > 1) AS several_period_ends,
                       count(*) FILTER (WHERE conflict_inside_one_fact_key)
                         AS conflict_inside_one_fact_key,
                       count(*) FILTER (WHERE n_values_at_latest_end = 1)
                         AS latest_end_single_value,
                       count(*) FILTER (WHERE n_values_at_latest_end = 1
                                        AND n_rows_at_latest_end > 1)
                         AS latest_end_single_value_several_rows,
                       count(*) FILTER (WHERE n_values_at_latest_end > 1)
                         AS latest_end_several_values,
                       count(*) FILTER (WHERE n_values_at_latest_end = 0)
                         AS latest_end_no_finite_value,
                       count(*) FILTER (WHERE ratio < 1.01) AS ratio_lt_1_01,
                       count(*) FILTER (WHERE ratio >= 1.01 AND ratio < 1.1)
                         AS ratio_1_01_to_1_1,
                       count(*) FILTER (WHERE ratio >= 1.1 AND ratio < 2) AS ratio_1_1_to_2,
                       count(*) FILTER (WHERE ratio >= 2) AS ratio_ge_2,
                       count(*) FILTER (WHERE ratio IS NULL) AS ratio_undefined,
                       count(*) FILTER (WHERE min_value = 0) AS ratio_undefined_zero_min,
                       count(*) FILTER (WHERE min_value < 0) AS ratio_undefined_negative_min
                FROM g WHERE n_values > 1"""),
            "forms": counts(con, "SELECT forms, count(*) FROM g WHERE n_values > 1 "
                                 "GROUP BY forms ORDER BY 2 DESC, 1"),
            "namespaces": counts(con, "SELECT namespaces, count(*) FROM g WHERE n_values > 1 "
                                      "GROUP BY namespaces ORDER BY 2 DESC, 1"),
        },
        "companies_by_namespace": {
            "unit": "companies (cik) with any share-tag row",
            **one(con, f"""
                SELECT count(*) AS companies,
                       count(*) FILTER (WHERE has_usgaap) AS with_us_gaap_rows,
                       count(*) FILTER (WHERE has_dei) AS with_dei_rows,
                       count(*) FILTER (WHERE has_usgaap AND has_dei) AS with_both
                FROM (SELECT bool_or(source_namespace = 'us-gaap') AS has_usgaap,
                             bool_or(source_namespace = 'dei') AS has_dei
                      FROM fundamentals WHERE tag = '{SHARES}' GROUP BY cik)"""),
        },
    }
    # Every undefined-ratio group, row by row: these are few and each needs a
    # source check, so an aggregate by ticker is not enough.
    cur = con.execute(f"""
        SELECT f.cik, s.ticker, f.filed, f.accession, f.form, f.source_namespace,
               f.period_end, f.value
        FROM fundamentals f JOIN g USING (cik, filed)
        LEFT JOIN securities s USING (cik)
        WHERE f.tag = '{SHARES}' AND g.n_values > 1 AND g.ratio IS NULL
        ORDER BY f.cik, f.filed, f.period_end DESC, f.source_namespace, f.accession""")
    names = [c[0] for c in cur.description]
    out["ratio_undefined_groups"] = [dict(zip(names, r, strict=True)) for r in cur.fetchall()]

    # Stored price rows: latest group with filed <= trade_date, inside the ingest
    # staleness bound (attach_shares_outstanding merge_asof semantics).
    con.execute(f"""
        CREATE TEMP TABLE px AS
        SELECT p.ticker, p.trade_date, p.close, p.shares_out, s.cik, g.*
               EXCLUDE (cik),
               g.filed IS NOT NULL
                 AND p.trade_date - g.filed <= {staleness_days} AS in_window
        FROM prices p LEFT JOIN securities s USING (ticker)
        ASOF LEFT JOIN g ON s.cik = g.cik AND p.trade_date >= g.filed
    """)
    con.execute(f"""
        CREATE TEMP TABLE cand AS
        SELECT DISTINCT cik, filed, value FROM fundamentals
        WHERE tag = '{SHARES}' AND isfinite(value)
    """)
    out["price_rows"] = {
        "unit": "stored price rows (ticker, trade_date)",
        "denominator": "all stored price rows",
        "duplicate_tickers_in_securities": one(
            con, "SELECT count(*) - count(DISTINCT ticker) AS n FROM securities")["n"],
        **one(con, """
            SELECT count(*) AS rows,
                   count(*) FILTER (WHERE cik IS NOT NULL) AS with_cik,
                   count(*) FILTER (WHERE in_window) AS with_group_in_window,
                   count(*) FILTER (WHERE in_window AND n_values > 1) AS multi_value_exposed,
                   count(DISTINCT ticker) FILTER (WHERE in_window AND n_values > 1)
                     AS exposed_tickers,
                   count(*) FILTER (WHERE in_window AND has_nonfinite AND n_values > 0)
                     AS nonfinite_mixed_exposed,
                   count(*) FILTER (WHERE shares_out IS NOT NULL) AS with_stored_shares,
                   count(*) FILTER (WHERE shares_out = 0) AS zero_shares_rows,
                   count(DISTINCT ticker) FILTER (WHERE shares_out = 0)
                     AS zero_shares_tickers
            FROM px"""),
        "zero_shares_tickers_list": [r[0] for r in con.execute(
            "SELECT DISTINCT ticker FROM px WHERE shares_out = 0 ORDER BY 1").fetchall()],
        "stored_value_on_exposed_rows": {
            "denominator": "multi_value_exposed rows with stored shares_out",
            **one(con, f"""
                SELECT count(*) AS rows,
                       count(*) FILTER (WHERE c.value IS NULL) AS matches_no_candidate,
                       {selected()}
                FROM px LEFT JOIN cand c
                  ON px.cik = c.cik AND px.filed = c.filed AND px.shares_out = c.value
                WHERE in_window AND n_values > 1 AND shares_out IS NOT NULL"""),
        },
        "stored_value_on_all_in_window_rows": {
            "denominator": "in-window rows with stored shares_out",
            **one(con, """
                SELECT count(*) AS rows,
                       count(*) FILTER (WHERE c.value IS NULL) AS matches_no_candidate
                FROM px LEFT JOIN cand c
                  ON px.cik = c.cik AND px.filed = c.filed AND px.shares_out = c.value
                WHERE in_window AND shares_out IS NOT NULL"""),
        },
    }

    # Signal keys as demo.signal_dates_for plus the historical-universe gate;
    # market cap as library._market_cap: last non-null close*shares_out row,
    # carried at most carry_days.
    first, last = con.execute("SELECT min(trade_date), max(trade_date) FROM prices").fetchone()
    start = pd.Timestamp(first) + pd.DateOffset(months=history_months)
    dates = pd.date_range(start, pd.Timestamp(last), freq=pd.offsets.MonthEnd())
    con.execute("CREATE TEMP TABLE sd (signal_date DATE)")
    con.executemany("INSERT INTO sd VALUES (?)", [[d.date()] for d in dates])
    con.execute("""
        CREATE TEMP TABLE sig AS
        WITH members AS (
            SELECT s.ticker, sd.signal_date FROM securities s, sd
            WHERE (s.first_filing IS NULL OR s.first_filing <= sd.signal_date)
              AND (s.last_filing IS NULL OR s.last_filing >= sd.signal_date)
        ), caps AS (
            SELECT * FROM px WHERE close IS NOT NULL AND shares_out IS NOT NULL
                               AND isfinite(close * shares_out)
        )
        SELECT m.ticker, m.signal_date, c.* EXCLUDE (ticker)
        FROM members m ASOF LEFT JOIN caps c
          ON m.ticker = c.ticker AND m.signal_date >= c.trade_date
    """)
    exposed = f"signal_date - trade_date <= {carry_days} AND in_window AND n_values > 1"
    out["signal_keys"] = {
        "unit": "historical-universe (ticker, signal_date) keys",
        "denominator": "all universe keys; exposure counts are subsets of with_market_cap",
        "meaning": "exposed = the market-cap row used at the key came from a multi-value "
                   "group; not a count of keys any strategy would lose, since the carry "
                   "can substitute an earlier row",
        "signal_dates": len(dates),
        "rule": f"month ends from first price + {history_months} months; securities "
                f"first/last filing gate; market-cap row carried at most {carry_days} days; "
                "before factor-specific eligibility and cleaning",
        **one(con, f"""
            SELECT count(*) AS universe_keys,
                   count(*) FILTER (WHERE signal_date - trade_date <= {carry_days})
                     AS with_market_cap,
                   count(*) FILTER (WHERE {exposed}) AS exposed,
                   count(DISTINCT ticker) FILTER (WHERE {exposed}) AS exposed_tickers,
                   count(DISTINCT signal_date) FILTER (WHERE {exposed}) AS exposed_dates,
                   count(*) FILTER (WHERE {exposed} AND ratio >= 1.01) AS exposed_ratio_ge_1_01,
                   count(*) FILTER (WHERE {exposed} AND ratio >= 1.1) AS exposed_ratio_ge_1_1,
                   count(*) FILTER (WHERE {exposed} AND ratio IS NULL)
                     AS exposed_ratio_undefined,
                   count(*) FILTER (WHERE signal_date - trade_date <= {carry_days}
                                    AND shares_out = 0) AS market_cap_row_zero_shares,
                   {selected(exposed)}
            FROM sig"""),
        "zero_shares_tickers_list": [r[0] for r in con.execute(f"""
            SELECT DISTINCT ticker FROM sig
            WHERE signal_date - trade_date <= {carry_days} AND shares_out = 0
            ORDER BY 1""").fetchall()],
    }

    # Same period_end, several intervals, on the tags the factors actually read.
    out["interval_ties"] = {}
    for tag, path in READ_TAGS.items():
        out["interval_ties"][tag] = {
            "read_path": path,
            "restated_view": {
                "unit": "(cik, period_end) groups in fundamentals_restated",
                **one(con, """
                    SELECT count(*) AS groups,
                           count(*) FILTER (WHERE n_starts > 1) AS several_period_starts,
                           count(*) FILTER (WHERE n_starts > 1 AND n_values > 1)
                             AS several_starts_different_values,
                           count(*) FILTER (WHERE n_starts > 1 AND has_null)
                             AS several_starts_with_null_value
                    FROM (SELECT count(DISTINCT period_start) AS n_starts,
                                 count(DISTINCT value) FILTER (WHERE isfinite(value)) AS n_values,
                                 bool_or(value IS NULL) AS has_null
                          FROM fundamentals_restated WHERE tag = ?
                          GROUP BY cik, period_end)""", [tag]),
            },
            "pit_latest_ties": {
                "unit": "(cik, period_end, filed) groups in fundamentals",
                **one(con, """
                    SELECT count(*) AS groups,
                           count(*) FILTER (WHERE n_rows > 1) AS several_rows,
                           count(*) FILTER (WHERE n_starts > 1) AS several_period_starts,
                           count(*) FILTER (WHERE n_values > 1) AS different_values
                    FROM (SELECT count(*) AS n_rows,
                                 count(DISTINCT period_start) AS n_starts,
                                 count(DISTINCT value) FILTER (WHERE isfinite(value)) AS n_values
                          FROM fundamentals WHERE tag = ?
                          GROUP BY cik, period_end, filed)""", [tag]),
            },
        }

    # Consistency checks, reported as in disclosure_readonly_summary.py.
    context = out["disclosure_groups"]["multi_value_context"]
    bins = ("ratio_lt_1_01", "ratio_1_01_to_1_1", "ratio_1_1_to_2", "ratio_ge_2",
            "ratio_undefined")
    split = ("stored_equals_unique_latest_end_value",
             "stored_differs_from_unique_latest_end_value", "latest_end_not_unique")
    stored, keys = out["price_rows"]["stored_value_on_exposed_rows"], out["signal_keys"]
    undefined = {(r["cik"], r["filed"]) for r in out["ratio_undefined_groups"]}
    out["checks"] = {
        "ratio_bins_sum_to_groups": sum(context[b] for b in bins) == context["groups"],
        "undefined_groups_listed": len(undefined) == context["ratio_undefined"],
        "exposed_price_rows_split_sums": sum(stored[k] for k in split) == stored["rows"],
        "exposed_signal_keys_split_sums": sum(keys[k] for k in split) == keys["exposed"],
        "zero_share_signal_tickers_within_price_tickers": set(
            keys["zero_shares_tickers_list"]) <= set(out["price_rows"]["zero_shares_tickers_list"]),
    }
    out["failed_checks"] = [name for name, ok in out["checks"].items() if not ok]
    return out


SAMPLES = {  # category: (ticker, condition on the (cik, filed) group)
    "dei_and_us_gaap_differ": ("AAPL", "ns = 'dei+us-gaap' AND nv > 1 AND nv_latest = 1"),
    "us_gaap_only_multi_value": ("GOOGL", "ns = 'us-gaap' AND nv > 1"),
    "dei_only_multi_value": ("JPM", "ns = 'dei' AND nv > 1"),
    "latest_period_end_conflict": ("CAT", "nv > 1 AND nv_latest > 1"),
    "ratio_undefined_zero": ("HOOD", "nv > 1 AND lo = 0"),
    "ratio_ge_2": ("PLTR", "nv > 1 AND lo > 0 AND hi / lo >= 2"),
    "multi_class_issuer_brk": ("BRK-B", "TRUE"),
    "multi_class_issuer_v": ("V", "TRUE"),
}


def samples(con, staleness_days=400):
    """Most recent group per category, with every candidate row and the stored
    price-row share count on the first trade date at or after ``filed``.

    The price row is attributed to the group only if the as-of group for that
    row (latest share-tag ``filed`` on or before its trade date) is the listed
    one and lies inside the staleness window. Index URLs are candidates built
    from the accession and are not fetched or validated here.
    """
    con.execute(f"""
        CREATE TEMP TABLE sg AS
        SELECT cik, filed, count(DISTINCT value) FILTER (WHERE isfinite(value)) AS nv,
               string_agg(DISTINCT source_namespace, '+' ORDER BY source_namespace) AS ns,
               min(value) AS lo, max(value) AS hi,
               count(DISTINCT value) FILTER (WHERE period_end = max_end) AS nv_latest
        FROM (SELECT *, max(period_end) OVER (PARTITION BY cik, filed) AS max_end
              FROM fundamentals WHERE tag = '{SHARES}')
        GROUP BY cik, filed
    """)
    out = {}
    for category, (ticker, condition) in SAMPLES.items():
        group = con.execute(f"""
            SELECT sg.cik, sg.filed FROM sg JOIN securities s USING (cik)
            WHERE s.ticker = ? AND {condition} ORDER BY sg.filed DESC LIMIT 1""",
                            [ticker]).fetchone()
        if group is None:
            out[category] = {"ticker": ticker, "group": None}
            continue
        cik, filed = group
        cur = con.execute("""
            SELECT source_namespace, form, accession, period_start, period_end, value,
                   unit, frame, fact_type
            FROM fundamentals WHERE tag = ? AND cik = ? AND filed = ?
            ORDER BY period_end DESC, source_namespace, accession""", [SHARES, cik, filed])
        names = [c[0] for c in cur.description]
        candidates = [dict(zip(names, r, strict=True)) for r in cur.fetchall()]
        for row in candidates:
            accession = row["accession"]
            row["candidate_index_url"] = (
                f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/"
                f"{accession.replace('-', '')}/{accession}-index.htm")
        price = con.execute("""
            SELECT trade_date, shares_out FROM prices
            WHERE ticker = ? AND trade_date >= ? ORDER BY trade_date LIMIT 1""",
                            [ticker, filed]).fetchone()
        attribution = None
        if price is not None:
            asof = con.execute("""
                SELECT max(filed) FROM fundamentals
                WHERE tag = ? AND cik = ? AND filed <= ?""",
                               [SHARES, cik, price[0]]).fetchone()[0]
            age = (price[0] - asof).days if asof is not None else None
            attribution = {
                "asof_group_filed": asof, "age_days": age,
                "matches_listed_group": asof == filed,
                "inside_staleness_window": age is not None and age <= staleness_days,
                "stored_value_is_a_candidate": price[1] in {c["value"] for c in candidates},
            }
            attribution["attributed_to_listed_group"] = (
                attribution["matches_listed_group"]
                and attribution["inside_staleness_window"]
                and attribution["stored_value_is_a_candidate"])
        out[category] = {"ticker": ticker, "cik": cik, "filed": filed,
                         "candidates": candidates,
                         "first_price_row_on_or_after_filed": price,
                         "price_row_attribution": attribution,
                         "share_class_or_dimension": "not stored; cannot be determined "
                                                     "from the Store"}
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("db", type=Path)
    ap.add_argument("--memory-limit", default="512MB")
    ap.add_argument("--samples", action="store_true",
                    help="print representative groups (a few raw rows) instead of counts")
    args = ap.parse_args(argv)
    before = sha256(args.db)
    con = duckdb.connect(str(args.db), read_only=True)
    try:
        con.execute(f"SET memory_limit = '{args.memory_limit}'")
        con.execute("SET threads = 1")
        report = samples(con) if args.samples else probe(con)
    finally:
        con.close()
    report = {"db": args.db.name, "sha256_before": before, **report,
              "sha256_after": sha256(args.db)}
    print(json.dumps(report, indent=2, default=str))
    unchanged = report["sha256_before"] == report["sha256_after"]
    return 0 if unchanged and not report.get("failed_checks") else 1


if __name__ == "__main__":
    raise SystemExit(main())
