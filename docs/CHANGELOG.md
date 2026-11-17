# Changelog

All notable changes to npm-pymanager. Format follows Keep a Changelog.
Base language is English; other languages live only in `locales/`.

## [Unreleased]

### Added

-c Respond to a and q immediately
- On a terminal, the `--update` selection reacts to `a` and `q` on the first
  keypress; numbers still need Enter because more digits or commas may follow.
- Ctrl+C cancels the selection, and special keys such as arrows are ignored.
- Piped input keeps line-based reading, so scripts and tests behave the same.

-c Restyle CLI package tables
- `--list` and the `--update` selection now share one aligned table:
  `#`, `package`, `scope`, `current`, `latest`, with a column rule and a
  `→` arrow. There is no title header and no package count line; the table
  starts directly with the column headers.
- The arrow is `→` on a terminal and `>` otherwise. No ANSI escapes, no size
  measurement, no extra npm calls.
- A blank line separates the collection notice from the table output.
- The selection prompt is now a short `>` marker on stderr, with the accepted
  answers listed under the table.

-c Add CLI update spinner
- `--update`, the numbered update selection, and `--update-all` show the same
  transient spinner as the interactive mode while each npm update runs. When
  stdout is not a terminal the spinner is skipped, so piped output stays plain.

-c Add interactive update selection
- `--update` without a package name now prints a numbered list of outdated
  packages instead of failing. Answer with one number, a comma-separated
  list, `a`/`all` for every entry, or `q`/`quit` to cancel.
- The list has one line per package and scope, ordered by name with `LOCAL`
  before `GLOBAL`, so each number runs exactly one `npm update`.
- Empty input or EOF cancels with exit code `5`; an invalid answer exits
  with code `2`; neither case runs npm. `--yes` is ignored in this mode.
- `--update <package>` keeps its exact-name behavior unchanged.
- New CLI selection keys in all three locale files.

-c Add deterministic CLI mode
- `--list`, `--update-all`, `--update PACKAGE`, and `--uninstall PACKAGE`
  run one bounded command and exit without opening the interactive menu.
- `--help` and `--version` work without collection or a language prompt.
- Exact package-name resolution: partial names, substrings, and table row
  numbers are rejected, and `--scope` is required when a package is installed
  in both local and global scopes.
- `--uninstall` always asks for confirmation, even with `--yes`, `--force`,
  or `--auto`; `--yes` skips only the `--update-all` prompt.
- Stable exit codes (0, 1, 2, 3, 4, 5, 6, 124) and pipe-safe output: results
  on stdout, diagnostics and prompts on stderr, no ANSI in CLI output.
- 32 new CLI message keys in all three locale files.

### Fixed

- Keep demo mode isolated after simulated updates
- `--test` never leaks into real npm collection after `a`/`o` updates:
  simulated updates mark the fictitious rows as updated (`left-pad` keeps
  failing), `start_fetch()` refuses to run in demo mode, and `run()`
  never starts a subprocess in demo mode.

- Fix nested Linux raw input
- get_key_timeout() uses a single raw section without nested get_key() calls.
- getch() degrades safely without a TTY; language selection defaults to English.

-c Fix Linux key input
- Linux menu keys are read immediately without waiting for Enter.
- Failed key polling no longer falls back to an unbounded read.

-c remove redundant status legend
- Removed the redundant update legend from the menu; package status remains visible in the table.

### Added

- Show activity spinner during update and uninstall
- A spinner animates on the current package line while npm runs,
  so a single large package no longer looks frozen.

-c Add confirmed package uninstall
- `u` uninstalls one selected package after `y/n` and exact-name confirmations.
- Global packages use `npm uninstall -g`; when a package exists in both scopes,
  the local installation is removed first.

-c improve initial package loading
- The package table appears after installed-package listings, while update checks and size measurements continue in the background.
- Pending and failed update checks have explicit statuses, and update actions remain disabled until checks succeed.
- `r` queues a refresh during collection; `q` exits without waiting for background workers.
- Global package sizes share one `npm root -g` lookup and tolerate files disappearing during traversal.

-c add multi-package selection
- `o` and direct number input accept comma-separated IDs; Backspace edits the selection.
- `status` locale key for the table STATUS header (all three locales).

### Changed

-c Move status before package number
- STATUS now appears before the package number in every display mode.
- Docs live in `docs/` (`README.md`, `CHANGELOG.md`); `README`
  project structure updated and locale key count corrected (55 → 56).
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
