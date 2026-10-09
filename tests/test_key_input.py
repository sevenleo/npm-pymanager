"""Verificacoes focadas para leitura de teclas no terminal POSIX."""
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import main


def run_fake_timeout(ready, error=None):
    """Simula polling POSIX e retorna o resultado e o estado do terminal."""
    state = {"mode": "cooked", "reads": 0}

    def read_char(size):
        state["reads"] += 1
        return "a"

    def select_input(readers, writers, errors, timeout):
        state["mode_when_polled"] = state["mode"]
        if error:
            raise error
        return ([7] if ready else [], [], [])

    def setraw(fd):
        state["mode"] = "raw"

    termios = SimpleNamespace(
        TCSADRAIN=0,
        tcgetattr=lambda fd: state["mode"],
        tcsetattr=lambda fd, when, settings: state.update(mode=settings),
    )
    select = ModuleType("select")
    select.select = select_input

    with patch.object(main, "IS_WINDOWS", False):
        with patch.object(main, "termios", termios, create=True):
            with patch.object(
                main, "tty", SimpleNamespace(setraw=setraw), create=True
            ):
                with patch.object(
                    main.sys,
                    "stdin",
                    SimpleNamespace(fileno=lambda: 7, read=read_char),
                ):
                    with patch.dict(sys.modules, {"select": select}):
                        result = main.get_key_timeout(0.01)

    return result, state


def test_key_is_read_while_terminal_is_raw():
    result, state = run_fake_timeout(ready=True)

    assert result == "a"
    assert state["mode_when_polled"] == "raw"
    assert state["mode"] == "cooked"
    assert state["reads"] == 1


def test_timeout_restores_terminal_without_reading():
    result, state = run_fake_timeout(ready=False)

    assert result is None
    assert state["mode_when_polled"] == "raw"
    assert state["mode"] == "cooked"
    assert state["reads"] == 0


def test_select_error_does_not_fall_back_to_blocking_read():
    result, state = run_fake_timeout(ready=False, error=OSError("select failed"))

    assert result is None
    assert state["mode"] == "cooked"
    assert state["reads"] == 0


if __name__ == "__main__":
    test_key_is_read_while_terminal_is_raw()
    test_timeout_restores_terminal_without_reading()
    test_select_error_does_not_fall_back_to_blocking_read()
    print("OK")
