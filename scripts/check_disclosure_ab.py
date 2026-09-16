"""One-off bounded comparison of real demo executions, not historical test oracles.

Both arms use the same built-in fixture and sixteen selected dates. This is not a
selected-200 rerun, full-grid validation or proof of raw-panel identity.
"""

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--old-src", type=Path, required=True)
    parser.add_argument("--new-src", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=False)
    expected = {
        "scope": "ten factors, built-in fixture, max-dates=16, same interpreter",
        "allowed_changed_top_level": ["generated_at_utc", "runtime", "implementation"],
        "allowed_added_summary_fields": ["disclosure_summary", "legacy_restatement_scope"],
        "limitations": "No raw panel comparison; sparse scoring can be unavailable.",
    }
    (args.out / "expectations.json").write_text(json.dumps(expected, indent=2))
    bundles = {}
    for arm, source in (("old", args.old_src), ("new", args.new_src)):
        env = os.environ.copy()
        env["PYTHONPATH"] = str(source.resolve())
        command = [sys.executable, "-m", "fza.demo", "--db",
                   str((args.out / "absent-fixture-input.duckdb").resolve()),
                   "--max-dates", "16", "--outdir", str((args.out / arm).resolve())]
        print(f"Starting {arm} source={source.resolve()}", flush=True)
        with (args.out / f"{arm}.log").open("w", encoding="utf-8") as log:
            result = subprocess.run(command, env=env, stdout=log, stderr=log, check=False)
        if result.returncode:
            raise RuntimeError(f"{arm} exited {result.returncode}; retain {arm}.log")
        bundles[arm] = json.loads((args.out / arm / "demo_run.json").read_text())
    old, new = bundles["old"], bundles["new"]
    assert set(old) == set(new), "Unexpected top-level schema change"
    stable = sorted(set(old) - set(expected["allowed_changed_top_level"]) - {"data_summary"})
    mismatches = [key for key in stable if old[key] != new[key]]
    assert not mismatches, f"Unexpected result differences: {mismatches}"
    assert set(new["data_summary"]) - set(old["data_summary"]) == set(
        expected["allowed_added_summary_fields"]
    )
    for key, value in old["data_summary"].items():
        assert new["data_summary"][key] == value, f"Legacy summary changed: {key}"
    assert len(new["factors"]) == 10
    states = {key: value["computation_status"] for key, value in new["factors"].items()}
    assert all(state == "COMPLETED" for state in states.values()), states
    report = {"status": "MATCHED_WITH_DECLARED_REPORTING_ADDITIONS",
              "equal_top_level_fields": stable, "factor_states": states,
              "new_disclosure_summary": new["data_summary"]["disclosure_summary"],
              "limitations": expected["limitations"]}
    (args.out / "comparison.json").write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2), flush=True)


if __name__ == "__main__":
    main()
