"""Verificacoes focadas de isolamento do modo de teste (--test)."""
from contextlib import redirect_stdout
import io
from pathlib import Path
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import main


def _boom_run(*args, **kwargs):
    raise AssertionError("coleta real de npm disparada em modo demo")


def _boom_collection(*args, **kwargs):
    raise AssertionError("start_fetch real disparado em modo demo")


def _boom_subprocess(*args, **kwargs):
    raise AssertionError("subprocess real disparado em modo demo")


def run_demo_update(choices, keys="", input_line=None):
    """Executa sessao demo com entradas controladas e stdout capturado."""
    originals = {
        "DEMO_MODE": main.DEMO_MODE,
        "DELAY": main.DELAY,
        "load_language": main.load_language,
        "get_key": main.get_key,
        "get_key_timeout": main.get_key_timeout,
        "_read_input_line": main._read_input_line,
        "start_spinner": main.start_spinner,
        "stop_spinner": main.stop_spinner,
        "run": main.run,
        "_new_collection": main._new_collection,
    }
    process_run = subprocess.run
    key_iter = iter(keys)
    choice_iter = iter(choices)

    main.DEMO_MODE = True
    main.DELAY = 0
    main.load_language = lambda: None
    main.get_key = lambda: next(key_iter, "y")
    main.get_key_timeout = lambda timeout=None: next(choice_iter)
    main._read_input_line = lambda initial="": (
        input_line if input_line is not None else initial
    )
    main.start_spinner = lambda message: None
    main.stop_spinner = lambda handle: None
    main.run = _boom_run
    main._new_collection = _boom_collection
    subprocess.run = _boom_subprocess

    buffer = io.StringIO()
    try:
        with redirect_stdout(buffer):
            main.main()
    finally:
        subprocess.run = process_run
        for name, value in originals.items():
            setattr(main, name, value)
    return buffer.getvalue()


def assert_final_status(output, package, status_key):
    """Confirma o status do pacote no ultimo desenho da tabela."""
    idx = output.rfind(package)
    assert idx >= 0, f"{package} ausente do desenho final"
    window = output[max(0, idx - 160):idx]
    assert status_key in window, (
        f"{package} sem {status_key} no ultimo desenho:\n"
        f"{output[-1200:]}"
    )


def test_run_retorna_vazio_no_demo_mesmo_chamado_direto():
    original_mode = main.DEMO_MODE
    process_run = subprocess.run
    main.DEMO_MODE = True
    subprocess.run = _boom_subprocess
    try:
        assert main.run("npm list --depth=0 --json") == ""
    finally:
        subprocess.run = process_run
        main.DEMO_MODE = original_mode


def test_collect_rows_demo_marca_escopo_atualizado():
    rows = main.collect_rows_demo(updated={("chalk", "LOCAL")})
    chalk = next(row for row in rows if row["name"] == "chalk")
    assert chalk["lver"] == "5.3.0"
    assert chalk["lnew"] == ""
    assert chalk["local_outdated"] is False
    assert chalk["global_outdated"] is True
    assert chalk["gnew"] == "5.3.0"


def test_demo_uninstall_preserva_atualizados_marcados():
    rows = main.collect_rows_demo(
        {("axios", "GLOBAL")}, {("chalk", "LOCAL")}
    )
    names = [row["name"] for row in rows]
    assert "axios" not in names
    chalk = next(row for row in rows if row["name"] == "chalk")
    assert chalk["lver"] == "5.3.0"
    assert chalk["local_outdated"] is False


def test_update_all_demo_nunca_sai_do_modo_teste():
    out = run_demo_update(("a", "q"), keys="y")
    assert "demo_mode" in out
    assert_final_status(out, "chalk", "status_ok")
    assert_final_status(out, "left-pad", "status_update")


def test_update_one_demo_nunca_sai_do_modo_teste():
    out = run_demo_update(("3", "q"), input_line="3")
    assert "demo_mode" in out
    assert_final_status(out, "chalk", "status_ok")
    assert_final_status(out, "left-pad", "status_update")


def test_refresh_demo_nao_coleta_real():
    out = run_demo_update(("r", "q"))
    assert "demo_mode" in out


if __name__ == "__main__":
    test_run_retorna_vazio_no_demo_mesmo_chamado_direto()
    test_collect_rows_demo_marca_escopo_atualizado()
    test_demo_uninstall_preserva_atualizados_marcados()
    test_update_all_demo_nunca_sai_do_modo_teste()
    test_update_one_demo_nunca_sai_do_modo_teste()
    test_refresh_demo_nao_coleta_real()
    print("OK")
