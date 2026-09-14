#!/usr/bin/env python3
import subprocess
import json
import os
import re
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache


# =====================================================
# PLATFORM COMPATIBILITY
# =====================================================
IS_WINDOWS = os.name == "nt"

if not IS_WINDOWS:
    import tty
    import termios


def _read_msvcrt_key(read_fn):
    """
    Lê uma tecla via msvcrt descartando prefixos de teclas especiais.

    O byte b'\\xe0' sozinho nao e UTF-8 valido: com errors='ignore' o
    decode o descartava e o teste de prefixo nunca casava, deixando o
    scan code seguinte vazar como letra (setas viravam k/p/m/h,
    End abria 'o', PgDn encerrava com 'q'). Comparar bytes crus evita
    isso. Funcao pura via read_fn injetavel para testes sem console.

    Args:
        read_fn: funcao sem args que retorna o proximo byte (ex: msvcrt.getch)

    Returns:
        caractere decodificado ou '' se tecla especial
    """
    raw = read_fn()
    if raw in (b'\xe0', b'\x00'):  # setas, Delete/End/PgUp/PgDn, F1-F12...
        read_fn()  # consome o scan code (K/P/M/H/S/O/Q/I...)
        return ''
    if isinstance(raw, bytes):
        return raw.decode('utf-8', errors='ignore')
    return raw or ''


def getch():
    """
    Lê um único caractere do teclado sem precisar pressionar Enter.
    Funciona em Windows, Linux e Mac.
    """
    if IS_WINDOWS:
        import msvcrt
        return _read_msvcrt_key(msvcrt.getch)
    else:
        fd = sys.stdin.fileno()
        old_settings = termios.tcgetattr(fd)
        try:
            tty.setraw(fd)
            ch = sys.stdin.read(1)
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
        return ch


def get_key():
    """
    Lê uma tecla imprimível, ignorando setas e teclas especiais.

    Setas e teclas de função chegam como sequências de escape
    (ex: '\\x1b[A' no Linux, prefixo \\xe0 no Windows). Sem este
    filtro cada byte viraria um "Invalid option".

    Returns:
        caractere imprimível ou '\\n'/'\\r' (Enter); '' se ignorada
    """
    ch = getch()
    if not ch:
        return ''
    if ch == '\x1b':
        if not IS_WINDOWS:
            # Consome o resto da sequência ANSI sem travar: se nada
            # chegar em ~50ms era um Escape avulso (também ignorado).
            # ponytail: import local intencional; select não existe no Windows.
            try:
                import select
                while True:
                    ready, _, _ = select.select([sys.stdin], [], [], 0.05)
                    if not ready:
                        break
                    nxt = sys.stdin.read(1)
                    if not nxt:
                        break
                    if nxt.isalpha() or nxt == '~':
                        break
            except Exception:
                pass
        return ''
    return ch


# =====================================================
# CONFIG
# =====================================================
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
LOCALES_DIR = os.path.join(SCRIPT_DIR, "locales")
LANG = "en"
STRINGS = {}
DELAY = int(os.environ.get("NPM_PM_DELAY", 2))
NPM_TIMEOUT = int(os.environ.get("NPM_PM_TIMEOUT", 90))
NPM_UPDATE_TIMEOUT = int(os.environ.get("NPM_PM_UPDATE_TIMEOUT", 300))
CACHE_TTL = int(os.environ.get("NPM_PM_TTL", 120))
SIZE_CACHE = {}
_TIMED_OUT = []
COLOR_ENABLED = True
USE_UNICODE = True
DEMO_MODE = "--test" in sys.argv
DEMO_FAIL_NAME = "left-pad"
_FRAME_LINES = 0

# =====================================================
# I18N
# =====================================================
def load_language():
    global LANG, STRINGS

    init_theme()
    if USE_UNICODE:
        print("╭─ Language / Idioma / Idioma ─────────")
    else:
        print("+-- Language / Idioma / Idioma ----------")
    print("  [1] English (default)")
    print("  [2] Português")
    print("  [3] Español")
    print("\nPress key (1/2/3) or Enter for default: ", end="", flush=True)

    while True:
        ch = get_key()
        if ch == '':
            continue  # setas e especiais: espera tecla válida em silêncio
        break
    print(ch)  # eco da tecla pressionada

    # Enter retorna \n ou \r, converte para string vazia
    if ch == '\n' or ch == '\r':
        ch = ''

    # Mapeamento direto com fallback para English
    mapping = {"1": "en", "2": "pt", "3": "es", "": "en"}
    LANG = mapping.get(ch, "en")  # fallback: qualquer tecla inválida → en

    path = os.path.join(LOCALES_DIR, f"{LANG}.json")

    if not os.path.exists(path):
        print(f"Missing locale file: {path}")
        sys.exit(1)

    with open(path, "r", encoding="utf-8") as f:
        STRINGS = json.load(f)


def t(key):
    return STRINGS.get(key, key)


COLORS = {
    "reset": "\x1b[0m",
    "ok": "\x1b[32m",
    "update": "\x1b[33m",
    "error": "\x1b[31m",
    "muted": "\x1b[90m",
    "info": "\x1b[36m",
}

_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")


def _enable_windows_vt():
    """
    Habilita sequencias ANSI no console do Windows.

    Retorna: True se VT ativo ou nao necessario, False caso contrario
    """
    if not IS_WINDOWS:
        return True
    try:
        import ctypes
        kernel32 = ctypes.windll.kernel32
        handle = kernel32.GetStdHandle(-11)
        mode = ctypes.c_ulong()
        if not kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
            return False
        return bool(kernel32.SetConsoleMode(handle, mode.value | 4))
    except Exception:
        return False


def supports_color():
    """
    Detecta se o terminal atual suporta cores ANSI.

    Respeita NO_COLOR, --no-color, TERM=dumb e saida redirecionada.

    Retorna: True se pode usar cores, False caso contrario
    """
    if os.environ.get("NO_COLOR"):
        return False
    if "--no-color" in sys.argv:
        return False
    if os.environ.get("TERM") == "dumb":
        return False
    try:
        if not sys.stdout.isatty():
            return False
    except Exception:
        return False
    if IS_WINDOWS and not _enable_windows_vt():
        return False
    return True


def _detect_unicode():
    """
    Detecta se o terminal aceita glifos Unicode (bordas finas).

    Retorna: True para Unicode, False para fallback ASCII
    """
    if os.environ.get("NPM_PM_ASCII") == "1":
        return False
    try:
        if not sys.stdout.isatty():
            return False
        enc = sys.stdout.encoding or "utf-8"
        "─✓→".encode(enc)
        return True
    except Exception:
        return False


def init_theme():
    """
    Inicializa flags globais de tema (cor e Unicode).

    Deve ser chamada uma vez no inicio do programa.
    """
    global COLOR_ENABLED, USE_UNICODE
    COLOR_ENABLED = supports_color()
    USE_UNICODE = _detect_unicode()


def c(name, text):
    """
    Colore texto apenas se o terminal suportar.

    Args:
        name: chave em COLORS (ok, update, error, muted, info)
        text: texto a ser colorido

    Returns:
        texto com ANSI ou texto puro como fallback
    """
    # ponytail: cor somente em status; texto estrutural nunca passa aqui
    if not COLOR_ENABLED:
        return text
    code = COLORS.get(name)
    if not code:
        return text
    return f"{code}{text}{COLORS['reset']}"


def _line_char():
    """
    Retorna: caractere de linha fina (Unicode ou ASCII fallback)
    """
    return "─" if USE_UNICODE else "-"


def _visible_len(text):
    """
    Comprimento visivel ignorando sequencias ANSI.

    Args:
        text: texto possivelmente colorido

    Returns:
        numero de caracteres visiveis
    """
    return len(_ANSI_RE.sub("", text or ""))


def _pad_visible(text, width):
    """
    Alinha texto a esquerda respeitando ANSI.

    Args:
        text: texto possivelmente colorido
        width: largura desejada em caracteres visiveis

    Returns:
        texto com espacos a direita ate width
    """
    pad = width - _visible_len(text)
    return text + (" " * pad if pad > 0 else "")


def _truncate_visible(text, width, mode="end"):
    """
    Trunca texto para largura visivel preservando a cor externa.

    Args:
        text: texto possivelmente colorido
        width: largura maxima em caracteres visiveis
        mode: repassado a truncate_string

    Returns:
        texto truncado que nunca excede width visivel
    """
    if _visible_len(text) <= width:
        return text
    plain = _ANSI_RE.sub("", text or "")
    short = truncate_string(plain, width, mode=mode)
    match = _ANSI_RE.match(text or "")
    if match:
        return match.group(0) + short + COLORS["reset"]
    return short


def status_label(outdated):
    """
    Rotulo textual de status com cor apenas na etiqueta.

    Args:
        outdated: True se precisa atualizar

    Returns:
        string como [ok] ou [atualizar] (traduzida via t())
    """
    if outdated:
        return c("update", "[" + t("status_update") + "]")
    return c("ok", "[" + t("status_ok") + "]")


def _processing_text():
    """
    Texto de 'processando' sem quebrar consoles sem Unicode.

    O glifo padrao (locale update_processing) nao existe em codepages
    antigas (ex: cp1252) e causava UnicodeEncodeError. Sem Unicode,
    usa reticencias ASCII.

    Returns:
        string segura para o terminal atual
    """
    if USE_UNICODE:
        return t("update_processing")
    return "..."


def print_message(kind, text):
    """
    Imprime mensagem padronizada com prefixo calmo.

    Args:
        kind: ok, warn, error ou info
        text: mensagem a exibir
    """
    marks = {"ok": "[ok]", "warn": "[!]", "error": "[x]", "info": "[i]"}
    colors = {"ok": "ok", "warn": "update", "error": "error", "info": "info"}
    mark = marks.get(kind, "[i]")
    print(f"  {c(colors.get(kind, 'info'), mark)} {text}")


def start_spinner(message):
    """
    Inicia spinner discreto na mesma linha (sem clear).

    Args:
        message: texto exibido ao lado do spinner

    Returns:
        tupla (stop_event, thread) para encerrar com stop_spinner
    """
    if not sys.stdout.isatty():
        print(f"  {message}...")
        return (None, None)
    frames = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴"] if USE_UNICODE else ["|", "/", "-", "\\"]
    stop = threading.Event()

    def _spin():
        i = 0
        while not stop.is_set():
            frame = frames[i % len(frames)]
            sys.stdout.write(f"\r  {frame} {message}   ")
            sys.stdout.flush()
            stop.wait(0.08)
            i += 1

    th = threading.Thread(target=_spin, daemon=True)
    th.start()
    return (stop, th)


def stop_spinner(handle):
    """
    Encerra spinner iniciado com start_spinner e limpa a linha.

    Args:
        handle: tupla (stop_event, thread) retornada por start_spinner
    """
    if not handle or not handle[0]:
        return
    stop, th = handle
    stop.set()
    th.join(timeout=1)
    try:
        width, _ = get_terminal_size()
        sys.stdout.write("\r" + " " * min(width - 1, 80) + "\r")
        sys.stdout.flush()
    except Exception:
        sys.stdout.write("\r")
        sys.stdout.flush()


# =====================================================
# TERMINAL SIZE & UI HELPERS
# =====================================================
def get_terminal_size():
    """
    Detecta largura e altura do terminal.
    Retorna: tuple (width, height)
    Fallback: (80, 24) se detecção falhar
    """
    try:
        size = os.get_terminal_size()
        return (size.columns, size.lines)
    except OSError:
        # Fallback para variáveis de ambiente
        width = int(os.environ.get("COLUMNS", 80))
        height = int(os.environ.get("LINES", 24))
        return (width, height)


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
    if style == "single":
        print(c("muted", _line_char() * width))
        return
    styles = {
        "double": "=",
        "bold": "█" if USE_UNICODE else "#",
        "dashed": "- ",
    }
    char = styles.get(style, "-")
    if style == "dashed":
        print(c("muted", (char * (width // 2 + 1))[:width]))
    else:
        print(c("muted", char * width))


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
    Imprime titulo e resumo calmo com contagens.

    Args:
        rows: lista de dicionarios com dados dos pacotes
        terminal_width: largura atual do terminal
    """
    title = t("packages_title")
    total = len(rows)
    outdated = sum(1 for r in rows if r.get("local_outdated") or r.get("global_outdated"))
    healthy = total - outdated

    print(f"\n  {title}")
    sep = "·" if USE_UNICODE else "|"
    if terminal_width < 60:
        print(f"  {total} {sep} {outdated} {t('summary_to_update')}")
    else:
        summary = f"{total} {sep} {outdated} {t('summary_to_update')} {sep} {healthy} {t('summary_ok')}"
        print(f"  {c('muted', summary)}")
    print_separator(min(terminal_width - 2, 72), "single")


def show_progress(current, total, package_name, next_package=None, prefix=""):
    """
    Exibe barra de progresso fina e informacoes do pacote atual.

    Args:
        current: índice atual (1-based)
        total: total de pacotes
        package_name: nome do pacote sendo atualizado
        next_package: nome do próximo pacote (opcional)
        prefix: prefixo para a linha (ex: "LOCAL", "GLOBAL")
    """
    try:
        term_width, _ = get_terminal_size()
    except Exception:
        term_width = 80
    bar, detail, third = _progress_bar_lines(
        current, total, package_name, next_package, prefix, term_width
    )

    print(f"\n  {bar}")
    print(f"  {detail}")
    if third:
        print(f"  {c('muted', third)}")


def _progress_bar_lines(current, total, package_name, next_package=None, prefix="",
                        term_width=80):
    """
    Monta as 3 linhas da barra de progresso sem imprimir.

    Args:
        current: índice atual (1-based)
        total: total de pacotes
        package_name: nome do pacote sendo atualizado
        next_package: nome do próximo pacote (opcional)
        prefix: prefixo para a linha (ex: "LOCAL", "GLOBAL")
        term_width: largura para truncar as linhas

    Returns:
        lista com 3 strings (barra, pacote atual, proximo/processando)
    """
    percent = (current / total) * 100 if total > 0 else 0
    bar_width = max(10, min(24, term_width - 40))
    filled = int(bar_width * current / total) if total > 0 else 0
    if USE_UNICODE:
        bar = "█" * filled + "░" * (bar_width - filled)
    else:
        bar = "=" * filled + "-" * (bar_width - filled)

    prefix_str = f"{prefix}: " if prefix else ""
    detail = truncate_string(
        f"{t('updating_package')}: {prefix_str}{package_name}",
        max(10, term_width - 2),
        mode="middle",
    )
    if next_package:
        nxt = truncate_string(
            t("next_package") + ": " + next_package,
            max(10, term_width - 4),
            mode="middle",
        )
        third = nxt
    elif current == total:
        third = _processing_text()
    else:
        third = ""
    return [f"[{bar}] {current}/{total} ({percent:.0f}%)", detail, third]


def _can_rewrite():
    """
    Detecta se da para redesenhar linhas no lugar com ANSI.

    Independe de NO_COLOR (mover o cursor nao e cor).

    Returns:
        True se pode usar \\x1b[nA e \\x1b[K, False caso contrario
    """
    if os.environ.get("TERM") == "dumb":
        return False
    try:
        if not sys.stdout.isatty():
            return False
    except Exception:
        return False
    if IS_WINDOWS and not _enable_windows_vt():
        return False
    return True


def _viewport_window(total, current, max_rows):
    """
    Calcula janela movel centralizada no item atual.

    Funcao pura (sem terminal), coberta por asserts manuais.

    Args:
        total: numero total de itens
        current: índice atual (0-based)
        max_rows: maximo de linhas visiveis

    Returns:
        tupla (start, end, hidden_above, hidden_below)
    """
    max_rows = max(1, max_rows)
    if total <= max_rows:
        return (0, total, 0, 0)
    start = current - max_rows // 2
    start = max(0, min(start, total - max_rows))
    end = start + max_rows
    return (start, end, start, total - end)


def _task_row(scope, name, state, term_width):
    """
    Monta uma linha da lista de pacotes (somente nome).

    Args:
        scope: "LOCAL" ou "GLOBAL" (vira tag [L]/[G])
        name: nome do pacote
        state: pending, active, ok ou fail
        term_width: largura para truncar

    Returns:
        linha com no maximo term_width caracteres visiveis
    """
    marks = {
        "pending": c("muted", "[ ]"),
        "active": c("update", "[>]"),
        "ok": c("ok", "[ok]"),
        "fail": c("error", "[x]"),
    }
    tag = c("muted", "[L]" if scope == "LOCAL" else "[G]")
    prefix = f"  {marks.get(state, marks['pending'])} {tag} "
    name_max = max(4, term_width - _visible_len(prefix))
    return prefix + truncate_string(name, name_max, mode="middle")


def _build_progress_frame(tasks, states, current, term_width, term_height):
    """
    Monta o frame completo: barra fixa no topo + viewport da lista.

    Args:
        tasks: lista de tuplas (scope, nome)
        states: lista paralela com pending/active/ok/fail
        current: índice atual (0-based)
        term_width: largura do terminal
        term_height: altura do terminal

    Returns:
        lista de linhas (com ANSI de cor, sem codigos de cursor)
    """
    total = len(tasks)
    scope, name = tasks[current] if 0 <= current < total else ("", "")
    nxt = tasks[current + 1][1] if 0 <= current + 1 < total else None
    bar, detail, third = _progress_bar_lines(
        min(current + 1, total), total, name, nxt, scope, term_width
    )
    lines = ["", f"  {bar}", f"  {detail}", f"  {c('muted', third)}" if third else ""]

    # Viewport: ocupa o maximo da tela sem gerar scroll
    max_rows = max(3, term_height - 3 - 1 - 2 - 1)
    start, end, above, below = _viewport_window(total, current, max_rows)

    lines.append("  " + c("muted", _line_char() * max(10, term_width - 4)))
    if above:
        lines.append("  " + c("muted", format_with_placeholders(
            t("more_above"), count=above)))
    for i in range(start, end):
        lines.append(_task_row(tasks[i][0], tasks[i][1], states[i], term_width))
    if below:
        lines.append("  " + c("muted", format_with_placeholders(
            t("more_below"), count=below)))
    return lines


def _frame_emit(lines, term_width):
    """
    Exibe um frame: reescreve no lugar (TTY) ou imprime fresco (pipe).

    Cada linha e ajustada a term_width para nunca quebrar o terminal.
    Apos a chamada o cursor esta sempre no inicio de uma linha fresca.

    Args:
        lines: linhas do frame (podem conter ANSI de cor)
        term_width: largura maxima visivel por linha
    """
    global _FRAME_LINES
    fitted = [""] + [_truncate_visible(ln, term_width, mode="end") for ln in lines]
    if _can_rewrite() and _FRAME_LINES:
        sys.stdout.write("\r\x1b[%dA" % _FRAME_LINES)
        for ln in fitted:
            sys.stdout.write("\x1b[K" + ln + "\n")
        sys.stdout.flush()
    else:
        for ln in fitted:
            print(ln)
    _FRAME_LINES = len(fitted)


def _frame_seal():
    """
    Encerra a sessao de frames e reseta a contagem de linhas.
    """
    global _FRAME_LINES
    _FRAME_LINES = 0


def _combined_version(current, latest):
    """
    Combina versao instalada e disponivel em texto compacto.

    Args:
        current: versao instalada (pode ser vazia)
        latest: versao nova disponivel (pode ser vazia)

    Returns:
        string como '1.2.3 -> 1.3.0', '1.2.3' ou '-'
    """
    arrow = " → " if USE_UNICODE else " -> "
    if current and latest and latest != current:
        return f"{current}{arrow}{latest}"
    return current or "-"


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
    if num_cols <= 4:
        min_widths = [4, 12, 12, 12][:num_cols]
    else:
        min_widths = [4, 12, 10, 10, 10, 10, 8, 10][:num_cols]

    # Pisos absolutos para encolhimento (STATUS nunca encolhe: é o sinal calmo)
    floors = [3, 10, 6, 6, 6, 6, 6, 0][:num_cols]

    # Espaço disponível (subtraindo margens e separadores)
    margin = 4  # margem lateral
    separator_space = num_cols - 1  # espaços entre colunas
    available_width = terminal_width - margin * 2 - separator_space

    # Calcula largura máxima necessária para cada coluna baseado nos dados
    max_needed = []
    for i, header in enumerate(headers):
        max_len = len(header)
        for row in rows[:50]:  # amostra dos primeiros 50 pacotes
            if num_cols <= 4:
                if i == 0:
                    val = str(row.get("id", ""))
                elif i == 1:
                    val = row.get("name", "")
                elif i == 2:
                    val = _combined_version(row.get("gver", ""), row.get("gnew", ""))
                elif i == 3:
                    val = _combined_version(row.get("lver", ""), row.get("lnew", ""))
                else:
                    val = header
            elif i == 0:  # coluna #
                val = str(row.get("id", ""))
            elif i == 1:  # coluna PACKAGE
                val = row.get("name", "")
            elif i == 2:  # GLOBAL_VERSION
                val = row.get("gver", "")
            elif i == 3:  # GLOBAL_NEW
                val = row.get("gnew", "")
            elif i == 4:  # LOCAL_VERSION
                val = row.get("lver", "")
            elif i == 5:  # LOCAL_NEW
                val = row.get("lnew", "")
            elif i == 6:  # SIZE
                val = row.get("size", "")
            elif i == 7:  # STATUS
                val = "[" + t("status_update" if (
                    row.get("global_outdated") or row.get("local_outdated")
                ) else "status_ok") + "]"
            else:
                val = ""
            max_len = max(max_len, len(val))
        max_needed.append(min(max_len, 22))  # limita a 22 caracteres

    # Distribui espaço extra (ou falta) via PACKAGE, sem afundar o mínimo
    total_needed = sum(max(min_widths[i], max_needed[i]) for i in range(num_cols))
    extra_space = available_width - total_needed

    widths = []
    for i in range(num_cols):
        base_width = max(min_widths[i], max_needed[i])
        # Coluna PACKAGE absorve sobra ou falta primeiro
        if i == 1:
            widths.append(max(floors[i], base_width + extra_space))
        else:
            widths.append(base_width)

    # Garante que a linha final nunca exceda o terminal.
    # STATUS (última no modo completo) nunca encolhe: é o sinal calmo.
    # ponytail: encolhimento guloso intencional; upgrade = truncar versões antes.
    overflow = sum(widths) + num_cols - 1 - terminal_width
    for i in [1, 5, 3, 2, 4, 6, 0]:
        if i >= num_cols or overflow <= 0:
            continue
        cut = min(overflow, max(0, widths[i] - floors[i]))
        widths[i] -= cut
        overflow -= cut

    return widths


# =====================================================
# NPM HELPERS
# =====================================================
def run(cmd):
    try:
        result = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            shell=True,
            timeout=NPM_TIMEOUT,
        )
    except subprocess.TimeoutExpired:
        _TIMED_OUT.append(cmd)
        return ""
    except Exception:
        return ""
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
    cmd = "npm outdated --depth=0 --json"
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
    if DEMO_MODE:
        for spec in DEMO_ROWSPEC:
            if spec[0] == name:
                return spec[5] if global_mode else spec[6]
        return ""
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


# Tuplas demo: (nome, versao global, nova global, versao local, nova local,
# tamanho global, tamanho local). 4 ok, 5 com update, 1 com falha (left-pad).
# ponytail: dados fixos intencionais; upgrade = falha configuravel via argv.
DEMO_ROWSPEC = [
    ("react", "18.3.1", "", "", "", "320.5KB", ""),
    ("lodash", "", "", "4.17.21", "", "", "1.4MB"),
    ("typescript", "5.4.5", "", "5.4.5", "", "68.2MB", "68.2MB"),
    ("vite", "", "", "5.2.0", "", "", "12.8MB"),
    ("express", "", "", "4.18.2", "4.19.2", "", "2.1MB"),
    ("axios", "1.6.0", "1.7.4", "", "", "800.3KB", ""),
    ("a-very-long-package-name-for-truncation-demo", "", "", "2.0.1", "2.1.0", "", "4.4MB"),
    ("chalk", "4.1.2", "5.3.0", "4.1.2", "5.3.0", "120.0KB", "120.0KB"),
    ("commander", "", "", "11.0.0", "12.0.0", "", "900.0KB"),
    ("left-pad", "1.3.0", "1.3.1", "", "", "12.4KB", ""),
]


def collect_rows_demo():
    """
    Monta 10 linhas ficticias no mesmo formato de build_rows.

    4 pacotes ok, 5 com update e 1 (left-pad) que falha ao atualizar.
    Nenhum comando npm ou acesso ao disco e executado.

    Returns:
        lista de dicionarios de pacotes ordenada por nome
    """
    rows = []
    for i, (name, gver, gnew, lver, lnew, gsize, lsize) in enumerate(
        sorted(DEMO_ROWSPEC, key=lambda spec: spec[0]), start=1
    ):
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
                "global_outdated": bool(gnew),
                "local_outdated": bool(lnew),
            }
        )

    return rows


def mark(text, outdated):
    if not text:
        return ""
    return text


def print_table_responsive(rows, terminal_width=None):
    """
    Imprime tabela adaptada ao tamanho do terminal.

    Comportamento:
        - >= 80 colunas: tabela completa com STATUS
        - 60-79 colunas: modo compacto (versoes combinadas + STATUS)
        - < 60 colunas: modo ultra-compacto (lista vertical)
    """
    if terminal_width is None:
        terminal_width, _ = get_terminal_size()

    if not rows:
        print_message("info", t("nothing_to_update"))
        return

    # Determina modo de exibição
    if terminal_width < 60:
        _print_table_ultra_compact(rows, terminal_width)
        return

    if terminal_width < 80:
        headers = ["#", t("package"), t("global_version"), t("local_version")]
        # Reserva espaco real da etiqueta STATUS ao fim da linha
        status_w = 4
        for r in rows[:50]:
            label = t("status_update" if (
                r.get("global_outdated") or r.get("local_outdated")
            ) else "status_ok")
            status_w = max(status_w, len(label) + 2)
        widths = calculate_column_widths(terminal_width - status_w - 1, rows, headers)
        print(f"  {c('muted', '[' + t('compact_mode') + ']')}")
        print()
        print(c("muted", _build_row_line(headers, widths, header=True)))
        print_separator(sum(widths) + len(headers) - 1, "single")
        for r in rows:
            outdated = bool(r.get("global_outdated") or r.get("local_outdated"))
            values = [
                str(r["id"]),
                truncate_string(r["name"], widths[1], mode="middle"),
                truncate_string(
                    _combined_version(r["gver"], r["gnew"]), widths[2], mode="end"
                ),
                truncate_string(
                    _combined_version(r["lver"], r["lnew"]), widths[3], mode="end"
                ),
            ]
            line = _build_row_line(values, widths)
            print(line + " " + status_label(outdated))
        return

    headers = [
        "#",
        t("package"),
        t("global_version"),
        t("global_new"),
        t("local_version"),
        t("local_new"),
        t("size"),
        t("status"),
    ]

    # Calcula larguras dinâmicas
    widths = calculate_column_widths(terminal_width, rows, headers)

    # Imprime cabeçalho da tabela
    print()
    print(c("muted", _build_row_line(headers, widths, header=True)))

    print_separator(sum(widths) + len(headers) - 1, "single")

    # Imprime linhas
    for r in rows:
        outdated = bool(r.get("global_outdated") or r.get("local_outdated"))
        values = [
            str(r["id"]),
            truncate_string(r["name"], widths[1], mode="middle"),
            r["gver"] or "-",
            r["gnew"] or "-",
            r["lver"] or "-",
            r["lnew"] or "-",
            r["size"] or "-",
            status_label(outdated),
        ]
        print(_build_row_line(values, widths))


def _build_row_line(values, widths, header=False):
    """
    Monta linha da tabela com alinhamento calmo.

    Args:
        values: lista de textos (podem conter ANSI)
        widths: lista de larguras visiveis
        header: True se for cabecalho (sem mudanca de alinhamento)

    Returns:
        linha montada com # a direita e SIZE a direita
    """
    parts = []
    total = len(values)
    for i, (val, w) in enumerate(zip(values, widths)):
        text = _truncate_visible(str(val), w, mode="end")
        if i == 0:
            visible = _visible_len(text)
            parts.append(text.rjust(w) if visible <= w else text)
        elif total > 4 and i == total - 2 and not header:
            # Coluna SIZE a direita no modo completo
            visible = _visible_len(text)
            parts.append(text.rjust(w) if visible <= w else text)
        else:
            parts.append(_pad_visible(text, w))
    return " ".join(parts)


def _print_table_ultra_compact(rows, terminal_width):
    """
    Imprime tabela em modo ultra-compacto (lista vertical) para terminais < 60 colunas.
    """
    print(f"  {c('muted', '[' + t('compact_mode') + ']')}")
    if terminal_width < 40:
        warn = "[!] " + t("screen_too_small")
        print(f"  {c('update', truncate_string(warn, terminal_width - 2, mode='end'))}")
    print()

    for r in rows:
        outdated = bool(r.get("global_outdated") or r.get("local_outdated"))
        print_separator(min(terminal_width, 60), "dashed")
        name_max = max(10, terminal_width - 20)
        name = truncate_string(r["name"], name_max, mode="middle")
        print(f"  #{r['id']} {name} {status_label(outdated)}")

        if r["gver"] or r["gnew"]:
            print(f"     G: {_combined_version(r['gver'], r['gnew'])}")

        if r["lver"] or r["lnew"]:
            print(f"     L: {_combined_version(r['lver'], r['lnew'])}")

        if r["size"]:
            print(f"     {t('size')}: {r['size']}")
        print()


def run_npm_cmd(args):
    """
    Executa comando npm com compatibilidade Windows/Linux/Mac.

    No modo demo (--test) apenas simula: espera 0.4s e falha somente
    para o pacote DEMO_FAIL_NAME. Nenhum subprocess e iniciado.

    Args:
        args: lista de argumentos do comando npm

    Returns:
        True se exitcode == 0, False caso contrário
    """
    if DEMO_MODE:
        time.sleep(0.4)
        return DEMO_FAIL_NAME not in args
    try:
        # Windows precisa de shell=True para encontrar npm no PATH
        result = subprocess.run(
            args,
            shell=IS_WINDOWS,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=NPM_UPDATE_TIMEOUT,
        )
        return result.returncode == 0
    except subprocess.TimeoutExpired:
        _TIMED_OUT.append(" ".join(args))
        return False
    except Exception:
        return False


# =====================================================
# UPDATE
# =====================================================
def _npm_args(scope, name):
    """
    Monta comando npm para o escopo.

    Args:
        scope: "LOCAL" ou "GLOBAL"
        name: nome do pacote

    Returns:
        lista de argumentos para run_npm_cmd
    """
    if scope == "GLOBAL":
        return ["npm", "update", "-g", name]
    return ["npm", "update", name]


def _run_tasks_frame(tasks):
    """
    Executa tasks com barra fixa no topo + viewport (terminal interativo).

    Args:
        tasks: lista de tuplas (scope, nome)

    Returns:
        tupla (all_ok, failed) com nomes "SCOPE: nome" que falharam
    """
    total = len(tasks)
    states = ["pending"] * total
    failed = []

    for i, (scope, name) in enumerate(tasks):
        states[i] = "active"
        term_width, term_height = get_terminal_size()
        _frame_emit(
            _build_progress_frame(tasks, states, i, term_width, term_height),
            term_width,
        )
        if run_npm_cmd(_npm_args(scope, name)):
            states[i] = "ok"
        else:
            states[i] = "fail"
            failed.append(f"{scope}: {name}")

    term_width, term_height = get_terminal_size()
    _frame_emit(
        _build_progress_frame(tasks, states, total - 1, term_width, term_height),
        term_width,
    )
    _frame_seal()
    return (not failed, failed)


def _run_tasks_legacy(tasks):
    """
    Executa tasks com log sequencial (pipe ou terminal sem ANSI).

    Mesmo formato de antes do modo frame: barra + resultado por pacote.

    Args:
        tasks: lista de tuplas (scope, nome)

    Returns:
        tupla (all_ok, failed) com nomes "SCOPE: nome" que falharam
    """
    failed = []
    total = len(tasks)
    last_scope = None

    for pos, (scope, name) in enumerate(tasks, start=1):
        if scope != last_scope:
            if scope == "LOCAL":
                print("\n  " + t("updating_local"))
            else:
                print("\n  " + t("updating_global"))
            last_scope = scope

        nxt = tasks[pos][1] if pos < total else None
        show_progress(pos, total, name, next_package=nxt, prefix=scope)

        if run_npm_cmd(_npm_args(scope, name)):
            print_message("ok", f"{name}")
        else:
            failed.append(f"{scope}: {name}")
            print_message("error", f"{name}")

    return (not failed, failed)


def update_all(rows):
    # Get only packages that need update
    local_to_update = [r["name"] for r in rows if r["local_outdated"]]
    global_to_update = [r["name"] for r in rows if r["global_outdated"]]

    if not local_to_update and not global_to_update:
        print()
        print_message("info", t("nothing_to_update"))
        time.sleep(DELAY)
        return False

    tasks = [("LOCAL", n) for n in local_to_update]
    tasks += [("GLOBAL", n) for n in global_to_update]

    if _can_rewrite():
        all_ok, failed = _run_tasks_frame(tasks)
    else:
        all_ok, failed = _run_tasks_legacy(tasks)

    print()
    for entry in failed:
        print_message("error", entry)
    if all_ok:
        print_message("ok", t("update_done"))
    else:
        print_message("error", t("update_failed"))
    time.sleep(DELAY)
    return True


def update_one(row):
    if not row["local_outdated"] and not row["global_outdated"]:
        print()
        print_message("info", t("already_updated"))
        time.sleep(DELAY)
        return False

    name = row["name"]
    tasks = []
    if row["local_outdated"]:
        tasks.append(("LOCAL", name))
    if row["global_outdated"]:
        tasks.append(("GLOBAL", name))

    if _can_rewrite():
        all_ok, failed = _run_tasks_frame(tasks)
    else:
        all_ok, failed = _run_tasks_legacy(tasks)

    print()
    for entry in failed:
        print_message("error", entry)
    if all_ok:
        print_message("ok", t("update_done"))
    else:
        print_message("error", t("update_failed"))
    time.sleep(DELAY)
    return True


# =====================================================
# DATA REFRESH
# =====================================================
def collect_rows():
    if DEMO_MODE:
        return collect_rows_demo()
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

    rows = None
    fetched_at = 0
    need_fetch = True

    while True:
        if need_fetch or rows is None or (
            CACHE_TTL > 0 and time.time() - fetched_at > CACHE_TTL
        ):
            clear()
            spinner = start_spinner(t("collecting_data"))
            try:
                rows = collect_rows()
                fetched_at = time.time()
            finally:
                stop_spinner(spinner)
            timed_out = bool(_TIMED_OUT)
            del _TIMED_OUT[:]
            need_fetch = False
        else:
            timed_out = False

        clear()

        # Imprime cabeçalho informativo
        terminal_width, _ = get_terminal_size()

        if DEMO_MODE:
            print_message(
                "warn",
                truncate_string(t("demo_mode"), terminal_width - 6, mode="end"),
            )
        print_header(rows, terminal_width)

        # Imprime tabela responsiva
        print_table_responsive(rows, terminal_width)

        if timed_out:
            print_message("warn", t("npm_timeout"))

        print("\n  " + c("muted", t("options")))
        print(f"  {c('muted', '[a]')} {t('update_all')}")
        print(f"  {c('muted', '[o]')} {t('update_one')}")
        print(f"  {c('muted', '[r]')} {t('refresh')}")
        print(f"  {c('muted', '[q]')} {t('exit')}")
        print(f"  {c('muted', t('needs_update') + ': ' + t('status_update'))}")

        print("\n  " + t("choose") + " ", end="", flush=True)
        while True:
            choice = get_key().strip().lower()
            if choice == "" or choice in ("\n", "\r"):
                continue  # setas, especiais e Enter avulso: sem erro
            break

        if choice == "q":
            print(choice)
            print_message("info", t("bye"))
            break

        elif choice == "r":
            print(choice)
            need_fetch = True
            continue

        elif choice == "a":
            print(choice)
            print("  " + t("confirm_update_all") + " (y/N) ", end="", flush=True)
            confirm = ""
            while confirm == "":
                confirm = get_key().strip().lower()
            print(confirm)
            if confirm == "y":
                if update_all(rows):
                    need_fetch = True
            else:
                print_message("info", t("cancelled"))
                time.sleep(min(DELAY, 1))

        elif choice == "o":
            print(choice)
            print("  " + t("enter_number") + " ", end="", flush=True)
            num_str = ""
            while True:
                ch = get_key()
                if ch == "\n" or ch == "\r":
                    break
                if ch == "":
                    continue
                print(ch, end="", flush=True)
                num_str += ch
            print()

            try:
                num = int(num_str.strip())
                row = next(r for r in rows if r["id"] == num)
            except (TypeError, ValueError, StopIteration):
                print_message("warn", t("invalid_number"))
                time.sleep(min(DELAY, 1))
                continue

            if update_one(row):
                need_fetch = True
        elif choice.isdigit():
            num_str = choice
            print(choice, end="", flush=True)
            while True:
                ch = get_key()
                if ch == "\n" or ch == "\r":
                    break
                if ch == "":
                    continue
                print(ch, end="", flush=True)
                num_str += ch
            print()
            try:
                num = int(num_str.strip())
                row = next(r for r in rows if r["id"] == num)
                if update_one(row):
                    need_fetch = True
            except (TypeError, ValueError, StopIteration):
                print_message("warn", t("invalid_number"))
                time.sleep(min(DELAY, 1))
        else:
            print(choice)
            print_message("warn", t("invalid_option"))
            time.sleep(min(DELAY, 1))


if __name__ == "__main__":
    main()
