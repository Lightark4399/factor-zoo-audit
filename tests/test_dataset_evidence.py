"""Dataset qualification is fail-closed independently of today's sidecars."""

import json

import pytest

from fza.provenance import dataset_evidence, file_sha256


@pytest.mark.parametrize("flag", [True, False])
@pytest.mark.parametrize("binding", ["MATCHED", "MISMATCH", "UNVERIFIED"])
def test_even_matching_declarations_cannot_promote_research(tmp_path, flag, binding):
    db = tmp_path / "data.duckdb"
    db.write_bytes(b"synthetic bytes for provenance, not a SQL fixture")
    declaration = {"research_evidence": flag}
    if binding != "UNVERIFIED":
        declaration["database_sha256"] = file_sha256(db) if binding == "MATCHED" else "0" * 64
    db.with_suffix(".report.json").write_text(json.dumps(declaration), encoding="utf-8")
    result = dataset_evidence(db, "real")
    assert result["sidecar_binding"] == binding
    assert result["declared_research_evidence"] is flag
    assert result["statistics_status"] == "DIAGNOSTIC_ONLY"
    assert result["claims"]["market_wide_anomaly_survival"]["status"] == "NOT_EVIDENCE"


def test_unreadable_sidecar_is_not_implicit_approval(tmp_path):
    db = tmp_path / "data.duckdb"
    db.write_bytes(b"synthetic")
    db.with_suffix(".report.json").mkdir()
    assert "sidecar_unreadable" in dataset_evidence(db, "real")["reasons"]


def test_active_wal_invalidates_main_file_binding(tmp_path):
    db = tmp_path / "data.duckdb"
    db.write_bytes(b"synthetic")
    db.with_suffix(".report.json").write_text(
        json.dumps({"research_evidence": True, "database_sha256": file_sha256(db)}),
        encoding="utf-8",
    )
    (tmp_path / "data.duckdb.wal").write_bytes(b"uncheckpointed")
    result = dataset_evidence(db, "real")
    assert result["sidecar_binding"] == "UNVERIFIED"
    assert "database_wal_present" in result["reasons"]


def test_fixture_never_reads_an_adjacent_real_declaration(tmp_path):
    db = tmp_path / "absent.duckdb"
    db.with_suffix(".report.json").write_text('{"research_evidence":true}', encoding="utf-8")
    result = dataset_evidence(db, "fixture")
    assert result["reasons"] == ["synthetic_fixture"]
    assert result["declared_research_evidence"] is None
