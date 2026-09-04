"""Release resources must exist independently of an editable checkout."""

import hashlib
from importlib.resources import files

from fza.factors.registry import load_all
from fza.provenance import RESEARCH_LOCK, research_environment
from fza.store import Store


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
    assert environment["lock_status"] == "MATCHED"
    assert environment["lock_mismatches"] == {}
    for package in ("python", "pandas", "numpy", "scipy", "statsmodels"):
        assert environment[package]
