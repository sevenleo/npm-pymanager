# Performance Plan for npm-pymanager (revised)

> Rewritten after auditing the real code. The original version of this file
> is obsolete: it marked Phase 1 as done (it was not), used stale line
> numbers, and did not know about the UI rewrite (theme, frame progress,
> demo mode, `get_key()`).

## Executive Summary

`main.py` (~1550 lines, stdlib only) shells out to `npm list`, `npm outdated`
and `npm update`. Cost profile per cycle:

1. `collect_rows()` — 4 npm queries in parallel (network-bound, slowest part).
2. `collect_sizes()` — `os.walk` over every installed package, 8 workers,
   cached in `SIZE_CACHE` keyed by `(scope, name, version)`.
3. Main loop used to redo 1+2 on **every keypress**, plus `SIZE_CACHE.clear()`
   on refresh and `time.sleep(DELAY)` on every feedback path.

## Implemented

- [x] Parallel npm queries (`collect_rows`, 4 workers) and sizes (8 workers).
- [x] `SIZE_CACHE` keyed by version — **never cleared**; refresh and
      post-update refetches reuse sizes for unchanged versions.
- [x] Cached main loop: data fetched once, reused for render+input; refetch
      only on `r`, after an update, or when older than `NPM_PM_TTL` (120s).
- [x] Short feedback pauses (`min(DELAY, 1)`) on invalid/cancelled input;
      full `DELAY` only after real updates. Non-printable keys never reach
      the error paths (`get_key()` filter).
- [x] Timeouts fail-soft: `NPM_PM_TIMEOUT` (90s) for queries,
      `NPM_PM_UPDATE_TIMEOUT` (300s) for updates; timeouts surface as empty
      results / `False` plus an `npm_timeout` warning toast.
- [x] `npm outdated --depth=0 --json` for local scope (was missing the flag).
      A/B tested 2026-09-14 on a fixture with outdated deps
      (`express@4.17.1`, `lodash@4.17.20`): identical package sets with and
      without the flag (~1s both); adopted for explicit top-level scope,
      matching the global command and `npm list`.
- [x] Spinner during collection (`start_spinner`/`stop_spinner`).
- [x] `loading_sizes` locale key exists (currently unused — reserved for a
      future incremental-size display).

## Deliberately Deferred

- **Lazy/incremental size display**: with session caching + no-clear + cached
  loop, repeat cost is ~zero and first load is covered by the spinner.
  A live re-render would fight the static UI for little gain.
- **Persistent disk cache** (`~/.cache`): rejected — staleness risk when
  `node_modules` changes outside the app; version-keyed session cache is
  enough.
- **Worker-count auto-tuning**: 4 (npm, network-bound) and 8 (sizes,
  IO-bound) are sane stdlib defaults; revisit only with measurements.

## Tuning

| Variable | Default |
| --- | --- |
| `NPM_PM_DELAY` | `2` |
| `NPM_PM_TTL` | `120` (`0` = refresh only on `r` / after update) |
| `NPM_PM_TIMEOUT` | `90` |
| `NPM_PM_UPDATE_TIMEOUT` | `300` |

## Validation (manual — no test suite per project rule)

```bash
python -c "import ast; ast.parse(open('main.py', encoding='utf-8').read()); print('OK')"
python main.py --test
# - invalid keys/arrows: no spinner, no reload, ~instant re-render
# - 'r': refetch with spinner; second refresh visibly faster (sizes cached)
# - NPM_PM_TIMEOUT=1 with slow network: warning toast in ~1s, no traceback
```
