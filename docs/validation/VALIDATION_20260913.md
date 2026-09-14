# Stage probe validation — 2026-09-13

## Scope

The prospective plan is PERFORMANCE_STAGE_PLAN.md. No factor formula, runner,
vintage comparison or original report archive was edited in this batch.
The new fza.stage_probe module is an explicitly invoked diagnostic tool, not
production demo instrumentation. It neither optimizes TTM nor resumes a report.

Prior 281-test dual-environment regression remains evidence for the previously
tested source state. This addition was checked separately: three tests pass
in each environment, zero failures/errors/skips, exit 0. XML artifacts are
`.diagnostic-envs/stage-tests-locked.xml` and `stage-tests-minimum.xml`.
Ruff passes on the two new Python files. No new whole-suite pass is claimed.

## Fixed-input probe

20 synthetic securities, full 2018–2021 fixture history, seed 11, ep_ratio,
first 12 evaluation dates after the standard history exclusion. The manifest
records input-frame hashes, dates, fixture parameters, source and environment.
One warm-up, one unprofiled pass, one profiled pass, sequentially per environment.
The equality check covers the full serialized VintageComparison, not raw panels.
This is a diagnostic comparison, not an assertion against a historical oracle.

Locked environment: exit 0; serialized results exactly equal. Unprofiled wall
12.6036398 s / CPU 12.8125 s; profiled wall 28.1435539 s / CPU 27.828125 s.
Process CPU may exceed wall time because it includes work by process threads.
Profiling overhead is substantial; do not infer production stage percentages.

The profiled trace records two TTM-panel calls (11.8504064 s and 12.2405614 s,
inclusive), 480 TTM-value calls, and diagnostic_layers at 2.2348959 s inclusive.
Nested stage durations must not be summed. The trace has balanced stage exits
and an explicit completed=true outer record. It does not explain the real-data
9.93x ratio, establish an environment speed ranking, or justify an optimization.

Locked artifacts: `.diagnostic-envs/stage-probe-locked-0913-v2/`.
Minimum environment: exit 0; serialized results exactly equal. Unprofiled wall
11.2465510 s / CPU 11.46875 s; profiled wall 46.0697363 s / CPU 46.078125 s.
Artifacts: `.diagnostic-envs/stage-probe-minimum-0913/`. These single sequential
observations do not establish a stable performance ratio between environments.

Artifact SHA-256 (local diagnostic artifacts, not original report files):

| Environment | File | SHA-256 |
|---|---|---|
| locked | probe.json | 6905f54e05fc20dd258158d187f61323449776f60c7aa4ffd52083afb3e83a8d |
| locked | stages.jsonl | 6cec27440054754312627a14ffeaf485cd67a2f5eeb09fef3c4fc177f1c929f7 |
| minimum | probe.json | 5dcb4020b535e0dc5fa680ecde11cf9e8fdb43f30ec0f4e67f21b90d9363fc54 |
| minimum | stages.jsonl | dd64be4e54f7cc938f607d0cbd091a60256959d5e04bdf8f5090570ab6fcffac |

The initial locked probe exited 1 before factor calculation: the first draft
mistook load_fixture_into's counts dictionary for the underlying frames.
It was corrected to build, hash and load the actual fixture frames. The failed
directory is retained; the successful probe used a new directory.

## Remaining work

Historical-version fixed-real-input timing is still pending. Production phase
telemetry (including warm-up/setup failures) is not supplied by this bounded
probe. Do not replace the 41-hour archive or launch another full-grid run merely
to obtain timings. Choose an optimization only after the controlled comparison.
