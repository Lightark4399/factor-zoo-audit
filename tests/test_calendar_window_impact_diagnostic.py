"""Synthetic checks for scripts/diagnose_calendar_window_impact.py.

Unit tests give every checker a case it must reject. End-to-end tests run the
two real source trees (exported from local git objects) on the script's own
synthetic database; missing objects make them fail, never skip. Negative
end-to-end cases change the synthetic input (S0), the file or hash evidence
(S1), or a copy of the collected results (S2-S5).
"""

import copy
import importlib.util
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

SCRIPT = Path(__file__).parents[1] / "scripts" / "diagnose_calendar_window_impact.py"
spec = importlib.util.spec_from_file_location("diagnose_calendar_window_impact", SCRIPT)
diag = importlib.util.module_from_spec(spec)
spec.loader.exec_module(diag)
PASS, FAIL, NOT_RUN, EMPTY = diag.PASS, diag.FAIL, diag.NOT_RUN, diag.EMPTY


# ----------------------------------------------------------------------
# Small hand-built inputs for the pure checkers
# ----------------------------------------------------------------------
def month_ends(start, n):
    return list(pd.date_range(start, periods=n, freq=pd.offsets.MonthEnd()))


def small_prices():
    """Two tickers with month-end closes 2019-01..2020-12; one all-missing ticker."""
    ends = month_ends("2019-01-31", 24)
    rows = []
    for j, d in enumerate(ends):
        rows += [("A", d, 100.0 * 1.01 ** j), ("B", d, 50.0 + j)]
        rows.append(("NA", d, np.nan))
    return pd.DataFrame(rows, columns=["ticker", "trade_date", "close_adj"])


SMALL_DATES = month_ends("2020-01-31", 12)  # request rows 0..11


def perfect_raw(expect):
    return {v: {f: [[t, str(s.date()), val] for (t, s), val in
                    sorted(expect["values"][(v, f)].items())] for f in diag.FACTORS}
            for v in (diag.OLD, diag.NEW)}


@pytest.fixture()
def small():
    expect = diag.expectations(small_prices(), SMALL_DATES)
    return expect, perfect_raw(expect)


# ----------------------------------------------------------------------
# Independent pricing and S0
# ----------------------------------------------------------------------
def test_anchor_same_day_ten_day_carry_and_eleven_day_stale():
    prices = pd.DataFrame({"ticker": "A", "close_adj": [10.0, 11.0, 12.0],
                           "trade_date": pd.to_datetime(["2020-07-10", "2020-07-21",
                                                         "2020-09-30"])})
    a = diag.AnchorPrices(prices)
    same = a.at("A", pd.Timestamp("2020-09-30"))
    assert (same["price"], same["age_days"], same["reason"]) == (12.0, 0, "ok")
    ten = a.at("A", pd.Timestamp("2020-07-31"))
    assert (ten["price"], ten["age_days"]) == (11.0, 10)
    eleven = a.at("A", pd.Timestamp("2020-08-01"))
    assert (eleven["price"], eleven["age_days"], eleven["reason"]) == (None, 11, "stale")
    assert a.at("A", pd.Timestamp("2020-07-01"))["reason"] == "no_history"


def test_zero_latest_price_is_used_not_skipped_and_s0_rejects_it():
    prices = small_prices()
    prices.loc[(prices.ticker == "A") & (prices.trade_date == "2019-12-31"), "close_adj"] = 0.0
    a = diag.AnchorPrices(prices)
    assert a.at("A", pd.Timestamp("2019-12-31"))["price"] == 0.0  # no fallback to 2019-11
    expect = diag.expectations(prices, SMALL_DATES)
    assert diag.check_s0(expect)["verdict"] == FAIL


def test_zero_anchor_fails_s0_even_when_the_other_anchor_is_missing():
    # Z has a single close of 0 on 2020-01-31: for rev_1m at that date P(s) = 0
    # and P(s-1) has no history. The zero must still be caught.
    prices = pd.concat([small_prices(), pd.DataFrame(
        {"ticker": ["Z"], "trade_date": [pd.Timestamp("2020-01-31")], "close_adj": [0.0]})],
        ignore_index=True)
    expect = diag.expectations(prices, SMALL_DATES)
    s0 = diag.check_s0(expect)
    assert s0["verdict"] == FAIL
    zero = [v for v in s0["violations"] if v["ticker"] == "Z"]
    assert zero and all(v["reason"] == "anchor_not_positive_finite" for v in zero)
    assert any(v["factor"] == "rev_1m" and v["start"]["reason"] == "no_history" for v in zero)


def test_overflow_of_positive_finite_prices_fails_s0():
    prices = small_prices()
    a = prices.ticker == "A"
    prices.loc[a, "close_adj"] = np.where(prices.loc[a, "trade_date"] <= "2019-06-30",
                                          1e-300, 1e300)
    assert diag.check_s0(diag.expectations(prices, SMALL_DATES))["verdict"] == FAIL


def test_all_missing_ticker_stays_in_domain_without_expected_keys(small):
    expect, _ = small
    assert "NA" in expect["domain_tickers"]
    for key in expect["values"]:
        assert not any(t == "NA" for t, _ in expect["values"][key])
    assert diag.check_s0(expect)["verdict"] == PASS


def test_old_warmup_rows_are_expected_missing_and_formulas_differ(small):
    expect, _ = small
    old12 = expect["values"][(diag.OLD, "mom_12_1")]
    assert {s for _, s in old12} == set()  # 12 request rows < warmup 13
    old6 = expect["values"][(diag.OLD, "mom_6_1")]
    assert min(s for _, s in old6) == SMALL_DATES[7]
    new12 = expect["values"][(diag.NEW, "mom_12_1")]
    s = SMALL_DATES[0]  # A: +1% a month, so P(s-1)/P(s-12)-1 = 1.01**11-1
    assert new12[("A", s)] == pytest.approx(1.01 ** 11 - 1, rel=1e-12)


# ----------------------------------------------------------------------
# S1-S5 checkers, each with a case it must reject
# ----------------------------------------------------------------------
def test_s1_rejects_a_changed_hash_or_wrong_reference():
    same = {"after_build": "a" * 64, "after_compare": "a" * 64}
    assert diag.check_s1(same)["verdict"] == PASS
    assert diag.check_s1({**same, "after_compare": "b" * 64})["verdict"] == FAIL
    assert diag.check_s1(same, reference="c" * 64)["verdict"] == FAIL
    assert diag.check_s1(same, reference="a" * 64)["verdict"] == PASS


def test_s2_rejects_missing_extra_and_duplicate_rows(small):
    expect, raw = small
    assert diag.check_s2(expect, raw)["verdict"] == PASS
    both_missing = copy.deepcopy(raw)
    for v in (diag.OLD, diag.NEW):
        both_missing[v]["rev_1m"] = both_missing[v]["rev_1m"][1:]
    assert diag.check_s2(expect, both_missing)["verdict"] == FAIL
    extra = copy.deepcopy(raw)
    extra[diag.NEW]["mom_6_1"].append(["NA", "2020-12-31", 0.1])
    assert diag.check_s2(expect, extra)["verdict"] == FAIL
    dup = copy.deepcopy(raw)
    dup[diag.OLD]["rev_1m"].append(list(dup[diag.OLD]["rev_1m"][0]))
    result = diag.check_s2(expect, dup)
    assert result["verdict"] == FAIL
    assert result["detail"][f"{diag.OLD}:rev_1m"]["duplicates"] == 1


def test_s3_rejects_tampered_and_nonfinite_values_and_empty_is_not_pass(small):
    # On 12 request rows old mom_12_1 has no keys, so S3 cannot be PASS there.
    assert diag.check_s3(*small)["verdict"] == EMPTY
    expect = diag.expectations(small_prices(), month_ends("2019-11-30", 14))
    raw = perfect_raw(expect)
    assert diag.check_s3(expect, raw)["verdict"] == PASS
    tampered = copy.deepcopy(raw)
    tampered[diag.NEW]["mom_12_1"][0][2] += 1e-6
    assert diag.check_s3(expect, tampered)["verdict"] == FAIL
    nan = copy.deepcopy(raw)
    nan[diag.NEW]["rev_1m"][0][2] = float("nan")
    assert diag.check_s3(expect, nan)["verdict"] == FAIL
    empty = copy.deepcopy(raw)
    for v in (diag.OLD, diag.NEW):
        for f in diag.FACTORS:
            empty[v][f] = []
    assert diag.check_s3(expect, empty)["verdict"] == EMPTY


def test_doubling_total_return_in_both_versions_keeps_identity_but_fails_s3():
    # 14 request rows, so old mom_12_1 has keys (row >= 13) common with the new one.
    dates = month_ends("2019-11-30", 14)
    expect = diag.expectations(small_prices(), dates)
    raw = perfect_raw(expect)
    assert diag.check_s4(expect, raw, dates)["detail"]["mom_12_1"]["subchecks"][
        "identity_on_C"] == PASS
    doubled = copy.deepcopy(raw)
    for v in (diag.OLD, diag.NEW):
        for row in doubled[v]["mom_12_1"]:
            row[2] = 2.0 * (1.0 + row[2]) - 1.0
    s4 = diag.check_s4(expect, doubled, dates)["detail"]["mom_12_1"]
    assert s4["C"] > 0 and s4["subchecks"]["identity_on_C"] == PASS
    assert diag.check_s3(expect, doubled)["verdict"] == FAIL


def test_s4_rejects_illegal_old_only_keys_and_a_wrong_identity():
    prices = small_prices()
    dates = month_ends("2019-11-30", 14)
    expect = diag.expectations(prices, dates)
    raw = perfect_raw(expect)
    assert diag.check_s4(expect, raw, dates)["verdict"] == PASS
    illegal = copy.deepcopy(raw)
    old_key = illegal[diag.OLD]["mom_6_1"][0][:2]  # drop it from the new version only
    illegal[diag.NEW]["mom_6_1"] = [r for r in illegal[diag.NEW]["mom_6_1"]
                                    if r[:2] != old_key]
    d = diag.check_s4(expect, illegal, dates)["detail"]["mom_6_1"]
    assert d["subchecks"]["O_empty"] == FAIL
    late_new = copy.deepcopy(raw)
    late_new[diag.OLD]["rev_1m"] = [r for r in late_new[diag.OLD]["rev_1m"]
                                    if r[1] != str(dates[5].date())]
    d = diag.check_s4(expect, late_new, dates)["detail"]["rev_1m"]
    assert d["subchecks"]["N_only_in_old_warmup"] == FAIL
    wrong = copy.deepcopy(raw)
    wrong[diag.OLD]["mom_12_1"] = [[t, d_, v + 0.01] for t, d_, v in wrong[diag.OLD]["mom_12_1"]]
    d = diag.check_s4(expect, wrong, dates)["detail"]["mom_12_1"]
    assert d["subchecks"]["identity_on_C"] == FAIL


def test_s4_numeric_checks_with_no_common_keys_are_not_pass(small):
    expect, raw = small  # old mom_12_1 has no keys at all on 12 request rows
    d = diag.check_s4(expect, raw, SMALL_DATES)["detail"]["mom_12_1"]
    assert d["C"] == 0 and d["subchecks"]["identity_on_C"] == EMPTY
    assert d["verdict"] == EMPTY


def test_s5_rejects_a_changed_or_nonfinite_label_and_empty_is_not_pass():
    rows = [["A", "2020-01-31", 0.5, 0.01], ["B", "2020-01-31", -0.5, 0.02]]
    panels = {v: {f: copy.deepcopy(rows) for f in diag.FACTORS} for v in (diag.OLD, diag.NEW)}
    assert diag.check_s5(panels)["verdict"] == PASS
    changed = copy.deepcopy(panels)
    changed[diag.NEW]["rev_1m"][0][3] = 0.010000000000000002
    assert diag.check_s5(changed)["verdict"] == FAIL
    nan = copy.deepcopy(panels)
    for v in (diag.OLD, diag.NEW):
        nan[v]["mom_6_1"][0][3] = float("nan")
    assert diag.check_s5(nan)["verdict"] == FAIL
    empty = {v: {f: [] for f in diag.FACTORS} for v in (diag.OLD, diag.NEW)}
    assert diag.check_s5(empty)["verdict"] == EMPTY


def test_tolerance_never_passes_nonfinite_values():
    assert diag.close(1.0, 1.0 + 1e-13)
    assert not diag.close(1.0, 1.0 + 1e-9)
    for bad in (float("nan"), float("inf"), None):
        assert not diag.close(bad, bad)


IC_DATES = month_ends("2020-01-31", 6)


def ic_rows():
    rows = [["A", "2020-01-31", 1.0, 0.1]]  # fewer than 5 rows
    rows += [[t, "2020-02-29", 1.0, r] for t, r in zip("ABCDE", [.1, .2, .3, .4, .5],
                                                        strict=True)]  # constant prediction
    rows += [[t, "2020-03-31", p, r] for t, p, r in zip("ABCDE", [1, 2, 3, 4, 5],
                                                         [.5, .4, .3, .2, .1], strict=True)]
    rows += [[t, "2020-04-30", p, r] for t, p, r in zip(
        "ABCDE", [1, 2, 3, 4, 5], [.1, .3, float("nan"), .5, .4], strict=True)]  # NaN label
    return rows  # 2020-05-31 and 2020-06-30: no panel rows


def test_ic_date_accounting_separates_input_confirmed_undefined_dates():
    out = diag.classify_dates(ic_rows(), {"2020-03-31": -1.0}, IC_DATES)
    assert out["counts"] == {"valid": 1, "no_panel_rows": 2, "lt_min_rows": 1, "constant": 1,
                             "nonfinite_input": 1, "unexplained_missing_ic": 0}
    assert out["accounting_complete"] and not any(out["anomalies"].values())
    assert out["verdict"] == PASS and out["mean_ic_equal_weight"] == -1.0
    empty = diag.classify_dates([], {}, IC_DATES)
    assert empty["counts"]["no_panel_rows"] == 6 and empty["mean_ic_equal_weight"] is None
    assert empty["verdict"] == EMPTY


def test_ic_accounting_rejects_extra_missing_and_nonfinite_ic():
    extra = diag.classify_dates(ic_rows(), {"2020-03-31": -1.0, "2020-05-31": 0.2}, IC_DATES)
    assert extra["anomalies"]["unexplained_extra_ic"] == ["2020-05-31"]
    assert extra["verdict"] == FAIL
    outside = diag.classify_dates(ic_rows(), {"2020-03-31": -1.0, "2019-12-31": 0.2}, IC_DATES)
    assert outside["anomalies"]["unexplained_extra_ic"] == ["2019-12-31"]
    assert outside["verdict"] == FAIL
    missed = diag.classify_dates(ic_rows(), {}, IC_DATES)
    assert missed["counts"]["unexplained_missing_ic"] == 1
    assert missed["anomalies"]["unexplained_missing_ic"] == ["2020-03-31"]
    assert missed["verdict"] == FAIL
    nonfinite = diag.classify_dates(ic_rows(), {"2020-03-31": float("nan")}, IC_DATES)
    assert nonfinite["anomalies"]["nonfinite_ic_value"] == ["2020-03-31"]
    assert nonfinite["verdict"] == FAIL


# ----------------------------------------------------------------------
# End to end: the two real source trees on the synthetic database
# ----------------------------------------------------------------------
@pytest.fixture(scope="module")
def positive(tmp_path_factory):
    workdir = tmp_path_factory.mktemp("window-impact") / "positive"
    obs = diag.collect(workdir, "positive")
    return obs, diag.evaluate(obs)


def test_positive_control_passes_s0_to_s5_with_two_isolated_versions(positive):
    obs, report = positive
    assert {k: report[k]["verdict"] for k in diag.CHECKS} == {k: PASS for k in diag.CHECKS}
    assert obs["tag_commits"] == diag.VERSIONS
    old, new = obs["versions"][diag.OLD], obs["versions"][diag.NEW]
    workdir = Path(obs["workdir"])
    assert Path(old["fza_file"]).is_relative_to(workdir / "src-v0.1.0" / "src")
    assert Path(new["fza_file"]).is_relative_to(workdir / "src-v0.2.0" / "src")
    assert old["executable"] == new["executable"] and old["dependencies"] == new["dependencies"]
    s4 = report["S4"]["detail"]["mom_12_1"]
    assert s4["N_after_old_warmup"] >= 1 and s4["O"] >= 1  # GAPM: both directions occur
    for k in ("S2", "S3", "S5"):
        assert all(d["verdict"] == PASS for d in report[k]["detail"].values())


def test_positive_control_boundaries_reach_the_real_outputs(positive):
    obs, _ = positive
    new_rev = {(t, d) for t, d, _ in obs["raw"][diag.NEW]["rev_1m"]}
    assert ("CARRY10", "2020-08-31") in new_rev  # P(2020-07-31) carried 10 days
    assert ("STALE11", "2020-08-31") not in new_rev  # 11 days: stale
    for v in (diag.OLD, diag.NEW):
        for f in diag.FACTORS:
            assert not any(t == "ALLNA" for t, *_ in obs["raw"][v][f])
    assert "ALLNA" in obs["expect"]["domain_tickers"]


def test_ic_accounting_on_the_positive_control(positive):
    _, report = positive
    for v in (diag.OLD, diag.NEW):
        for f in diag.FACTORS:
            for sample in ("own_sample", "common_scoring_keys"):
                c = report["IC"][v][f][sample]
                assert c["accounting_complete"] and not any(c["anomalies"].values())
                assert c["counts"]["valid"] > 0 and c["verdict"] == PASS
    assert report["IC"]["verdict"] == PASS


def test_end_to_end_tampered_copies_are_rejected(positive):
    obs, _ = positive
    gone = copy.deepcopy(obs)
    key = gone["raw"][diag.NEW]["rev_1m"][5][:2]
    for v in (diag.OLD, diag.NEW):
        gone["raw"][v]["rev_1m"] = [r for r in gone["raw"][v]["rev_1m"] if r[:2] != key]
    assert diag.evaluate(gone)["S2"]["verdict"] == FAIL
    extra = copy.deepcopy(obs)
    extra["raw"][diag.OLD]["mom_6_1"].append(list(extra["raw"][diag.OLD]["mom_6_1"][0]))
    assert diag.evaluate(extra)["S2"]["verdict"] == FAIL
    value = copy.deepcopy(obs)
    value["raw"][diag.OLD]["mom_12_1"][0][2] *= 1.001
    assert diag.evaluate(value)["S3"]["verdict"] == FAIL
    doubled = copy.deepcopy(obs)
    for v in (diag.OLD, diag.NEW):
        for row in doubled["raw"][v]["mom_12_1"]:
            row[2] = 2.0 * (1.0 + row[2]) - 1.0
    report = diag.evaluate(doubled)
    assert report["S3"]["verdict"] == FAIL
    assert report["S4"]["detail"]["mom_12_1"]["subchecks"]["identity_on_C"] == PASS
    label = copy.deepcopy(obs)
    old_keys = {tuple(r[:2]) for r in label["panels"][diag.OLD]["rev_1m"]}
    row = next(r for r in label["panels"][diag.NEW]["rev_1m"] if tuple(r[:2]) in old_keys)
    row[3] = row[3] + 1e-12
    assert diag.evaluate(label)["S5"]["verdict"] == FAIL
    missed = copy.deepcopy(obs)
    missed["ic"][diag.NEW]["rev_1m"]["own"].popitem()
    assert diag.evaluate(missed)["IC"]["verdict"] == FAIL
    extra_ic = copy.deepcopy(obs)
    extra_ic["ic"][diag.OLD]["mom_12_1"]["own"]["2019-01-31"] = 0.1  # old warm-up row
    assert diag.evaluate(extra_ic)["IC"]["verdict"] == FAIL
    # The untouched observations still pass: tampering happened on copies only.
    assert diag.evaluate(obs)["S2"]["verdict"] == PASS


def test_end_to_end_file_change_or_wrong_reference_fails_s1(positive, tmp_path):
    obs, _ = positive
    db = Path(obs["workdir"]) / "synthetic.duckdb"
    copy_path = tmp_path / "copy.duckdb"
    copy_path.write_bytes(db.read_bytes() + b"\0")
    changed = {"after_build": obs["hashes"]["after_build"], "after_compare": diag.sha256(copy_path)}
    assert diag.check_s1(changed)["verdict"] == FAIL
    assert diag.check_s1(obs["hashes"], reference="0" * 64)["verdict"] == FAIL
    assert diag.check_s1(obs["hashes"], reference=diag.sha256(db))["verdict"] == PASS


@pytest.mark.parametrize("scenario", ["zero_latest", "overflow"])
def test_end_to_end_s0_violation_stops_before_any_version_runs(tmp_path, scenario):
    obs = diag.collect(tmp_path / scenario, scenario)
    report = diag.evaluate(obs)
    assert report["S0"]["verdict"] == FAIL and report["S0"]["n_violations"] > 0
    assert all(report[k]["verdict"] == NOT_RUN for k in ("S2", "S3", "S4", "S5", "IC"))
    assert "raw" not in obs and obs["versions"] == {}
    assert report["S1"]["verdict"] == PASS


def recording_worker(monkeypatch, after=None):
    """Wrap the real worker and record each mode; optionally act after a call."""
    calls, real = [], diag.worker

    def wrapper(mode, src, args, log):
        calls.append(mode)
        real(mode, src, args, log)
        if after:
            after(mode, args)

    monkeypatch.setattr(diag, "worker", wrapper)
    return calls


def test_s1_wrong_reference_stops_before_any_compute_worker(tmp_path, monkeypatch):
    calls = recording_worker(monkeypatch)
    obs = diag.collect(tmp_path / "wrong-ref", "positive", reference="0" * 64)
    assert calls == ["worker-build"]
    assert obs["s1_gate"] == "failed_before_compare" and "raw" not in obs
    report = diag.evaluate(obs)
    assert report["S0"]["verdict"] == PASS and report["S1"]["verdict"] == FAIL
    assert all(report[k]["verdict"] == NOT_RUN for k in ("S2", "S3", "S4", "S5", "IC"))


def test_s1_file_change_during_compare_stops_before_ic(tmp_path, monkeypatch):
    def change_file(mode, args):
        if mode == "worker-compute" and args[args.index("--out") + 1].endswith("v0.2.0.json"):
            db = Path(args[args.index("--db") + 1])
            db.write_bytes(db.read_bytes() + b"\0")

    calls = recording_worker(monkeypatch, after=change_file)
    obs = diag.collect(tmp_path / "changed", "positive")
    assert calls == ["worker-build", "worker-compute", "worker-compute"]
    assert obs["s1_gate"] == "failed_after_compare" and "ic" not in obs
    report = diag.evaluate(obs)
    assert report["S1"]["verdict"] == FAIL
    assert all(report[k]["verdict"] == NOT_RUN for k in ("S2", "S3", "S4", "S5", "IC"))


# ----------------------------------------------------------------------
# CLI exit code: every check, IC included, must PASS
# ----------------------------------------------------------------------
@pytest.mark.parametrize("ic, code", [(PASS, 0), (FAIL, 1)])
def test_main_exit_code_requires_every_check_including_ic(tmp_path, monkeypatch, ic, code):
    report = {k: {"verdict": PASS} for k in ("S0", "S1", "S2", "S3", "S4", "S5")}
    report["IC"] = {"verdict": ic}
    monkeypatch.setattr(diag, "run_synthetic", lambda workdir, scenario, reference: (None, report))
    assert diag.main(["synthetic", "--workdir", str(tmp_path / "unused")]) == code
