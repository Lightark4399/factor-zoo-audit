"""Build a diagnostic, commit-by-commit numerical attribution ledger.

The outputs from this script are investigative artefacts.  They describe how
the synthetic fixture behaves at historical commits; they are deliberately not
regression expectations.  Tests must assert economic invariants, not these
captured numbers.

Two commands are provided::

    python examples/attribute_commit_deltas.py snapshot \
        --source-root <checked-out-commit> --commit <sha> --output out.json
    python examples/attribute_commit_deltas.py compare \
        --environment locked --snapshots <ordered snapshot paths> \
        --json-output ledger.json --markdown-output ledger.md

Keeping the driver outside each historical checkout lets one version of the
measurement code inspect every commit without modifying those commits.
"""

from __future__ import annotations

import argparse
import hashlib
import inspect
import json
import math
import platform
import sys
from pathlib import Path
from typing import Any

STATUS = "DIAGNOSTIC_ONLY"
ASSERTION_STATUS = "NOT_AN_ASSERTION"
SIGNAL_DATE_START = "2019-01-31"
SIGNAL_DATE_END = "2021-06-30"

COMMIT_EXPECTATIONS = {
    "770a065": {
        "label": "pre-fix characterization only",
        "allowed_prefixes": [],
    },
    "0991a06": {
        "label": "historical-universe eligibility gate",
        "allowed_prefixes": [
            "eligible.",
            "cleaned.",
            "panel.",
            "performance.",
            "label_attrition.",
            "magnitude.",
        ],
    },
    "9a2a193": {
        "label": "explicit pct_change missing-value semantics",
        "allowed_prefixes": [
            "raw.",
            "eligible.",
            "cleaned.",
            "panel.",
            "performance.",
            "label_attrition.",
            "magnitude.",
        ],
        "factors": ["idio_vol"],
        "environment_note": (
            "A numerical delta is expected only where the installed pandas "
            "default pads pct_change gaps (not in the locked pandas 3.x run)."
        ),
    },
    "e66ab5c": {
        "label": "bounded freshness for market-derived signals",
        "allowed_prefixes": [
            "raw.",
            "eligible.",
            "cleaned.",
            "panel.",
            "performance.",
            "label_attrition.",
            "magnitude.",
        ],
        "factors": ["idio_vol", "mom_12_1", "mom_6_1", "rev_1m", "turnover"],
    },
    "9e06d2b": {
        "label": "label-attrition diagnostics",
        "allowed_prefixes": ["label_attrition.native_outcomes"],
    },
    "1d51a59": {
        "label": "market-session execution-date semantics",
        "allowed_prefixes": [
            "panel.",
            "performance.",
            "label_attrition.",
        ],
    },
    "583d7e9": {
        "label": "definition audit documentation only",
        "allowed_prefixes": [],
    },
}


def _normalise(value: Any) -> Any:
    """Convert dataframe scalars to stable, JSON-safe representations."""
    if value is None:
        return None
    if hasattr(value, "isoformat"):
        try:
            return value.isoformat()
        except (TypeError, ValueError):
            pass
    if hasattr(value, "item"):
        try:
            value = value.item()
        except (ValueError, AttributeError):
            pass
    if isinstance(value, float):
        if math.isnan(value):
            return "NaN"
        if math.isinf(value):
            return "Infinity" if value > 0 else "-Infinity"
        return format(value, ".17g")
    if isinstance(value, (str, int, bool)):
        return value
    return str(value)


def _frame_hash(frame, columns: list[str]) -> str:
    """Hash a frame independent of its current ordering and pandas internals."""
    present = [column for column in columns if column in frame.columns]
    if not present:
        return hashlib.sha256(b"[]").hexdigest()
    rows = [
        {column: _normalise(value) for column, value in row.items()}
        for row in frame[present].to_dict(orient="records")
    ]
    rows.sort(key=lambda row: json.dumps(row, sort_keys=True, separators=(",", ":")))
    encoded = json.dumps(rows, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def _stage(frame, value_columns: list[str]) -> dict[str, Any]:
    key_columns = ["ticker", "signal_date"]
    return {
        "n_rows": int(len(frame)),
        "n_keys": int(frame[key_columns].drop_duplicates().shape[0]),
        "key_hash": _frame_hash(frame, key_columns),
        "value_hash": _frame_hash(frame, key_columns + value_columns),
    }


def _finite(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _install_minimum_version_shims(pd) -> tuple[dict[str, Any], Any, Any]:
    """Make historical code runnable on pandas 2.0, while recording faults.

    ``ME`` and ``QE`` are newer spellings for the older ``M`` and ``Q`` aliases.
    The repository declares pandas 2.0 support but uses the newer spellings in
    both source and tests.  The diagnostic needs to get past that independent
    compatibility failure to measure pct_change, so it applies only this exact
    synonym mapping and reports that the unmodified checkout was not runnable.
    """
    unsupported: list[str] = []
    for alias in ("ME", "QE"):
        try:
            pd.date_range("2020-01-01", periods=2, freq=alias)
        except ValueError:
            unsupported.append(alias)

    original_date_range = pd.date_range
    original_stack = pd.DataFrame.stack
    if unsupported:
        replacements = {"ME": "M", "QE": "Q"}

        def compatible_date_range(*args, **kwargs):
            frequency = kwargs.get("freq")
            if frequency in replacements:
                kwargs["freq"] = replacements[frequency]
            return original_date_range(*args, **kwargs)

        pd.date_range = compatible_date_range

    stack_supports_future = "future_stack" in inspect.signature(original_stack).parameters
    if not stack_supports_future:

        def compatible_stack(frame, level=-1, dropna=True, **kwargs):
            future_stack = kwargs.pop("future_stack", False)
            if kwargs:
                unexpected = ", ".join(sorted(kwargs))
                raise TypeError(f"unsupported stack arguments: {unexpected}")
            # future_stack retains the observed column combinations instead of
            # dropping missing values.  For the single-level wide frames used
            # here, old stack(dropna=False) is the matching operation.
            if future_stack:
                dropna = False
            return original_stack(frame, level=level, dropna=dropna)

        pd.DataFrame.stack = compatible_stack

    blockers = []
    if unsupported:
        blockers.append("new_frequency_aliases")
    if not stack_supports_future:
        blockers.append("DataFrame.stack(future_stack=True)")

    observation = {
        "unsupported_frequency_aliases": unsupported,
        "stack_supports_future_stack": stack_supports_future,
        "unmodified_checkout_runnable": not blockers,
        "diagnostic_shim": (
            {
                "frequency_aliases": {"ME": "M", "QE": "Q"} if unsupported else None,
                "future_stack": "DataFrame.stack(dropna=False)"
                if not stack_supports_future
                else None,
            }
            if blockers
            else None
        ),
        "blockers": blockers,
        "classification": "UNEXPECTED_COMPATIBILITY_BLOCKER" if blockers else "NONE",
    }
    return observation, original_date_range, original_stack


def _call_panel_builder(prepare_module, cleaned, prices):
    """Call the panel API on either side of the date-semantics rename."""
    if hasattr(prepare_module, "build_panel_with_report"):
        function = prepare_module.build_panel_with_report
        parameters = inspect.signature(function).parameters
        kwargs = (
            {"horizon_sessions": 21, "execution_lag_sessions": 1}
            if "horizon_sessions" in parameters
            else {"horizon_days": 21, "execution_lag": 1}
        )
        panel, report = function(cleaned, prices, **kwargs)
        native = report.to_dict()
        return panel, native

    function = prepare_module.build_panel
    parameters = inspect.signature(function).parameters
    kwargs = (
        {"horizon_sessions": 21, "execution_lag_sessions": 1}
        if "horizon_sessions" in parameters
        else {"horizon_days": 21, "execution_lag": 1}
    )
    return function(cleaned, prices, **kwargs), None


def create_snapshot(source_root: Path, commit: str) -> dict[str, Any]:
    """Measure every factor in one historical source checkout."""
    source_root = source_root.resolve()
    sys.path.insert(0, str(source_root / "src"))

    import numpy as np
    import pandas as pd
    import scipy
    import statsmodels

    from fza.factors.registry import load_all
    from fza.fixtures import FixtureSpec, load_fixture_into
    from fza.pipeline import prepare as prepare_module
    from fza.pipeline import run as run_module
    from fza.pipeline.protocol import run_protocol
    from fza.store import Store

    # The ``ME`` alias was introduced after the declared pandas 2.0 floor.
    # Using the offset object keeps the diagnostic calendar identical in both
    # environments instead of making the driver itself the compatibility fault.
    compatibility, original_date_range, original_stack = _install_minimum_version_shims(pd)
    dates = pd.DatetimeIndex(
        pd.date_range(SIGNAL_DATE_START, SIGNAL_DATE_END, freq=pd.offsets.MonthEnd())
    )
    store = Store()
    factors: dict[str, Any] = {}
    try:
        load_fixture_into(store, FixtureSpec())
        prices = store.prices()
        membership = None
        if hasattr(run_module, "historical_universe_membership"):
            membership = run_module.historical_universe_membership(store, dates)

        for factor_id, factor in sorted(load_all().items()):
            raw = factor.compute(store, dates).copy()
            raw["ticker"] = raw["ticker"].astype(str)
            raw["signal_date"] = pd.to_datetime(raw["signal_date"])

            if membership is not None:
                eligible, universe_report = run_module.filter_to_historical_universe(
                    raw, membership, dates
                )
                universe = universe_report.to_dict()
            else:
                eligible = raw.copy()
                universe = {
                    "status": "UNWIRED",
                    "n_input": int(len(raw)),
                    "n_output": int(len(raw)),
                    "n_excluded_outside_universe": 0,
                }

            try:
                magnitude = run_module.check_plausible_magnitude(factor, eligible)
                magnitude["raised"] = False
            except run_module.ImplausibleMagnitudeError as exc:
                magnitude = {**exc.detail, "raised": True, "message": str(exc)}

            cleaned, cleaning = prepare_module.prepare_cross_sections(eligible)
            panel, native_label_report = _call_panel_builder(
                prepare_module, cleaned, prices
            )
            protocol = run_protocol(factor_id, panel)

            cleaned_keys = cleaned[["ticker", "signal_date"]].drop_duplicates()
            panel_keys = panel[["ticker", "signal_date"]].drop_duplicates()
            unmatched = cleaned_keys.merge(
                panel_keys,
                on=["ticker", "signal_date"],
                how="left",
                indicator=True,
            )
            generic_label = {
                "n_input": int(len(cleaned)),
                "n_output": int(len(panel)),
                "n_dropped_without_label": int((unmatched["_merge"] == "left_only").sum()),
                "native_outcomes": (
                    native_label_report.get("outcome_counts")
                    if native_label_report is not None
                    else None
                ),
            }

            panel_values = [
                column
                for column in [
                    "prediction",
                    "label",
                    "formation_session",
                    "entry_date",
                    "exit_date",
                ]
                if column in panel.columns
            ]
            factors[factor_id] = {
                "raw": _stage(raw, ["value"]),
                "eligible": _stage(eligible, ["value"]),
                "cleaned": _stage(cleaned, ["value"]),
                "panel": _stage(panel, panel_values),
                "performance": {
                    "ic_mean": _finite(protocol.summary["ic_mean"]),
                    "ls_sharpe": _finite(protocol.summary["ls_sharpe"]),
                },
                "universe": universe,
                "cleaning": cleaning.to_dict(),
                "label_attrition": generic_label,
                "magnitude": {
                    key: _normalise(value)
                    for key, value in magnitude.items()
                    if key not in {"worst", "message"}
                },
                # Retain the cleaned values only for parent/child z-score deltas.
                "_cleaned_values": [
                    {
                        "ticker": str(row.ticker),
                        "signal_date": pd.Timestamp(row.signal_date).isoformat(),
                        "value": _finite(row.value),
                    }
                    for row in cleaned.itertuples(index=False)
                ],
            }
    finally:
        store.close()
        pd.date_range = original_date_range
        pd.DataFrame.stack = original_stack

    return {
        "status": STATUS,
        "assertion_status": ASSERTION_STATUS,
        "purpose": (
            "Attribute numerical changes to individual commits. This is a one-time "
            "diagnostic ledger, not a stored-output assertion."
        ),
        "commit": commit,
        "source_root": str(source_root),
        "environment": {
            "python": platform.python_version(),
            "pandas": pd.__version__,
            "numpy": np.__version__,
            "scipy": scipy.__version__,
            "statsmodels": statsmodels.__version__,
        },
        "compatibility_observation": compatibility,
        "fixture": {
            "signal_date_start": SIGNAL_DATE_START,
            "signal_date_end": SIGNAL_DATE_END,
            "n_signal_dates": int(len(dates)),
        },
        "factors": factors,
    }


def _flatten(value: Any, prefix: str = "") -> dict[str, Any]:
    out: dict[str, Any] = {}
    if isinstance(value, dict):
        for key in sorted(value):
            if key.startswith("_") or key in {"universe", "cleaning"}:
                continue
            child = f"{prefix}.{key}" if prefix else key
            out.update(_flatten(value[key], child))
    else:
        out[prefix] = value
    return out


def _zscore_delta(parent: dict[str, Any], child: dict[str, Any]) -> dict[str, Any]:
    def keyed(rows):
        return {
            (row["ticker"], row["signal_date"]): row["value"]
            for row in rows
            if row["value"] is not None
        }

    left = keyed(parent.get("_cleaned_values", []))
    right = keyed(child.get("_cleaned_values", []))
    shared = left.keys() & right.keys()
    deltas = [abs(left[key] - right[key]) for key in shared]
    return {
        "n_shared": len(shared),
        "n_added": len(right.keys() - left.keys()),
        "n_removed": len(left.keys() - right.keys()),
        "n_changed": sum(delta > 1e-12 for delta in deltas),
        "max_abs_delta": max(deltas) if deltas else None,
    }


def _allowed(commit: str, factor_id: str, path: str) -> bool:
    expectation = COMMIT_EXPECTATIONS.get(commit, {})
    factors = expectation.get("factors")
    if factors is not None and factor_id not in factors:
        return False
    return any(path.startswith(prefix) for prefix in expectation.get("allowed_prefixes", []))


def compare_snapshots(environment: str, paths: list[Path]) -> dict[str, Any]:
    snapshots = [json.loads(path.read_text(encoding="utf-8")) for path in paths]
    compatibility = snapshots[-1].get(
        "compatibility_observation",
        {
            "unsupported_frequency_aliases": [],
            "stack_supports_future_stack": True,
            "unmodified_checkout_runnable": True,
            "diagnostic_shim": None,
            "blockers": [],
            "classification": "NONE",
        },
    )
    rows: list[dict[str, Any]] = []
    for parent, child in zip(snapshots[:-1], snapshots[1:], strict=True):
        commit = child["commit"][:7]
        expectation = COMMIT_EXPECTATIONS.get(commit, {"label": "unclassified"})
        for factor_id in sorted(child["factors"]):
            before = parent["factors"][factor_id]
            after = child["factors"][factor_id]
            left = _flatten(before)
            right = _flatten(after)
            changed = sorted(
                path for path in left.keys() | right.keys() if left.get(path) != right.get(path)
            )
            unexpected = [
                path for path in changed if not _allowed(commit, factor_id, path)
            ]
            raw_changed = before["raw"]["value_hash"] != after["raw"]["value_hash"]
            eligible_changed = (
                before["eligible"]["value_hash"] != after["eligible"]["value_hash"]
            )
            rows.append(
                {
                    "commit": commit,
                    "change": expectation["label"],
                    "factor_id": factor_id,
                    "changed_fields": changed,
                    "unexpected_changed_fields": unexpected,
                    "zscore_delta": _zscore_delta(before, after),
                    "raw_effect_masked_by_universe": raw_changed and not eligible_changed,
                    "freshness_effect_masked_by_universe": (
                        commit == "e66ab5c" and raw_changed and not eligible_changed
                    ),
                    "before": {
                        "raw_n": before["raw"]["n_rows"],
                        "eligible_n": before["eligible"]["n_rows"],
                        "cleaned_n": before["cleaned"]["n_rows"],
                        "panel_n": before["panel"]["n_rows"],
                        **before["performance"],
                        "label_dropped": before["label_attrition"][
                            "n_dropped_without_label"
                        ],
                    },
                    "after": {
                        "raw_n": after["raw"]["n_rows"],
                        "eligible_n": after["eligible"]["n_rows"],
                        "cleaned_n": after["cleaned"]["n_rows"],
                        "panel_n": after["panel"]["n_rows"],
                        **after["performance"],
                        "label_dropped": after["label_attrition"][
                            "n_dropped_without_label"
                        ],
                    },
                }
            )

    return {
        "status": STATUS,
        "assertion_status": ASSERTION_STATUS,
        "environment_name": environment,
        "environment": snapshots[-1]["environment"],
        "compatibility_observation": compatibility,
        "commits": [snapshot["commit"] for snapshot in snapshots],
        "unexpected_change_count": sum(
            bool(row["unexpected_changed_fields"]) for row in rows
        ),
        "rows": rows,
    }


def render_markdown(ledger: dict[str, Any]) -> str:
    lines = [
        "# Commit attribution ledger",
        "",
        f"- Status: `{STATUS}`",
        f"- Assertion status: `{ASSERTION_STATUS}`",
        f"- Environment: `{ledger['environment_name']}` "
        f"(Python {ledger['environment']['python']}, pandas {ledger['environment']['pandas']})",
        f"- Factor/commit rows with unexpected changes: "
        f"`{ledger['unexpected_change_count']}`",
        f"- Unmodified checkout runnable in this environment: "
        f"`{ledger['compatibility_observation']['unmodified_checkout_runnable']}`",
        "",
        "This ledger is a one-time diagnostic artefact. Its numbers are not test expectations.",
        "",
        "| Commit | Factor | Raw | Eligible | Cleaned | Panel | IC | LS Sharpe | "
        "Max Δz | Raw effect masked | Unexpected |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|:---:|---|",
    ]
    for row in ledger["rows"]:
        before = row["before"]
        after = row["after"]

        def delta(name: str, before=before, after=after) -> str:
            left, right = before[name], after[name]
            if left is None or right is None:
                return "—" if left == right else f"{left} → {right}"
            change = right - left
            return "0" if abs(change) <= 1e-15 else f"{change:+.6g}"

        unexpected = ", ".join(row["unexpected_changed_fields"]) or "—"
        maximum = row["zscore_delta"]["max_abs_delta"]
        max_text = "—" if maximum is None else f"{maximum:.6g}"
        lines.append(
            f"| `{row['commit']}` | `{row['factor_id']}` | {delta('raw_n')} | "
            f"{delta('eligible_n')} | {delta('cleaned_n')} | {delta('panel_n')} | "
            f"{delta('ic_mean')} | {delta('ls_sharpe')} | {max_text} | "
            f"{'yes' if row['raw_effect_masked_by_universe'] else 'no'} | "
            f"{unexpected} |"
        )

    lines.extend(["", "## Expected scope by commit", ""])
    for commit, expectation in COMMIT_EXPECTATIONS.items():
        lines.append(f"- `{commit}` — {expectation['label']}")
        if expectation.get("environment_note"):
            lines.append(f"  - {expectation['environment_note']}")
    observation = ledger["compatibility_observation"]
    if not observation["unmodified_checkout_runnable"]:
        lines.extend(
            [
                "",
                "## Compatibility blocker encountered",
                "",
                "The unmodified checkout failed before the attribution run could complete. "
                f"Blockers: `{', '.join(observation['blockers'])}`. "
                "The diagnostic applied the recorded compatibility shim so that independent "
                "commit effects could still be measured. This shim does not make the declared "
                "minimum-version check pass.",
            ]
        )
    return "\n".join(lines) + "\n"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)

    snapshot = subparsers.add_parser("snapshot")
    snapshot.add_argument("--source-root", type=Path, required=True)
    snapshot.add_argument("--commit", required=True)
    snapshot.add_argument("--output", type=Path, required=True)

    compare = subparsers.add_parser("compare")
    compare.add_argument("--environment", required=True)
    compare.add_argument("--snapshots", nargs="+", type=Path, required=True)
    compare.add_argument("--json-output", type=Path, required=True)
    compare.add_argument("--markdown-output", type=Path, required=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.command == "snapshot":
        payload = create_snapshot(args.source_root, args.commit)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(payload, indent=2, sort_keys=True, allow_nan=False) + "\n",
            encoding="utf-8",
        )
        return

    ledger = compare_snapshots(args.environment, args.snapshots)
    args.json_output.parent.mkdir(parents=True, exist_ok=True)
    args.json_output.write_text(
        json.dumps(ledger, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    args.markdown_output.write_text(render_markdown(ledger), encoding="utf-8")


if __name__ == "__main__":
    main()
