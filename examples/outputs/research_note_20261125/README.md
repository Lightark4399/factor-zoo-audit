# Research-note recomputation, 2026-11-25

DIAGNOSTIC_ONLY, the same scope as the source archive
[`b_selected_200_rerun_20260909/`](../b_selected_200_rerun_20260909/demo_run.json).
These files recompute `compare_vintages` for the four fundamental factors
(`bm_ratio`, `ep_ratio`, `roe`, `asset_growth`) and keep the per-date IC series
of every layer and arm, which the source archive does not store. They are used
by [docs/RESEARCH_NOTE.md](../../../docs/RESEARCH_NOTE.md).

## Identity

- **Code.** Commit `c4840f19bfb3ec420577c42898f547cf8cbe7684` (branch
  `docs/research-note`; `src/` identical to `main` at `b3d6c35`). Each of the
  four original run logs
  records `git status --porcelain -- src` as clean and `fza` imported from this
  checkout's `src/`.
- **Store.** The local `fza_200.duckdb` (not in the repository), SHA-256
  `66c60785d1c085d4883f49796a33f20ad2bdf418072086fbfd938100666312d9`, the
  source archive's `database_sha256_after_run`. Opened `read_only`; each log
  records the same hash before and after its run.
- **Environment.** Windows; Python 3.12.14, pandas 3.0.5, numpy 2.5.2,
  scipy 1.18.1, duckdb 1.5.5, as printed in each log. Python, pandas, numpy and
  scipy match the source archive's `environment` block. DuckDB
  `memory_limit='1GB'` (reported as 953.6 MiB) and `threads=1`.
- **Grid and protocol.** 185 month-end signal dates, 2011-04-30 to 2026-08-31;
  `horizon_sessions=21`, `execution_lag_sessions=1`, `n_quantiles=5`, as in the
  source archive's `configuration`.

## Runs

One factor per process, sequentially. Times are from the logs (UTC offset
+00:00).

| factor | `compare_vintages` start | seconds | peak working set |
|---|---|---|---|
| bm_ratio | 2026-11-25T21:36:52 | 41.8 | 511 MiB |
| ep_ratio | 2026-11-25T21:54:20 | 3515.0 | 1248 MiB |
| roe | 2026-11-25T22:53:02 | 3972.0 | 1209 MiB |
| asset_growth | 2026-11-25T23:59:22 | 380.8 | 825 MiB |

## Commands

### As run

The runs used pre-commit copies of the two scripts in a temporary directory:
the driver (SHA-256
`90e49eba15f332832da8e199103b11a1a6195496069198f8368530f84ac3ff7b`), which
hard-coded the repository path and the expected store hash, and the checker
(SHA-256 `ade8bec7c32735c09ef0cdc432fb098ab047b5dfd3ce8690d3870c80af2fc2e7`),
which did not yet print MDE. Two PowerShell commands were run, unmodified.
Each log's final `wrote` line records the output path.

`bm_ratio`, as a trial run:

```powershell
& {
  $py    = 'C:\Users\86181\OneDrive\文档\ChatGPT\github\factor-zoo-audit\.diagnostic-envs\locked\Scripts\python.exe'
  $db    = 'C:\Users\86181\OneDrive\文档\ChatGPT\github\factor-zoo-audit\data\fza_200.duckdb'
  $pilot = 'C:\Users\86181\AppData\Local\Temp\claude\562be76720cb0d3a\ea88ccde-087f-45f7-9714-86ffee5a1e2a\scratchpad\vintage_pilot'
  if (-not (Test-Path $py) -or -not (Test-Path $db)) { Write-Error 'python or DB path not found'; return }
  & $py -I -u "$pilot\run_vintage_series.py" --db $db --factor bm_ratio --out "$pilot\out\bm_ratio_series.json" --log "$pilot\out\bm_ratio_run.log"
}
```

followed by the pre-commit checker on its output, as a separate command:

```powershell
& 'C:\Users\86181\OneDrive\文档\ChatGPT\github\factor-zoo-audit\.diagnostic-envs\locked\Scripts\python.exe' -I 'C:\Users\86181\AppData\Local\Temp\claude\562be76720cb0d3a\ea88ccde-087f-45f7-9714-86ffee5a1e2a\scratchpad\vintage_pilot\check_vintage_series.py' 'C:\Users\86181\AppData\Local\Temp\claude\562be76720cb0d3a\ea88ccde-087f-45f7-9714-86ffee5a1e2a\scratchpad\vintage_pilot\out\bm_ratio_series.json'
```

`ep_ratio`, `roe` and `asset_growth`, one process at a time in a single loop,
then the pre-commit checker on each, then a copy of all outputs to a backup
directory:

```powershell
& {
  $py    = 'C:\Users\86181\OneDrive\文档\ChatGPT\github\factor-zoo-audit\.diagnostic-envs\locked\Scripts\python.exe'
  $db    = 'C:\Users\86181\OneDrive\文档\ChatGPT\github\factor-zoo-audit\data\fza_200.duckdb'
  $pilot = 'C:\Users\86181\AppData\Local\Temp\claude\562be76720cb0d3a\ea88ccde-087f-45f7-9714-86ffee5a1e2a\scratchpad\vintage_pilot'
  foreach ($f in 'ep_ratio','roe','asset_growth') {
    & $py -I -u "$pilot\run_vintage_series.py" --db $db --factor $f --out "$pilot\out\${f}_series.json" --log "$pilot\out\${f}_run.log"
    if ($LASTEXITCODE -ne 0) { Write-Error "$f failed"; break }
  }
  foreach ($f in 'ep_ratio','roe','asset_growth') {
    & $py -I "$pilot\check_vintage_series.py" "$pilot\out\${f}_series.json"
  }
  Copy-Item -Force "$pilot\out\*" "$HOME\vintage_pilot\vintage_pilot\out\"
}
```

The checker's console output was not saved; the `check_<factor>.txt` files
here come from the committed checker (below). The files committed here are
byte-identical in the run directory and the backup directory.

### With the committed scripts

The committed
[`scripts/research_note/run_vintage_series.py`](../../../scripts/research_note/run_vintage_series.py)
differs from the driver as run only by taking the repository path and the
expected hash as `--repo` (default: this checkout) and `--expected-sha256`,
by splitting one import line, and by its docstring. The equivalent command,
from the repository root, per factor:

```powershell
python -I -u scripts/research_note/run_vintage_series.py --db <path>\fza_200.duckdb `
  --factor bm_ratio `
  --out examples/outputs/research_note_20261125/bm_ratio_series.json `
  --log examples/outputs/research_note_20261125/bm_ratio_run.log `
  --expected-sha256 66c60785d1c085d4883f49796a33f20ad2bdf418072086fbfd938100666312d9
```

`python` must be an environment with this project's dependencies; the runs used
the locked environment listed above. The `check_<factor>.txt` files were
produced afterwards by the committed
[`scripts/research_note/check_vintage_series.py`](../../../scripts/research_note/check_vintage_series.py)
(standard library only; run with Python 3.12.10):

```powershell
python -I scripts/research_note/check_vintage_series.py `
  examples/outputs/research_note_20261125/bm_ratio_series.json > check_bm_ratio.txt
```

Part 1 of each check output compares every layer and arm with the source
archive; part 2 gives the per-date gap statistics. The `check_<factor>.txt`
files were regenerated on 2026-11-26, after the checker changed MDE to
2.8 × the Newey-West standard error and added the sign, two-sided and
one-sided p-values, NW t at lags 0, 3, 5 and 12, and the Bonferroni
threshold. Part 1 is byte-identical to the previous version.

[`scripts/research_note/compare_series.py`](../../../scripts/research_note/compare_series.py)
compares two driver outputs field by field (all fields except `generated_at`
and `stage_seconds`) and exits 1 on any difference:

```powershell
python -I scripts/research_note/compare_series.py <old>_series.json <new>_series.json
```

## Reproduction with the committed scripts

A check that the committed scripts reproduce the runs above. Only `bm_ratio`
was rerun; `ep_ratio`, `roe` and `asset_growth` were not, because each takes
about an hour.

- **Rerun.** The committed `run_vintage_series.py`, run on 2026-11-26 with the
  locked environment and the same store, writing to a temporary directory (the
  log's final `wrote` line records the path).
  [`bm_ratio_rerun_run.log`](bm_ratio_rerun_run.log) records `git rev-parse
  HEAD` as `28b1d18b8a3825254a2bb25667f7c6787bbfa52a`,
  `git status --porcelain -- src` as clean, `fza` imported from this checkout's
  `src/`, and the store's SHA-256 as
  `66c60785d1c085d4883f49796a33f20ad2bdf418072086fbfd938100666312d9` both
  before and after (`UNCHANGED`). `compare_vintages` took 62.1 s, and the peak
  working set was 476 MiB. Its output is
  [`bm_ratio_rerun_series.json`](bm_ratio_rerun_series.json).
- **Comparison.** The committed `compare_series.py`, with
  `bm_ratio_series.json` as the old file and `bm_ratio_rerun_series.json` as the
  new one, exited 0. Its output is
  [`compare_bm_ratio_rerun.txt`](compare_bm_ratio_rerun.txt):

```text
  SAME     db
  SAME     db_sha256_after
  SAME     db_sha256_before
  SAME     duckdb
  SAME     factor
  SAME     fza_file
  skip     generated_at (volatile)
  SAME     layer_ic_gap
  SAME     series.common-observation/pit (183 per-date IC values)
  SAME     series.common-observation/restated (183 per-date IC values)
  SAME     series.common-support/pit (183 per-date IC values)
  SAME     series.common-support/restated (183 per-date IC values)
  SAME     series.original-process/pit (183 per-date IC values)
  SAME     series.original-process/restated (183 per-date IC values)
  SAME     signal_dates
  skip     stage_seconds (volatile)

ALL COMPARED FIELDS IDENTICAL
```

## Files

Bytes are preserved as generated (CRLF line endings; `-text` in
`.gitattributes`). The logs and JSON record local paths (interpreter, store,
imported `fza`) exactly as written at run time.

| file | bytes | SHA-256 |
|---|---|---|
| `asset_growth_run.log` | 5419 | `0cb40d6ebdc11f1783dec746a697af1fbbb7667b41fec0ffd71c1aa94a8e41a1` |
| `asset_growth_series.json` | 51871 | `cef0bc35bfe49cf115ed25e4de397ae2a61f8d1c7e46ef8b90956c4e904525b1` |
| `bm_ratio_rerun_run.log` | 5409 | `bc813d37aea1c935a981897997346c5eb71d14bc81512f225d0b17854762063f` |
| `bm_ratio_rerun_series.json` | 52014 | `c66adc5dba53f71fc2b851280866fdb22d14a1dfc061d7c064bfb0f3d44b4c19` |
| `bm_ratio_run.log` | 5399 | `36b230339c0cb50c780706b1768c613cd336f599fb731c2d647dce135c33c0ff` |
| `bm_ratio_series.json` | 52020 | `0a323fdc6aaad0a2ee4c5dc368d96265b9a40f62e54afd0c8d0cc1632ecd0835` |
| `check_asset_growth.txt` | 2391 | `c8d7a842a77dcb540b70dd6e4ffae0395de973c8e97276fb995dc7e4c9bc2aad` |
| `check_bm_ratio.txt` | 2383 | `c4dbcc173bdc33853bd0712f81d4646435611f1969dd9c3e6bd84aa0191e3418` |
| `check_ep_ratio.txt` | 2383 | `8aca2665ee4bd1892eeaf11f41c8990a840a21fa0b2ae3c78c5aa06303e7cabb` |
| `check_roe.txt` | 2373 | `890d403583e3892313c46b483b3e60765c8470df4eba5f1b2a7426226bb6d1f4` |
| `compare_bm_ratio_rerun.txt` | 692 | `4e23cc42c9e6312170d87b37710730cee809e9db908b22dbb47bd691f3f99418` |
| `ep_ratio_run.log` | 5430 | `060b07562f82f1869ba13c63f3705d89f4327b9966bf2df6705bf13b513e3fcb` |
| `ep_ratio_series.json` | 51987 | `4b2857ad3da82333c21616aae54c55210803eda590ebf449414408bb7ca56e4f` |
| `roe_run.log` | 5410 | `63a5cca59d8f5da54e2fac27c0e8b799832c5d063e4438f1938d57d91831a0d5` |
| `roe_series.json` | 52023 | `2ab316b81ef3a1b7b00aab020ca7673ef0f1e0a2235706e844ac66069555e5e4` |

Series fields: `series.<layer>/<arm>.{dates,ic,ic_mean,n_dates,n_observations}`,
with `<layer>` one of `original-process`, `common-observation`,
`common-support` and `<arm>` `pit` or `restated`; `layer_ic_gap.<layer>`;
`db_sha256_before`, `db_sha256_after`; `stage_seconds`.
