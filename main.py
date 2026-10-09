#!/usr/bin/env python3
import subprocess
import json
import os
import queue
import re
import sys
import threading
import time
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

    Returns:
        caractere lido ou '' se nao houver terminal ou a leitura falhar
    """
    if IS_WINDOWS:
        import msvcrt
        return _read_msvcrt_key(msvcrt.getch)

    try:
        fd = sys.stdin.fileno()
    except Exception:
        return ''

    try:
        old_settings = termios.tcgetattr(fd)
    except Exception:
        try:
            return sys.stdin.read(1) or ''
        except Exception:
            return ''

    try:
        tty.setraw(fd)
        return sys.stdin.read(1) or ''
    except Exception:
        return ''
    finally:
        try:
            termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
        except Exception:
            pass


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
                try:
                    target = sys.stdin.fileno()
                except Exception:
                    target = sys.stdin
                while True:
                    ready, _, _ = select.select([target], [], [], 0.05)
                    if not ready:
                        break
                    try:
                        nxt = sys.stdin.read(1)
                    except Exception:
                        break
                    if not nxt:
                        break
                    if nxt.isalpha() or nxt == '~':
                        break
            except Exception:
                pass
        return ''
    return ch


def get_key_timeout(timeout):
    """
    Aguarda uma tecla por um tempo limitado sem bloquear a coleta em segundo plano.

    Usa uma unica secao raw: seleciona antes de ler e restaura uma vez,
    sem chamar get_key() de forma aninhada.

    Args:
        timeout: tempo maximo de espera em segundos

    Returns:
        tecla lida, string vazia para tecla especial ou None se nao houve tecla
    """
    if IS_WINDOWS:
        import msvcrt
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if msvcrt.kbhit():
                return get_key()
            time.sleep(min(0.02, max(0, deadline - time.monotonic())))
        return None

    try:
        fd = sys.stdin.fileno()
    except Exception:
        return None

    try:
        old_settings = termios.tcgetattr(fd)
    except Exception:
        return None

    try:
        tty.setraw(fd)
        import select
        ready, _, _ = select.select([fd], [], [], timeout)
        if not ready:
            return None

        try:
            ch = sys.stdin.read(1)
        except Exception:
            return ''

        if not ch:
            return ''

        if ch != '\x1b':
            return ch

        try:
            while True:
                more, _, _ = select.select([fd], [], [], 0.05)
                if not more:
                    break
                try:
                    nxt = sys.stdin.read(1)
                except Exception:
                    break
                if not nxt:
                    break
                if nxt.isalpha() or nxt == '~':
                    break
        except Exception:
            pass
        return ''
    except Exception:
        return None
    finally:
        try:
            termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
        except Exception:
            pass


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
_TIMED_OUT_LOCK = threading.Lock()
COLOR_ENABLED = True
USE_UNICODE = True
DEMO_MODE = "--test" in sys.argv
DEMO_FAIL_NAME = "left-pad"
_FRAME_LINES = 0

# =====================================================
# I18N
# =====================================================
def load_language():
    """
    Carrega o idioma escolhido sem travar fora de um terminal.

    Returns:
        None; define LANG e STRINGS com fallback para en
    """
    global LANG, STRINGS

    init_theme()
    if not sys.stdin.isatty():
        LANG = "en"
        path = os.path.join(LOCALES_DIR, "en.json")
        if not os.path.exists(path):
            print(f"Missing locale file: {path}")
            sys.exit(1)
        with open(path, "r", encoding="utf-8") as f:
            STRINGS = json.load(f)
        return
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
    if isinstance(outdated, dict):
        checks = []
        if outdated.get("lver"):
            checks.append(outdated.get("local_check", "ready"))
        if outdated.get("gver"):
            checks.append(outdated.get("global_check", "ready"))
        if outdated.get("local_outdated") or outdated.get("global_outdated"):
            return c("update", "[" + t("status_update") + "]")
        if outdated.get("inventory_failed") or "failed" in checks:
            return c("error", "[" + t("status_unknown") + "]")
        if "pending" in checks:
            return c("muted", "[" + t("status_checking") + "]")
        outdated = False
    if outdated:
        return c("update", "[" + t("status_update") + "]")
    return c("ok", "[" + t("status_ok") + "]")


def status_label_key(row):
    if row.get("local_outdated") or row.get("global_outdated"):
        return "update"
    checks = []
    if row.get("lver"):
        checks.append(row.get("local_check", "ready"))
    if row.get("gver"):
        checks.append(row.get("global_check", "ready"))
    if row.get("inventory_failed") or "failed" in checks:
        return "unknown"
    if "pending" in checks:
        return "checking"
    return "ok"


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
    if sys.stdout.isatty():
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
    pending = sum(1 for r in rows if status_label_key(r) == "checking")
    failed = sum(1 for r in rows if status_label_key(r) == "unknown")
    healthy = total - outdated - pending - failed

    print(f"\n  {title}")
    sep = "·" if USE_UNICODE else "|"
    if terminal_width < 60:
        summary = f"{total} {sep} {outdated} {t('summary_to_update')}"
        if pending:
            summary += f" {sep} {pending} {t('summary_checking')}"
        if failed:
            summary += f" {sep} {failed} {t('summary_unknown')}"
        print(f"  {summary}")
    else:
        summary = f"{total} {sep} {outdated} {t('summary_to_update')} {sep} {healthy} {t('summary_ok')}"
        if pending:
            summary += f" {sep} {pending} {t('summary_checking')}"
        if failed:
            summary += f" {sep} {failed} {t('summary_unknown')}"
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


def _version_display(row, scope, compact=False):
    current = row["gver" if scope == "global" else "lver"]
    latest = row["gnew" if scope == "global" else "lnew"]
    state = row.get(scope[0] + "_check", "ready")
    if not current and not latest:
        return "-"
    if latest:
        return _combined_version(current, latest) if compact else latest
    if state == "pending":
        return (
            _combined_version(current, t("checking_version"))
            if compact else t("checking_version")
        )
    if state == "failed":
        return (
            _combined_version(current, t("status_unknown"))
            if compact else t("status_unknown")
        )
    return _combined_version(current, "") if compact else "-"


def _size_display(row):
    size = row.get("size", "")
    if row.get("size_pending"):
        return (size + " " if size else "") + t("measuring_size")
    return size or "-"


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
    if num_cols <= 5:
        min_widths = [4, 4, 12, 12, 12][:num_cols]
    else:
        min_widths = [4, 4, 12, 10, 10, 10, 10, 8][:num_cols]

    # STATUS fica fora da ordem de encolhimento para preservar o sinal.
    floors = [0, 3, 10, 6, 6, 6, 6, 0][:num_cols]

    # Espaço disponível (subtraindo margens e separadores)
    margin = 4  # margem lateral
    separator_space = num_cols - 1  # espaços entre colunas
    available_width = terminal_width - margin * 2 - separator_space

    # Calcula largura máxima necessária para cada coluna baseado nos dados
    max_needed = []
    for i, header in enumerate(headers):
        max_len = len(header)
        for row in rows[:50]:  # amostra dos primeiros 50 pacotes
            if num_cols <= 5:
                if i == 0:
                    val = _ANSI_RE.sub("", status_label(row))
                elif i == 1:
                    val = str(row.get("id", ""))
                elif i == 2:
                    val = row.get("name", "")
                elif i == 3:
                    val = _version_display(row, "global", compact=True)
                elif i == 4:
                    val = _version_display(row, "local", compact=True)
                else:
                    val = header
            elif i == 0:  # coluna STATUS
                val = _ANSI_RE.sub("", status_label(row))
            elif i == 1:  # coluna #
                val = str(row.get("id", ""))
            elif i == 2:  # coluna PACKAGE
                val = row.get("name", "")
            elif i == 3:  # GLOBAL_VERSION
                val = row.get("gver", "")
            elif i == 4:  # GLOBAL_NEW
                val = _version_display(row, "global")
            elif i == 5:  # LOCAL_VERSION
                val = row.get("lver", "")
            elif i == 6:  # LOCAL_NEW
                val = _version_display(row, "local")
            elif i == 7:  # SIZE
                val = _size_display(row)
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
        if i == 2:
            widths.append(max(floors[i], base_width + extra_space))
        else:
            widths.append(base_width)

    # Garante que a linha final nunca exceda o terminal.
    # STATUS (primeira coluna) fica fora da ordem de encolhimento.
    # ponytail: encolhimento guloso intencional; upgrade = truncar versões antes.
    overflow = sum(widths) + num_cols - 1 - terminal_width
    for i in [2, 6, 4, 3, 5, 7, 1]:
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
        with _TIMED_OUT_LOCK:
            _TIMED_OUT.append(cmd)
        return ""
    except Exception:
        return ""
    return result.stdout.strip()


def _consume_timeout(cmd):
    with _TIMED_OUT_LOCK:
        if cmd not in _TIMED_OUT:
            return False
        _TIMED_OUT.remove(cmd)
        return True


def npm_list(global_mode=False):
    return _npm_list_result(global_mode)[0]


def _npm_list_result(global_mode=False):
    cmd = "npm list --depth=0 --json"
    if global_mode:
        cmd = "npm list -g --depth=0 --json"

    output = run(cmd)
    timed_out = _consume_timeout(cmd)
    if not output:
        return {}, False, timed_out

    try:
        data = json.loads(output)
    except Exception:
        return {}, False, timed_out

    deps = data.get("dependencies", {})
    if not isinstance(data, dict) or not isinstance(deps, dict):
        return {}, False, timed_out

    # Filter out hidden/private packages (starting with .)
    return (
        {name: info for name, info in deps.items() if not name.startswith(".")},
        True,
        timed_out,
    )


def npm_outdated(global_mode=False):
    return _npm_outdated_result(global_mode)[0]


def _npm_outdated_result(global_mode=False):
    cmd = "npm outdated --depth=0 --json"
    if global_mode:
        cmd = "npm outdated -g --depth=0 --json"

    output = run(cmd)
    timed_out = _consume_timeout(cmd)
    if not output:
        return {}, False, timed_out

    try:
        data = json.loads(output)
        if not isinstance(data, dict):
            return {}, False, timed_out
        # Filter out hidden/private packages (starting with .)
        return (
            {name: info for name, info in data.items() if not name.startswith(".")},
            True,
            timed_out,
        )
    except Exception:
        return {}, False, timed_out


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


def get_pkg_size(name, global_mode=False, version="", base_path=None,
                 cancel_event=None):
    """Calcula e armazena em cache o tamanho instalado de um pacote.

    Args:
        name: nome do pacote
        global_mode: True para pacote global
        version: versao usada na chave do cache
        base_path: raiz ja resolvida ou None para resolver dentro da funcao
        cancel_event: sinal opcional para interromper a varredura

    Returns:
        tamanho formatado ou string vazia se o pacote nao existir
    """
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
        if cancel_event and cancel_event.is_set():
            return ""
        base = base_path if base_path is not None else npm_root(global_mode)
        path = os.path.join(base, name)

        if not os.path.isdir(path):
            SIZE_CACHE[cache_key] = ""
            return ""

        total = 0
        for root, _, files in os.walk(path):
            if cancel_event and cancel_event.is_set():
                return ""
            for f in files:
                if cancel_event and cancel_event.is_set():
                    return ""
                fp = os.path.join(root, f)
                try:
                    total += os.path.getsize(fp)
                except OSError:
                    continue

        size = human_size(total)
    except Exception:
        size = "-"

    SIZE_CACHE[cache_key] = size
    return size


def collect_sizes(local, global_, names, cancel_event=None, on_result=None):
    """Mede tamanhos em paralelo e publica resultados conforme terminam.

    Args:
        local: mapa de pacotes locais instalados
        global_: mapa de pacotes globais instalados
        names: nomes de pacotes a medir
        cancel_event: sinal opcional para cancelar trabalhos pendentes
        on_result: callback opcional chamado com chave e tamanho

    Returns:
        mapa de tamanhos por escopo e nome
    """
    size_map = {}
    jobs = []

    for name in names:
        if name in local:
            jobs.append(("local", name, local.get(name, {}).get("version", "")))
        if name in global_:
            jobs.append(("global", name, global_.get(name, {}).get("version", "")))

    if not jobs:
        return size_map

    if cancel_event and cancel_event.is_set():
        return size_map
    max_workers = min(8, len(jobs))
    global_root = (
        npm_root(True) if any(scope == "global" for scope, _, _ in jobs)
        else None
    )
    work = queue.Queue()
    for job in jobs:
        work.put(job)

    def _measure():
        while True:
            job = work.get()
            try:
                if job is None:
                    return
                if cancel_event and cancel_event.is_set():
                    continue
                scope, name, version = job
                size = get_pkg_size(
                    name,
                    scope == "global",
                    version,
                    global_root if scope == "global" else "node_modules",
                    cancel_event,
                )
                if not (cancel_event and cancel_event.is_set()):
                    key = (scope, name)
                    size_map[key] = size
                    if on_result:
                        on_result(key, size)
            finally:
                work.task_done()

    workers = [threading.Thread(target=_measure, daemon=True)
               for _ in range(max_workers)]
    for worker in workers:
        worker.start()
    for _ in workers:
        work.put(None)
    work.join()

    return size_map


# =====================================================
# TABLE
# =====================================================
def build_rows(local, global_, outdated_local, outdated_global, size_map=None,
               check_states=None, size_pending=False, inventory_failed=False):
    """Monta as linhas da tabela sem repetir coletas ja iniciadas.

    Args:
        local: mapa de pacotes locais
        global_: mapa de pacotes globais
        outdated_local: atualizacoes locais disponiveis
        outdated_global: atualizacoes globais disponiveis
        size_map: tamanhos conhecidos ou None para medi-los
        check_states: estado de cada consulta outdated
        size_pending: True enquanto alguns tamanhos nao estao disponiveis
        inventory_failed: True se uma listagem de pacotes falhou

    Returns:
        linhas ordenadas com IDs estaveis para o conjunto recebido
    """
    names = sorted(set(local) | set(global_))
    if size_map is None:
        size_map = collect_sizes(local, global_, names)
    check_states = check_states or {}
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
                "global_check": check_states.get("outdated_global", "ready"),
                "local_check": check_states.get("outdated_local", "ready"),
                "size_pending": size_pending and any(
                    (scope, name) not in size_map
                    for scope, installed in (("local", lver), ("global", gver))
                    if installed
                ),
                "inventory_failed": inventory_failed,
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


def collect_rows_demo(uninstalled=None):
    """
    Monta 10 linhas ficticias no mesmo formato de build_rows.

    4 pacotes ok, 5 com update e 1 (left-pad) que falha ao atualizar.
    Nenhum comando npm ou acesso ao disco e executado.

    Args:
        uninstalled: pares (nome, escopo) removidos apenas na simulacao

    Returns:
        lista de dicionarios de pacotes ordenada por nome
    """
    uninstalled = uninstalled or set()
    rows = []
    for name, gver, gnew, lver, lnew, gsize, lsize in sorted(
        DEMO_ROWSPEC, key=lambda spec: spec[0]
    ):
        if (name, "GLOBAL") in uninstalled:
            gver = gnew = gsize = ""
        if (name, "LOCAL") in uninstalled:
            lver = lnew = lsize = ""
        if not gver and not lver:
            continue

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
                "id": len(rows) + 1,
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
        headers = [
            t("status"), "#", t("package"),
            t("global_version"), t("local_version"),
        ]
        widths = calculate_column_widths(terminal_width, rows, headers)
        print(f"  {c('muted', '[' + t('compact_mode') + ']')}")
        print()
        print(c("muted", _build_row_line(headers, widths, header=True)))
        print_separator(sum(widths) + len(headers) - 1, "single")
        for r in rows:
            values = [
                status_label(r),
                str(r["id"]),
                truncate_string(r["name"], widths[2], mode="middle"),
                truncate_string(
                    _version_display(r, "global", compact=True), widths[3], mode="end"
                ),
                truncate_string(
                    _version_display(r, "local", compact=True), widths[4], mode="end"
                ),
            ]
            print(_build_row_line(values, widths))
        return

    headers = [
        t("status"),
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

    # Imprime cabeçalho da tabela
    print()
    print(c("muted", _build_row_line(headers, widths, header=True)))

    print_separator(sum(widths) + len(headers) - 1, "single")

    # Imprime linhas
    for r in rows:
        values = [
            status_label(r),
            str(r["id"]),
            truncate_string(r["name"], widths[2], mode="middle"),
            r["gver"] or "-",
            _version_display(r, "global"),
            r["lver"] or "-",
            _version_display(r, "local"),
            _size_display(r),
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
        linha montada com # e SIZE a direita
    """
    parts = []
    total = len(values)
    for i, (val, w) in enumerate(zip(values, widths)):
        text = _truncate_visible(str(val), w, mode="end")
        if i == 1:
            visible = _visible_len(text)
            parts.append(text.rjust(w) if visible <= w else text)
        elif total == 8 and i == 7 and not header:
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
        print_separator(min(terminal_width, 60), "dashed")
        name_max = max(10, terminal_width - 20)
        name = truncate_string(r["name"], name_max, mode="middle")
        print(f"  {status_label(r)} #{r['id']} {name}")

        if r["gver"] or r["gnew"]:
            print(f"     G: {_version_display(r, 'global', compact=True)}")

        if r["lver"] or r["lnew"]:
            print(f"     L: {_version_display(r, 'local', compact=True)}")

        if r["size"] or r.get("size_pending"):
            print(f"     {t('size')}: {_size_display(r)}")
        print()


def run_npm_cmd(args):
    """
    Executa comando npm com compatibilidade Windows/Linux/Mac.

    No modo demo (--test) simula comandos de pacote: espera 0.4s e falha
    somente para o pacote DEMO_FAIL_NAME. Nenhum subprocess e iniciado.

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
        with _TIMED_OUT_LOCK:
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


def _npm_uninstall_args(scope, name):
    """Monta o comando npm para remover uma instalacao do pacote.

    Args:
        scope: "LOCAL" ou "GLOBAL"
        name: nome do pacote

    Returns:
        lista de argumentos para run_npm_cmd
    """
    args = ["npm", "uninstall"]
    if scope == "GLOBAL":
        args.append("-g")
    args.append(name)
    return args


def _uninstall_scope(row):
    """Retorna o escopo seguro, priorizando a instalacao local.

    Args:
        row: linha selecionada da tabela

    Returns:
        "LOCAL", "GLOBAL" ou None se o escopo nao puder ser confirmado
    """
    if row.get("inventory_failed"):
        return None
    if row.get("lver"):
        return "LOCAL"
    if row.get("gver"):
        return "GLOBAL"
    return None


def uninstall_one(row, scope):
    """Remove uma instalacao e exibe o resultado do comando npm.

    Args:
        row: linha selecionada da tabela
        scope: "LOCAL" ou "GLOBAL"

    Returns:
        True se npm uninstall terminar com codigo zero
    """
    name = row["name"]
    print("  " + t("uninstalling").format(
        scope=t("local" if scope == "LOCAL" else "global"), name=name
    ))
    handle = start_spinner(f"{scope}: {name}")
    try:
        succeeded = run_npm_cmd(_npm_uninstall_args(scope, name))
    finally:
        stop_spinner(handle)
    key = "uninstall_done" if succeeded else "uninstall_failed"
    print_message("ok" if succeeded else "error", t(key).format(name=name))
    time.sleep(min(DELAY, 1))
    return succeeded


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
        handle = start_spinner(f"{scope}: {name}")
        try:
            succeeded = run_npm_cmd(_npm_args(scope, name))
        finally:
            stop_spinner(handle)
        if succeeded:
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

        handle = start_spinner(f"{scope}: {name}")
        try:
            succeeded = run_npm_cmd(_npm_args(scope, name))
        finally:
            stop_spinner(handle)
        if succeeded:
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
    results = queue.Queue()
    queries = {
        "local": lambda: _npm_list_result(False),
        "global": lambda: _npm_list_result(True),
        "outdated_local": lambda: _npm_outdated_result(False),
        "outdated_global": lambda: _npm_outdated_result(True),
    }
    for name, query in queries.items():
        _start_daemon_task(results, 0, name, query)
    collected = {}
    for _ in queries:
        _, name, result = results.get()
        collected[name] = result
    local, global_ = collected["local"][0], collected["global"][0]
    outdated_local = collected["outdated_local"][0]
    outdated_global = collected["outdated_global"][0]
    return build_rows(local, global_, outdated_local, outdated_global)


def _start_daemon_task(results, generation, name, task):
    """Executa tarefa daemon e envia o resultado pela fila.

    Args:
        results: fila de eventos consumida pela interface
        generation: identificador do ciclo de coleta
        name: tipo do resultado
        task: funcao sem argumentos que realiza o trabalho
    """
    def _run_task():
        try:
            result = task()
        except Exception:
            result = None
        results.put((generation, name, result))

    thread = threading.Thread(target=_run_task, daemon=True)
    thread.start()


def _new_collection(generation, results):
    """Inicia consultas npm independentes para um novo ciclo.

    Args:
        generation: identificador crescente do ciclo
        results: fila que recebe conclusoes dos workers

    Returns:
        estado inicial da coleta
    """
    collection = {
        "generation": generation,
        "cancel": threading.Event(),
        "local": {},
        "global": {},
        "outdated_local": {},
        "outdated_global": {},
        "size_map": {},
        "states": {
            "local": "pending",
            "global": "pending",
            "outdated_local": "pending",
            "outdated_global": "pending",
        },
        "list_ok": {"local": None, "global": None},
        "size_state": "waiting",
        "timed_out": False,
        "failed": False,
        "rows_ready": False,
    }
    queries = {
        "local": lambda: _npm_list_result(False),
        "global": lambda: _npm_list_result(True),
        "outdated_local": lambda: _npm_outdated_result(False),
        "outdated_global": lambda: _npm_outdated_result(True),
    }
    for name, query in queries.items():
        _start_daemon_task(results, generation, name, query)
    return collection


def _collection_done(collection):
    """Indica se consultas npm e tamanhos terminaram."""
    return (
        all(state != "pending" for state in collection["states"].values())
        and collection["size_state"] == "ready"
    )


def _update_action_state(collection):
    """Retorna pending, failed ou ready para os dados de atualizacao."""
    if collection is None:
        return "pending"
    states = list(collection["states"].values())
    if any(state == "pending" for state in states):
        return "pending"
    if any(state != "ready" for state in states):
        return "failed"
    return "ready"


def _refresh_rows(collection):
    """Reconstrui linhas usando somente resultados ja recebidos."""
    if not collection["rows_ready"]:
        return None
    states = {
        "outdated_local": collection["states"]["outdated_local"],
        "outdated_global": collection["states"]["outdated_global"],
    }
    return build_rows(
        collection["local"],
        collection["global"],
        collection["outdated_local"],
        collection["outdated_global"],
        size_map=collection["size_map"],
        check_states=states,
        size_pending=collection["size_state"] == "pending",
        inventory_failed=any(
            state == "failed" for state in collection["list_ok"].values()
        ),
    )


def _start_size_collection(collection, results):
    """Inicia tamanhos assim que as listagens instaladas terminam."""
    names = sorted(set(collection["local"]) | set(collection["global"]))
    if not names or collection["cancel"].is_set():
        collection["size_state"] = "ready"
        return
    collection["size_state"] = "pending"

    def _collect():
        return collect_sizes(
            collection["local"],
            collection["global"],
            names,
            collection["cancel"],
            lambda key, size: results.put((
                collection["generation"], "size", (key, size)
            )),
        )

    _start_daemon_task(
        results, collection["generation"], "sizes_done", _collect
    )


def _apply_collection_events(collection, results):
    """Aplica resultados prontos e informa se a tela precisa ser redesenhada."""
    changed = False
    while True:
        try:
            generation, name, result = results.get_nowait()
        except queue.Empty:
            break
        if generation != collection["generation"]:
            continue
        if name == "size":
            key, size = result
            collection["size_map"][key] = size
            changed = True
            continue
        if name == "sizes_done":
            collection["size_map"] = result or {}
            collection["size_state"] = "ready"
            collection["timed_out"] = (
                collection["timed_out"] or _consume_timeout("npm root -g")
            )
            changed = True
            continue

        if not isinstance(result, tuple) or len(result) != 3:
            data, ok, timed_out = {}, False, False
        else:
            data, ok, timed_out = result
        collection["states"][name] = "ready" if ok else "failed"
        collection["timed_out"] = collection["timed_out"] or timed_out
        collection["failed"] = collection["failed"] or not ok
        if name in ("local", "global"):
            collection[name] = data or {}
            collection["list_ok"][name] = ok
            if all(state is not None for state in collection["list_ok"].values()):
                collection["rows_ready"] = True
                _start_size_collection(collection, results)
        else:
            collection[name] = data or {}
        changed = True
    return changed


# =====================================================
# MAIN LOOP
# =====================================================
def _read_input_line(initial=""):
    """
    Lê uma linha editável, tratando Backspace sem deixar artefatos na tela.

    Args:
        initial: texto já digitado antes de iniciar a leitura

    Returns:
        texto final informado pelo usuário
    """
    value = initial
    if initial:
        sys.stdout.write(initial)
        sys.stdout.flush()

    while True:
        ch = get_key()
        if ch in ("\n", "\r"):
            break
        if ch in ("\x08", "\x7f"):
            if value:
                value = value[:-1]
                sys.stdout.write("\b \b")
                sys.stdout.flush()
            continue
        if ch and ch.isprintable():
            value += ch
            sys.stdout.write(ch)
            sys.stdout.flush()

    print()
    return value


def _selected_rows_from_input(value, rows):
    """
    Resolve todos os IDs da entrada ou rejeita a seleção inteira.

    Args:
        value: números dos pacotes separados por vírgulas
        rows: linhas de pacotes exibidas na tabela

    Returns:
        lista de linhas selecionadas ou None se algum ID for inválido
    """
    row_by_id = {row["id"]: row for row in rows}
    selected = []
    selected_ids = set()

    for token in value.split(","):
        token = token.strip()
        if not token.isdigit():
            return None

        try:
            package_id = int(token)
        except ValueError:
            return None
        if package_id not in row_by_id:
            return None
        if package_id not in selected_ids:
            selected.append(row_by_id[package_id])
            selected_ids.add(package_id)

    return selected


def main():
    load_language()
    results = queue.Queue()
    rows = collect_rows_demo() if DEMO_MODE else None
    demo_uninstalled = set()
    active = None
    last_collection = None
    if DEMO_MODE:
        last_collection = {
            "states": {name: "ready" for name in (
                "local", "global", "outdated_local", "outdated_global"
            )},
            "warning": "",
        }
    generation = 0
    fetched_at = time.time() if DEMO_MODE else 0
    refresh_requested = False
    dirty = True

    def start_fetch():
        nonlocal active, last_collection, generation
        generation += 1
        active = _new_collection(generation, results)
        last_collection = active

    def stop_sizes_before_update(selected_rows):
        nonlocal refresh_requested
        has_updates = any(
            row.get("local_outdated") or row.get("global_outdated")
            for row in selected_rows
        )
        if active and active["size_state"] == "pending" and has_updates:
            active["cancel"].set()
            refresh_requested = True

    if not DEMO_MODE:
        start_fetch()

    while True:
        changed = False
        had_no_rows = rows is None
        if active:
            changed = _apply_collection_events(active, results)
            new_rows = _refresh_rows(active)
            if new_rows is not None and (changed or rows is None):
                rows = new_rows
                changed = True

            if _collection_done(active):
                fetched_at = time.time()
                if active["timed_out"]:
                    active["warning"] = "timeout"
                elif active["failed"]:
                    active["warning"] = "failed"
                else:
                    active["warning"] = ""
                last_collection = active
                active = None
                changed = True
                if refresh_requested:
                    refresh_requested = False
                    start_fetch()

        if (not DEMO_MODE and active is None and not refresh_requested
                and CACHE_TTL > 0 and time.time() - fetched_at > CACHE_TTL):
            start_fetch()
            changed = True

        if changed and (sys.stdout.isatty() or had_no_rows or active is None):
            dirty = True

        if dirty:
            clear()
            terminal_width, _ = get_terminal_size()
            if DEMO_MODE:
                print_message(
                    "warn",
                    truncate_string(t("demo_mode"), terminal_width - 6, mode="end"),
                )
            if rows is None:
                print("\n  " + t("collecting_data"))
            else:
                print_header(rows, terminal_width)
                print_table_responsive(rows, terminal_width)

            status = active or last_collection
            if status and status.get("warning") == "timeout":
                print_message("warn", t("npm_timeout"))
            elif status and status.get("failed"):
                print_message("warn", t("checks_failed"))
            if refresh_requested:
                print_message("info", t("refresh_pending"))
            elif active and _update_action_state(active) == "pending" and rows:
                print_message("info", t("checks_pending"))

            print("\n  " + c("muted", t("options")))
            print(f"  {c('muted', '[a]')} {t('update_all')}")
            print(f"  {c('muted', '[o]')} {t('update_one')}")
            print(f"  {c('muted', '[u]')} {t('uninstall_one')}")
            print(f"  {c('muted', '[r]')} {t('refresh')}")
            print(f"  {c('muted', '[q]')} {t('exit')}")
            print("\n  " + t("choose") + " ", end="", flush=True)
            dirty = False

        choice = get_key_timeout(0.08)
        if choice is None or choice == "" or choice in ("\n", "\r"):
            continue
        choice = choice.strip().lower()

        if choice == "q":
            print(choice)
            print_message("info", t("bye"))
            if active:
                active["cancel"].set()
            break

        elif choice == "r":
            print(choice)
            if active:
                refresh_requested = True
                active["cancel"].set()
                dirty = True
            elif not DEMO_MODE:
                start_fetch()
                dirty = True
            else:
                dirty = True

        elif choice == "a":
            print(choice)
            if _update_action_state(active or last_collection) != "ready":
                state = _update_action_state(active or last_collection)
                print_message("warn", t("checks_pending" if state == "pending" else "checks_failed"))
                time.sleep(min(DELAY, 1))
                dirty = True
                continue
            print("  " + t("confirm_update_all") + " (y/N) ", end="", flush=True)
            confirm = ""
            while confirm == "":
                confirm = get_key().strip().lower()
            print(confirm)
            if confirm == "y":
                stop_sizes_before_update(rows or [])
                if update_all(rows):
                    if active:
                        refresh_requested = True
                        active["cancel"].set()
                    else:
                        start_fetch()
                    dirty = True
            else:
                print_message("info", t("cancelled"))
                time.sleep(min(DELAY, 1))
                dirty = True

        elif choice == "u":
            print(choice)
            if rows is None:
                print_message("warn", t("collecting_data"))
                dirty = True
                continue
            if not rows:
                print_message("info", t("nothing_to_uninstall"))
                time.sleep(min(DELAY, 1))
                dirty = True
                continue

            print("  " + t("enter_uninstall_number") + " ", end="", flush=True)
            number = _read_input_line().strip()
            selected_rows = (
                _selected_rows_from_input(number, rows)
                if number.isdigit() else None
            )
            if selected_rows is None or len(selected_rows) != 1:
                print_message("warn", t("invalid_number"))
                time.sleep(min(DELAY, 1))
                dirty = True
                continue

            row = selected_rows[0]
            if row.get("inventory_failed"):
                print_message("warn", t("inventory_failed"))
                time.sleep(min(DELAY, 1))
                dirty = True
                continue

            scope = _uninstall_scope(row)
            if scope is None:
                print_message("warn", t("uninstall_unavailable"))
                time.sleep(min(DELAY, 1))
                dirty = True
                continue

            scope_label = t("local" if scope == "LOCAL" else "global")
            print("  " + t("confirm_uninstall").format(
                name=row["name"], scope=scope_label
            ) + " (y/n) ", end="", flush=True)
            confirm = ""
            while not confirm:
                confirm = get_key().strip().lower()
            print(confirm)

            if confirm != "y":
                print_message("info", t("cancelled"))
                time.sleep(min(DELAY, 1))
                dirty = True
                continue

            print("  " + t("confirm_package_name").format(
                name=row["name"]
            ) + " ", end="", flush=True)
            typed_name = _read_input_line()
            if typed_name != row["name"]:
                print_message("info", t("invalid_package_name"))
                time.sleep(min(DELAY, 1))
                dirty = True
                continue

            succeeded = uninstall_one(row, scope)
            if DEMO_MODE:
                if succeeded:
                    demo_uninstalled.add((row["name"], scope))
                    rows = collect_rows_demo(demo_uninstalled)
            elif active:
                refresh_requested = True
                active["cancel"].set()
            else:
                start_fetch()
            dirty = True

        elif choice == "o" or choice.isdigit():
            initial = choice
            if choice == "o":
                print(choice)
                print("  " + t("enter_number") + " ", end="", flush=True)
                initial = ""
            if rows is None:
                print_message("warn", t("checks_pending"))
                dirty = True
                continue
            selected_rows = _selected_rows_from_input(
                _read_input_line(initial), rows
            )
            if selected_rows is None:
                print_message("warn", t("invalid_number"))
                time.sleep(min(DELAY, 1))
                dirty = True
                continue
            if _update_action_state(active or last_collection) != "ready":
                state = _update_action_state(active or last_collection)
                print_message("warn", t("checks_pending" if state == "pending" else "checks_failed"))
                dirty = True
                continue

            stop_sizes_before_update(selected_rows)
            updated = (
                update_one(selected_rows[0])
                if len(selected_rows) == 1
                else update_all(selected_rows)
            )
            if updated:
                if active:
                    refresh_requested = True
                    active["cancel"].set()
                else:
                    start_fetch()
            dirty = True
        else:
            print(choice)
            print_message("warn", t("invalid_option"))
            time.sleep(min(DELAY, 1))
            dirty = True


if __name__ == "__main__":
    main()
