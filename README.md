# NPM Package Manager TUI (Python)

Terminal utility in Python to inspect and update local and global npm packages from a single screen.

It shows installed versions, available updates, and package size, then lets you update everything outdated or only one selected package.

---

## Features

- Displays local and global npm packages in one merged table
- Highlights outdated packages with `(u)`
- Shows installed version and latest available version for each scope
- Calculates disk usage for local and global installs in a single `SIZE` column
- Supports English, Portuguese, and Spanish
- Updates only packages that are actually outdated
- Refreshes the table automatically after each update cycle

## Performance Notes

The current implementation was optimized to reduce initial load time:

- `npm list` and `npm outdated` are collected in parallel
- Package size calculation runs in parallel
- Size results are cached by package scope and version during the current session

This keeps the first load much faster than the original implementation, and repeated refreshes are faster again because size values are reused while versions stay the same.

---

## Requirements

- Python 3.8+
- Node.js
- npm available in `PATH`

Check your environment:

```bash
node -v
npm -v
python --version
```

---

## Project Structure

```text
project/
├── main.py
└── locales/
    ├── en.json
    ├── pt.json
    └── es.json
```

---

## How It Works

### Data collection

The app collects:

- `npm list --depth=0 --json` for local packages
- `npm list -g --depth=0 --json` for global packages
- `npm outdated --json` for local outdated packages
- `npm outdated -g --depth=0 --json` for global outdated packages

Hidden/private packages whose names start with `.` are filtered out.

If `npm list` or `npm outdated` returns invalid or empty JSON, the app falls back to an empty result instead of crashing.

### Size calculation

The `SIZE` column is built from the installed package directories:

- local packages: `node_modules/<package>`
- global packages: `<npm root -g>/<package>`

Display behavior:

- only local installed: `8.5KB`
- only global installed: `15.2MB`
- both installed: `15.2MB(G) 8.5KB(L)`

### Update behavior

When updating, the application:

- updates only packages flagged as outdated
- runs local and global updates separately
- reports success only if the underlying `npm update` command returns exit code `0`
- shows a failure message if one or more update commands fail

---

## Usage

Run the script from the repository root:

```bash
python main.py
```

Select a language:

1. English
2. Português
3. Español

Then wait for package data to load.

Note:

- If you run the tool outside a Node.js project, the local package section will usually be empty.
- Global packages are still shown if npm can resolve the global install root.

---

## Table Columns

| Column | Meaning |
| --- | --- |
| `#` | Numeric identifier used to select one package |
| `PACKAGE` | Package name |
| `GLOBAL_VERSION` | Installed global version |
| `GLOBAL_NEW` | Latest version available for the global install |
| `LOCAL_VERSION` | Installed local version |
| `LOCAL_NEW` | Latest version available for the local install |
| `SIZE` | Combined size view for local/global installs |

Outdated entries are marked with `(u)` beside the installed version.

---

## Controls

| Key | Action |
| --- | --- |
| `a` | Update all outdated packages |
| `o` | Update one package by number |
| `q` | Exit |

### Update all

Press `a` to update every outdated package found in the current screen.

The app:

- lists outdated local packages first
- lists outdated global packages second
- executes only the required `npm update` commands

### Update one

Press `o`, then type the package number shown in the first column.

The app updates only the outdated scope(s) for that package:

- local only
- global only
- or both

If the selected package is already current in both scopes, the app shows an "already updated" message and returns to the menu.

---

## Error Handling

Current behavior:

- invalid menu input shows an `invalid option` message
- invalid package number shows an `invalid number` message
- invalid JSON from npm list/outdated becomes an empty result
- failed update commands show `update_failed`
- Unicode-only symbols were removed from the update flow to avoid crashes in Windows terminals with ANSI code pages

---

## Internationalization

All user-facing strings are loaded from:

```text
locales/en.json
locales/pt.json
locales/es.json
```

Adding a new language requires:

1. creating a new locale JSON file
2. adding it to the language selection mapping in `main.py`

---

## Limitations

- There is no automated test suite yet
- Size calculation still depends on filesystem traversal, so very large package trees can take noticeable time on the first load
- The tool assumes `npm` commands are available in the current shell environment

---

## Possible Next Improvements

- Search/filter by package name
- Sorting by version, update status, or size
- Optional lazy loading for size values
- Better error reporting when `npm` itself is unavailable
- Rich/Textual-based navigation instead of plain `input()`

---

## License

MIT
