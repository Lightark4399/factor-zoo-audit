"""Refusal checks for scripts/research_note/run_vintage_series.py, plus the
checker's self-test. No store, no fza import: every case stops before loading."""

import importlib.util
import os
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).parents[1] / "scripts" / "research_note"


def load(name):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


run = load("run_vintage_series")


@pytest.fixture
def paths(tmp_path):
    db = tmp_path / "store.duckdb"
    db.write_bytes(b"not a real store")
    return db, tmp_path / "out" / "series.json", tmp_path / "out" / "run.log"


@pytest.mark.parametrize("pair", [("db", "out"), ("db", "log"), ("out", "log")])
def test_same_path_refused(paths, pair):
    p = dict(zip(("db", "out", "log"), paths, strict=True))
    p[pair[1]] = p[pair[0]]
    with pytest.raises(SystemExit, match="same path"):
        run.check_paths(p["db"], p["out"], p["log"], force=True)


def test_same_path_refused_after_resolving(paths, monkeypatch):
    db, _, log = paths
    monkeypatch.chdir(db.parent)
    with pytest.raises(SystemExit, match="same path"):
        run.check_paths(db, Path("out") / ".." / db.name, log, force=True)
    if os.name == "nt":  # case-insensitive file system
        with pytest.raises(SystemExit, match="same path"):
            run.check_paths(db, str(db).upper(), log, force=True)


@pytest.mark.parametrize("existing", ["out", "log"])
def test_existing_output_refused_without_force(paths, existing):
    db, out, log = paths
    target = out if existing == "out" else log
    target.parent.mkdir(parents=True)
    target.write_text("archived", encoding="utf-8")
    with pytest.raises(SystemExit, match="already exists"):
        run.check_paths(db, out, log)
    assert run.check_paths(db, out, log, force=True) == (db.resolve(), out.resolve(),
                                                         log.resolve())
    assert target.read_text(encoding="utf-8") == "archived"


@pytest.mark.parametrize("db_exists", [True, False])
def test_no_log_or_output_before_store_check_passes(paths, monkeypatch, db_exists):
    db, out, log = paths
    if not db_exists:
        db.unlink()
    monkeypatch.setattr(sys, "stdout", sys.stdout)  # main() replaces both; restore after
    monkeypatch.setattr(sys, "stderr", sys.stderr)
    with pytest.raises(SystemExit):
        run.main(["--db", str(db), "--factor", "bm_ratio", "--out", str(out),
                  "--log", str(log), "--expected-sha256", "0" * 64])
    assert not log.exists() and not out.exists() and not out.parent.exists()


def test_checker_selftest():
    load("check_vintage_series").selftest()
