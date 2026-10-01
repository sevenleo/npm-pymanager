"""Verificacoes focadas para o fluxo de desinstalacao."""
from contextlib import redirect_stdout
import io
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import main


def run_demo_uninstall(
    package_name, confirmation="y", typed_name=None, number_override=None
):
    """Executa a opcao de desinstalacao com entradas controladas."""
    originals = {
        "DEMO_MODE": main.DEMO_MODE,
        "DELAY": main.DELAY,
        "load_language": main.load_language,
        "get_key": main.get_key,
        "get_key_timeout": main.get_key_timeout,
        "run_npm_cmd": main.run_npm_cmd,
    }
    rows = main.collect_rows_demo()
    number = number_override
    if number is None:
        number = str(next(
            row["id"] for row in rows if row["name"] == package_name
        ))
    keys = iter(number + "\r" + confirmation + (typed_name or package_name) + "\r")
    choices = iter(("u", "q"))
    calls = []

    main.DEMO_MODE = True
    main.DELAY = 0
    main.load_language = lambda: None
    main.get_key = lambda: next(keys)
    main.get_key_timeout = lambda timeout=None: next(choices, None)
    main.run_npm_cmd = lambda args: calls.append(args) or True
    try:
        with redirect_stdout(io.StringIO()):
            main.main()
    finally:
        for name, value in originals.items():
            setattr(main, name, value)
    return calls


def test_npm_uninstall_arguments_and_scope():
    assert main._npm_uninstall_args("LOCAL", "@scope/pkg") == [
        "npm", "uninstall", "@scope/pkg"
    ]
    assert main._npm_uninstall_args("GLOBAL", "@scope/pkg") == [
        "npm", "uninstall", "-g", "@scope/pkg"
    ]
    assert main._uninstall_scope({"lver": "1.0", "gver": "2.0"}) == "LOCAL"
    assert main._uninstall_scope({"lver": "", "gver": "2.0"}) == "GLOBAL"
    assert main._uninstall_scope({
        "lver": "1.0", "gver": "2.0", "inventory_failed": True
    }) is None


def test_confirmation_runs_one_global_uninstall():
    assert run_demo_uninstall("react") == [[
        "npm", "uninstall", "-g", "react"
    ]]


def test_confirmation_runs_local_first_for_both_scopes():
    assert run_demo_uninstall("typescript") == [[
        "npm", "uninstall", "typescript"
    ]]
    remaining = main.collect_rows_demo({("typescript", "LOCAL")})
    row = next(row for row in remaining if row["name"] == "typescript")
    assert row["gver"] == "5.4.5"
    assert row["lver"] == ""


def test_mismatched_name_cancels_without_running_npm():
    assert run_demo_uninstall("react", typed_name="React") == []


def test_non_y_and_multiple_numbers_cancel_without_running_npm():
    assert run_demo_uninstall("react", confirmation="n") == []
    assert run_demo_uninstall("react", number_override="1,2") == []


if __name__ == "__main__":
    test_npm_uninstall_arguments_and_scope()
    test_confirmation_runs_one_global_uninstall()
    test_confirmation_runs_local_first_for_both_scopes()
    test_mismatched_name_cancels_without_running_npm()
    test_non_y_and_multiple_numbers_cancel_without_running_npm()
    print("OK")
