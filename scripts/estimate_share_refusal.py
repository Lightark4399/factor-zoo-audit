"""Read-only estimate of conservative share-count refusal, factor by factor.

Simulates refusing the stored share count on every price row whose as-of
(cik, filed) share group -- the group attach_shares_outstanding used, within
its 400-day window -- matches a refusal rule. It then runs the consumers
(log_mktcap, bm_ratio, ep_ratio, turnover) through their real library code on
the unchanged Store, substituting only the prices frame.

Two substitutions per refusal rule:
  zeroed_no_carry  refused shares_out -> 0. Every consumer drops non-positive
                   market caps / share counts, and a non-null zero also stops
                   the 10-day carry. Keys lost here are the simulated loss when
                   no carry across a refusal is allowed. This is not a count of
                   all exposure, and not an error count.
  null_with_carry  refused shares_out -> NULL, so the 10-day carry in
                   _market_cap / share_turnover may pick an earlier row, whose
                   count comes from an earlier filing.

Counts are finite factor keys after the historical-universe gate, before the
magnitude check and cleaning. Numerator panels do not depend on prices and are
memoized within one estimate only. Memory: the prices frame is held once and
copied per variant, and each factor pivots it; use --factor / --rule to bound a
run to one factor or rule per process. No write to the Store.
"""

import argparse
import hashlib
import json
from contextlib import contextmanager
from pathlib import Path

import pandas as pd

import fza.factors.library as library
from fza.demo import signal_dates_for
from fza.factors.registry import load_all
from fza.pipeline.run import historical_universe_membership
from fza.store import Store

SHARES = "CommonStockSharesOutstanding"
FACTORS = ("log_mktcap", "bm_ratio", "ep_ratio", "turnover")
PRICE_COLUMNS = ["ticker", "trade_date", "close", "volume", "shares_out"]
KEYS = ["ticker", "signal_date"]
RULES = {
    # every multi-value group
    "refuse_multi_value": "g.n_values > 1",
    # only groups the latest-period rule would leave undecided
    "refuse_latest_end_not_unique": "g.n_values > 1 AND g.n_latest <> 1",
}


class EstimateError(RuntimeError):
    """An input invariant the estimate relies on does not hold."""


def sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def require(condition, message):
    if not condition:
        raise EstimateError(message)


def refusal_masks(con, rules, staleness_days=400):
    duplicate_tickers = con.execute(
        "SELECT count(*) - count(DISTINCT ticker) FROM securities").fetchone()[0]
    # The mask joins prices to securities on ticker; a repeated ticker would
    # multiply price rows and attach two CIKs' share groups to one row.
    require(duplicate_tickers == 0, f"{duplicate_tickers} duplicate tickers in securities")
    columns = ", ".join(
        f"coalesce(({RULES[name]}) AND p.trade_date - g.filed <= {staleness_days}, false)"
        f" AS {name}" for name in rules)
    return con.execute(f"""
        WITH g AS (
            SELECT cik, filed,
                   count(DISTINCT value) FILTER (WHERE isfinite(value)) AS n_values,
                   count(DISTINCT value) FILTER (WHERE period_end = max_end
                                                 AND isfinite(value)) AS n_latest
            FROM (SELECT *, max(period_end) OVER (PARTITION BY cik, filed) AS max_end
                  FROM fundamentals WHERE tag = '{SHARES}')
            GROUP BY cik, filed
        )
        SELECT p.ticker, p.trade_date, {columns}
        FROM prices p LEFT JOIN securities s USING (ticker)
        ASOF LEFT JOIN g ON s.cik = g.cik AND p.trade_date >= g.filed
    """).df()


class PricesOverride:
    """The real Store, except that prices() returns a substituted frame."""

    def __init__(self, store, prices):
        self._store, self._prices = store, prices

    def prices(self, *args, **kwargs):
        if args or kwargs:
            raise TypeError("the estimate only substitutes the unfiltered prices() call")
        return self._prices.copy()

    def __getattr__(self, name):
        return getattr(self._store, name)


@contextmanager
def memoized_numerators():
    """Numerator panels read fundamentals only; reuse them across price variants.

    Keyed by the underlying Store, and restored on exit.
    """
    names = ("_fundamental_panel", "_ttm_fundamental_panel")
    originals = {name: getattr(library, name) for name in names}
    memo = {}

    def wrap(name, fn):
        def wrapper(store, signal_dates, *args, **kwargs):
            key = repr((name, id(getattr(store, "_store", store)),
                        list(pd.DatetimeIndex(signal_dates)), args, sorted(kwargs.items())))
            if key not in memo:
                memo[key] = fn(store, signal_dates, *args, **kwargs)
            return memo[key].copy()
        return wrapper

    try:
        for name, fn in originals.items():
            setattr(library, name, wrap(name, fn))
        yield
    finally:
        for name, fn in originals.items():
            setattr(library, name, fn)


def prepare(store, rules, history_months=15):
    """Signal dates, universe keys and the price frame with refusal flags."""
    dates = signal_dates_for(store, min_history_months=history_months)
    members = historical_universe_membership(store, dates)[KEYS]
    members = members.assign(signal_date=pd.to_datetime(members["signal_date"]))
    require(not members.duplicated(KEYS).any(), "duplicate universe keys")
    base = store.prices()[PRICE_COLUMNS].copy()
    base["trade_date"] = pd.to_datetime(base["trade_date"])
    require(not base.duplicated(["ticker", "trade_date"]).any(), "duplicate price rows")
    masks = refusal_masks(store.con, rules)
    masks["trade_date"] = pd.to_datetime(masks["trade_date"])
    require(len(masks) == len(base), f"mask rows {len(masks)} != price rows {len(base)}")
    require(not masks.duplicated(["ticker", "trade_date"]).any(), "duplicate mask rows")
    merged = base.merge(masks, on=["ticker", "trade_date"], how="left", validate="one_to_one")
    require(len(merged) == len(base), "price/mask merge changed the row count")
    for rule in rules:
        require(merged[rule].notna().all(), f"price rows without a {rule} flag")
        merged[rule] = merged[rule].astype(bool)
    return dates, members, merged


def factor_values(factor, store, prices, dates, members):
    """Finite post-universe factor values, indexed by unique (ticker, signal_date)."""
    raw = factor.compute(PricesOverride(store, prices), dates)
    raw = raw.assign(signal_date=pd.to_datetime(raw["signal_date"]))
    require(not raw.duplicated(KEYS).any(), f"{factor.factor_id}: duplicate output keys")
    value = pd.to_numeric(raw["value"], errors="coerce")
    raw = raw.loc[value.notna() & (value.abs() != float("inf"))]
    return raw.merge(members, on=KEYS).set_index(KEYS)["value"]


def variants(factor, store, base, dates, members, rule):
    """Current values and the two refusal substitutions for one factor and rule."""
    refused = base[rule] & base["shares_out"].notna()
    out = {"current": factor_values(factor, store, base[PRICE_COLUMNS], dates, members)}
    for name, fill in (("zeroed_no_carry", 0.0), ("null_with_carry", float("nan"))):
        prices = base[PRICE_COLUMNS].copy()
        prices.loc[refused, "shares_out"] = fill
        out[name] = factor_values(factor, store, prices, dates, members)
    return out


def summarize(values):
    current, zeroed, kept = (values[k] for k in ("current", "zeroed_no_carry",
                                                 "null_with_carry"))
    lost = current.index.difference(kept.index)
    common = current.index.intersection(kept.index)
    return {
        "current_keys": len(current),
        "simulated_key_loss_zeroed_no_carry": len(current.index.difference(zeroed.index)),
        "simulated_key_loss_null_with_carry": len(lost),
        "lost_tickers_null_with_carry": lost.get_level_values(0).nunique(),
        "kept_by_carry_value_changed": int((current.loc[common] != kept.loc[common]).sum()),
        "remaining_keys_null_with_carry": len(kept),
    }, {
        "carry_adds_no_new_keys": kept.index.difference(current.index).empty,
        "zeroed_subset_of_null_with_carry": zeroed.index.difference(kept.index).empty,
    }


def estimate(store, factors=FACTORS, rules=tuple(RULES), history_months=15):
    with memoized_numerators():
        dates, members, base = prepare(store, rules, history_months)
        registry = load_all()
        has_shares = base["shares_out"].notna()
        out = {
            "signal_dates": len(dates),
            "universe_keys": len(members),
            "price_rows": {"rows": len(base), "with_shares": int(has_shares.sum()),
                           **{rule: int((base[rule] & has_shares).sum()) for rule in rules}},
            "factors": {},
        }
        checks = {}
        for fid in factors:
            out["factors"][fid] = {}
            for rule in rules:
                counts, rule_checks = summarize(
                    variants(registry[fid], store, base, dates, members, rule))
                out["factors"][fid][rule] = counts
                checks.update({f"{fid}:{rule}:{k}": v for k, v in rule_checks.items()})
        out["checks"] = checks
        out["failed_checks"] = [name for name, ok in checks.items() if not ok]
        return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("db", type=Path)
    ap.add_argument("--memory-limit", default="256MB")
    ap.add_argument("--factor", choices=FACTORS, action="append",
                    help="bound the run to these factors (repeatable; default all)")
    ap.add_argument("--rule", choices=tuple(RULES), action="append",
                    help="bound the run to these rules (repeatable; default all)")
    args = ap.parse_args(argv)
    before = sha256(args.db)
    store = Store(str(args.db), read_only=True)
    try:
        store.con.execute(f"SET memory_limit = '{args.memory_limit}'")
        store.con.execute("SET threads = 1")
        report = estimate(store, tuple(args.factor or FACTORS), tuple(args.rule or RULES))
    finally:
        store.close()
    report = {"db": args.db.name, "sha256_before": before, **report,
              "sha256_after": sha256(args.db)}
    print(json.dumps(report, indent=2, default=str))
    unchanged = report["sha256_before"] == report["sha256_after"]
    return 0 if unchanged and not report["failed_checks"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
