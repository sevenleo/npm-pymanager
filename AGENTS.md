# AGENTS.md — npm-pymanager

## Project Overview

A terminal user interface (TUI) for managing npm packages interactively. Written in pure Python 3 stdlib (no external dependencies). Shells out to `npm list`, `npm outdated`, and `npm update` commands.

## Tech Stack

- **Language:** Python 3.8+ (no external packages, stdlib only)
- **Runtime:** any system with Python 3 and Node.js/npm installed
- **UI:** raw terminal via `\x1b` escape codes + `shutil.get_terminal_size()`

## Build / Test / Lint Commands

There is **no build system**, **no test suite**, and **no linter/formatter configured**. The project runs directly as a script:

```bash
# Run the app
python main.py

# Verify syntax (the only validation available)
python -c "import ast; ast.parse(open('main.py').read()); print('OK')"
```

If you add code, verify it works by running `python main.py` and exercising the changed path. Do NOT introduce external dependencies.

## Code Style Guidelines

### Imports
- stdlib only, one per line, alphabetical order after the shebang
- `#!/usr/bin/env python3` on line 1
- No `from x import *` or relative imports

### Naming
- `snake_case` for functions and variables
- `UPPER_CASE` for globals and constants
- `_leading_underscore` for "private" helper functions
- Classes: not used in this project — keep it functional

### Type Hints
- **Do NOT add type hints.** The codebase avoids them entirely.
- Document types verbally in the docstring instead (e.g., `value (int): ...`).

### Docstrings
- Google-style with `Args:` and `Returns:` sections
- Written in **Portuguese** (Brazilian)
- Every function with non-trivial logic should have one

### Error Handling
- Use `try/except Exception as e` for expected failure modes
- Return sensible defaults on error (empty dict `{}`, string `"-"`, etc.)
- Use `print()` for user-facing messages (no logging module)
- Prefer silent degradation over crashing

### Line Length & Formatting
- Aim for ~80 characters per line, soft limit at 100
- Two blank lines between top-level function definitions
- One blank line between logical sections inside functions
- No trailing whitespace

### Code Organization

The file is structured into ASCII-bannered sections in this order:
1. PLATFORM COMPATIBILITY — `os.name` checks, `msvcrt` vs `tty`/`termios`
   input, `_read_msvcrt_key` / `getch` / `get_key` special-key filtering
2. CONFIG — `SCRIPT_DIR` / `LOCALES_DIR`, `LANG` / `STRINGS`, `DELAY`,
   `NPM_TIMEOUT` / `NPM_UPDATE_TIMEOUT`, `CACHE_TTL`, `SIZE_CACHE`,
   `COLOR_ENABLED` / `USE_UNICODE`, `DEMO_MODE`, `_FRAME_LINES`
3. I18N — locale loader and `t()` helper, theme init (`supports_color`,
   `_detect_unicode`, `NO_COLOR` / `NPM_PM_ASCII`), `c()` / `status_label`
4. TERMINAL SIZE & UI HELPERS — `get_terminal_size`,
   `truncate_string`, separators, spinners, message prefixes
5. TERMINAL — `clear`, `print_header`, progress bar lines, frame/viewport
   rendering (`_build_progress_frame`, `_viewport_window`, `_frame_emit`)
6. NPM HELPERS — `npm list --json`, `npm outdated --json`, `npm update`
   via `run` / `run_npm_cmd` with timeouts and fail-soft defaults
7. SIZE — `os.walk` traversal + `human_size`, `npm_root` (`lru_cache`),
   per-scope/version `SIZE_CACHE`, parallel `collect_sizes`
8. TABLE — drawing logic for the package table (full / compact /
   ultra-compact) plus `DEMO_ROWSPEC` / `collect_rows_demo`
9. UPDATE — `npm update [pkg]` execution (`_npm_args`, `_run_tasks_frame`
   vs `_run_tasks_legacy`, `update_all` / `update_one`)
10. DATA REFRESH — cached fetch loop (`collect_rows`, `CACHE_TTL`
    staleness), progressive daemon-worker results, and queued refreshes
11. MAIN LOOP — keyboard handling and dispatch (`a` / `o` / digits /
    `r` / `q`, `(y/N)` confirm)

### Docs
- User docs live in `docs/` (`README.md`, `CHANGELOG.md`), not at root.

### User-Facing Strings
- All user-facing strings go through `t(key)` which looks up the current locale (en/es/pt)
- Never hardcode visible text in Portuguese/English — add a translation key to all three locale files instead
- Locale files live in `locales/{en,es,pt}.json`

### Testing
- No test framework is set up. Do NOT add one without explicit user request.
- If you modify logic, manually verify with `python main.py`
- The `docs/README.md` explicitly states "There is no automated test suite yet"

### Git
- Commits are short lowercase English phrases without conventional-commit prefixes
- Branch: `main` (single long-running branch)

### Critical Rules
- **Do not add external dependencies** — this is a deliberate stdlib-only project
- **Keep the locale files in sync** — any new `t()` key must exist in all three `locales/*.json`
- Do not refactor the ASCII banner section headers
- Preserve the `__main__` guard pattern
- The skeleton `package-lock.json` has zero packages and exists only so `npm` commands don't error — do not modify it
