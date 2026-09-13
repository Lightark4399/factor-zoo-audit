"""Opt-in, single-thread diagnostic profiler; never imported by the runner."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter, process_time

TARGETS = {
    "fza.pipeline.run": {
        "compute_factor", "compare_vintages", "historical_universe_membership",
        "filter_to_historical_universe", "check_plausible_magnitude",
    },
    "fza.pipeline.prepare": {"prepare_cross_sections", "build_panel_with_report"},
    "fza.pipeline.protocol": {"run_protocol"},
    "fza.pipeline.vintage": {"diagnostic_layers", "evaluate"},
    "fza.factors.library": {"_fundamental_history", "_ttm_fundamental_panel"},
    "fza.store": {"prices", "measure_naive_trap", "assert_read_path_respected"},
}


class StageProbe:
    """Flush stage events; refuse to replace another profiler or existing file."""

    def __init__(self, path, targets=None):
        self.path = Path(path)
        self.targets = TARGETS if targets is None else targets
        self.stack = []
        self.sequence = 0
        self.counts = Counter()

    def emit(self, **record):
        self.stream.write(json.dumps(record, sort_keys=True) + "\n")
        self.stream.flush()

    def __enter__(self):
        if sys.getprofile() is not None:
            raise RuntimeError("An existing profiler must not be replaced")
        self.stream = self.path.open("x", encoding="utf-8", newline="\n")
        self.emit(event="probe_start", utc=datetime.now(timezone.utc).isoformat(),
                  scope="current thread; inclusive times; profiling overhead included")
        sys.setprofile(self.observe)
        return self

    def observe(self, frame, event, arg):
        if event not in {"call", "return"}:
            return
        module = frame.f_globals.get("__name__", "")
        name = frame.f_code.co_name
        if event == "call" and module == "fza.factors.library" and name == "_ttm_value":
            self.counts["ttm_value_calls"] += 1
        if name not in self.targets.get(module, ()):
            return
        if event == "call":
            self.sequence += 1
            context = {}
            for key in ("vintage", "factor_id", "name"):
                value = frame.f_locals.get(key)
                if isinstance(value, str):
                    context[key] = value
            factor = frame.f_locals.get("factor")
            if factor is not None and hasattr(factor, "factor_id"):
                context["factor_id"] = factor.factor_id
            parent = self.stack[-1][1] if self.stack else None
            self.emit(event="enter", id=self.sequence, parent=parent,
                      stage=f"{module}.{name}", context=context)
            self.stack.append((frame, self.sequence, perf_counter(), process_time()))
        elif self.stack and self.stack[-1][0] is frame:
            _, identifier, wall, cpu = self.stack.pop()
            self.emit(event="leave", id=identifier,
                      wall_seconds=perf_counter() - wall,
                      cpu_seconds=process_time() - cpu,
                      success="NOT_INFERRED_FROM_PROFILE_RETURN")

    def __exit__(self, kind, value, traceback):
        sys.setprofile(None)
        try:
            self.emit(event="probe_end", completed=kind is None,
                      exception_type=None if kind is None else kind.__name__,
                      open_spans=len(self.stack), counts=dict(self.counts))
        finally:
            self.stream.close()
            self.stack.clear()


def main(argv=None):
    from dataclasses import asdict

    from .demo import signal_dates_for
    from .factors.registry import load_all
    from .fixtures import FixtureSpec, build_fixture
    from .pipeline.run import compare_vintages
    from .provenance import implementation_manifest, research_environment
    from .reporting import json_safe
    from .store import Store

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--outdir", type=Path, required=True)
    args = parser.parse_args(argv)
    args.outdir.mkdir(parents=True, exist_ok=False)
    spec = FixtureSpec(n_securities=20, seed=11)
    factor = load_all()["ep_ratio"]
    store = Store()
    try:
        inputs = build_fixture(spec)
        store.load_securities(inputs["securities"])
        store.load_prices(inputs["prices"])
        store.load_fundamentals(inputs["fundamentals"])
        dates = signal_dates_for(store)[:12]
        input_hashes = {
            key: hashlib.sha256(frame.to_json(date_format="iso").encode()).hexdigest()
            for key, frame in inputs.items() if key != "spec"
        }

        def run():
            start, cpu = perf_counter(), process_time()
            result = json_safe(compare_vintages(factor, store, dates).to_dict())
            return result, {"wall_seconds": perf_counter() - start,
                            "cpu_seconds": process_time() - cpu}

        run()  # unmeasured warm-up, identical input
        baseline, unprofiled = run()
        with StageProbe(args.outdir / "stages.jsonl"):
            observed, profiled = run()
        equal = baseline == observed
        record = dict(status="DIAGNOSTIC_ONLY", fixture=asdict(spec),
                      dates=[str(d) for d in dates], input_hashes=input_hashes,
                      implementation=implementation_manifest(), environment=research_environment(),
                      result_equal=equal, equality_scope="serialized VintageComparison only",
                      unprofiled=unprofiled, profiled=profiled,
                      baseline=baseline, observed=observed,
                      historical_slowdown_explained=False)
        (args.outdir / "probe.json").write_text(
            json.dumps(record, indent=2, allow_nan=False) + "\n", encoding="utf-8", newline="\n"
        )
        print(json.dumps({"result_equal": equal, "unprofiled": unprofiled,
                          "profiled": profiled}))
        return 0 if equal else 1
    finally:
        store.close()


if __name__ == "__main__":
    raise SystemExit(main())
