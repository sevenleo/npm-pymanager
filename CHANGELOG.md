# Changelog

All notable changes to npm-pymanager. Format follows Keep a Changelog.
Base language is English; other languages live only in `locales/`.

## [Unreleased]

### Added

- `status` locale key for the table STATUS header (all three locales).

### Changed

- Refresh (`r`) keeps the size cache; `README` documents the real
  project structure and the `CHANGELOG.md` itself.

## [2026-09-14]

### Added

- Demo mode (`--test`): 10 fictitious packages (4 up to date, 5 outdated,
  1 failing) with simulated updates; combines with `--no-color`.
- Pinned progress bar with a scrolling viewport list during updates
  (`[ok]` / `[>]` / `[ ]` / `[x]`, `[L]`/`[G]` scope tags,
  `... N more above/below`); sequential logging when piped.
- Timeouts for every npm call (`NPM_PM_TIMEOUT`, `NPM_PM_UPDATE_TIMEOUT`)
  with fail-soft behavior and an `npm_timeout` warning.
- `NPM_PM_TTL` for stale-data auto-refresh; `NPM_PM_ASCII` and `NO_COLOR`
  overrides documented in `README`.

### Changed

- Main loop reuses fetched data (refetch on `r`, after updates, or TTL);
  short pauses on invalid/cancelled input instead of the full delay.
- Size cache keyed by version is never cleared; new versions remeasure once.
- `npm outdated --depth=0` for the local scope (A/B identical output).
- Arrow/function keys ignored everywhere (raw-byte `msvcrt` handling);
  stray Enter no longer errors; `(y/N)` confirmation hint fixed.
- ASCII fallbacks (`...` for the processing glyph) prevent
  `UnicodeEncodeError` on legacy consoles.

## [2026-06-15]

### Added

- Direct package-number input at the menu.

### Changed

- Hidden packages (names starting with `.`) filtered out.

## [2026-03-29]

### Added

- Responsive table (full / compact / ultra-compact) with smart truncation.
- Progress bar with current/next package and `LOCAL`/`GLOBAL` prefixes.
- Language menu with English, Portuguese and Spanish locales.
- Spinner during data collection.

### Fixed

- Windows support (`msvcrt` input, `shell=True` npm resolution,
  relative locale paths).

## [2026-03-16] – v1

### Added

- Merged local+global npm package table with versions, latest available
  and disk sizes; update all / update one flows; parallel data
  collection; instant single-key controls.
