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
1. PLATFORM COMPATIBILITY — `os.name` / `sys.platform` checks
2. CONFIG — default directory, editor, colors
3. I18N — locale loader and `t()` helper
4. TERMINAL SIZE & UI HELPERS — cursor movement, colors
5. NPM HELPERS — `npm list --json`, `npm outdated --json`, `npm update`
6. SIZE — `ls -la` size calculation and `du-like` totals
7. TABLE — drawing logic for the package table
8. UPDATE — `npm update [pkg]` execution
9. DATA REFRESH — async refresh loop via `concurrent.futures`
10. MAIN LOOP — keyboard handling and dispatch

### User-Facing Strings
- All user-facing strings go through `t(key)` which looks up the current locale (en/es/pt)
- Never hardcode visible text in Portuguese/English — add a translation key to all three locale files instead
- Locale files live in `locales/{en,es,pt}.json`

### Testing
- No test framework is set up. Do NOT add one without explicit user request.
- If you modify logic, manually verify with `python main.py`
- The README explicitly states "There is no automated test suite yet"

### Git
- Commits are short lowercase English phrases without conventional-commit prefixes
- Branch: `main` (single long-running branch)

### Critical Rules
- **Do not add external dependencies** — this is a deliberate stdlib-only project
- **Keep the locale files in sync** — any new `t()` key must exist in all three `locales/*.json`
- Do not refactor the ASCII banner section headers
- Preserve the `__main__` guard pattern
- The skeleton `package-lock.json` has zero packages and exists only so `npm` commands don't error — do not modify it
