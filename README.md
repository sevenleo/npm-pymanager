# NPM Package Manager TUI (Python)

> A lightweight terminal-based NPM package manager written in Python that allows you to visualize, compare, and update local and global npm packages from a single interactive interface.

This tool simplifies maintenance of npm environments by providing a clear overview of installed packages, update status, versions, and disk usage — all inside one screen.

---

## ✨ Features

### 📦 Package Visualization

- Displays **local** and **global** npm packages side-by-side
- Automatically merges both lists into a single table
- Each package receives a numeric identifier for quick selection

**Displayed information:**

| Column | Description |
|--------|-------------|
| `Package` | Package name |
| `Local Version` | Installed local version |
| `Local New` | Latest available version |
| `Local Size` | Disk usage of local package |
| `Global Version` | Installed global version |
| `Global New` | Latest available version |
| `Global Size` | Disk usage of global package |

Packages requiring updates are marked with: **(u)**

---

### 🔄 Update Management

#### Update All Packages

Press **`t`** to update:
- All outdated local packages
- All outdated global packages

If nothing requires updating, the system informs the user.

#### Update a Single Package

Press **`o`**, then enter the package number shown in the table.

**Behavior:**
- Updates only outdated targets
- Supports local and global updates automatically
- Prevents updating packages already up to date

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

---

### 📏 Package Size Detection

The script calculates installed package size by scanning:

- `node_modules/` (local)
- Global npm directories

Sizes are displayed in human-readable format: **B / KB / MB / GB**

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
| `t` | Update all packages |
| `o` | Update one package |
| `0` | Exit program |

---

## 🔍 How Data is Collected

The script uses:

- `npm list --json` — Local packages
- `npm list -g --json` — Global packages
- `npm outdated --json` — Outdated packages
- Filesystem scanning — Package size

**No external Python libraries are required.**

---

## 🛡️ Safety Behavior

- Will not update already updated packages
- Warns when no updates are available
- Handles npm command failures gracefully
- Prevents crashes caused by invalid input

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
