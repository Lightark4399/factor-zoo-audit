# Historical validation records

These are dated snapshots, not a live release dashboard. A pass, interruption,
pending check or remaining task describes the source state and scope in that
record; it does not automatically describe today's checkout. Dates alone do not
identify tested code. Commit anchors below retain the roles stated in the records
(baseline, computation or correction), not an invented exact test target.

## Reading guide

| Record | Source anchor / scope | Historical status and limits |
|---|---|---|
| [2026-09-05](VALIDATION_20260905.md) | Review baseline `0a2dde0`; implementation `052d696`, `82b2e55` | Local validation and test-count reconciliation; not research qualification |
| [2026-09-06](VALIDATION_20260906.md) | Baseline `2bf5aa0`; AS-03 fix `36071e9` | Interrupted; replaced by the September 7 run, not a completed full run |
| [2026-09-07](VALIDATION_20260907.md) | Computation `0bd03bf` | Computation snapshot verified; later presentation checks have their own scope |
| [2026-09-08](VALIDATION_20260908.md) | Base `0199040` | Vintage scope checkpoint, not completion of three-layer diagnostics |
| [2026-09-09](VALIDATION_20260909.md) | Base `f3bce92` | Three-layer comparison checkpoint |
| [Rules, 2026-09-09](VALIDATION_RULES_20260909.md) | Documentation correction `027b65a`; parent `d9c203b` | Rule and documentation checks; does not replace the selected-200 archive |
| [2026-09-12](VALIDATION_20260912.md) | Compares `0bd03bf` and `de1e836` archives | Scoped artifact review and presentation migration; no raw-panel identity claim |
| [Stage probe, 2026-09-13](VALIDATION_20260913.md) | Bounded synthetic probe; exact tested commit not specified in this record | Focused checks; does not extend the earlier full-suite result to new code |
| [Real performance, 2026-09-13](VALIDATION_REAL_PERFORMANCE_20260913.md) | Workers compare `0bd03bf` and `de1e836` | Fixed-input observations and power-state confounding; not a production speed ratio |
| [README, 2026-09-13](VALIDATION_README_20260913.md) | Projects the `de1e836` archive; exact test commit not specified in this record | Documentation projection checks, not scientific validation of calculations |

## Navigation and provenance

Start with the [project README](../../README.md) and [delivery guide](../../B_DELIVERY.md)
for the deliverable's evidence limits. Use the [output archive index](../../examples/outputs/README.md)
for saved reports. CI results must be matched to their commit, not inferred from
one of these older records.

These files moved from the repository root on 2026-09-14. Historical prose and
results were retained; relative navigation links were adjusted. Bare code paths
in the records (for example `src/`, `scripts/` and `.diagnostic-envs/`) remain
repository-root-relative unless explicitly stated otherwise. Ignored local
artifacts named in a record are not supplied merely because their hashes are
listed. Original report JSON, text and manifests were not rewritten.
