#!/usr/bin/env python3
import subprocess
import json
import os
import sys
import time


# =====================================================
# CONFIG
# =====================================================
LOCALES_DIR = "locales"
LANG = "en"
STRINGS = {}

# =====================================================
# I18N
# =====================================================
def load_language():
    global LANG, STRINGS

    print("Select language / Selecione idioma / Seleccione idioma")
    print("1. English")
    print("2. Português")
    print("3. Español")

    choice = input("> ").strip()
    mapping = {"1": "en", "2": "pt", "3": "es"}
    LANG = mapping.get(choice, "en")

    path = os.path.join(LOCALES_DIR, f"{LANG}.json")

    if not os.path.exists(path):
        print(f"Missing locale file: {path}")
        sys.exit(1)

    with open(path, "r", encoding="utf-8") as f:
        STRINGS = json.load(f)


def t(key):
    return STRINGS.get(key, key)


# =====================================================
# TERMINAL
# =====================================================
def clear():
    os.system("cls" if os.name == "nt" else "clear")


# =====================================================
# NPM HELPERS
# =====================================================
def run(cmd):
    result = subprocess.run(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
        shell=True,
    )
    return result.stdout.strip()


def npm_list(global_mode=False):
    cmd = "npm list --depth=0 --json"
    if global_mode:
        cmd = "npm list -g --depth=0 --json"

    output = run(cmd)
    if not output:
        return {}

    data = json.loads(output)
    deps = data.get("dependencies", {})
    
    # Filter out hidden/private packages (starting with .)
    return {name: info for name, info in deps.items() if not name.startswith(".")}


def npm_outdated(global_mode=False):
    cmd = "npm outdated --json"
    if global_mode:
        cmd = "npm outdated -g --depth=0 --json"

    output = run(cmd)
    if not output:
        return {}

    try:
        data = json.loads(output)
        # Filter out hidden/private packages (starting with .)
        return {name: info for name, info in data.items() if not name.startswith(".")}
    except Exception:
        return {}


# =====================================================
# SIZE
# =====================================================
def human_size(size):
    for unit in ["B", "KB", "MB", "GB"]:
        if size < 1024:
            return f"{size:.1f}{unit}"
        size /= 1024
    return f"{size:.1f}TB"


def get_pkg_size(name, global_mode=False):
    try:
        base = run("npm root -g") if global_mode else "node_modules"
        path = os.path.join(base, name)

        total = 0
        for root, _, files in os.walk(path):
            for f in files:
                fp = os.path.join(root, f)
                if os.path.exists(fp):
                    total += os.path.getsize(fp)

        return human_size(total)
    except Exception:
        return "-"


# =====================================================
# TABLE
# =====================================================
def build_rows(local, global_, outdated_local, outdated_global):
    names = sorted(set(local) | set(global_))
    rows = []

    for i, name in enumerate(names, start=1):

        lver = local.get(name, {}).get("version", "")
        gver = global_.get(name, {}).get("version", "")

        lnew = outdated_local.get(name, {}).get("latest", "")
        gnew = outdated_global.get(name, {}).get("latest", "")

        rows.append(
            {
                "id": i,
                "name": name,
                "lver": lver,
                "gver": gver,
                "lnew": lnew,
                "gnew": gnew,
                "lsize": get_pkg_size(name, False) if name in local else "",
                "gsize": get_pkg_size(name, True) if name in global_ else "",
                "local_outdated": name in outdated_local,
                "global_outdated": name in outdated_global,
            }
        )

    return rows


def mark(text, outdated):
    if not text:
        return ""
    return f"{text} (u)" if outdated else text


def print_table(rows):
    headers = [
        "#",
        t("package"),
        t("local_version"),
        t("local_new"),
        t("local_size"),
        t("global_version"),
        t("global_new"),
        t("global_size"),
    ]

    widths = [5, 28, 14, 14, 12, 14, 14, 12]

    print("\n" + t("packages_title") + "\n")

    for h, w in zip(headers, widths):
        print(h.ljust(w), end="")
    print()

    print("-" * sum(widths))

    for r in rows:
        print(str(r["id"]).ljust(widths[0]), end="")
        print(r["name"][:27].ljust(widths[1]), end="")
        print(mark(r["lver"], r["local_outdated"]).ljust(widths[2]), end="")
        print(r["lnew"].ljust(widths[3]), end="")
        print(r["lsize"].ljust(widths[4]), end="")
        print(mark(r["gver"], r["global_outdated"]).ljust(widths[5]), end="")
        print(r["gnew"].ljust(widths[6]), end="")
        print(r["gsize"].ljust(widths[7]))


# =====================================================
# UPDATE
# =====================================================
def update_all(rows):
    any_update = any(r["local_outdated"] or r["global_outdated"] for r in rows)

    if not any_update:
        input("\n" + t("nothing_to_update"))
        return

    print("\n" + t("updating_local"))
    os.system("npm update")

    print("\n" + t("updating_global"))
    os.system("npm update -g")

    input("\n" + t("update_done"))


def update_one(row):
    if not row["local_outdated"] and not row["global_outdated"]:
        input("\n" + t("already_updated"))
        return

    name = row["name"]

    if row["local_outdated"]:
        print(f"\n{t('updating_local_pkg')} {name}")
        os.system(f"npm update {name}")

    if row["global_outdated"]:
        print(f"\n{t('updating_global_pkg')} {name}")
        os.system(f"npm update -g {name}")

    input("\n" + t("update_done"))


# =====================================================
# DATA REFRESH
# =====================================================
def collect_rows():
    local_pkgs = npm_list(False)
    global_pkgs = npm_list(True)
    outdated_local = npm_outdated(False)
    outdated_global = npm_outdated(True)

    return build_rows(local_pkgs, global_pkgs, outdated_local, outdated_global)


# =====================================================
# MAIN LOOP
# =====================================================
def main():
    load_language()
    delay = 2

    while True:
        clear()
        print(t("collecting_data"))

        rows = collect_rows()

        clear()
        print_table(rows)

        print("\n(u) =", t("needs_update"))
        print("\n" + t("options"))
        print("[a]", t("update_all"))
        print("[o]", t("update_one"))
        print("[q]", t("exit"))

        choice = input("\n" + t("choose") + " ").strip().lower()

        if choice == "q":
            break

        elif choice == "a":
            update_all(rows)

        elif choice == "o":
            try:
                num = int(input(t("enter_number") + " ").strip())
                row = next(r for r in rows if r["id"] == num)
                update_one(row)
            except Exception:
                print(t("invalid_number"))
                time.sleep(delay)
        else:
            print(t("invalid_option"))
            time.sleep(delay)


if __name__ == "__main__":
    main()