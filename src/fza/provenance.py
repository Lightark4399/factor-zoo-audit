"""Runtime provenance for research outputs."""

from __future__ import annotations

import hashlib
import json
import platform
from importlib.metadata import PackageNotFoundError, version
from importlib.resources import files
from pathlib import Path

RESEARCH_LOCK = "research-requirements.lock"
CORE_PACKAGES = ("pandas", "numpy", "scipy", "statsmodels")


def file_sha256(path: Path) -> str:
    """Fingerprint bytes without loading a database into memory."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def dataset_evidence(db_path: Path, mode: str) -> dict:
    """Report source declarations without treating them as certification.

    Legacy ingest sidecars have no database hash. Their contents are explicitly
    unbound declarations. Even a matching hash plus ``true`` cannot establish
    historical completeness, terminal outcomes or the four research gates.
    This diagnostic entry point has no research-promotion path.
    """
    reasons = ["synthetic_fixture"] if mode == "fixture" else []
    report = {
        "schema_version": 1,
        "mode": mode,
        "statistics_status": "DIAGNOSTIC_ONLY",
        "database_path": str(db_path.resolve()) if mode == "real" else None,
        "database_sha256": None,
        "sidecar_path": None,
        "sidecar_sha256": None,
        "sidecar_binding": "NOT_APPLICABLE" if mode == "fixture" else "UNVERIFIED",
        "declared_research_evidence": None,
        "declared_run_purpose": None,
        "declared_survivorship_prone_share": None,
        "reasons": reasons,
        "claims": {
            "selected_sample_statistics": {
                "status": "DIAGNOSTIC_ONLY",
                "reason": "describes_this_run_not_market_wide_evidence",
            },
            "market_wide_anomaly_survival": {
                "status": "NOT_EVIDENCE",
                "reason": "historical_membership_outcomes_and_research_gates_not_validated",
            },
        },
    }
    if mode == "fixture":
        return report
    if mode != "real":
        raise ValueError(f"unknown dataset mode: {mode}")
    reasons.append("research_qualification_not_implemented")
    try:
        report["database_sha256"] = file_sha256(db_path)
    except OSError:
        reasons.append("database_hash_unavailable")
    sidecar = db_path.with_suffix(".report.json")
    report["sidecar_path"] = str(sidecar.resolve())
    try:
        raw = sidecar.read_bytes()
    except FileNotFoundError:
        reasons.append("sidecar_missing")
        return report
    except OSError:
        reasons.append("sidecar_unreadable")
        return report
    report["sidecar_sha256"] = hashlib.sha256(raw).hexdigest()
    try:
        declaration = json.loads(raw)
    except (ValueError, UnicodeError):
        reasons.append("sidecar_malformed")
        return report
    if not isinstance(declaration, dict) or type(declaration.get("research_evidence")) is not bool:
        reasons.append("sidecar_invalid_schema")
        return report
    report["declared_research_evidence"] = declaration["research_evidence"]
    purpose = declaration.get("run_purpose")
    report["declared_run_purpose"] = purpose if isinstance(purpose, str) else None
    prices = declaration.get("prices")
    share = prices.get("survivorship_prone_share") if isinstance(prices, dict) else None
    if type(share) in (int, float) and 0 <= share <= 1:
        report["declared_survivorship_prone_share"] = share
    expected = declaration.get("database_sha256")
    if expected is not None:
        report["sidecar_binding"] = (
            "MATCHED" if isinstance(expected, str) and expected == report["database_sha256"]
            else "MISMATCH"
        )
    # A main-file hash is not a snapshot identity when an active WAL exists.
    if Path(str(db_path) + ".wal").exists():
        report["sidecar_binding"] = "UNVERIFIED"
        reasons.append("database_wal_present")
    if report["sidecar_binding"] != "MATCHED":
        reasons.append("sidecar_database_binding_" + report["sidecar_binding"].lower())
    if not declaration["research_evidence"]:
        reasons.append("declared_diagnostic")
    return report


def _installed_version(distribution: str) -> str:
    try:
        return version(distribution)
    except PackageNotFoundError:
        return "not-installed"


def research_environment() -> dict[str, object]:
    """Return actual core versions and the hash of the shipped research lock."""
    lock_bytes = files("fza").joinpath(RESEARCH_LOCK).read_bytes()
    actual = {name: _installed_version(name) for name in CORE_PACKAGES}
    locked = {}
    for line in lock_bytes.decode("utf-8").splitlines():
        if "==" not in line or line.lstrip().startswith("#"):
            continue
        name, pinned = line.split("==", 1)
        locked[name.lower()] = pinned
    mismatches = {
        name: {"installed": actual[name], "locked": locked.get(name, "not-locked")}
        for name in CORE_PACKAGES
        if actual[name] != locked.get(name)
    }
    return {
        "python": platform.python_version(),
        **actual,
        "lock_file": RESEARCH_LOCK,
        "lock_sha256": hashlib.sha256(lock_bytes).hexdigest(),
        "lock_status": "MATCHED" if not mismatches else "MISMATCH",
        "lock_mismatches": mismatches,
    }
