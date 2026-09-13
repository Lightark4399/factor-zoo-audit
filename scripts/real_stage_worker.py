"""Run one historical source against a frozen subset; no production code edits."""
from __future__ import annotations

import argparse
import hashlib
import importlib
import json
import sys
from contextlib import ExitStack
from functools import wraps
from pathlib import Path
from time import perf_counter, process_time
from unittest.mock import patch


class Timings:
    def __init__(self, stream):
        self.stream = stream
        self.stack = []
        self.sequence = 0
        self.ttm_calls = 0
        self.ttm_input_rows = []

    def emit(self, **record):
        self.stream.write(json.dumps(record, sort_keys=True) + "\n")
        self.stream.flush()

    def wrap(self, function, label):
        @wraps(function)
        def measured(*args, **kwargs):
            if label.endswith("._ttm_value"):
                self.ttm_calls += 1
                self.ttm_input_rows.append(len(args[0]))
                return function(*args, **kwargs)
            self.sequence += 1
            identifier = self.sequence
            self.emit(event="enter", id=identifier,
                      parent=self.stack[-1] if self.stack else None, stage=label,
                      vintage=kwargs.get("vintage"))
            self.stack.append(identifier)
            wall, cpu = perf_counter(), process_time()
            success = False
            try:
                result = function(*args, **kwargs)
                success = True
                return result
            finally:
                elapsed, used = perf_counter() - wall, process_time() - cpu
                self.stack.pop()
                self.emit(event="leave", id=identifier, completed=success,
                          wall_seconds=elapsed, cpu_seconds=used)
        return measured

    def install(self, stack):
        targets = {
            "fza.pipeline.run": ["compute_factor", "historical_universe_membership",
                                 "prepare_cross_sections", "build_panel_with_report",
                                 "run_protocol", "diagnostic_layers"],
            "fza.pipeline.vintage": ["prepare_cross_sections", "run_protocol"],
            "fza.factors.library": ["_ttm_fundamental_panel", "_fundamental_history",
                                    "_ttm_value"],
        }
        for module_name, names in targets.items():
            try:
                module = importlib.import_module(module_name)
            except ModuleNotFoundError as exc:
                if exc.name != module_name:
                    raise
                continue  # old anchor has no vintage module
            for name in names:
                if hasattr(module, name):
                    function = getattr(module, name)
                    stack.enter_context(patch.object(
                        module, name, self.wrap(function, f"{module_name}.{name}")))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--db", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    sys.path.insert(0, str(args.source.resolve() / "src"))
    import pandas as pd

    from fza.factors.registry import load_all
    from fza.pipeline import run
    from fza.provenance import implementation_manifest, research_environment
    from fza.reporting import json_safe
    from fza.store import Store

    args.output.mkdir(parents=True, exist_ok=False)
    dates = pd.date_range("2018-01-01", "2018-12-31", freq=pd.offsets.MonthEnd())
    factor = load_all()["ep_ratio"]
    store = Store(str(args.db.resolve()), read_only=True)
    with (args.output / "stages.jsonl").open("x", encoding="utf-8", newline="\n") as stream:
        timing = Timings(stream)

        def execute(phase):
            timing.emit(event="phase_start", phase=phase)
            wall, cpu = perf_counter(), process_time()
            comparison = run.compare_vintages(factor, store, dates)
            elapsed = {"wall_seconds": perf_counter() - wall,
                       "cpu_seconds": process_time() - cpu}
            result = json_safe(comparison.to_dict())
            timing.emit(event="phase_end", phase=phase, **elapsed)
            return result, elapsed

        try:
            execute("warmup")
            baseline, plain = execute("plain")
            with ExitStack() as stack:
                timing.install(stack)
                observed, instrumented = execute("instrumented")
            equal = baseline == observed
            record = dict(
                status="DIAGNOSTIC_ONLY", source=str(args.source.resolve()),
                implementation=implementation_manifest(), environment=research_environment(),
                harness_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                input_sha256=hashlib.sha256(args.db.read_bytes()).hexdigest(),
                dates=[str(x.date()) for x in dates], plain=plain, instrumented=instrumented,
                result_equal=equal, baseline=baseline, observed=observed,
                ttm_calls=timing.ttm_calls, ttm_input_rows=timing.ttm_input_rows,
            )
            with (args.output / "result.json").open("x", encoding="utf-8", newline="\n") as out:
                json.dump(record, out, indent=2, allow_nan=False)
                out.write("\n")
            timing.emit(event="worker_end", completed=True, result_equal=equal)
            print(json.dumps({"output": str(args.output), "result_equal": equal,
                              "plain": plain, "instrumented": instrumented}), flush=True)
            return 0 if equal else 1
        except BaseException as exc:
            timing.emit(event="worker_end", completed=False,
                        exception_type=type(exc).__name__, message=str(exc))
            raise
        finally:
            store.close()


if __name__ == "__main__":
    raise SystemExit(main())
