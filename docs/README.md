# NPM Package Manager TUI (Python)

Terminal utility in Python to inspect, update, and uninstall local and global npm packages from a single screen.

It shows installed versions, available updates, and package size, then lets you update packages or safely uninstall one selected package.

---

## Features

- Displays local and global npm packages in one merged table
- Highlights outdated packages with a `[update]` STATUS label (calm color, `[ok]` when current)
- Shows installed version and latest available version for each scope
- Calculates disk usage for local and global installs in a single `SIZE` column
- Supports English, Portuguese, and Spanish
- Updates only packages that are actually outdated
- Refreshes the table automatically after package updates and uninstall attempts
- Uninstalls one selected package after a `y/n` prompt and exact package-name confirmation
- **Responsive UI** that adapts to any terminal size automatically
- **Pinned progress bar** with a scrolling viewport list during updates (no repeated bars, no terminal scroll)
- **Activity spinner** on the current package line while each `npm update` or `npm uninstall` runs (single large packages no longer look frozen)
- **Instant keyboard controls** - no Enter key needed for menu actions; arrows and special keys are silently ignored
- **Package selection** - update packages by number, including comma-separated selections
- **Confirmed uninstall** - removes one local or global installation at a time after two confirmations
- **Update All confirmation** - `(y/N)` prompt before updating all packages
- **Demo mode** (`--test`) - 10 fictitious packages to preview the UI without touching npm
- **Progressive loading** - installed packages appear before update checks and size measurements finish
- **Cached data loop** - fetches once and reuses; refetches on demand, after updates, or when stale (TTL)
- **Timeout-safe npm calls** - every command has a timeout and fails soft with a warning
- **Cross-platform support** for Windows, Linux, and macOS

## Performance Notes

The application prioritizes the first package list and continues enrichment in the background:

- Local and global `npm list` queries run in parallel. The first table appears as soon as both finish, without waiting for registry queries or filesystem traversal.
- `npm outdated` queries run in parallel with size calculation. Update actions stay unavailable until all package and update checks succeed; pending or failed checks never appear as up to date.
- Package sizes are measured in the background by up to eight daemon workers. The global npm root is resolved once per collection, and individual file errors do not stop the scan.
- Size results are cached by package scope and version for the whole session — refresh (`r`) never clears the cache; new versions simply miss and get measured once
- The main loop refreshes the display as results arrive and reuses fetched data: it refetches only on `r`, after an update, or when the data is older than the TTL (default 120s)
- Every npm call has a timeout and fails soft (empty result / `False`) with a warning instead of hanging
- Pressing `r` during collection queues one refresh and cancels outstanding size traversal. Pressing `q` exits without waiting for daemon workers.
- Redirected output prints the initial and completed tables sequentially without terminal-clear sequences.

Tuning via environment:

| Variable | Default | Meaning |
| --- | --- | --- |
| `NPM_PM_DELAY` | `2` | Pause after update confirmations |
| `NPM_PM_TTL` | `120` | Seconds before idle data is considered stale (`0` disables auto-refresh) |
| `NPM_PM_TIMEOUT` | `90` | Timeout for `npm list` / `outdated` / `root` queries |
| `NPM_PM_UPDATE_TIMEOUT` | `300` | Timeout for each `npm update` or `npm uninstall` command |
| `NPM_PM_ASCII` | unset | Set to `1` to force ASCII fallback |
| `NO_COLOR` | unset | Set to disable all ANSI colors |

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
├── locales/
│   ├── en.json
│   ├── pt.json
│   └── es.json
├── tests/
│   ├── test_key_input.py
│   ├── test_package_selection.py
│   ├── test_progressive_loading.py
│   └── test_uninstall.py
├── docs/
│   ├── README.md
│   └── CHANGELOG.md
├── AGENTS.md
└── package-lock.json
```

See `docs/CHANGELOG.md` for the history of changes.

---

## How It Works

### Data collection

The app collects:

- `npm list --depth=0 --json` for local packages
- `npm list -g --depth=0 --json` for global packages
- `npm outdated --depth=0 --json` for local outdated packages
- `npm outdated -g --depth=0 --json` for global outdated packages

Hidden/private packages whose names start with `.` are filtered out.

If `npm list` or `npm outdated` returns invalid or empty JSON — or times out — the app falls back to an empty result instead of crashing. A failed listing or update check is shown as unknown and disables package updates until a successful refresh. On timeouts a warning is shown.

After both installed-package listings finish, the table appears with update-check and size states marked as pending. Update versions and sizes fill in as their background tasks finish. The `q` key remains available during collection; refresh requests wait for the current npm queries to finish before starting another cycle.

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
- runs them as one task list with per-row scope tags (`[L]`/`[G]`), locals first
- reports success only if the underlying `npm update` command returns exit code `0`
- lists every failed package at the end plus a failure message if one or more update commands fail or time out

---

## Usage

Run the script from the repository root:

```bash
python main.py
```

### Demo mode (fictitious data)

Preview the interface without touching npm:

```bash
python main.py --test
```

- Shows 10 fictitious packages: 4 up to date, 5 needing update, 1 (`left-pad`) that fails with `[x]`
- Package actions are simulated (~0.4s each) — no real npm commands run, no files change
- Combines with `--no-color`; language selection still appears first

### Language Selection

Quick language selection with instant input (single keypress, no Enter):

- Press `1` for English (default)
- Press `2` for Português
- Press `3` for Español
- Press `Enter` alone selects English (default)

Without a TTY (piped input), language defaults to English without prompting.

Note:

- If you run the tool outside a Node.js project, the local package section will usually be empty.
- Global packages are still shown if npm can resolve the global install root.

---

## Table Columns

| Column | Meaning |
| --- | --- |
| `STATUS` | `[ok]` when current, `[update]` when any scope is outdated, `[checking]` or `[unknown]` while update status is pending or unavailable |
| `#` | Numeric identifier used to select one package |
| `PACKAGE` | Package name |
| `GLOBAL_VERSION` | Installed global version |
| `GLOBAL_NEW` | Latest version available for the global install |
| `LOCAL_VERSION` | Installed local version |
| `LOCAL_NEW` | Latest version available for the local install |
| `SIZE` | Combined size view for local/global installs |

STATUS is the first column in every display mode, before the package number.
In compact mode (60-79 columns), installed and available versions are combined
as `1.2.3 -> 1.3.0`.

---

## Controls

| Key | Action |
| --- | --- |
| `a` | Update all outdated packages with `(y/N)` confirmation (instant) |
| `o` | Select packages by number (instant, then type numbers + Enter) |
| `u` | Uninstall one package with two confirmations (instant) |
| `1-9` | Direct number/list input, separated by commas + Enter |
| `r` | Refresh package list (instant, no Enter needed) |
| `q` | Exit (instant, no Enter needed) |

Arrow keys, Delete, End, PageUp/PageDown, function keys and a stray `Enter` are silently ignored everywhere — they never trigger actions or errors.

### Instant Keyboard Controls

Menu actions use single-key input - just press the key without needing to hit Enter:

- Press `a` to ask for confirmation before updating all outdated packages
- Press `o` to immediately enter package selection mode
- Press `u` to enter single-package uninstall mode
- Press `r` to immediately refresh the package list
- Press `q` to immediately exit

Package selection (via `o` or direct number input) requires Enter to submit.
Enter multiple package numbers separated by commas, such as `1,3,5,6`.
Backspace edits the current input before it is submitted.

### Direct Number Input

You can type a package number directly at the main menu without pressing `o` first:

- Type `3` + `Enter` to update package #3
- Type `1` + `0` + `Enter` to update package #10
- Type `1,3,5` + `Enter` to update only packages #1, #3, and #5
- Invalid numbers show an error message

### Update all

Press `a` to update every outdated package. The app asks for confirmation (`(y/N)`, default `N`) before proceeding.

The app:

- updates outdated local packages first, then global ones
- executes only the required `npm update` commands
- refetches the package list once when finished

### Update selected packages

Press `o`, then enter one or more package numbers shown in the first column,
separated by commas. You can also type the first number directly at the menu.

For each selected package, the app updates only its outdated scope(s):

- local only
- global only
- or both

- A single selected package that is already current shows an "already updated" message.
- Invalid selections are rejected before any package update starts.

### Uninstall one package

Press `u`, enter one package number, confirm with `y`, then type the exact
package name. Any other first response or a name mismatch cancels the action.

- Local installations use `npm uninstall <name>`; global installations use
  `npm uninstall -g <name>`.
- If the selected package exists in both scopes, the local installation is
  removed first. Refresh the list and repeat to remove its global installation.
- A failed inventory check blocks uninstalling because the package scope cannot
  be verified. After a real npm attempt, the list is refreshed to show its state.
- Demo mode simulates the command and removes the selected scope from its
  fictitious table only.

### Refresh

Press `r` to force a refresh of the package list:

- Keeps cached sizes (keyed by scope, name and version — unchanged packages are not remeasured)
- Re-detects terminal dimensions
- Reloads package data from npm
- Re-renders the table with current information

Without `r`, data is reused automatically and only refetched after an update or uninstall, or when older than the TTL (`NPM_PM_TTL`, default 120s).

Use `r` when you've installed/uninstalled packages externally and want to see updated data.

---

## Responsive UI

The interface automatically adapts to your terminal size, providing an optimal viewing experience on any screen:

### Display Modes

The table layout changes based on terminal width:

| Mode | Terminal Width | Behavior |
| --- | --- | --- |
| **Full** | ≥80 columns | Complete table with STATUS first, then package number and all package columns |
| **Compact** | 60-79 columns | STATUS and package number first, followed by combined versions |
| **Ultra-Compact** | <60 columns | Vertical cards with STATUS before the package number |

### Smart Features

- **Automatic detection**: Terminal dimensions are detected on startup and every refresh
- **Dynamic resizing**: Table re-renders automatically when terminal is resized
- **Smart truncation**: Long package names are truncated with `...` to fit available space
- **Calm color**: color is used only for status labels; everything else stays default
- **No-color support**: `NO_COLOR=1`, `--no-color`, `TERM=dumb`, or piped output disables all ANSI codes
- **ASCII fallback**: `NPM_PM_ASCII=1` or non-UTF8 terminals use `-`, `->`, `[ok]` instead of `─`, `→`, `✓`

This ensures the tool works comfortably on small laptop terminals, large desktop screens, and everything in between.

---

## Progress Feedback

During package updates, a visual progress indicator keeps you informed:

### Progress Bar

```
[████████░░░░░░░░] 3/7 (43%)
Updating package: LOCAL: commander
Next: express
────────────────────────────────
[ok] [L] axios
[ok] [L] chalk
[>]  [L] commander
[ ]  [L] express
... 3 more below
```

- **Pinned bar**: in interactive terminals a single bar stays at the top and updates in place — no repeated bars
- **Viewport list**: one row per package (`[L]`/`[G]` scope + name only); done show `[ok]`, current `[>]`, pending `[ ]`, failed `[x]`
- **No scrolling**: the list is a window centered on the current package sized to your terminal height, with `... N more above/below` indicators when it doesn't all fit
- **Piped output**: without a TTY each step is logged sequentially instead (same info, no cursor codes)

Components:

- **Visual bar**: thin block bar (`█`/`░`, ASCII `=`/`-` fallback) sized to the terminal
- **Counter**: `[X/Y]` displays current package out of total
- **Percentage**: Numeric percentage for precise tracking
- **Current package**: Shows which package is being updated
- **Next package**: Preview of what's coming next (muted)

A spinner is shown while npm data is being collected and on the current
package line (`SCOPE: name`) while each update or uninstall command runs,
so the screen never looks frozen. Without a TTY the spinner degrades to a
single `SCOPE: name...` line per package instead of animating.

### Status Symbols

- `[ok]` (green) - up to date / update succeeded
- `[update]` (yellow) - needs update
- `[>]` (yellow) - package currently updating
- `[ ]` (muted) - pending in the update queue
- `[!]` (yellow) - warning (invalid input, narrow terminal, demo mode, npm timeout)
- `[x]` (red) - update failed

This feedback system provides clear visibility into the update process, making it easy to track progress and identify any issues.

---

## Cross-Platform Compatibility

The application runs seamlessly on Windows, Linux, and macOS with automatic platform detection:

### Platform-Specific Optimizations

**Windows:**
- Uses `msvcrt` for keyboard input handling, comparing raw bytes so arrow/function keys (which arrive as prefix + scan code) are discarded instead of leaking as letters
- npm commands executed with `shell=True` for proper PATH resolution
- ANSI escape codes handled correctly for progress indicators (VT mode enabled; graceful fallback without it)

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

- Invalid menu input shows an `invalid option` message with a short pause (arrows/special keys are ignored silently and never reach this path)
- Invalid package selections show an `invalid number` message with a short pause
- Backspace edits the current package selection without leaving visual artifacts
- Invalid JSON from npm list/outdated becomes an empty result
- npm commands that exceed their timeout fail soft (empty result / `False`) with an `npm_timeout` warning; update timeouts are also listed as failed packages
- Failed update commands are listed by name plus `update_failed`
- Unicode fallbacks (ASCII) prevent crashes on Windows terminals with legacy code pages
- Graceful fallback when terminal size detection fails
- Update All and uninstall confirmations cancel on any key other than `y`
- Failed key polling never falls back to a blocking read; outside a TTY input degrades safely (language defaults to English)
- Uninstall requires the exact package name and blocks when inventory failed

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

### Locale Keys (75 per file)

All user-facing strings including table headers, menu options, progress bar labels, error messages, demo/viewport labels, and confirmation prompts. Keep the three files in sync — every `t()` key must exist in all of them.

---

## Limitations

- There is no test framework; run the focused checks with `python tests/test_key_input.py`, `python tests/test_package_selection.py`, `python tests/test_progressive_loading.py`, and `python tests/test_uninstall.py`
- Size calculation still depends on filesystem traversal, so very large package trees can take noticeable time to finish; the package list remains usable while sizes are measured
- `npm outdated` needs network access to check the registry; without it the outdated columns stay empty
- The tool assumes `npm` commands are available in the current shell environment

---

## License

MIT
