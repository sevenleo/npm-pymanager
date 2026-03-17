NPM Package Manager TUI (Python)

A lightweight terminal-based NPM package manager written in Python that allows you to visualize, compare, and update local and global npm packages from a single interactive interface.

This tool simplifies maintenance of npm environments by providing a clear overview of installed packages, update status, versions, and disk usage — all inside one screen.


==================================================
FEATURES
==================================================

PACKAGE VISUALIZATION

- Displays local and global npm packages side-by-side.
- Automatically merges both lists into a single table.
- Each package receives a numeric identifier for quick selection.

Displayed information includes:

Package            -> Package name
Local Version      -> Installed local version
Local New          -> Latest available version
Local Size         -> Disk usage of local package
Global Version     -> Installed global version
Global New         -> Latest available version
Global Size        -> Disk usage of global package

Packages requiring updates are marked with:

(u)


--------------------------------------------------
UPDATE MANAGEMENT
--------------------------------------------------

Update All Packages

Press:
t

Updates:
- all outdated local packages
- all outdated global packages

If nothing requires updating, the system informs the user.


Update a Single Package

Press:
o

Then enter the package number shown in the table.

Behavior:
- Updates only outdated targets.
- Supports local and global updates automatically.
- Prevents updating packages already up to date.


--------------------------------------------------
AUTOMATIC REFRESH
--------------------------------------------------

After any update operation:

- Package data is recollected
- Table is rebuilt
- Screen refreshes automatically
- Returns to selection menu

No restart required.


--------------------------------------------------
MULTI-LANGUAGE SUPPORT (i18n)
--------------------------------------------------

At startup, the user selects a language:

1. English
2. Portuguese
3. Spanish

All interface text is loaded dynamically from JSON locale files.

Locale structure:

locales/
 ├── en.json
 ├── pt.json
 └── es.json

Adding a new language only requires creating another JSON file.


--------------------------------------------------
SMART VALIDATION
--------------------------------------------------

The application:

- Runs in a continuous loop
- Rejects invalid options
- Prevents invalid updates
- Displays informative messages
- Never exits unexpectedly due to input errors


--------------------------------------------------
PACKAGE SIZE DETECTION
--------------------------------------------------

The script calculates installed package size by scanning:

node_modules/

and global npm directories.

Sizes are displayed in human-readable format:

B / KB / MB / GB


--------------------------------------------------
TERMINAL EXPERIENCE
--------------------------------------------------

- Automatic screen clearing between actions
- Persistent interactive menu
- Clean aligned table layout
- Minimal dependencies (Python standard library only)


==================================================
PROJECT STRUCTURE
==================================================

project/

├── main.py
└── locales/
    ├── en.json
    ├── pt.json
    └── es.json


==================================================
REQUIREMENTS
==================================================

- Python 3.8+
- Node.js
- npm available in PATH

Verify installation:

node -v
npm -v
python --version


==================================================
USAGE
==================================================

Run:

python main.py

Select language and start managing packages.


==================================================
CONTROLS
==================================================

t  -> Update all packages
o  -> Update one package
0  -> Exit program


==================================================
HOW DATA IS COLLECTED
==================================================

The script uses:

- npm list --json
- npm list -g --json
- npm outdated --json
- filesystem scanning for package size

No external Python libraries are required.


==================================================
SAFETY BEHAVIOR
==================================================

- Will not update already updated packages.
- Warns when no updates are available.
- Handles npm command failures gracefully.
- Prevents crashes caused by invalid input.


==================================================
EXTENSIBILITY
==================================================

Possible future improvements:

- Arrow-key navigation (Textual/Rich TUI)
- Async npm calls
- Parallel size calculation
- Filtering/search
- Sorting columns
- Update preview (changelog view)
- Auto-update mode
- CLI flags support


==================================================
LICENSE
==================================================

MIT License — free to use and modify.


==================================================
PURPOSE
==================================================

Provide a simple, transparent and efficient way to maintain npm environments without relying on heavy GUI tools or multiple commands.

Ideal for developers managing multiple Node.js environments or maintaining shared systems.