"""Replay saved results without opening a database or computing a factor.

Legacy supplements are extracted from their companion text, never from today's
registry. Full token-stream agreement is required before accepting a supplement.
Source format is provenance, not a research-evidence grade.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from .provenance import implementation_manifest, research_environment
from .render import render_report


def source_record(path, locator, method):
    return {
        "file": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "locator": locator, "extraction_method": method,
    }


def legacy_presentation(text):
    """Parse only the original fixed-column display sections; reject ambiguity."""
    lines = text.splitlines()
    paths = [line.removeprefix("  DATA: ") for line in lines if line.startswith("  DATA: ")]
    if len(paths) != 1:
        raise ValueError("expected exactly one DATA path")
    registered = []
    start = lines.index("REGISTERED FACTORS")
    stop = lines.index("PUBLISHED-ANOMALY DENOMINATOR")
    for line in lines[start:stop]:
        if len(line) >= 78 and line[44:58].strip().isdigit():
            flag = line[30:44].strip()
            if flag not in {"yes", "no"}:
                raise ValueError("invalid registered-factor fundamentals flag")
            registered.append({
                "factor_id": line[2:16].strip(), "category": line[16:30].strip(),
                "uses_fundamentals": flag == "yes",
                "n_falsification_criteria": int(line[44:58]),
                "plausible_range": line[58:].strip(),
            })
    coverage = []
    if "DATA QUALITY" in lines:
        for line in lines[lines.index("DATA QUALITY"):start]:
            if line.rstrip().endswith("%") and line[18:30].strip().replace(",", "").isdigit():
                coverage.append({
                    "column": line[2:18].strip(),
                    "non_null": int(line[18:30].replace(",", "")),
                    "coverage": float(line[30:].strip().rstrip("%")) / 100,
                })
    if not registered:
        raise ValueError("registered-factor snapshot missing")
    return {
        "database_display": paths[0], "registered_factors": registered,
        "price_coverage": coverage,
        "capture_method": "legacy_text_display_extraction_not_original_structured_capture",
        "coverage_precision": "display_rounding_only; omitted columns not reconstructed",
    }


def replay(bundle_path, outdir, legacy_text=None):
    bundle = json.loads(bundle_path.read_text(encoding="utf-8"))
    original = copy.deepcopy(bundle)
    sources = [source_record(bundle_path, "/", "JSON decode; no recalculation")]
    if "presentation" not in bundle:
        if legacy_text is None:
            raise ValueError(
                "legacy bundle requires companion text for missing presentation inputs"
            )
        text = legacy_text.read_text(encoding="utf-8")
        bundle["presentation"] = legacy_presentation(text)
        sources.append(source_record(
            legacy_text, "DATA / DATA QUALITY / REGISTERED FACTORS",
            "fixed-column display extraction; coverage precision limited to printed percentage",
        ))
        rendered = render_report(bundle, local_sensitivity_notice=False)
        if rendered.split() != text.split():
            raise ValueError("source conflict: rendered token stream differs from companion report")
        rendered = render_report(bundle)
    else:
        rendered = render_report(bundle)
        if legacy_text is not None:
            raise ValueError("companion text is only supported for legacy bundles")
    if {k: v for k, v in bundle.items() if k != "presentation"} != {
        k: v for k, v in original.items() if k != "presentation"
    }:
        raise ValueError("replay altered computation fields")
    manifest = {
        "role": "PRESENTATION_REPLAY_NOT_A_NEW_COMPUTATION",
        "rendered_at_utc": datetime.now(timezone.utc).isoformat(),
        "sources": sources,
        "renderer": source_record(Path(__file__).with_name("render.py"), "/", "source bytes"),
        "replay_adapter": source_record(Path(__file__), "/", "source bytes"),
        "render_implementation": implementation_manifest(),
        "render_environment": research_environment(),
        "computation_fields_changed": False,
        "original_schema_version": original["schema_version"],
        "supplement_added_after_run": "presentation" not in original,
        "source_types_are_not_evidence_grades": True,
        "line_endings": "LF",
        "presentation_changes": ["84-column wrapping", "one excluded key per line",
                                 "repeat sensitivity limitation within each comparison block"],
        "report_sha256": hashlib.sha256(rendered.encode("utf-8")).hexdigest(),
    }
    # Never overwrite original or previously rendered artifacts.
    outdir.mkdir(parents=True, exist_ok=False)
    for name, value in (
        ("demo_report.txt", rendered),
        ("replay_input.json", json.dumps(bundle, indent=2, allow_nan=False)),
        ("render_manifest.json", json.dumps(manifest, indent=2, allow_nan=False)),
    ):
        (outdir / name).write_text(value, encoding="utf-8", newline="\n")
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("bundle", type=Path)
    parser.add_argument("--legacy-text", type=Path)
    parser.add_argument("--outdir", type=Path, required=True)
    args = parser.parse_args()
    replay(args.bundle, args.outdir, args.legacy_text)


if __name__ == "__main__":
    main()
