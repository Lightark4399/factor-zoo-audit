"""Fixture bridge: mom_12_1 from this pipeline into backtest-audit's descriptive IC.

Scope. A synthetic fixture test only: not a connected audit, not real-data
validation and not research qualification. ``compute_factor`` still runs this
project's own protocol; the bridge consumes nothing from it. From backtest-audit
it uses only ``Panel`` and the raw cross-sectional IC (Pearson and Spearman) with
``scope="all"``, meaning every row of the declared synthetic panel, not an
out-of-sample period. No ``run_baseline_audit``, baselines, demeaning,
Newey-West, PnL, Sharpe, survivorship or qualification result is produced.

Mapping: entity_id = ticker, event_date = upstream exit_date, prediction = the
cleaned value (groups=None), label = upstream label. signal_date,
formation_session, entry_date, exit_date and the raw value ride along as extra
columns. Every expected value is written from the fixture definitions below,
never from the output under test.

Cleaning uses this version's defaults: winsor (0.01, 0.99) with linear
quantiles, no neutralisation, cross-sectional standardisation with ddof=1,
min_cross_section=10.
"""

from __future__ import annotations

import json
from functools import cache
from importlib import metadata
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from scipy import stats

BACKTEST_DIST = "backtest-credibility-audit"
BACKTEST_VERSION = "0.2.1"
BACKTEST_COMMIT = "e53ed6d601ea77da7d35b52c31cde93954297f8f"

# Only an absent distribution is a skip. Once it is installed, any import error
# or incompatibility below must fail the run, not disappear into a skip.
try:
    _DIST = metadata.distribution(BACKTEST_DIST)
except metadata.PackageNotFoundError:
    pytest.skip(
        f"{BACKTEST_DIST} not installed; install the bridge extra: pip install -e '.[bridge]'",
        allow_module_level=True,
    )

import audit  # noqa: E402
from audit.metrics.ic import cross_sectional_ic  # noqa: E402
from audit.panel import Panel, PanelError  # noqa: E402

from fza.factors.registry import load_all  # noqa: E402
from fza.pipeline.run import compute_factor  # noqa: E402
from fza.store import Store  # noqa: E402

RTOL = 1e-10  # fixture-formula comparisons, atol=0
IC_ATOL = 1e-12  # IC cross-checks, rtol=0

# ----------------------------------------------------------------------
# The fixture
# ----------------------------------------------------------------------
# Synthetic Monday-Friday calendar with no holidays; not an exchange calendar.
SESSIONS = pd.bdate_range("2019-01-01", "2021-03-31")
SIGNALS = pd.DatetimeIndex(
    [pd.Timestamp("2020-01-31") + pd.offsets.MonthEnd(m) for m in range(12)]
)
J = range(1, 21)
LAG, HORIZON = 1, 21
MAX_CARRY_DAYS = 10


def ticker(j: int) -> str:
    return f"T{j:02d}"


def growth(j: int, i) -> np.ndarray:
    """1 + a_j + b*i for 1-based global session index i."""
    return 1.0 + 0.0001 * j + 0.000001 * np.asarray(i, dtype=float)


# P(j, k) = 100 * prod_{i=1..k} growth(j, i), k = 1 at the first session.
PRICES = {
    j: pd.Series(100.0 * np.cumprod(growth(j, np.arange(1, len(SESSIONS) + 1))), index=SESSIONS)
    for j in J
}


def d(text: str) -> pd.Timestamp:
    return pd.Timestamp(text)


def key(t: str, s) -> tuple:
    """(ticker, calendar date): independent of the datetime unit pandas chose."""
    return (t, pd.Timestamp(s).date())


SCENARIOS = {
    "base": {},
    # 7: anchor 2019-06-30 falls back one more session, still within the carry.
    "drop_j7": {7: [d("2019-06-28")]},
    # 8: last close before anchor 2019-06-30 is 2019-06-13, beyond the carry.
    "drop_j8": {8: list(pd.bdate_range("2019-06-14", "2019-06-28"))},
    # 9: exit price of the March signal; numerator anchor of the May signal.
    "drop_j9": {9: [d("2020-04-30")]},
}


def available(scenario: str, j: int) -> pd.Series:
    return PRICES[j].drop(SCENARIOS[scenario].get(j, []))


def anchor_price(series: pd.Series, anchor: pd.Timestamp) -> float | None:
    """Last price on or before the anchor, at most MAX_CARRY_DAYS old."""
    before = series.loc[:anchor]
    if before.empty or (anchor - before.index[-1]).days > MAX_CARRY_DAYS:
        return None
    return float(before.iloc[-1])


def expected_raw(scenario: str, j: int, s: pd.Timestamp) -> float | None:
    series = available(scenario, j)
    num = anchor_price(series, s - pd.offsets.MonthEnd(1))
    den = anchor_price(series, s - pd.offsets.MonthEnd(12))
    return None if num is None or den is None else num / den - 1.0


def expected_positions(s: pd.Timestamp) -> tuple[int, int, int]:
    formation = int(SESSIONS.searchsorted(s, side="right")) - 1
    return formation, formation + LAG, formation + LAG + HORIZON


def expected_dates(s: pd.Timestamp) -> dict:
    f, e, x = expected_positions(s)
    return {"formation_session": SESSIONS[f], "entry_date": SESSIONS[e], "exit_date": SESSIONS[x]}


def label_formula(j: int, entry_pos: int, exit_pos: int) -> float:
    """prod_{i=entry_index+1..exit_index} growth(j, i) - 1, with 1-based indexes."""
    return float(np.prod(growth(j, np.arange(entry_pos + 2, exit_pos + 2)))) - 1.0


def expected_label(j: int, s: pd.Timestamp) -> float:
    _, e, x = expected_positions(s)
    return label_formula(j, e, x)


def expected_cleaned(raw: dict) -> dict:
    """Winsorise (0.01, 0.99) with linear quantiles, then z-score with ddof=1."""
    keys = list(raw)
    v = np.array([raw[k] for k in keys], dtype=float)
    lo, hi = np.quantile(v, [0.01, 0.99])
    c = np.clip(v, lo, hi)
    z = (c - c.mean()) / c.std(ddof=1)
    return dict(zip(keys, z, strict=True))


@cache
def expectation(scenario: str) -> dict:
    """K0 with each key's fixture-derived destination, and expected values.

    Destinations are derived from the fixture; they are not records exported by
    the pipeline, which reports counts only.
    """
    destination, raw = {}, {}
    for s in SIGNALS:
        for j in J:
            k = key(ticker(j), s)
            value = expected_raw(scenario, j, s)
            if value is None:
                destination[k] = "excluded: stale or missing anchor"
                continue
            raw[k] = value
            dates = expected_dates(s)
            series = available(scenario, j)
            if dates["entry_date"] not in series.index:
                destination[k] = "excluded: missing entry price"
            elif dates["exit_date"] not in series.index:
                destination[k] = "excluded: missing exit price"
            else:
                destination[k] = "retained"
    cleaned = {}
    for s in SIGNALS:  # cleaning precedes the label join
        cleaned.update(expected_cleaned({k: v for k, v in raw.items() if k[1] == s.date()}))
    retained = {k for k, v in destination.items() if v == "retained"}
    return {"destination": destination, "raw": raw, "cleaned": cleaned, "retained": retained}


@cache
def _run(scenario: str):
    store = Store()
    for j in J:
        series = available(scenario, j)
        store.con.executemany(
            "INSERT INTO prices (ticker, trade_date, close, close_adj) VALUES (?, ?, ?, ?)",
            [[ticker(j), day.date(), float(p), float(p)] for day, p in series.items()],
        )
    membership = pd.DataFrame(
        [(ticker(j), s) for s in SIGNALS for j in J], columns=["ticker", "signal_date"]
    )
    return compute_factor(
        load_all()["mom_12_1"], store, SIGNALS, groups=None,
        horizon_sessions=HORIZON, execution_lag_sessions=LAG,
        universe_membership=membership,
    )


def run(scenario: str):
    """Cached computation; callers receive copies so no case can alter another."""
    r = _run(scenario)
    return {
        "panel": r.panel.copy(deep=True),
        "values": r.values.copy(deep=True),
        "eligible": r.eligible_values.copy(deep=True),
        "label_join": r.label_join.to_dict(),
        "cleaning": r.cleaning.to_dict(),
    }


# ----------------------------------------------------------------------
# The adapter (test-local; not a production interface)
# ----------------------------------------------------------------------
KEY = ["ticker", "signal_date"]
DATE_COLUMNS = ["signal_date", "formation_session", "entry_date", "exit_date"]


def ns(series: pd.Series) -> pd.Series:
    return pd.to_datetime(series).astype("datetime64[ns]")


def unique_keys(frame: pd.DataFrame, cols: list[str], what: str) -> None:
    dupes = frame.duplicated(cols).sum()
    if dupes:
        raise ValueError(f"{what}: {dupes} duplicate {cols} key(s)")


def k1_with_raw(out: dict) -> pd.DataFrame:
    """K1 joined to its raw and cleaned values on explicit, checked-unique keys."""
    k1, raw, cleaned = out["panel"].copy(), out["eligible"].copy(), out["values"].copy()
    for frame, what in ((k1, "panel"), (raw, "eligible values"), (cleaned, "cleaned values")):
        frame["signal_date"] = ns(frame["signal_date"])
        unique_keys(frame, KEY, what)
    k1 = k1.merge(raw.rename(columns={"value": "factor_value_raw"}), on=KEY, how="left",
                  validate="one_to_one")
    k1 = k1.merge(cleaned.rename(columns={"value": "cleaned_value"}), on=KEY, how="left",
                  validate="one_to_one")
    if k1["factor_value_raw"].isna().any() or k1["cleaned_value"].isna().any():
        raise ValueError("a labelled key has no raw or cleaned value")
    if not (k1["prediction"] == k1["cleaned_value"]).all():
        raise ValueError("panel prediction differs from the cleaned value")
    return k1.drop(columns="cleaned_value")


def adapt(out: dict) -> pd.DataFrame:
    """The declared mapping into backtest's column names; timing rides along."""
    k1 = k1_with_raw(out)
    return pd.DataFrame({
        "entity_id": k1["ticker"],
        "event_date": k1["exit_date"],
        "prediction": k1["prediction"],
        "label": k1["label"],
        **{c: k1[c] for c in DATE_COLUMNS},
        "factor_value_raw": k1["factor_value_raw"],
    })


def to_panel(frame: pd.DataFrame) -> Panel:
    # drop_incomplete=False: a non-finite row must raise, never vanish.
    return Panel.from_frame(frame, drop_incomplete=False)


# ----------------------------------------------------------------------
# Validators: each returns every problem it finds, so one failure cannot hide another
# ----------------------------------------------------------------------
def close(a: float, b: float) -> bool:
    return np.isclose(a, b, rtol=RTOL, atol=0.0)


def keys_of(frame: pd.DataFrame, ticker_col: str = "ticker") -> list:
    return [key(t, s) for t, s in zip(frame[ticker_col], frame["signal_date"], strict=True)]


def v1_keys(k1: pd.DataFrame, raw: pd.DataFrame, exp: dict) -> list:
    problems = []
    keys = keys_of(k1)
    if len(keys) != len(set(keys)):
        problems.append("duplicate K1 keys")
    if set(keys) != exp["retained"]:
        problems.append(("K1 != expected retained",
                         sorted(set(keys) - exp["retained"]), sorted(exp["retained"] - set(keys))))
    eligible = set(keys_of(raw))
    for k, dest in exp["destination"].items():
        if dest.startswith("excluded: stale") and k in eligible:
            problems.append(("stale-anchor key reached the eligible values", k))
        if dest != "excluded: stale or missing anchor" and k not in eligible:
            problems.append(("key with valid anchors missing from eligible values", k))
    return problems


def v2_dates(k1: pd.DataFrame) -> list:
    problems = []
    for row in k1.itertuples(index=False):
        want = expected_dates(pd.Timestamp(row.signal_date))
        for col, value in want.items():
            if pd.Timestamp(getattr(row, col)) != value:
                problems.append((row.ticker, row.signal_date, col, getattr(row, col), value))
    return problems


def v3_labels(k1: pd.DataFrame) -> list:
    return [
        (row.ticker, row.signal_date, row.label)
        for row in k1.itertuples(index=False)
        if not close(row.label, expected_label(int(row.ticker[1:]), pd.Timestamp(row.signal_date)))
    ]


def v4_raw(raw: pd.DataFrame, exp: dict) -> list:
    problems = []
    for k, value in zip(keys_of(raw), raw["value"], strict=True):
        if k not in exp["raw"] or not close(value, exp["raw"][k]):
            problems.append((k, value, exp["raw"].get(k)))
    if len(raw) != len(exp["raw"]):
        problems.append(("raw row count", len(raw), len(exp["raw"])))
    return problems


def v4_cleaned(cleaned: pd.DataFrame, exp: dict) -> list:
    problems = []
    for k, value in zip(keys_of(cleaned), cleaned["value"], strict=True):
        if k not in exp["cleaned"] or not close(value, exp["cleaned"][k]):
            problems.append((k, value, exp["cleaned"].get(k)))
    if len(cleaned) != len(exp["cleaned"]):
        problems.append(("cleaned row count", len(cleaned), len(exp["cleaned"])))
    return problems


def v5_mapping(k2: pd.DataFrame, k1: pd.DataFrame) -> list:
    problems = []
    if k2.duplicated(["entity_id", "event_date"]).any():
        problems.append("duplicate (entity_id, event_date) in K2")
    if k2.duplicated(["entity_id", "signal_date"]).any():
        problems.append("duplicate (entity_id, signal_date) in K2")
    left = k2.assign(signal_date=ns(k2["signal_date"])).rename(columns={"entity_id": "ticker"})
    right = k1.assign(signal_date=ns(k1["signal_date"]))
    if set(keys_of(left)) != set(keys_of(right)):
        problems.append("K2 keys != K1 keys")
    both = left.drop_duplicates(KEY).merge(right, on=KEY, suffixes=("_k2", "_k1"))
    for col in ("prediction", "label", "factor_value_raw"):
        bad = both[col + "_k2"] != both[col + "_k1"]
        problems += [(col, k) for k in both.loc[bad, KEY].itertuples(index=False)]
    for col in DATE_COLUMNS[1:]:
        bad = ns(both[col + "_k2"]) != ns(both[col + "_k1"])
        problems += [(col, k) for k in both.loc[bad, KEY].itertuples(index=False)]
    for row in left.itertuples(index=False):
        want = expected_dates(pd.Timestamp(row.signal_date))["exit_date"]
        if pd.Timestamp(row.event_date) != want:
            problems.append(("event_date != expected exit", row.ticker, row.signal_date))
    return problems


def v6_one_exit_per_signal(k1: pd.DataFrame) -> list:
    n = k1.groupby("signal_date")["exit_date"].nunique()
    return list(n[n != 1].index)


def score(k2: pd.DataFrame) -> dict:
    panel = to_panel(k2)
    return {m: cross_sectional_ic(panel, method=m, scope="all") for m in ("pearson", "spearman")}


def v7_v8_v9(k2: pd.DataFrame, ics: dict, expected_n: dict) -> list:
    problems = []
    for method, series in ics.items():
        scored = set(series.values.index)
        scored_days = {t.date() for t in scored}
        if scored_days != set(expected_n):
            problems.append((method, "scored dates", sorted(scored_days ^ set(expected_n))))
        if (series.n_dates_undefined, series.n_dates_too_small) != (0, 0):
            problems.append((method, "undefined/too-small", series.n_dates_undefined,
                             series.n_dates_too_small))
        if series.n_dates_total != len(expected_n):
            problems.append((method, "n_dates_total", series.n_dates_total))
        k3 = k2.loc[ns(k2["event_date"]).isin(scored)]
        if len(k3) != len(k2):  # finite inputs: every K2 row on a scored date is scored
            problems.append((method, "K3 != K2"))
        for date, ic in series.values.items():
            day = k2.loc[ns(k2["event_date"]) == date]
            n_obs, want_n = int(series.n_obs.loc[date]), expected_n.get(date.date())
            if not n_obs == len(day) == want_n:
                problems.append((method, date, "n_obs", n_obs, len(day), want_n))
            ref = stats.pearsonr if method == "pearson" else stats.spearmanr
            want = float(ref(day["prediction"], day["label"])[0])
            if not np.isclose(ic, want, rtol=0.0, atol=IC_ATOL):
                problems.append((method, date, ic, want))
    return problems


def expected_counts(exp: dict) -> dict:
    counts: dict = {}
    for _, s in exp["retained"]:
        exit_ = expected_dates(pd.Timestamp(s))["exit_date"].date()
        counts[exit_] = counts.get(exit_, 0) + 1
    return counts


def all_checks(scenario: str) -> dict:
    out, exp = run(scenario), expectation(scenario)
    k1 = out["panel"]
    panel = to_panel(adapt(out))
    return {
        "V1": v1_keys(k1, out["eligible"], exp),
        "V2": v2_dates(k1),
        "V3": v3_labels(k1),
        "V4": v4_raw(out["eligible"], exp) + v4_cleaned(out["values"], exp),
        "V5": v5_mapping(panel.data, k1_with_raw(out)),
        "V6": v6_one_exit_per_signal(k1),
        "V7-V9": v7_v8_v9(panel.data, score(panel.data), expected_counts(exp)),
    }


# ----------------------------------------------------------------------
# Source of the backtest dependency
# ----------------------------------------------------------------------
def test_backtest_dependency_is_the_pinned_commit():
    assert _DIST.version == BACKTEST_VERSION
    direct = json.loads(_DIST.read_text("direct_url.json") or "null")
    assert direct is not None, "no direct_url.json: install source cannot be verified"
    assert direct["vcs_info"]["vcs"] == "git"
    assert direct["vcs_info"]["commit_id"] == BACKTEST_COMMIT
    assert direct["url"] == "https://github.com/Lightark4399/backtest-audit.git"
    init = next(f for f in _DIST.files if f.as_posix() == "audit/__init__.py")
    assert Path(_DIST.locate_file(init)).resolve() == Path(audit.__file__).resolve()


# ----------------------------------------------------------------------
# Honest fixture and price perturbations (cases 7-9), end to end
# ----------------------------------------------------------------------
@pytest.mark.parametrize("scenario", list(SCENARIOS))
def test_every_check_passes_end_to_end(scenario):
    results = all_checks(scenario)
    assert {name: problems for name, problems in results.items() if problems} == {}


def test_base_fixture_ranks_perfectly_on_every_date():
    out = run("base")
    assert len(out["panel"]) == 240
    assert out["cleaning"]["n_winsorised"] == 2 * 12  # one name clipped at each tail
    for series in score(adapt(out)).values():
        assert len(series.values) == 12
    spearman = score(adapt(out))["spearman"].values
    assert np.allclose(spearman.to_numpy(), 1.0, rtol=0.0, atol=IC_ATOL)


def test_case7_one_session_fallback_keeps_the_key():
    s = d("2020-06-30")
    k, exp, out = key("T07", s), expectation("drop_j7"), run("drop_j7")
    assert exp["destination"][k] == "retained"
    new = PRICES[7][d("2020-05-29")] / PRICES[7][d("2019-06-27")] - 1.0
    old = PRICES[7][d("2020-05-29")] / PRICES[7][d("2019-06-28")] - 1.0
    q = float(growth(7, SESSIONS.get_loc(d("2019-06-28")) + 1)) - 1.0  # dropped session
    assert close(1.0 + new, (1.0 + old) * (1.0 + q))
    raw = dict(zip(keys_of(out["eligible"]), out["eligible"]["value"], strict=True))
    assert close(raw[k], new)
    # Whether the order on that date changed is read from the formula, not assumed.
    values = out["values"]
    day = values.loc[ns(values["signal_date"]) == s].set_index("ticker")["value"]
    by_formula = pd.Series({t: v for (t, ss), v in exp["raw"].items() if ss == s.date()})
    assert list(day.sort_values().index) == list(by_formula.sort_values().index)


def test_case8_stale_anchor_drops_the_key_and_cleans_on_19_names():
    out, s = run("drop_j8"), d("2020-06-30")
    assert key("T08", s) not in set(keys_of(out["eligible"]))
    assert key("T08", s) not in set(keys_of(out["panel"]))
    june = out["values"].loc[ns(out["values"]["signal_date"]) == s]
    assert len(june) == 19 and "T08" not in set(june["ticker"])


def test_case9_missing_exit_price_drops_one_label_only():
    out, base = run("drop_j9"), run("base")
    march, may = d("2020-03-31"), d("2020-05-31")
    assert expected_dates(march)["entry_date"] == d("2020-04-01")
    assert expected_dates(march)["exit_date"] == d("2020-04-30")
    # Exported by the pipeline itself, not derived from the fixture.
    assert out["label_join"]["outcome_counts"].get("missing_exit_price") == 1
    assert out["label_join"]["n_dropped_without_label"] == 1
    k1 = set(keys_of(out["panel"]))
    assert key("T09", march) not in k1 and key("T09", may) in k1
    # Cleaning precedes the label join: March cleaned values are unchanged.
    def march_values(o):
        v = o["values"]
        return v.loc[ns(v["signal_date"]) == march].set_index("ticker")["value"].sort_index()
    got, ref = march_values(out), march_values(base)
    assert len(got) == 20 and list(got.index) == list(ref.index)
    assert np.allclose(got.to_numpy(), ref.to_numpy(), rtol=RTOL, atol=0.0)
    raw = dict(zip(keys_of(out["eligible"]), out["eligible"]["value"], strict=True))
    want = PRICES[9][d("2020-04-29")] / PRICES[9][d("2019-05-31")] - 1.0
    assert close(raw[key("T09", may)], want)


# ----------------------------------------------------------------------
# Adapter negatives (cases 1-3): the mutated copy must be rejected
# ----------------------------------------------------------------------
def k1_k2(scenario="base"):
    out = run(scenario)
    return out["panel"], adapt(out), k1_with_raw(out)


def test_case1_event_date_as_signal_date_fails_v5():
    _, honest, k1_ref = k1_k2()
    assert v5_mapping(honest, k1_ref) == []
    bad = honest.copy()
    bad["event_date"] = bad["signal_date"]
    assert any(p[0] == "event_date != expected exit" for p in v5_mapping(bad, k1_ref)
               if isinstance(p, tuple))


def test_case2_entry_date_changed_only_in_k2_fails_v5():
    _, honest, k1_ref = k1_k2()
    assert v5_mapping(honest, k1_ref) == []
    bad = honest.copy()
    bad.loc[bad.index[0], "entry_date"] = pd.Timestamp(bad.loc[bad.index[0], "entry_date"]) \
        + pd.offsets.BDay(1)
    assert [p for p in v5_mapping(bad, k1_ref) if p[0] == "entry_date"]


def test_case3_duplicate_key_is_refused_not_deduplicated():
    _, honest, k1_ref = k1_k2()
    to_panel(honest)  # honest control is accepted
    bad = pd.concat([honest, honest.iloc[[0]]], ignore_index=True)
    with pytest.raises(PanelError, match="duplicate"):
        to_panel(bad)
    assert "duplicate (entity_id, event_date) in K2" in v5_mapping(bad, k1_ref)


# ----------------------------------------------------------------------
# Upstream-output negatives (cases 4-6): expectations come from the fixture
# ----------------------------------------------------------------------
def shifted(frame: pd.DataFrame, cols: list[str], sessions: int) -> pd.DataFrame:
    out = frame.copy()
    for col in cols:
        pos = SESSIONS.get_indexer(ns(out[col]))
        out[col] = SESSIONS[pos + sessions]
    return out


def test_case4_exit_one_session_early_fails_v2_only():
    k1 = run("base")["panel"]
    assert v2_dates(k1) == [] and v3_labels(k1) == []
    bad = shifted(k1, ["exit_date"], -1)
    assert v2_dates(bad) and v3_labels(bad) == []


def test_case5_label_from_early_exit_fails_v3_only():
    k1 = run("base")["panel"]
    bad = k1.copy()
    bad["label"] = [
        label_formula(int(t[1:]), e, x - 1)
        for t, (_, e, x) in zip(bad["ticker"], map(expected_positions, ns(bad["signal_date"])),
                                strict=True)
    ]
    assert v2_dates(bad) == [] and v3_labels(bad)


def test_case6_consistently_late_output_fails_v2_and_v3():
    k1 = run("base")["panel"]
    bad = shifted(k1, ["entry_date", "exit_date"], 1)
    entry = SESSIONS.get_indexer(ns(bad["entry_date"]))
    exit_ = SESSIONS.get_indexer(ns(bad["exit_date"]))
    bad["label"] = [label_formula(int(t[1:]), e, x)
                    for t, e, x in zip(bad["ticker"], entry, exit_, strict=True)]
    assert v2_dates(bad) and v3_labels(bad)


# ----------------------------------------------------------------------
# IC-layer controls built directly (cases 10-12); not end to end
# ----------------------------------------------------------------------
def direct_panel(days: list[tuple[str, list, list]]) -> pd.DataFrame:
    rows = [
        {"entity_id": f"E{i:02d}", "event_date": pd.Timestamp(day), "prediction": p, "label": y}
        for day, preds, labels in days
        for i, (p, y) in enumerate(zip(preds, labels, strict=True))
    ]
    return pd.DataFrame(rows)


UP, DOWN = list(range(1, 11)), list(range(10, 0, -1))


def ics(frame: pd.DataFrame) -> dict:
    panel = to_panel(frame)
    return {m: cross_sectional_ic(panel, method=m, scope="all") for m in ("pearson", "spearman")}


def test_case10_hand_built_plus_and_minus_one():
    right = ics(direct_panel([("2020-01-31", UP, UP), ("2020-02-28", DOWN, DOWN)]))
    swapped = ics(direct_panel([("2020-01-31", UP, DOWN), ("2020-02-28", DOWN, UP)]))
    for m in ("pearson", "spearman"):
        assert np.allclose(right[m].values.to_numpy(), [1.0, 1.0], rtol=0.0, atol=IC_ATOL)
        assert np.allclose(swapped[m].values.to_numpy(), [-1.0, -1.0], rtol=0.0, atol=IC_ATOL)


def test_case11_and_12_undefined_and_small_dates_are_not_scored():
    days = [("2020-01-31", UP, UP), ("2020-02-28", DOWN, DOWN),
            ("2020-03-31", [5] * 10, UP),  # constant prediction: undefined
            ("2020-04-30", [1, 2], [1, 2])]  # fewer than three names: too small
    frame = direct_panel(days)
    for m, series in ics(frame).items():
        assert list(series.values.index) == [d("2020-01-31"), d("2020-02-28")]
        assert series.n_dates_undefined == 1 and series.n_dates_too_small == 1
        assert series.n_dates_total == 4
        assert np.isclose(series.mean, 1.0, rtol=0.0, atol=IC_ATOL)  # not averaged as zero
        # Classify each unscored date with the same function, one date at a time.
        for day, kind in (("2020-03-31", "undefined"), ("2020-04-30", "small")):
            one = cross_sectional_ic(
                to_panel(frame.loc[frame["event_date"] == d(day)]), method=m, scope="all")
            assert len(one.values) == 0
            assert (one.n_dates_undefined, one.n_dates_too_small) == (
                (1, 0) if kind == "undefined" else (0, 1))
