# Report replay and source boundaries

`fza.render.render_report` consumes saved results and captured display inputs.
It does not open a store, call a factor, score a panel or consult the current
factor registry. Both the demo's stdout and its saved text use this renderer.
Progress is emitted to stderr, separately from the report.

## New runs: schema 2

`presentation` captures the database display path, price-column coverage and
registered-factor table during the run. Detailed failures are structured under
`failure`: exception type, status, full message, display reasons and any
structured exception detail. Text consumes those same display reasons.
Previously, some failure reasons existed only in text. This is a serialization
gap separate from the seven overwidth lines; successful selected-200 results
were not affected. Legacy missing details are not invented during replay.

`runtime` records UTC start/computation-finish and monotonic elapsed seconds.
Its scope explicitly excludes final rendering and artifact writes. It is not
CPU time or end-to-end launch-to-exit time. Per-stage JSONL/checkpoint timing and
performance optimization remain separate work.

All three newly written demo files use explicit LF. Existing CRLF archives are
unchanged. Rendering code/version changes can change text without changing a
single computed statistic.

## Legacy runs: explicit supplement

Schema 1 lacks some display inputs. `fza.replay` requires the original companion
text. It extracts only DATA, DATA QUALITY and REGISTERED FACTORS using their
existing sections/columns, never today's registry or a replacement database.
Only displayed low-coverage columns are recoverable; their percentages have
display precision, not the unavailable full-precision coverage. Failure details
absent from a legacy bundle are not reconstructed by this adapter.

Before adding repeated local sensitivity notices, the complete rendered token
stream must equal the companion report. A mismatch raises an error before any
output is created. This checks source consistency, not truth of the statistics.
Ambiguous or unsupported legacy reports should fail rather than silently omit
information. The adapter is not promised to parse every historical layout.

The new directory contains:

- `demo_report.txt`: presentation only, with 84-column wrapping.
- `replay_input.json`: original computation fields plus explicit presentation
  supplement; not misnamed as a newly computed `demo_run.json`.
- `render_manifest.json`: source file hashes, section locators, extraction
  methods, renderer/adapter hashes, supplement flag, output hash and LF policy.

The source formats are not ranked as evidence grades. Research qualification
remains the archived qualification. Original files are never overwritten.

## Verification boundaries

Long source reasons must wrap without losing content. A deliberately overwidth
rendered line must fail with its line number. Short table rows preserve column
positions independently of the width check. Excluded-key samples use one key
per line. Sample/processing sensitivity is explicitly not a causal decomposition,
including next to each comparison block.

The active SPEC requests runtime/failures in a structured bundle. That supports
fixing the concrete omissions; it does not establish that schema 1 promised
standalone reproduction of every line of prose.
