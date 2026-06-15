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
- **Responsive UI** that adapts to any terminal size automatically
- **Visual progress bar** during package updates
- **Instant keyboard controls** - no Enter key needed for menu actions
- **Direct number input** - type a package number at the menu to update it directly
- **Update All confirmation** - y/n prompt before updating all packages
- **Cross-platform support** for Windows, Linux, and macOS

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
├── ui/
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

### Language Selection

Quick language selection with instant input:

- Press `1` + `Enter` for English (default)
- Press `2` + `Enter` for Português
- Press `3` + `Enter` for Español
- Press `Enter` alone selects English (default)

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
| `a` | Update all outdated packages with y/n confirmation (instant) |
| `o` | Update one package by number (instant, then type number + Enter) |
| `1-9` | Direct number input - type package number + Enter to update |
| `r` | Refresh package list (instant, no Enter needed) |
| `q` | Exit (instant, no Enter needed) |

### Instant Keyboard Controls

Menu actions use single-key input - just press the key without needing to hit Enter:

- Press `a` to ask for confirmation before updating all outdated packages
- Press `o` to immediately enter package selection mode
- Press `r` to immediately refresh the package list
- Press `q` to immediately exit

Package number selection (via `o` or direct number input) requires typing a number followed by Enter. Multi-digit numbers (e.g., 10, 99) work correctly.

### Direct Number Input

You can type a package number directly at the main menu without pressing `o` first:

- Type `3` + `Enter` to update package #3
- Type `1` + `0` + `Enter` to update package #10
- Invalid numbers show an error message

### Update all

Press `a` to update every outdated package. The app asks for confirmation (`y/n`) before proceeding.

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

### Refresh

Press `r` to refresh the package list:

- Clears size cache
- Re-detects terminal dimensions
- Reloads package data from npm
- Re-renders the table with current information

Use this when you've installed/uninstalled packages externally and want to see updated data.

---

## Responsive UI

The interface automatically adapts to your terminal size, providing an optimal viewing experience on any screen:

### Display Modes

The table layout changes based on terminal width:

| Mode | Terminal Width | Behavior |
| --- | --- | --- |
| **Full** | ≥100 columns | Complete table with all columns at full width |
| **Standard** | 80-99 columns | Slightly condensed, all columns visible |
| **Compact** | 60-79 columns | Truncated package names, optimized spacing |
| **Ultra-Compact** | <60 columns | Minimal layout, aggressive truncation |

### Smart Features

- **Automatic detection**: Terminal dimensions are detected on startup and every refresh
- **Dynamic resizing**: Table re-renders automatically when terminal is resized
- **Smart truncation**: Long package names are truncated with `...` to fit available space
- **Height adaptation**: Number of visible rows adjusts to terminal height

This ensures the tool works comfortably on small laptop terminals, large desktop screens, and everything in between.

---

## Progress Feedback

During package updates, a visual progress indicator keeps you informed:

### Progress Bar

```
[=====>    ] 45% [3/7] updating: lodash...
```

Components:

- **Visual bar**: `[=====>    ]` shows completion percentage graphically
- **Counter**: `[X/Y]` displays current package out of total
- **Percentage**: Numeric percentage for precise tracking
- **Current package**: Shows which package is being updated
- **Next package**: Preview of what's coming next

### Status Symbols

- `✓` - Update completed successfully
- `✗` - Update failed

This feedback system provides clear visibility into the update process, making it easy to track progress and identify any issues.

---

## Cross-Platform Compatibility

The application runs seamlessly on Windows, Linux, and macOS with automatic platform detection:

### Platform-Specific Optimizations

**Windows:**
- Uses `msvcrt` for keyboard input handling
- npm commands executed with `shell=True` for proper PATH resolution
- ANSI escape codes handled correctly for progress indicators

**Linux/macOS:**
- Uses `tty` and `termios` for instant keyboard input
- Standard POSIX terminal handling
- Native ANSI support for visual elements

### Automatic Detection

The app detects your operating system at runtime and configures:

- Input method (instant key press vs buffered)
- Command execution strategy
- Terminal control sequences

This ensures consistent behavior across all platforms without requiring manual configuration.

---

## Error Handling

Current behavior:

- Invalid menu input shows an `invalid option` message
- Invalid package number shows an `invalid number` message
- Invalid JSON from npm list/outdated becomes an empty result
- Failed update commands show `update_failed`
- Cross-platform compatibility prevents Unicode crashes on Windows terminals with ANSI code pages
- Graceful fallback when terminal size detection fails
- Update All confirmation cancels on any key other than `y`

---

## Internationalization

All user-facing strings are loaded from:

```text
locales/en.json
locales/pt.json
locales/es.json
```

Adding a new language requires:

1. Creating a new locale JSON file
2. Adding it to the language selection mapping in `main.py`

### Locale Keys (45 per file)

All user-facing strings including table headers, menu options, progress bar labels, error messages, and the `confirm_update_all` prompt.

---

## Limitations

- There is no automated test suite yet
- Size calculation still depends on filesystem traversal, so very large package trees can take noticeable time on the first load
- The tool assumes `npm` commands are available in the current shell environment

---

## License

MIT
