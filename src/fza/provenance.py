"""Runtime provenance for research outputs."""

from __future__ import annotations

import hashlib
import platform
from importlib.metadata import PackageNotFoundError, version
from importlib.resources import files

RESEARCH_LOCK = "research-requirements.lock"
CORE_PACKAGES = ("pandas", "numpy", "scipy", "statsmodels")


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
