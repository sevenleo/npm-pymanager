#!/usr/bin/env python3
import subprocess
import json
import os
import sys
import time
import shutil
import tty
import termios
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
TERMINAL_SIZE_CACHE = None

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
# TERMINAL SIZE & UI HELPERS
# =====================================================
def get_terminal_size():
    """
    Detecta largura e altura do terminal.
    Retorna: tuple (width, height)
    Fallback: (80, 24) se detecção falhar
    """
    global TERMINAL_SIZE_CACHE
    
    if TERMINAL_SIZE_CACHE is not None:
        return TERMINAL_SIZE_CACHE
    
    try:
        size = os.get_terminal_size()
        TERMINAL_SIZE_CACHE = (size.columns, size.lines)
        return TERMINAL_SIZE_CACHE
    except OSError:
        # Fallback para variáveis de ambiente
        width = int(os.environ.get("COLUMNS", 80))
        height = int(os.environ.get("LINES", 24))
        TERMINAL_SIZE_CACHE = (width, height)
        return TERMINAL_SIZE_CACHE


def reset_terminal_cache():
    """Reseta o cache do tamanho do terminal para forçar nova detecção."""
    global TERMINAL_SIZE_CACHE
    TERMINAL_SIZE_CACHE = None


def getch():
    """
    Lê um único caractere do teclado sem precisar pressionar Enter.
    Funciona em terminais Unix/Linux/Mac.
    """
    fd = sys.stdin.fileno()
    old_settings = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        ch = sys.stdin.read(1)
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
    return ch


def truncate_string(text, max_width, mode="end"):
    """
    Trunca string para caber na largura máxima.
    
    Args:
        text: texto a ser truncado
        max_width: largura máxima permitida
        mode: 'end' (final truncado), 'middle' (meio truncado), 'start' (início truncado)
    
    Returns:
        texto truncado com indicador visual (...)
    """
    if not text or len(text) <= max_width:
        return text
    
    if max_width <= 3:
        return text[:max_width]
    
    indicator = "..."
    content_width = max_width - len(indicator)
    
    if mode == "end":
        return text[:content_width] + indicator
    elif mode == "middle":
        half = content_width // 2
        return text[:half] + indicator + text[-(content_width - half):]
    elif mode == "start":
        return indicator + text[-content_width:]
    else:
        return text[:max_width - 3] + indicator


def print_separator(width, style="single"):
    """
    Imprime separador visual.
    
    Args:
        width: largura do separador
        style: 'single', 'double', 'bold', 'dashed'
    """
    styles = {
        "single": "-",
        "double": "=",
        "bold": "█",
        "dashed": "- ",
    }
    char = styles.get(style, "-")
    print(char * width)


def format_with_placeholders(text, **kwargs):
    """
    Formata texto com placeholders {key}.
    Se a chave não existir, mantém o placeholder original.
    """
    result = text
    for key, value in kwargs.items():
        result = result.replace("{" + key + "}", str(value))
    return result


# =====================================================
# TERMINAL
# =====================================================
def clear():
    os.system("cls" if os.name == "nt" else "clear")


def print_header(rows, terminal_width):
    """
    Imprime apenas o título centralizado.
    """
    title = t("packages_title")
    print(f"\n{title}")
    print()


def show_progress(current, total, package_name, next_package=None, prefix=""):
    """
    Exibe barra de progresso e informações do pacote atual.
    
    Args:
        current: índice atual (1-based)
        total: total de pacotes
        package_name: nome do pacote sendo atualizado
        next_package: nome do próximo pacote (opcional)
        prefix: prefixo para a linha (ex: "LOCAL", "GLOBAL")
    """
    percent = (current / total) * 100 if total > 0 else 0
    bar_width = 20
    filled = int(bar_width * current / total) if total > 0 else 0
    bar = "=" * filled + ">" + " " * (bar_width - filled - 1) if filled < bar_width else "=" * bar_width
    
    # Linha de progresso principal
    progress_text = format_with_placeholders(t("progress"), current=current, total=total)
    print(f"\n  [{bar}] {current}/{total} ({percent:.0f}%)")
    
    # Pacote atual
    prefix_str = f"{prefix}: " if prefix else ""
    print(f"  {t('updating_package')}: {prefix_str}{package_name}")
    
    # Próximo pacote
    if next_package:
        print(f"  {t('next_package')}: {next_package}")
    elif current == total:
        print(f"  {t('update_processing')}")


def calculate_column_widths(terminal_width, rows, headers):
    """
    Calcula larguras ótimas para cada coluna baseado no espaço disponível.
    
    Args:
        terminal_width: largura total do terminal
        rows: lista de dicionários com dados dos pacotes
        headers: lista de cabeçalhos das colunas
    
    Returns:
        lista de larguras para cada coluna
    """
    num_cols = len(headers)
    
    # Larguras mínimas por coluna
    min_widths = [5, 12, 10, 10, 10, 10, 8]
    
    # Espaço disponível (subtraindo margens e separadores)
    margin = 4  # margem lateral
    separator_space = num_cols - 1  # espaços entre colunas
    available_width = terminal_width - margin * 2 - separator_space
    
    if available_width < sum(min_widths):
        # Terminal muito estreito - usa larguras mínimas
        return min_widths
    
    # Calcula largura máxima necessária para cada coluna baseado nos dados
    max_needed = []
    for i, header in enumerate(headers):
        max_len = len(header)
        for row in rows[:50]:  # amostra dos primeiros 50 pacotes
            if i == 0:  # coluna #
                val = str(row.get("id", ""))
            elif i == 1:  # coluna PACKAGE
                val = row.get("name", "")
            elif i == 2:  # GLOBAL_VERSION
                val = row.get("gver", "")
                if row.get("global_outdated"):
                    val += " (u)"
            elif i == 3:  # GLOBAL_NEW
                val = row.get("gnew", "")
            elif i == 4:  # LOCAL_VERSION
                val = row.get("lver", "")
                if row.get("local_outdated"):
                    val += " (u)"
            elif i == 5:  # LOCAL_NEW
                val = row.get("lnew", "")
            elif i == 6:  # SIZE
                val = row.get("size", "")
            max_len = max(max_len, len(val))
        max_needed.append(min(max_len, 20))  # limita a 20 caracteres
    
    # Distribui espaço extra proporcionalmente
    total_needed = sum(max(min_widths[i], max_needed[i]) for i in range(num_cols))
    extra_space = available_width - total_needed
    
    widths = []
    for i in range(num_cols):
        base_width = max(min_widths[i], max_needed[i])
        # Coluna PACKAGE recebe mais espaço extra
        if i == 1:
            widths.append(base_width + extra_space)
        else:
            widths.append(base_width)
    
    return widths


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


def print_table_responsive(rows, terminal_width=None):
    """
    Imprime tabela adaptada ao tamanho do terminal.
    
    Comportamento:
        - >= 100 colunas: tabela completa
        - 80-99 colunas: tabela padrão
        - 60-79 colunas: modo compacto (remove coluna SIZE)
        - < 60 colunas: modo ultra-compacto (lista vertical)
    """
    if terminal_width is None:
        terminal_width, _ = get_terminal_size()
    
    headers = [
        "#",
        t("package"),
        t("global_version"),
        t("global_new"),
        t("local_version"),
        t("local_new"),
        t("size"),
    ]
    
    # Calcula larguras dinâmicas
    widths = calculate_column_widths(terminal_width, rows, headers)
    
    # Determina modo de exibição
    if terminal_width < 60:
        _print_table_ultra_compact(rows, terminal_width)
        return
    elif terminal_width < 80:
        # Modo compacto: remove coluna SIZE
        headers = headers[:6]
        widths = widths[:6]
        for i, row in enumerate(rows):
            rows[i] = {**row, "size": ""}
    
    # Imprime cabeçalho da tabela
    if terminal_width < 80:
        print(f"  [{t('compact_mode')}]")
    print()
    
    # Imprime cabeçalhos
    header_line = ""
    for i, (h, w) in enumerate(zip(headers, widths)):
        if i == 0:
            header_line += h.ljust(w)
        else:
            header_line += " " + h.ljust(w - 1)
    print(header_line)
    
    print_separator(sum(widths), "single")
    
    # Imprime linhas
    for r in rows:
        line = ""
        values = [
            str(r["id"]),
            truncate_string(r["name"], widths[1], mode="middle"),
            mark(r["gver"], r["global_outdated"]),
            r["gnew"],
            mark(r["lver"], r["local_outdated"]),
            r["lnew"],
            r["size"],
        ]
        
        # Ajusta para o número de colunas atual
        values = values[:len(headers)]
        widths_current = widths[:len(headers)]
        
        for i, (val, w) in enumerate(zip(values, widths_current)):
            if i == 0:
                line += val.ljust(w)
            else:
                line += " " + val.ljust(w - 1)
        print(line)


def _print_table_ultra_compact(rows, terminal_width):
    """
    Imprime tabela em modo ultra-compacto (lista vertical) para terminais < 60 colunas.
    """
    print(f"  [{t('compact_mode')}]")
    if terminal_width < 40:
        print(f"  ⚠️  {t('screen_too_small')}")
    print()
    
    for r in rows:
        print_separator(min(terminal_width, 60), "dashed")
        print(f"  #{r['id']} {truncate_string(r['name'], 30, mode='middle')}")
        
        if r["gver"] or r["gnew"]:
            g_status = "(u)" if r["global_outdated"] else "✓"
            g_ver = r["gver"] or "-"
            g_new = f" -> {r['gnew']}" if r["gnew"] else ""
            print(f"     G: {g_status} {g_ver}{g_new}")
        
        if r["lver"] or r["lnew"]:
            l_status = "(u)" if r["local_outdated"] else "✓"
            l_ver = r["lver"] or "-"
            l_new = f" -> {r['lnew']}" if r["lnew"] else ""
            print(f"     L: {l_status} {l_ver}{l_new}")
        
        if r["size"]:
            print(f"     SIZE: {r['size']}")
        print()


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
    total_local = len(local_to_update)
    total_global = len(global_to_update)
    total = total_local + total_global

    # Update local packages
    if local_to_update:
        print("\n" + t("updating_local"))
        for i, name in enumerate(local_to_update, start=1):
            next_pkg = local_to_update[i] if i < len(local_to_update) else None
            if total_global > 0 and i == len(local_to_update):
                next_pkg = global_to_update[0]
            
            reset_terminal_cache()  # força atualização do cache
            show_progress(i, total, name, next_package=next_pkg, prefix="LOCAL")
            
            result = subprocess.run(["npm", "update", name])
            if result.returncode != 0:
                all_ok = False
                print(f"    {t('update_failed_symbol')} {name}")
            else:
                print(f"    {t('update_success')} {name}")

    # Update global packages
    if global_to_update:
        print("\n" + t("updating_global"))
        for i, name in enumerate(global_to_update, start=1):
            next_pkg = global_to_update[i] if i < len(global_to_update) else None
            actual_index = total_local + i
            
            reset_terminal_cache()  # força atualização do cache
            show_progress(actual_index, total, name, next_package=next_pkg, prefix="GLOBAL")
            
            result = subprocess.run(["npm", "update", "-g", name])
            if result.returncode != 0:
                all_ok = False
                print(f"    {t('update_failed_symbol')} {name}")
            else:
                print(f"    {t('update_success')} {name}")

    print("\n" + t("update_done" if all_ok else "update_failed"))
    time.sleep(DELAY)


def update_one(row):
    if not row["local_outdated"] and not row["global_outdated"]:
        print("\n" + t("already_updated"))
        time.sleep(DELAY)
        return

    name = row["name"]
    all_ok = True
    total = 0
    current = 0
    
    if row["local_outdated"]:
        total += 1
    if row["global_outdated"]:
        total += 1

    if row["local_outdated"]:
        current += 1
        next_pkg = name if row["global_outdated"] else None
        reset_terminal_cache()
        show_progress(current, total, name, next_package=next_pkg, prefix="LOCAL")
        
        result = subprocess.run(["npm", "update", name])
        if result.returncode != 0:
            all_ok = False
            print(f"    {t('update_failed_symbol')} {name}")
        else:
            print(f"    {t('update_success')} {name}")

    if row["global_outdated"]:
        current += 1
        reset_terminal_cache()
        show_progress(current, total, name, next_package=None, prefix="GLOBAL")
        
        result = subprocess.run(["npm", "update", "-g", name])
        if result.returncode != 0:
            all_ok = False
            print(f"    {t('update_failed_symbol')} {name}")
        else:
            print(f"    {t('update_success')} {name}")

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
        
        # Imprime cabeçalho informativo
        terminal_width, _ = get_terminal_size()
        print_header(rows, terminal_width)
        
        # Imprime tabela responsiva
        print_table_responsive(rows, terminal_width)

        print("\n(u) =", t("needs_update"))
        print("\n" + t("options"))
        print("[a]", t("update_all"))
        print("[o]", t("update_one"))
        print("[q]", t("exit"))

        print("\n" + t("choose") + " ", end="", flush=True)
        choice = getch().strip().lower()
        print(choice)  # ecoa a tecla pressionada

        if choice == "q":
            break

        elif choice == "a":
            update_all(rows)

        elif choice == "o":
            print(t("enter_number") + " ", end="", flush=True)
            num_str = ""
            while True:
                ch = getch()
                if ch == "\n" or ch == "\r":
                    break
                print(ch, end="", flush=True)
                num_str += ch
            print()
            
            try:
                num = int(num_str.strip())
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
