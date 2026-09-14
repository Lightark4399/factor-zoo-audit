"""Navigation checks, not a correctness oracle for historical results."""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RECORDS = ROOT / "docs" / "validation"


def test_validation_index_lists_every_record():
    records = set(RECORDS.glob("VALIDATION*.md"))
    assert records
    assert not list(ROOT.glob("VALIDATION*.md"))
    index = (RECORDS / "README.md").read_text(encoding="utf-8")
    targets = set(re.findall(r"\]\((VALIDATION\w*\.md)\)", index))
    assert targets == {record.name for record in records}


def test_validation_navigation_targets_exist():
    # Scope: links in this index/record collection, and validation-path references
    # in editable Markdown surfaces. Exclude ignored local environments and do
    # not interpret archived output JSON/text or arbitrary prose as interfaces.
    surfaces = [*ROOT.glob("*.md"), *RECORDS.glob("*.md")]
    surfaces.extend((ROOT / "examples" / "outputs").rglob("README.md"))
    for source in surfaces:
        text = source.read_text(encoding="utf-8")
        targets = re.findall(r"\]\(([^)]+)\)", text)
        targets += re.findall(r"`([^`\n]*VALIDATION\w*\.md)`", text)
        for target in targets:
            if "://" in target or target.startswith("#"):
                continue
            if source.parent != RECORDS and "VALIDATION" not in target:
                continue
            path = target.split("#", 1)[0]
            assert (source.parent / path).is_file(), f"{source}: missing {target}"
