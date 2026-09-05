"""Release resources must exist independently of an editable checkout."""

import hashlib
from importlib.metadata import version
from importlib.resources import files

import pytest

from fza.factors.registry import load_all
from fza.provenance import RESEARCH_LOCK, research_environment
from fza.store import Store


def _locked_versions():
    text = files("fza").joinpath(RESEARCH_LOCK).read_text(encoding="utf-8")
    return dict(
        line.strip().split("==", 1)
        for line in text.splitlines()
        if "==" in line and not line.lstrip().startswith("#")
    )


def test_runtime_resources_are_packaged_and_readable():
    assert files("fza").joinpath("sql", "001_schema.sql").is_file()
    assert files("fza.factors").joinpath("denominators.yaml").is_file()
    cards = files("fza.factors").joinpath("cards")
    assert len(list(cards.iterdir())) == 10
    assert len(load_all()) == 10
    with Store(":memory:") as store:
        assert store.fundamentals_asof("2020-01-01").empty


def test_research_lock_is_packaged_and_its_hash_is_reportable():
    lock = files("fza").joinpath(RESEARCH_LOCK)
    expected = hashlib.sha256(lock.read_bytes()).hexdigest()
    environment = research_environment()

    assert lock.is_file()
    assert environment["lock_sha256"] == expected
    locked = _locked_versions()
    expected_mismatches = {
        package: {"installed": version(package), "locked": locked[package]}
        for package in ("pandas", "numpy", "scipy", "statsmodels")
        if version(package) != locked[package]
    }
    assert environment["lock_status"] == ("MISMATCH" if expected_mismatches else "MATCHED")
    assert environment["lock_mismatches"] == expected_mismatches
    for package in ("python", "pandas", "numpy", "scipy", "statsmodels"):
        assert environment[package]


@pytest.mark.parametrize("changed_package", [None, "pandas", "numpy", "scipy", "statsmodels"])
def test_lock_status_tracks_each_numerical_dependency(monkeypatch, changed_package):
    """A mismatch is valid diagnostic output, not an unsupported environment.

    Each library is perturbed independently so a pandas-only implementation
    cannot vouch for the remaining numerical dependencies.
    """
    installed = _locked_versions()
    if changed_package is not None:
        installed[changed_package] = "not-installed"
    monkeypatch.setattr("fza.provenance._installed_version", installed.__getitem__)

    report = research_environment()

    assert report["lock_status"] == ("MATCHED" if changed_package is None else "MISMATCH")
    assert report["lock_mismatches"] == (
        {}
        if changed_package is None
        else {
            changed_package: {
                "installed": "not-installed",
                "locked": _locked_versions()[changed_package],
            }
        }
    )
