# B: point-in-time audit with explicit evidence limits

This is an independently useful diagnostic deliverable, not a claim that the
original market-wide research question has been answered. No provider change,
terminal-return imputation or backtest-audit bridge is included.

## Five parts and their acceptance evidence

| Part | Delivered surface | What it does not establish |
|---|---|---|
| Reproducible run package | Runtime lock/hash, shipped code/rule hashes, selected roster/hash, explicit signal dates and protocol settings in `demo_run.json` | Provider downloads are not immutable; hashes identify bytes, not truth or a license to redistribute them |
| Synthetic controls | Existing filing/read-path, ghost-membership, missing-price/label tests; real-store report transport regressions backed by synthetic fixtures | A test pass is not proof of an anomaly or complete historical membership |
| Selected 200-company diagnostic | Full-grid archive from `0bd03bf` under `examples/outputs/b_selected_200_20260907/`; see validation for disclosed presentation defects and follow-up | The roster was selected from an ingest-time ticker map, not a contemporaneous historical roster |
| Evidence qualification | `demo_evidence.json`, per-factor diagnostic records, research gate ledger, visible failures and unavailable counts | No actual/estimated terminal-return adapter or automatic research-promotion path exists |
| Reading entry point | README headline, this guide, validation record and policy document | No survival numerator, market-wide inference or claim of completed backtest-audit integration |

## Run from a clone

```bash
python -m venv .venv
# Activate using the command appropriate for your shell.
python -m pip install -c src/fza/research-requirements.lock -e ".[dev]"
python -m pytest tests
python -m fza.demo --db does-not-exist.duckdb --outdir local-fixture-report
```

The intentionally absent DB selects the built-in `FixtureSpec`, whose seed and
parameters are written to the bundle. Fixture generation and tests need no
network once dependencies are installed. The full report retains the monthly
grid. `--max-dates` is only a faster, subsampled diagnostic: formation shifts
count selected dates, so its numbers are not definition-equivalent to a full run.

For a user who already holds the local selected database:

```bash
python -m fza.demo --db data/fza_200.duckdb --outdir local-selected-200-report
```

The local DB is not committed. A new download does not reproduce its historical
bytes. Exact reproduction of the archived diagnostic needs the database hash
recorded in that bundle, the corresponding code/rules, and its recorded runtime.
No new subscription or data redistribution permission is assumed.

## Three outputs from one computation

- `demo_report.txt`: readable report, with qualifications at the opening,
  protocol/vintage sections and conclusion. Stdout contains the same report.
- `demo_evidence.json`: dataset declarations, their binding status, byte hashes,
  explicit reasons, and claim-relative qualification.
- `demo_run.json`: the same evidence plus roster, signal dates, fixture spec
  when applicable, implementation/runtime manifests, definition denominator,
  each completed factor's existing protocol and stage reports, failures,
  vintage comparisons and unimplemented research gates.

`COMPLETED` means a computation ran, not that an anomaly passed. Non-finite
statistics become JSON null, never zero. A failed factor retains its entry and
null protocol; unavailable stage counts are not invented. Raw counts start
after factor-specific construction filters, which are reported separately.
LS Sharpe is the existing per-observation statistic, not an annualised claim.

## What the selected roster means

The bundle freezes the stored selection for reproducibility. It does not turn
that selection into a historical fixed cohort. Filing bounds remain proxies,
not official listing/exit dates. Missing issuers cannot be recovered by a gate
that sees only already-ingested rows. `survivorship_prone_share: 1.0` describes
source risk coverage, not 100% bias or any estimated IC distortion.

Loss counts describe observed processing. Unknown terminal outcomes and never
observed members remain unresolved; no automatic threshold treats them as
negligible. PIT/restated differences remain sample-conditional, not proof that
common defects cancel. Publication splits, multiple-testing correction,
free-baseline integration and cost gates are explicitly NOT_IMPLEMENTED here.

## Source qualification contract

`fza.qualification.qualification_policy()` is the single reviewed source for
qualification. Dataset evidence, text, both JSON exits and the README managed
block project it. Generate that block with `python -m fza.qualification`; a
test rejects a stale checked-in projection. Transport tests deliberately change
the source labels to catch hard-coded copies. These tests establish consistency,
not that the policy decisions are true. Generic docs-quote checking remains an
upstream reuse item in `CROSS_REPO_AUDIT.md`, not a second local implementation.

The legacy `.report.json` has no database hash: its fields are displayed as
unbound declarations, not authenticated facts about the open DB. New sidecars
may supply `database_sha256`; a byte match is binding evidence only, never
research approval. Active WAL files prevent main-file-only binding. Missing,
malformed or unreadable metadata is visibly unknown. Even `research_evidence:
true` cannot promote this diagnostic entry point.

The bundle records main-file hashes before/after the run. Equality is not a
transactional snapshot guarantee or proof of historical accuracy. The local
200-company report should show unchanged bytes; any discrepancy requires review.

## Delivery scope decision — 2026-09-08

B is the current delivery route. A (the licensed-data research extension) is
removed from current delivery dependencies, not kept as a pending prerequisite.
No institution reply, new provider, larger roster or exit-return implementation
is required to finish B. Previously downloaded licensed data are not incorporated
into this public delivery while post-affiliation usage rights are unconfirmed;
this is not a finding that all retention or publication is permanently forbidden.

Current access update (user confirmation, recorded 2026-09-09): WRDS access is
unavailable and is not awaiting a reply. Rights to retain/use old downloads or
publish aggregate results remain unconfirmed unless separately established.
Neither access nor usage-right status changes the two substantive data gates.

`historical_membership_completeness` and `terminal_outcomes` remain `UNRESOLVED`.
**No longer waiting for resolution does not mean resolved.** A permissions enquiry
addresses access/use rights, not those substantive data-quality gates. No email
has been sent by this repository's implementation task.

The remaining correctness work is ordered, with separate verification:

1. Correct vintage explanations and disclose actual scoring-key overlap and
   substituted-read coverage (including the docstrings and threshold comment).
   First correction implemented and tested: [2026-09-08 checkpoint](VALIDATION_20260908.md).
2. Add three diagnostic layers: original-process gap; common-observation scoring
   after arm-specific cleaning; common-support re-cleaning with fixed input keys
   and checked label/holding-period identity. Contrasts measure sensitivity, not
   a pure value/sample decomposition. The selected common set is not the cohort.
   Implementation contract: [three-layer comparison](VINTAGE_COMPARISON.md).
   Implemented and verified by [the 2026-09-09 checkpoint](VALIDATION_20260909.md);
   this is not a new full-grid selected-200 run or a complete regression claim.
3. Clarify breadth as names per retained date/quantile group. Any newly chosen
   warning threshold is post-observation, not preregistered.
4. Implement the reviewed multi-rule PlausibilityRule design. Input domains and
   transformed-output ranges must be distinguished; undefined is not passed.

OSAP is only a candidate external implementation comparator after these items.
No installation, integration, expanded factor set, code copying or data-package
redistribution is approved. Matching public implementations cannot verify an
unread original reference. No claim of unique novelty is made.

## Optional research extension, outside current delivery

Institutional access must cover the needed CRSP stock history and event/return
fields, not merely a WRDS login. Provider access and dataset acceptance remain
separate. The accepted conceptual policy separates terminal measurement from
named horizon-extension conventions; neither scenario has been implemented.
See `DATA_EXIT_POLICY_DRAFT.md`. A future research extension reuses these
controls rather than relaxing them to manufacture a headline.

## Read-only bridge preflight (not an implemented integration)

The tagged upstream `MIGRATION.md`, `pyproject.toml`, `panel.py` and `run.py`
were inspected. The release/tag/CI identity is recorded in `CROSS_REPO_AUDIT.md`.
No dependency was installed or bridge code added as part of this preflight.

The four column names do not establish semantic compatibility: upstream
`event_date` is target realisation time, whereas this pipeline retains
`signal_date`, `formation_date`, `entry_date` and `exit_date`. The eventual adapter
must use verified label timing, preserve those dates, and reject unaccounted
sample loss; a rename of signal_date is not sufficient. The baseline runner
requires a train/test boundary. Real-data cutoffs must be explicit, with boundary
overlap and information availability at signal formation checked. Do not infer
that a previous row's holding-period return was already known at the next signal.
No new real-data split, annualisation factor, trial count or exit assumption is
approved merely by the dependency release.
