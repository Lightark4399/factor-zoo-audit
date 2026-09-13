# Stage measurement plan — 2026-09-13

Frozen before the stage probe is run. DIAGNOSTIC_ONLY / NOT_AN_ASSERTION.

The observed wall-time ratio is 9.93, not a controlled speed comparison.
Historical anchors are 0bd03bf and de1e836. Three unchanged TTM function ASTs
do not establish equal inputs, call counts, environments or runtime.

## First bounded experiment

Use FixtureSpec(n_securities=20, seed=11), keeping its full 2018–2021 history.
Evaluate ep_ratio on the first 12 dates returned by signal_dates_for. This is
a diagnostic grid, not an equivalent selected-200 research run. Do not change
the data, dates or formula after seeing the timing. Run an unmeasured warm-up,
then an unprofiled pass and a profiled pass, sequentially in each environment.
Record exact serialized result equality, inputs, code manifest and environment.
This tests instrumentation and supplies a bounded stage observation; it does
not explain the historical ratio or establish cross-version performance.

The Python profiling hook records actual stage entry/exit, including nested
parent IDs, wall time and process CPU time. Times are inclusive and cannot be
summed across nested stages. Hook and flushed JSONL I/O overhead are present;
profiled and unprofiled times are not interchangeable. A return event does not
prove successful completion (exception unwinding also produces return events).
Only the outer run completion record certifies that the probe finished.

Hypothesis, not required result: additional vintage diagnostics may spend time
in cleaning, labels and scoring. Common-observation uses cleaned panels;
common-support re-cleans captured eligible values, without invoking the factor
formula again. Neither fact predicts a tenfold slowdown or similar TTM times.
Count observed TTM calls rather than treating three layers as three formulas.

## Subsequent experiment (not yet executed)

Compare historical anchors on identical, hashed real-data subsets, retaining
formation history separately from evaluation dates. Record actual inputs and
call counts, stage coverage, CPU/wall times, warm-up and repeated unprofiled
measurements. Added stages have no old counterpart; compare common stages
separately from added work. Explain discrepancies before choosing an optimization.
Do not optimize namedtuple construction or add caching on the microprofile alone.

No original archive is rewritten. Existing regression evidence remains scoped
to its tested source state. No full selected-200 rerun is authorized by this
diagnostic experiment. Phase JSONL is a progress record, not resumable state.
