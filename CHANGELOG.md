# Changelog

## 0.2.0

**Window correction in 0.2.0.** v0.1.0 computed the three price factors by
shifting rows of the requested signal dates. They now read calendar month-end
anchors:

- `mom_12_1` now uses lags 2–12, eleven monthly returns. On consecutive
  month-end requests, v0.1.0 used lags 2–13.
- `mom_6_1` and `rev_1m` keep the window lengths they had on consecutive
  month-end requests. On sparse requests, v0.1.0's actual calendar spans
  differed; those spans are not preserved.
- None of the three depends any longer on which dates are requested, so early
  keys with valid anchors may now return.

The selected-200 archives in `examples/outputs/` used the pre-correction
windows and were not recomputed. The effect on real-store values and coverage
has not been measured. The two known xfails and the research qualification
status are unchanged. See the 2026-09-29 correction in
[DEFINITION_AUDIT.md](docs/DEFINITION_AUDIT.md).
