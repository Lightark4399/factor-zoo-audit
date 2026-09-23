"""Stored disclosure diagnostics, not estimates of accounting restatement rates."""


def disclosure_summary(con) -> dict:
    """Classify repeated-date keys only when values and measurement units agree.

    Among comparable repeated keys, distinct stored finite values count as changes,
    including a change later reversed. A conflict on any filing date makes the
    entire key uncomparable; no conflicting date is silently discarded.
    Equality is exact; this is not a materiality or accounting-error judgement.
    """
    row = con.execute("""
        WITH dates AS (
            SELECT cik, tag, period_start, period_end, filed,
                   count(DISTINCT value) FILTER (WHERE isfinite(value)) AS n_values
            FROM fundamentals GROUP BY ALL
        ), conflicts AS (
            SELECT cik, tag, period_start, period_end, bool_or(n_values > 1) AS conflict
            FROM dates GROUP BY ALL
        ), facts AS (
            SELECT f.cik, f.tag, f.period_start, f.period_end,
                   count(DISTINCT filed) > 1 AS repeated,
                   -- Raw value diversity only; count changes with comparable below.
                   count(DISTINCT value) FILTER (WHERE isfinite(value)) > 1 AS changed,
                   count(*) = count(*) FILTER (WHERE isfinite(value))
                     AND count(unit) = count(*) AND count(DISTINCT unit) = 1
                     -- The Store schema enforces fact_type NOT NULL and its enum.
                     AND count(DISTINCT fact_type) = 1
                     AND min(fact_type) <> 'unknown'
                     AND NOT bool_or(c.conflict) AS comparable
            FROM fundamentals f JOIN conflicts c
              USING (cik, tag, period_start, period_end)
            GROUP BY f.cik, f.tag, f.period_start, f.period_end
        )
        SELECT count(*), count(*) FILTER (WHERE repeated),
               count(*) FILTER (WHERE repeated AND comparable AND changed),
               count(*) FILTER (WHERE repeated AND comparable AND NOT changed),
               count(*) FILTER (WHERE repeated AND NOT comparable)
        FROM facts
    """).fetchone()
    total, repeated, changed, unchanged, unknown = map(int, row)
    return {
        "contract": "stored_disclosures_v1",
        "fact_key": ["cik", "tag", "period_start", "period_end"],
        "fact_keys": total,
        "multiple_filing_date_keys": repeated,
        "multiple_filing_date_share_of_fact_keys": repeated / total if total else None,
        "changed_comparable_keys": changed,
        "unchanged_comparable_keys": unchanged,
        "uncomparable_repeated_keys": unknown,
        "changed_share_of_comparable_repeated_keys": (
            changed / (changed + unchanged) if changed + unchanged else None
        ),
    }


REASONS = ("nonfinite_or_missing_value", "missing_unit", "mixed_units",
           "mixed_fact_types", "unknown_fact_type", "same_date_conflict")


def uncomparable_reason_counts(con) -> dict:
    """Multi-label reasons for repeated keys that ``disclosure_summary`` cannot compare.

    One key may carry several reasons, so reason counts overlap and must not be
    summed; ``any_reason_keys`` is the union and equals the uncomparable count.
    NULL, NaN and +/-infinity values all count as non-finite or missing.
    """
    flags = ", ".join(f"count(*) FILTER (WHERE {r})" for r in REASONS)
    row = con.execute(f"""
        WITH dates AS (
            SELECT cik, tag, period_start, period_end, filed,
                   count(DISTINCT value) FILTER (WHERE isfinite(value)) > 1 AS conflict
            FROM fundamentals GROUP BY ALL
        ), facts AS (
            SELECT count(DISTINCT filed) > 1 AS repeated,
                   bool_or(value IS NULL OR NOT isfinite(value)) AS nonfinite_or_missing_value,
                   bool_or(unit IS NULL) AS missing_unit,
                   count(DISTINCT unit) > 1 AS mixed_units,
                   count(DISTINCT fact_type) > 1 AS mixed_fact_types,
                   bool_or(fact_type = 'unknown') AS unknown_fact_type,
                   bool_or(conflict) AS same_date_conflict
            FROM fundamentals JOIN dates USING (cik, tag, period_start, period_end, filed)
            GROUP BY cik, tag, period_start, period_end
        )
        SELECT {flags}, count(*) FILTER (WHERE {" OR ".join(REASONS)})
        FROM facts WHERE repeated
    """).fetchone()
    counts = dict(zip(REASONS, map(int, row[:-1]), strict=True))
    return {
        "population": "repeated_fact_keys_not_comparable",
        "counting": "MULTI_LABEL_MAY_OVERLAP_DO_NOT_SUM",
        "reason_keys": counts,
        "any_reason_keys": int(row[-1]),
    }
