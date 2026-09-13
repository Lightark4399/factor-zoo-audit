"""Document projection checks, not assertions of computational correctness."""
import copy
import json
import runpy
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PROJECTOR = runpy.run_path(str(ROOT / "scripts" / "readme_examples.py"))


@pytest.fixture
def bundle():
    return json.loads((ROOT / PROJECTOR["ARCHIVE"]).read_text(encoding="utf-8"))


def test_readme_examples_match_scoped_archive_projection(bundle):
    PROJECTOR["validate_readme"]((ROOT / "README.md").read_text(encoding="utf-8"), bundle)


@pytest.mark.parametrize("old,new", [
    ("+0.0082", "+0.0145"),
    ("DIAGNOSTIC_ONLY, not a replacement PASS", "PASS"),
    ("This does not mean all rows are future-filed", "All rows are future-filed"),
    ("not a pure sample-effect", "a pure sample-effect"),
])
def test_mutated_number_or_interpretation_fails(bundle, old, new):
    text = PROJECTOR["examples"](bundle)
    assert old in text
    with pytest.raises(ValueError, match="scoped wording drifted"):
        PROJECTOR["validate_readme"](text.replace(old, new), bundle)


@pytest.mark.parametrize("field,value", [
    ("status", "INCONCLUSIVE"),
    ("ic_gap", 0.0019),
    ("outcome_identity", {"status": "MISMATCHED"}),
    ("sample", {"scoring_scope": "ARM_SPECIFIC_OBSERVATIONS_ON_SHARED_DATES"}),
])
def test_same_number_is_not_enough_when_scope_changes(bundle, field, value):
    changed = copy.deepcopy(bundle)
    changed["vintage_comparisons"]["asset_growth"]["detail"]["layers"][
        "common-observation"][field] = value
    with pytest.raises(ValueError, match="requires review"):
        PROJECTOR["examples"](changed)


def test_unimplemented_gate_cannot_be_promoted_silently(bundle):
    bundle["research_gates"]["multiple_testing"]["status"] = "PASS"
    with pytest.raises(ValueError, match="unimplemented gates"):
        PROJECTOR["examples"](bundle)
