"""Read-only aggregate disclosure summary for an existing store.

Checks the fundamentals schema first and refuses to run if a column the
queries rely on is missing or nullable. Prints aggregates only, never raw keys.
No migration, factor run or demo.
"""

import argparse
import json
from pathlib import Path

import duckdb

from fza.disclosure import disclosure_summary, uncomparable_reason_counts

REQUIRED_NOT_NULL = ("cik", "tag", "period_start", "period_end", "filed", "fact_type")
REQUIRED = (*REQUIRED_NOT_NULL, "value", "unit")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("db", type=Path)
    ap.add_argument("--memory-limit", default="512MB")
    args = ap.parse_args(argv)
    con = duckdb.connect(str(args.db), read_only=True)
    try:
        con.execute(f"SET memory_limit = '{args.memory_limit}'")
        con.execute("SET threads = 1")
        try:
            described = con.execute("DESCRIBE fundamentals").fetchall()
        except duckdb.CatalogException:
            described = []
        schema = {name: (kind, nullable) for name, kind, nullable, *_ in described}
        missing = [c for c in REQUIRED if c not in schema]
        nullable = [c for c in REQUIRED_NOT_NULL if c in schema and schema[c][1] == "YES"]
        report = {"db": args.db.name, "schema": {c: schema.get(c) for c in REQUIRED},
                  "missing_columns": missing, "nullable_key_columns": nullable}
        if not missing and not nullable:
            summary = disclosure_summary(con)
            reasons = uncomparable_reason_counts(con)
            checks = {
                "union_matches_summary": (reasons["any_reason_keys"]
                                          == summary["uncomparable_repeated_keys"]),
                "partition_matches_repeated": (
                    summary["changed_comparable_keys"]
                    + summary["unchanged_comparable_keys"]
                    + summary["uncomparable_repeated_keys"]
                    == summary["multiple_filing_date_keys"]),
            }
            report.update(disclosure_summary=summary, uncomparable_reasons=reasons,
                          checks=checks,
                          failed_checks=[name for name, ok in checks.items() if not ok])
        print(json.dumps(report, indent=2, default=str))
        if "disclosure_summary" not in report:
            return 2
        return 1 if report["failed_checks"] else 0
    finally:
        con.close()


if __name__ == "__main__":
    raise SystemExit(main())
