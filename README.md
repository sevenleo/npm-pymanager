# NPM Package Manager TUI (Python)

> A lightweight terminal-based NPM package manager written in Python that allows you to visualize, compare, and update local and global npm packages from a single interactive interface.

This tool simplifies maintenance of npm environments by providing a clear overview of installed packages, update status, versions, and disk usage — all inside one screen.

---

## ✨ Features

### 📦 Package Visualization

- Displays **local** and **global** npm packages side-by-side
- Automatically merges both lists into a single table
- Each package receives a numeric identifier for quick selection
- Filters out hidden/private packages (starting with `.`)

**Table columns (in order):**

| Column | Description |
|--------|-------------|
| `#` | Package identifier number |
| `PACKAGE` | Package name |
| `GLOBAL_VERSION` | Installed global version |
| `GLOBAL_UPDATE` | Latest available global version |
| `LOCAL_VERSION` | Installed local version |
| `LOCAL_UPDATE` | Latest available local version |
| `SIZE` | Combined disk usage (shows global, local, or both with `(G)` / `(L)` labels) |

**Size column behavior:**
- Only global: `15.2MB`
- Only local: `8.5KB`
- Both: `15.2MB(G) 8.5KB(L)`

Packages requiring updates are marked with: **(u)**

---

### 🔄 Update Management

#### Update All Packages (Optimized)

Press **`A`** to update:
- Only packages that are actually outdated (local and/or global)
- Shows list of packages before updating
- Skips already up-to-date packages automatically

**Efficiency:**
- Does not run unnecessary npm commands
- Displays which packages will be updated
- Processes local and global updates separately

#### Update a Single Package

Press **`o`**, then enter the package number shown in the table.

**Behavior:**
- Updates only outdated targets (local and/or global)
- Prevents updating packages already up to date
- Shows feedback for each update operation

---

### 🔄 Automatic Refresh

After any update operation:

1. Package data is recollected
2. Table is rebuilt
3. Screen refreshes automatically
4. Returns to selection menu

**No restart required.**

---

### 🌍 Multi-Language Support (i18n)

At startup, the user selects a language:

1. **English**
2. **Portuguese**
3. **Spanish**

All interface text is loaded dynamically from JSON locale files.

**Locale structure:**

```
locales/
├── en.json
├── pt.json
└── es.json
```

Adding a new language only requires creating another JSON file.

---

### ✅ Smart Validation

The application:

- Runs in a continuous loop
- Rejects invalid options
- Prevents invalid updates
- Displays informative messages
- Never exits unexpectedly due to input errors
- Filters out invalid npm packages (hidden packages starting with `.`)

---

### 📏 Package Size Detection

The script calculates installed package size by scanning:

- `node_modules/` (local)
- Global npm directories

Sizes are displayed in human-readable format: **B / KB / MB / GB**

**Combined size column:**
- Shows global size, local size, or both with labels `(G)` and `(L)`

---

### 💻 Terminal Experience

- Automatic screen clearing between actions
- Persistent interactive menu
- Clean aligned table layout
- Minimal dependencies (Python standard library only)

---

## 📁 Project Structure

```
project/
├── main.py
└── locales/
    ├── en.json
    ├── pt.json
    └── es.json
```

---

## 📋 Requirements

- **Python 3.8+**
- **Node.js**
- **npm** available in PATH

**Verify installation:**

```bash
node -v
npm -v
python --version
```

---

## 🚀 Usage

**Run the application:**

```bash
python main.py
```

Select your language and start managing packages.

---

## 🎮 Controls

| Key | Action |
|-----|--------|
| `t` | Update ALL packages (optimized - only outdated) |
| `o` | Update ONE package (local and/or global) |
| `q` | Exit program |

---

## 🔍 How Data is Collected

The script uses:

- `npm list --json` — Local packages (filtered: excludes hidden packages)
- `npm list -g --json` — Global packages (filtered: excludes hidden packages)
- `npm outdated --json` — Outdated packages (filtered: excludes hidden packages)
- Filesystem scanning — Package size

**No external Python libraries are required.**

---

## 🛡️ Safety Behavior

- Will not update already updated packages
- Warns when no updates are available
- Handles npm command failures gracefully
- Prevents crashes caused by invalid input
- Filters out invalid package names (starting with `.`)

---

## 🔧 Extensibility

Possible future improvements:

- [ ] Arrow-key navigation (Textual/Rich TUI)
- [ ] Async npm calls
- [ ] Parallel size calculation
- [ ] Filtering/search
- [ ] Sorting columns
- [ ] Update preview (changelog view)
- [ ] Auto-update mode
- [ ] CLI flags support

---

## 📄 License

**MIT License** — free to use and modify.

---

## 🎯 Purpose

Provide a simple, transparent and efficient way to maintain npm environments without relying on heavy GUI tools or multiple commands.

**Ideal for developers managing multiple Node.js environments or maintaining shared systems.**
