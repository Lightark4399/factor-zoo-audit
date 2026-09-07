"""Projection regressions do not establish that the policy itself is correct."""

import json
from pathlib import Path
from types import SimpleNamespace

from fza.demo import main
from fza.qualification import qualification_lines, qualification_policy, readme_qualification
from fza.reporting import factor_record
from fza.store import Store


def test_policy_is_not_shared_mutable_state():
    changed = qualification_policy()
    changed["claims"]["selected_sample_statistics"]["status"] = "TEST_CHANGED"
    unchanged = qualification_policy()["claims"]["selected_sample_statistics"]
    assert unchanged["status"] != "TEST_CHANGED"


def test_readme_projects_the_current_policy():
    readme = (Path(__file__).parents[1] / "README.md").read_text(encoding="utf-8")
    assert readme.count("<!-- qualification:begin;") == 1
    assert readme.count("<!-- qualification:end -->") == 1
    assert readme_qualification() in readme


def test_policy_changes_propagate_through_all_report_exits(tmp_path, capsys, monkeypatch):
    # Deliberately different labels expose hard-coded copies of today's policy.
    policy = qualification_policy()
    policy["policy_id"] = "TEST_ONLY_POLICY"
    policy["statistics_status"] = "TEST_DIAGNOSTIC"
    policy["statistics_notice"] = "TEST statistics notice"
    claim = policy["claims"]["market_wide_anomaly_survival"]
    claim["status"] = "TEST_NO_EVIDENCE"
    claim["notice"] = "TEST claim notice"
    monkeypatch.setattr("fza.provenance.qualification_policy", lambda: policy)
    db = tmp_path / "transport.duckdb"
    with Store(str(db)):
        pass
    outdir = tmp_path / "report"
    assert main(["--db", str(db), "--outdir", str(outdir)]) == 0
    outputs = [capsys.readouterr().out,
               (outdir / "demo_report.txt").read_text(encoding="utf-8"),
               readme_qualification(policy)]
    for output in outputs:
        for line in qualification_lines(policy):
            assert line in output
    evidence = json.loads((outdir / "demo_evidence.json").read_text(encoding="utf-8"))
    bundle = json.loads((outdir / "demo_run.json").read_text(encoding="utf-8"))
    assert bundle["evidence"] == evidence
    for key, value in policy.items():
        assert evidence[key] == value
    assert bundle["artifact_role"].startswith(policy["statistics_status"])

    # Factor records must project the supplied policy too. The populated CLI
    # case separately checks this serializer is actually used by the pipeline.
    payload = SimpleNamespace(to_dict=lambda: {"test_payload": 17})
    run = SimpleNamespace(
        protocol=payload, universe_filter=payload, cleaning=payload, label_join=payload,
        construction_filters=[], read_path_check={}, magnitude_check={}, naive_trap={},
    )
    record = factor_record(run, policy)
    assert record["statistics_status"] == policy["statistics_status"]
    assert record["claims"] == policy["claims"]
    assert record["protocol"] == {"test_payload": 17}
    record["claims"]["market_wide_anomaly_survival"]["status"] = "TEST_MUTATED"
    assert policy["claims"]["market_wide_anomaly_survival"]["status"] == "TEST_NO_EVIDENCE"
