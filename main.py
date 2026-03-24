#!/usr/bin/env python3
import subprocess
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache


# =====================================================
# CONFIG
# =====================================================
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
LOCALES_DIR = os.path.join(SCRIPT_DIR, "locales")
LANG = "en"
STRINGS = {}
DELAY = 2
SIZE_CACHE = {}

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

    try:
        data = json.loads(output)
    except Exception:
        return {}

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


@lru_cache(maxsize=2)
def npm_root(global_mode=False):
    return run("npm root -g") if global_mode else "node_modules"


def get_pkg_size(name, global_mode=False, version=""):
    cache_key = (global_mode, name, version)
    cached_size = SIZE_CACHE.get(cache_key)
    if cached_size is not None:
        return cached_size

    try:
        base = npm_root(global_mode)
        path = os.path.join(base, name)

        if not os.path.isdir(path):
            SIZE_CACHE[cache_key] = ""
            return ""

        total = 0
        for root, _, files in os.walk(path):
            for f in files:
                fp = os.path.join(root, f)
                if os.path.exists(fp):
                    total += os.path.getsize(fp)

        size = human_size(total)
    except Exception:
        size = "-"

    SIZE_CACHE[cache_key] = size
    return size


def collect_sizes(local, global_, names):
    size_map = {}
    jobs = []

    for name in names:
        if name in local:
            jobs.append(("local", name, local.get(name, {}).get("version", "")))
        if name in global_:
            jobs.append(("global", name, global_.get(name, {}).get("version", "")))

    if not jobs:
        return size_map

    max_workers = min(8, len(jobs))
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            (scope, name): executor.submit(
                get_pkg_size,
                name,
                scope == "global",
                version,
            )
            for scope, name, version in jobs
        }

        for key, future in futures.items():
            size_map[key] = future.result()

    return size_map


# =====================================================
# TABLE
# =====================================================
def build_rows(local, global_, outdated_local, outdated_global):
    names = sorted(set(local) | set(global_))
    size_map = collect_sizes(local, global_, names)
    rows = []

    for i, name in enumerate(names, start=1):

        lver = local.get(name, {}).get("version", "")
        gver = global_.get(name, {}).get("version", "")

        lnew = outdated_local.get(name, {}).get("latest", "")
        gnew = outdated_global.get(name, {}).get("latest", "")

        lsize = size_map.get(("local", name), "")
        gsize = size_map.get(("global", name), "")

        # Single size column: show global if exists, else local, or both with labels
        if gsize and lsize:
            size_display = f"{gsize}(G) {lsize}(L)"
        elif gsize:
            size_display = gsize
        elif lsize:
            size_display = lsize
        else:
            size_display = ""

        rows.append(
            {
                "id": i,
                "name": name,
                "gver": gver,
                "gnew": gnew,
                "lver": lver,
                "lnew": lnew,
                "size": size_display,
                "global_outdated": name in outdated_global,
                "local_outdated": name in outdated_local,
            }
        )

    return rows


def mark(text, outdated):
    if not text:
        return ""
    return f"{text} (u)" if outdated else text


def run_update_command(args):
    result = subprocess.run(args)
    return result.returncode == 0


def print_table(rows):
    headers = [
        "#",
        t("package"),
        t("global_version"),
        t("global_new"),
        t("local_version"),
        t("local_new"),
        t("size"),
    ]

    widths = [5, 28, 14, 14, 14, 14, 20]

    print("\n" + t("packages_title") + "\n")

    for h, w in zip(headers, widths):
        print(h.ljust(w), end="")
    print()

    print("-" * sum(widths))

    for r in rows:
        print(str(r["id"]).ljust(widths[0]), end="")
        print(r["name"][:27].ljust(widths[1]), end="")
        print(mark(r["gver"], r["global_outdated"]).ljust(widths[2]), end="")
        print(r["gnew"].ljust(widths[3]), end="")
        print(mark(r["lver"], r["local_outdated"]).ljust(widths[4]), end="")
        print(r["lnew"].ljust(widths[5]), end="")
        print(r["size"].ljust(widths[6]))


# =====================================================
# UPDATE
# =====================================================
def update_all(rows):
    # Get only packages that need update
    local_to_update = [r["name"] for r in rows if r["local_outdated"]]
    global_to_update = [r["name"] for r in rows if r["global_outdated"]]

    if not local_to_update and not global_to_update:
        print("\n" + t("nothing_to_update"))
        time.sleep(DELAY)
        return

    all_ok = True

    # Update local packages
    if local_to_update:
        print("\n" + t("updating_local"))
        for name in local_to_update:
            print(f"  -> {name}")
        all_ok = run_update_command(["npm", "update", *local_to_update]) and all_ok

    # Update global packages
    if global_to_update:
        print("\n" + t("updating_global"))
        for name in global_to_update:
            print(f"  -> {name}")
        all_ok = run_update_command(["npm", "update", "-g", *global_to_update]) and all_ok

    print("\n" + t("update_done" if all_ok else "update_failed"))
    time.sleep(DELAY)


def update_one(row):
    if not row["local_outdated"] and not row["global_outdated"]:
        print("\n" + t("already_updated"))
        time.sleep(DELAY)
        return

    name = row["name"]
    all_ok = True

    if row["local_outdated"]:
        print(f"\n{t('updating_local_pkg')} {name}")
        all_ok = run_update_command(["npm", "update", name]) and all_ok

    if row["global_outdated"]:
        print(f"\n{t('updating_global_pkg')} {name}")
        all_ok = run_update_command(["npm", "update", "-g", name]) and all_ok

    print("\n" + t("update_done" if all_ok else "update_failed"))
    time.sleep(DELAY)


# =====================================================
# DATA REFRESH
# =====================================================
def collect_rows():
    # These npm calls are independent, so collect them concurrently.
    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = {
            "local": executor.submit(npm_list, False),
            "global": executor.submit(npm_list, True),
            "outdated_local": executor.submit(npm_outdated, False),
            "outdated_global": executor.submit(npm_outdated, True),
        }

        local_pkgs = futures["local"].result()
        global_pkgs = futures["global"].result()
        outdated_local = futures["outdated_local"].result()
        outdated_global = futures["outdated_global"].result()

    return build_rows(local_pkgs, global_pkgs, outdated_local, outdated_global)


# =====================================================
# MAIN LOOP
# =====================================================
def main():
    load_language()


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
            except (TypeError, ValueError, StopIteration):
                print(t("invalid_number"))
                time.sleep(DELAY)
                continue

            update_one(row)
        else:
            print(t("invalid_option"))
            time.sleep(DELAY)


if __name__ == "__main__":
    main()
