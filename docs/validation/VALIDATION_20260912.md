# Selected-200 artifact review and presentation migration

DIAGNOSTIC_ONLY / NOT_AN_ASSERTION. No research gate is promoted.

## Scope and immutable inputs

The de1e836 computation finished successfully; no factor computation was restarted
for this presentation repair. The old 0bd03bf and new de1e836 three-file archives
remain unmodified. The frozen expectations are not retrospectively rewritten.

| Artifact | SHA-256 |
|---|---|
| 20260907 demo_run.json | e7c8744d7f8998eb4de1f719823e568cd37f4654a21a6ebbbb4ad37506459a42 |
| 20260909 demo_run.json | 4bcefb562c17971de93604dd952ba1e61781d29c1dbf57722d26f29e404c4f34 |
| 20260907 demo_report.txt | e0965bf644d8a4e15cea0ab00cf5ce2642a2313cc8f2d91ae07005c2934ce329 |
| 20260909 demo_report.txt | 7cf55ae6643e96bd97c1fadd3d03c6d1a47749b43b828421d1b676e179964332 |
| Both demo_evidence.json files | 93124a719f2f1757c09e9254f558c716a35c17cae8db7325de6eeea8797483ee |

All six original files use CRLF. Contrary to the prospective prediction, only
two of three files changed bytes: evidence is byte-identical. This is a mistaken
prediction, not an unexplained computation change. New presentation files use LF.

## Checked results, not a blanket numerical pass

The earlier exact JSON comparison covers all ten original PIT protocol objects,
computation statuses, universe/cleaning/label-attrition fields, ordered 185-date
configuration, environment, roster and denominator/gate objects. Those checked
fields agree with 20260907. Raw panel equality remains NOT_CHECKED: the archives
do not preserve all intermediate values needed to establish it.

Additional artifact checks on 20260912 found unchanged naive-trap date/exposure/
row/rate counts and unchanged legacy magnitude objects (excluding newly added
rule/scope metadata). Four economic guards retain out-of-range counts of 76
(bm_ratio), 73 (ep_ratio), 68 (roe), 10 (asset_growth): WITHIN_TOLERANCE does not
mean zero violations. Turnover has zero sign violations; log_mktcap remains
DECLARED_UNBOUNDED; four price-only factors have no declared rules.

For all twelve applicable factor-by-layer results, checked gap arithmetic,
identical IC scoring dates, MATCHED label/holding-period outcomes, equal recorded
scoring key hashes in common layers, and equal recorded raw input key hashes plus
MATCHED source outcomes for common-support. These are consistency checks on
recorded diagnostics, not a recomputation of original panels.

| Factor | Original-process gap | Common-observation gap | Common-support gap |
|---|---:|---:|---:|
| bm_ratio | -0.0009245654 | -0.0003506227 | -0.0003624138 |
| ep_ratio | +0.0023486717 | +0.0016450570 | +0.0016291416 |
| roe | +0.0035967887 | +0.0026502712 | +0.0026533902 |
| asset_growth | +0.0081533673 | -0.0018664150 | -0.0018788977 |

Rounded diagnostic display only. Original-process retains arm-specific
observations/cleaning on shared dates. Common-observation aligns scoring keys
but retains upstream cleaning-sample effects. Common-support fixes cleaning
input keys; that selected common set is not the original cohort. Differences
between layers are sensitivities, not a decomposition into value/sample effects.
No factor was selected for a README performance headline.

### Interpretation correction after AI-assisted review

Common-sample diagnostics reverse the sign of asset_growth's IC gap. Therefore
we do not adopt the proposed interpretation of the original-process gap as a
restatement advantage. This does not attribute the gap to a pure sample effect.
The original-process FAIL at the directional 0.005 threshold remains unchanged;
the additional layers are DIAGNOSTIC_ONLY, not replacement PASS verdicts.

Absolute common-observation versus common-support IC-gap differences are
0.000011791144409379131 (bm_ratio), 0.000015915358796402337 (ep_ratio),
0.000003118921481754487 (roe), and 0.00001248266218384364 (asset_growth).
The largest is about 0.00001592, not 0.00012. These describe sensitivity of
aggregate IC gaps for this sample and these four factors, not effects on every
security or other metric. All four have neutralised=false; this run provides
no comparison of industry-neutralisation effects.

This interpretation was challenged through AI-assisted review and checks of
code and archived results, not formal external peer review. A sign reversal
does not establish a causal decomposition merely because a disclaimer is retained.

Six inapplicable comparisons retain null gaps and NOT_APPLICABLE. Their outcome
checks are not uniformly NOT_CHECKED: log_mktcap/turnover have MATCHED checks in
some layers, which does not make the substituted fundamental path applicable.
The separate evidence JSON equals the bundle's evidence object. The two unresolved
and four unimplemented research gates are unchanged.

README review retained historical-sample labels, updated the first-page report
link to an explicitly labelled presentation replay, and corrected the stale
status line that still described historical-data access as pending delivery work.

## Presentation and provenance

Seven original lines exceeded 84 columns (107, 94, 123, 108, 161, 97, 85).
The shared renderer wraps long text, preserves existing short table columns,
puts one excluded key per line and repeats the sensitivity disclaimer alongside
each comparison. Legacy display supplementation is documented in RENDERING.md.
The adapter requires full token equality with the original report before adding
local copies of the already-existing disclaimer. It does not read a database.

The presentation replay is not new research evidence and not a new numerical run.
Source-format provenance and research eligibility remain distinct.

## Runtime recovery

Previous runtime was recorded, but only in ignored local status metadata.

| Run | Start | End | Wall-clock duration |
|---|---|---|---|
| 20260907 | 2026-09-07 01:04:25.312917 UTC | 2026-09-07 05:16:19.490939 UTC | 4h 11m 54.178022s |
| 20260909 | 2026-09-09 18:10:27.4621480 +01:00 | 2026-09-11 11:51:12.2426191 +01:00 | 41h 40m 44.7804711s |

Old timestamps: .diagnostic-envs/b-selected-200-20260907.status.json. New timestamps:
REAL_RUN_START/REAL_RUN_END wrapper output captured in this task's tool transcript.
These are recovered observations, not fields originally present in demo_run.json.
The ratio is approximately 9.93, not 100. Different diagnostics/workloads and
wall-clock versus CPU time prevent attributing this ratio to one function.
The py-spy sample found _ttm_value in the PIT ep_ratio path; incomplete, short
sampling does not explain all elapsed time or prove a stall. Performance remains
unexplained; this record does not close operational-performance acceptance.

## Test migration and remaining acceptance

An initial focused run found the new renderer omitted the detailed failure status
from the vintage block (1 failed, 2 passed). Restored the status from the shared
failure record without weakening the existing assertion. Initial renderer tests
had 6 passes/2 setup errors from the default temporary-directory permissions;
rerunning with a repository-local temporary directory gave 8 passes in each
environment. Final integration results will be recorded separately below.

The first integration batch had 29 passes and 8 failures in each environment:
seven empty-store qualification paths hit a null percentage formatting error;
the populated thin-grid path exposed a null statistic formatting error. The
empty-table column schema also needed restoring when decoding an empty list.
These are renderer serialization-boundary defects, not changes to factor scores.
They were fixed without deleting or relaxing the existing qualification tests.
The repair batch passed all 18 renderer/real-store/qualification tests in each
environment (zero failures/errors/skips). Undefined statistics stay null in JSON;
the display adapter restores the former NaN spelling, never zero. An undefined
restatement rate is explicitly displayed as unavailable.

Passed scoped archive checks remain valid; presentation regression verification
is complete for the targeted batches below; performance remains unexplained. No unqualified numerical pass,
no raw-panel equality claim, and no market-wide anomaly survival claim follows.

### Final targeted regression

| Environment | Full demo module | Rendering / evidence / qualification | Documentation / reporting | Distinct total |
|---|---:|---:|---:|---:|
| Locked | 16 | 18 | 5 | 39 |
| Minimum | 16 | 18 | 5 | 39 |

All three disjoint batches per environment have zero failures, errors and skips;
test identities were deduplicated from XML. Full demo elapsed time was 409.263s
(locked), 538.332s (minimum). XMLs are in .diagnostic-envs with prefixes
render-demo-final-, render-transport-final-, render-contracts- and suffix 0912.
Additional repeated unit runs are not added to the distinct count.

The full demo includes a fresh synthetic computation, JSON-only replay with store
and factor entry points forbidden, and structured failure propagation. Separately,
the replay CLI reproduced the fresh schema-2 fixture report byte-for-byte without
legacy text. Ruff on changed Python files and git diff --check passed.

The final selected-200 presentation has 560 lines, maximum width 84, no CRLF,
matching output hash, one excluded key per line, unchanged short table columns,
and all original computation fields exactly equal after removing the explicit
presentation supplement. Source text token equality was verified before the
documented addition of local sensitivity notices. Reviewed the actual protocol,
construction filters, vintage layers, rules and qualification/gate sections.

281 tests are currently collected. The entire 281-test suite was NOT rerun in
this batch; these 39-per-environment results do not claim otherwise. Before a
whole-repository release, refresh full-suite validation. Performance profiling,
stage timing/checkpoints and optimization remain separate work. No commit/push
or backtest-audit bridge was performed as part of this repair.

### Follow-up full regression and static performance check

Full-suite runs were launched in both environments, using repository-local
temporary directories and full-post-render-{locked,minimum}-0912.xml outputs.
Both completed with exit code 0. Final XMLs each contain 281 distinct test
identities, 281 tests and zero failures, errors or skips:

| Environment | Tests | XML suite elapsed seconds | XML SHA-256 |
|---|---:|---:|---|
| Locked | 281 | 1086.540 | 434e8e9fe96d03a93739f0b14cd9f878e29ba506a1b9fb2b14f462303d3bfb99 |
| Minimum | 281 | 1213.618 | bf792763884add5554cb1dda7f0a5231cee1ccc0601dd34f7f7d851d408191f9 |

These full-suite results supersede the preceding targeted-only regression limit,
not the restrictions on research claims or historical raw-panel evidence. No
numerical source was changed while these tests were running.

An AST comparison between archive anchors 0bd03bf and de1e836 found identical
function definitions for _ttm_value, _ttm_fundamental_panel and _fundamental_history.
The library changes there concern rule declarations; the store change adds
deterministic ordering to naive-trap selection. New vintage diagnostics also
perform additional sample/processing/label checks. This narrows the investigation
but does not assign the 9.93 wall-clock ratio to any of these operations. A hot
unchanged function can still receive different inputs or run under different
conditions. No performance benchmark is run concurrently with full regression.

Common-support reuses captured eligible_values; its extra work is cleaning,
label building and scoring, not another invocation of the TTM factor formula.
Future timing must follow actual stages rather than count three layers as three
independent factor computations.

### Bounded microprofile after both regressions ended

A separate local diagnostic (.diagnostic-envs/ttm_microprofile_0912.py) used 64
explicit cumulative-quarter contexts over 2010-2025. The latest four quarters
must sum to 460; all measured calls returned exactly 460 in both environments.
After one warm-up call, three batches of 20 calls were timed without profiling;
a separate 20-call batch was profiled. Function-source SHA-256 in both:
4a50f7901c2651d1cdecf9598d82b795a79558ffc7905db910292aa2ddc63cee.

| Environment | Wall seconds for each 20-call batch | CPU seconds for each batch |
|---|---|---|
| Locked | 0.5611252 / 0.5510137 / 0.5353041 | 0.53125 / 0.53125 / 0.53125 |
| Minimum | 1.1517732 / 0.7897579 / 0.6529890 | 1.140625 / 0.765625 / 0.65625 |

The profile records 320 namedtuple constructions for 20 TTM calls in each
environment (16 start-date groups per call), plus pandas object/datetime handling.
This supplies a concrete candidate for later investigation, not an approved
optimization or a measured speedup. The first minimum invocation lacked an
installed fza import; the diagnostic was corrected to explicitly load this
workspace's src, then completed. No dependency installation or source algorithm
change was made.

The synthetic input distribution is not the real SEC distribution; store reads,
labels, scoring, OS sleep and historical CPU availability are absent. Batch
variation is visible and there are too few repetitions for a stable cross-version
performance conclusion. Profiled times are not compared with unprofiled times.
This experiment does not explain the 9.93 wall-clock ratio. Next: instrument
actual stages and compare fixed-input runs before selecting any optimization.
