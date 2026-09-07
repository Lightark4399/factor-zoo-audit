"""AS-03 regressions through the real-store CLI, never a mocked reporter."""

import json

import pytest

from fza.demo import main
from fza.fixtures import FixtureSpec, load_fixture_into
from fza.store import Store


@pytest.mark.parametrize(
    "sidecar, reason",
    [
        (None, "sidecar_missing"),
        ("{broken", "sidecar_malformed"),
        ("[]", "sidecar_invalid_schema"),
        ('{"research_evidence": "false"}', "sidecar_invalid_schema"),
        ('{"research_evidence": false}', "declared_diagnostic"),
        ('{"research_evidence": true}', "research_qualification_not_implemented"),
    ],
)
def test_real_store_qualification_survives_every_report_exit(tmp_path, capsys, sidecar, reason):
    # Empty stores keep the transport matrix cheap. A populated case below
    # separately exercises actual factor computations and vintage comparisons.
    db = tmp_path / "sample.duckdb"
    with Store(str(db)):
        pass
    if sidecar is not None:
        db.with_suffix(".report.json").write_text(sidecar, encoding="utf-8")
    outdir = tmp_path / "output"

    assert main(["--db", str(db), "--outdir", str(outdir)]) == 0
    stdout = capsys.readouterr().out
    saved = (outdir / "demo_report.txt").read_text(encoding="utf-8")
    for output in (stdout, saved):
        assert "DIAGNOSTIC_ONLY" in output
        assert "NOT_EVIDENCE" in output
        assert reason in output
        assert "The gap above is the value" not in output
        assert "NOT findings" in output
    assert stdout.startswith(saved)
    evidence = json.loads((outdir / "demo_evidence.json").read_text(encoding="utf-8"))
    assert evidence["mode"] == "real"
    assert evidence["statistics_status"] == "DIAGNOSTIC_ONLY"
    assert evidence["claims"]["market_wide_anomaly_survival"]["status"] == "NOT_EVIDENCE"
    assert reason in evidence["reasons"]


def test_populated_real_store_retains_diagnostic_label_with_actual_results(tmp_path, capsys):
    db = tmp_path / "populated.duckdb"
    with Store(str(db)) as store:
        load_fixture_into(store, FixtureSpec(n_securities=12))
    db.with_suffix(".report.json").write_text(
        json.dumps({"research_evidence": False, "run_purpose": "diagnostic_scale",
                    "prices": {"survivorship_prone_share": 1.0}}),
        encoding="utf-8",
    )
    outdir = tmp_path / "output"
    assert main(["--db", str(db), "--max-dates", "3", "--outdir", str(outdir)]) == 0
    output = capsys.readouterr().out
    assert "point-in-time IC" in output
    assert "  OK" in output
    assert "DIAGNOSTIC_ONLY" in output.split("STANDARD PROTOCOL")[1].split("HISTORICAL")[0]
    assert "NOT findings" in (outdir / "demo_report.txt").read_text(encoding="utf-8")
    evidence = json.loads((outdir / "demo_evidence.json").read_text(encoding="utf-8"))
    assert evidence["declared_research_evidence"] is False
    assert evidence["declared_survivorship_prone_share"] == 1.0
    assert evidence["sidecar_binding"] == "UNVERIFIED"
    bundle = json.loads((outdir / "demo_run.json").read_text(encoding="utf-8"))
    assert bundle["evidence"] == evidence
    assert len(bundle["selected_roster"]) == 12
    assert bundle["database_bytes_unchanged"] is True
    assert len(bundle["configuration"]["signal_dates"]) == 3
    assert len(bundle["factors"]) == 10
    for record in bundle["factors"].values():
        if record["computation_status"] != "COMPLETED":
            assert record["protocol"] is None
            continue
        assert record["claims"] == evidence["claims"]
        assert record["statistics_status"] == evidence["statistics_status"]
        assert record["universe_filter"]["n_output"] == record["cleaning"]["n_input"]
        assert record["cleaning"]["n_output"] == record["label_join"]["n_input"]
        assert record["label_join"]["n_output"] == record["protocol"]["n_observations"]
    for gate, record in bundle["research_gates"].items():
        assert record["status"] in {"UNRESOLVED", "NOT_IMPLEMENTED"}, gate
        assert record["status"] in output
