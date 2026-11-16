# CLI Mode — Concept Plan

> This document describes the planned CLI architecture for the next
> implementation. It is a design reference, not a promise that every command
> already exists in the current `main.py`.

The CLI must be a deterministic, single-run interface for scripts, terminals,
automation, and users who do not want the keyboard-driven TUI. It must share
the package and npm domain logic with interactive mode, but it must have its
own command dispatcher, validation rules, output contract, and exit lifecycle.

## 1. Goals

The new CLI should:

- execute one explicit operation and then exit;
- never open the interactive menu;
- never wait for an unrequested keypress;
- accept package names rather than table row numbers;
- distinguish local and global installations explicitly;
- print useful progress and final results in redirected terminals;
- return meaningful exit codes;
- keep destructive operations safe and intentional;
- reuse npm discovery, update, uninstall, timeout, and error-handling logic;
- remain usable on Windows, Linux, macOS, CI, and shell scripts.

## 2. Non-goals

The CLI should not:

- reproduce the interactive table or menu;
- depend on terminal cursor movement or ANSI escape codes;
- select packages by row number;
- perform fuzzy package-name matching;
- silently choose between local and global installations;
- bypass uninstall confirmation through `--yes` or `--force`;
- maintain a long-running refresh loop;
- mutate package data while merely listing it.

## 3. Relationship with interactive mode

Both modes use the same domain operations:

```text
package discovery
outdated-package discovery
scope resolution
package-size calculation
npm update execution
npm uninstall execution
timeouts and fail-soft error handling
localization
```

They must not share the same control loop.

| Concern | New CLI mode | Interactive mode |
| --- | --- | --- |
| Entry point | Explicit command-line action | No CLI action |
| Input | Parsed arguments and optional confirmation | Single-key menu controls |
| Display | Stable sequential text | Dynamic table and terminal redraw |
| Collection | One bounded collection per command | Background collection and refresh |
| Package selection | Exact package name | Table number or selection list |
| Update confirmation | Command policy | Menu confirmation |
| Uninstall confirmation | Always required | Existing multi-step confirmation |
| Refresh | Never automatic after exit | Manual, post-action, or TTL refresh |
| Lifecycle | One command, one result, exit | Runs until the user presses `q` |

The dispatcher should choose one mode before any collection starts:

```text
parse arguments
    |
    +-- help/version/errors -> print and exit
    |
    +-- explicit CLI command -> run one CLI command and exit
    |
    +-- no CLI command -> start interactive mode
```

An explicit CLI command must never fall through to `_interactive_loop()`.

## 4. Proposed command grammar

The canonical interface should use action-oriented commands while keeping
long options available for compatibility:

```bash
python main.py --help
python main.py --list
python main.py --update-all
python main.py --update <exact-package-name>
python main.py --uninstall <exact-package-name>
```

Scope is optional when a package exists in only one scope:

```bash
python main.py --update react --scope local
python main.py --uninstall lodash --scope global
```

The parser may also support the explicit form if compatibility requires it:

```bash
python main.py --update-one --package react --scope local
python main.py --uninstall --package lodash --scope global
```

The implementation must normalize both forms into one internal request:

```text
{
    action: "list" | "update_all" | "update_one" | "uninstall",
    package_name: string | None,
    scope: "LOCAL" | "GLOBAL" | None,
    assume_yes: bool
}
```

Unknown options, missing values, invalid scopes, and conflicting actions must
produce a usage error and must not start package collection.

## 5. Command behavior

### 5.1 `--help`

Print the complete command reference and exit successfully.

Requirements:

- no npm command;
- no package collection;
- no interactive prompt;
- output must work when redirected to a file.

### 5.2 `--list`

Collect package information once, print a stable text report, and exit.

The report should include:

- package name;
- local installed version, when present;
- global installed version, when present;
- available update, when present;
- scope;
- status;
- warnings for incomplete or timed-out checks.

`--list` must be read-only. It must never call `npm update` or
`npm uninstall`.

### 5.3 `--update-all`

Collect outdated packages once and update only packages that are outdated.

Suggested policy:

- local and global updates are separate tasks;
- an optional `--scope local|global` limits the operation;
- every task prints its package name and scope;
- all tasks finish before the final summary;
- one failed package does not hide the other failures;
- the process exits non-zero if any requested update fails.

`--yes` may be supported for update-all confirmation if the final design adds
a confirmation prompt. It must never change package selection or suppress
errors.

### 5.4 `--update <exact-package-name>`

Update one package by exact name.

Requirements:

- no substring or fuzzy matching;
- package names are case-sensitive according to npm naming rules;
- if the package is installed in both scopes and no scope was supplied,
  require `--scope` instead of guessing;
- if the exact package is not outdated in the selected scope, report that no
  update is needed;
- exit non-zero when the package is not found, the scope is ambiguous, or the
  npm command fails.

### 5.5 `--uninstall <exact-package-name>`

Uninstall one package by its exact package name.

This command is intentionally more restrictive than listing and updating:

1. The input must match the complete package name.
2. Partial names, substrings, row numbers, and fuzzy matches are rejected.
3. If the package exists in both scopes, `--scope local|global` is required.
4. The CLI must display the exact resolved target:

   ```text
   Package: lodash
   Scope: GLOBAL
   Action: uninstall
   ```

5. The CLI must ask for confirmation even when `--yes`, `--force`, or
   `--auto` is present:

   ```text
   Uninstall exactly "lodash" from GLOBAL? [y/N]:
   ```

6. Only an explicit `y` or `yes` proceeds. Empty input, `n`, `no`, EOF, and
   any other response cancel the operation.
7. Cancellation exits without calling `npm uninstall`.
8. A successful confirmation must still be followed by the normal npm
   timeout and exit-code checks.

The confirmation is a safety boundary, not a cosmetic prompt. It must remain
available when stdout is redirected, and the implementation must fail safely
when stdin is unavailable instead of assuming confirmation.

## 6. Exact package resolution

Package resolution should be a dedicated function used by update and
uninstall commands:

```text
resolve_package(name, requested_scope) -> resolved package or error
```

Resolution rules:

1. Reject an empty package name.
2. Match the complete name only.
3. Preserve npm names such as `@scope/package`.
4. Apply the requested scope when supplied.
5. If no scope is supplied:
   - use the only installed scope when there is one;
   - return an ambiguity error when both scopes exist;
   - return a not-found error when neither scope exists.
6. Never use a table row ID as a package selector.

The resolved object should contain the original package name, normalized scope,
installed version, available version, and the npm argument list. The command
handler should not rebuild this information independently.

## 7. Confirmation policy

Confirmation behavior must be explicit in the command policy:

| Operation | Default |
| --- | --- |
| `--list` | No confirmation |
| `--update-all` | Optional policy-controlled confirmation |
| `--update` | No confirmation unless policy enables it |
| `--uninstall` | Always confirm |
| `--help` | No confirmation |

`--force` and `--yes` must never be treated as permission to skip uninstall
confirmation. If a future automation mode needs unattended uninstall, it
should be a separately named, explicitly designed mechanism rather than a
side effect of a generic flag.

## 8. Output contract

CLI output should be sequential, readable, and safe to pipe:

```text
Collecting package information...
Found: lodash
Scope: GLOBAL
Installed: 4.17.21
Available: 4.17.22
Uninstall confirmation required.
Uninstall exactly "lodash" from GLOBAL? [y/N]: y
Uninstall completed: lodash (GLOBAL)
```

Recommended output rules:

- write normal results to stdout;
- write diagnostics and usage errors to stderr;
- avoid cursor movement and full-screen clearing;
- disable spinners when output is not a TTY;
- use localized messages through the existing translation system;
- do not hide npm failures behind a success-shaped message;
- include the package name and scope in every mutation result.

## 9. Exit codes

The new CLI should define stable exit codes:

| Code | Meaning |
| ---: | --- |
| `0` | Command completed successfully |
| `1` | npm operation failed |
| `2` | Invalid command-line usage |
| `3` | Package not found |
| `4` | Scope is ambiguous or invalid |
| `5` | Operation cancelled by the user |
| `6` | Collection or dependency check failed |
| `124` | Operation timed out |

The exact numeric values can be adjusted during implementation, but each
failure category must remain distinguishable for scripts.

## 10. Proposed internal architecture

The CLI should be implemented as small stages:

```text
argv
  -> parse_cli_args()
  -> validate_cli_request()
  -> collect_cli_data()
  -> resolve_cli_target()
  -> confirm_cli_operation()
  -> execute_cli_operation()
  -> render_cli_result()
  -> exit(code)
```

Suggested responsibilities:

- `parse_cli_args`: syntax only;
- `validate_cli_request`: action/argument combinations;
- `collect_cli_data`: one bounded package snapshot;
- `resolve_cli_target`: exact name and scope resolution;
- `confirm_cli_operation`: uninstall safety boundary;
- `execute_cli_operation`: call existing npm helpers;
- `render_cli_result`: stable text output;
- `main`: dispatch and process lifecycle only.

The interactive loop should call the same domain helpers but must not call CLI
renderers or CLI argument parsing.

## 11. Error handling

Errors must be explicit and actionable:

```text
Error: package "lod" was not found.
Hint: use the exact npm package name, such as "lodash".
```

The CLI must not:

- catch every exception and return success;
- treat an empty package result as a valid target;
- silently fall back from global to local;
- continue after a failed confirmation;
- report success when npm returned a non-zero exit code;
- enter interactive mode after a CLI validation error.

Timeouts, malformed npm JSON, missing npm, and failed commands should preserve
the project's existing fail-soft behavior while still producing a non-zero CLI
result when the requested operation cannot be trusted.

## 12. Migration plan

When rebuilding the CLI:

1. Preserve the existing interactive path unchanged.
2. Extract or reuse pure package-discovery and npm-command helpers.
3. Introduce a dedicated CLI request structure.
4. Add strict argument validation before collection.
5. Implement `--help` and `--list`.
6. Implement exact-name update resolution.
7. Implement exact-name uninstall resolution and mandatory confirmation.
8. Add stable exit codes and redirected-output behavior.
9. Add focused tests for parsing, resolution, confirmation, cancellation,
   failures, and command dispatch.
10. Run the existing interactive tests to ensure the CLI extraction did not
    change keyboard behavior.

## 13. Acceptance criteria

The new CLI is ready when:

- every documented command exits without opening the interactive menu;
- no command waits for an unrequested keypress;
- `--list` performs no mutation;
- update commands use exact package names and correct scopes;
- uninstall rejects partial names and row numbers;
- uninstall always asks for confirmation;
- `--yes` and `--force` cannot bypass uninstall confirmation;
- ambiguous local/global targets require an explicit scope;
- failures return non-zero and identify the package and scope;
- output remains readable when piped or redirected;
- interactive mode still works independently with no CLI action;
- focused CLI tests and the existing interactive tests pass.
