"""Verificacoes focadas para o modo CLI."""
from contextlib import redirect_stderr, redirect_stdout
import io
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import main

main._load_locale("en")


def _patch(values):
    """Substitui atributos de main e devolve os valores originais."""
    originals = {name: getattr(main, name) for name in values}
    for name, value in values.items():
        setattr(main, name, value)
    return originals


def _restore(originals):
    for name, value in originals.items():
        setattr(main, name, value)


def _capture_main(argv, stdin_text="", demo=True, npm_results=None, tty_keys=None):
    """Executa main.main com entradas controladas.

    Args:
        argv: argumentos do CLI
        stdin_text: conteudo lido pelas confirmacoes
        demo: True usa as linhas ficticias
        npm_results: funcao opcional que decide o resultado de cada npm
        tty_keys: teclas simuladas quando o stdin deve parecer um terminal

    Returns:
        tupla (code, stdout, stderr, calls)
    """
    calls = []
    entered = []
    old_stdin = sys.stdin
    out, err = io.StringIO(), io.StringIO()

    def _run_npm(args):
        calls.append(args)
        if npm_results is None:
            return True
        return npm_results(args)

    patches = {
        "DEMO_MODE": demo,
        "npm_available": lambda: True,
        "run_npm_cmd": _run_npm,
        "run_interactive": lambda: entered.append(True),
    }
    if tty_keys is not None:
        queue = list(tty_keys)

        def _key():
            assert queue, "CLI read more keys than expected"
            return queue.pop(0)

        patches["get_key"] = _key

    originals = _patch(patches)
    sys.stdin = _FakeTTY(stdin_text) if tty_keys is not None else io.StringIO(stdin_text)
    try:
        with redirect_stdout(out), redirect_stderr(err):
            code = main.main(argv)
    finally:
        sys.stdin = old_stdin
        _restore(originals)
    assert not entered, "CLI must not start the interactive mode"
    return code, out.getvalue(), err.getvalue(), calls


def _run_cli_with_snapshot(snapshot, npm=True, request=None):
    """Executa run_cli com uma coleta simulada e npm proibido por padrao."""
    request = request or {
        "action": "list",
        "package_name": None,
        "scope": None,
        "assume_yes": False,
    }
    originals = _patch({
        "DEMO_MODE": False,
        "npm_available": lambda: npm,
        "collect_cli_snapshot": lambda action, scope=None: snapshot,
        "run_npm_cmd": lambda args: (_ for _ in ()).throw(
            AssertionError("must not run npm")
        ),
    })
    out, err = io.StringIO(), io.StringIO()
    try:
        with redirect_stdout(out), redirect_stderr(err):
            code = main.run_cli(request)
    finally:
        _restore(originals)
    return code, out.getvalue(), err.getvalue()


def _confirm(text):
    """Executa confirm_cli com stdin controlado."""
    old_stdin = sys.stdin
    err = io.StringIO()
    sys.stdin = io.StringIO(text)
    try:
        with redirect_stderr(err):
            result = main.confirm_cli("Question? ")
    finally:
        sys.stdin = old_stdin
    return result, err.getvalue()


def test_parse_actions():
    assert main.parse_cli_args(["--list"]) == {
        "action": "list",
        "package_name": None,
        "scope": None,
        "assume_yes": False,
    }
    assert main.parse_cli_args(["--update-all"])["action"] == "update_all"
    assert main.parse_cli_args(["--update"]) == {
        "action": "update_select",
        "package_name": None,
        "scope": None,
        "assume_yes": False,
    }
    assert main.parse_cli_args(["--update", ""])["action"] == "update_select"
    assert main.parse_cli_args(["--update", "--scope", "local"]) == {
        "action": "update_select",
        "package_name": None,
        "scope": "LOCAL",
        "assume_yes": False,
    }
    assert main.parse_cli_args(["--update", "react"]) == {
        "action": "update_one",
        "package_name": "react",
        "scope": None,
        "assume_yes": False,
    }
    request = main.parse_cli_args(
        ["--uninstall", "@scope/pkg", "--scope", "global", "--yes"]
    )
    assert request["action"] == "uninstall"
    assert request["package_name"] == "@scope/pkg"
    assert request["scope"] == "GLOBAL"
    assert request["assume_yes"] is True
    assert main.parse_cli_args(["--scope", "local"])["action"] is None
    assert main.parse_cli_args([]) is None
    assert main.parse_cli_args(["--test"]) is None
    assert main.parse_cli_args(["--no-color"]) is None


def test_parse_rejects_invalid_usage():
    cases = [
        ["--list", "--update-all"],
        ["--list", "--update", "react"],
        ["--update", "react", "--uninstall", "lodash"],
        ["--scope", "bogus"],
        ["--list", "extra"],
    ]
    for argv in cases:
        try:
            with redirect_stderr(io.StringIO()):
                main.parse_cli_args(argv)
        except SystemExit as exc:
            assert exc.code == 2, argv
        else:
            raise AssertionError("expected usage error: %r" % (argv,))


def test_validate_cli_request():
    base = {"package_name": None, "scope": None, "assume_yes": False}
    assert main.validate_cli_request(dict(base, action=None)) is not None
    assert main.validate_cli_request(dict(base, action="list")) is None
    assert main.validate_cli_request(
        dict(base, action="list", scope="LOCAL")
    ) is not None
    assert main.validate_cli_request(
        dict(base, action="update_all", scope="GLOBAL")
    ) is None
    assert main.validate_cli_request(
        dict(base, action="update_select")
    ) is None
    assert main.validate_cli_request(
        dict(base, action="update_select", scope="LOCAL")
    ) is None
    assert main.validate_cli_request(
        dict(base, action="update_one", package_name="")
    ) is not None
    assert main.validate_cli_request(
        dict(base, action="uninstall", package_name="")
    ) is not None
    assert main.validate_cli_request(
        dict(base, action="uninstall", package_name="42")
    ) is not None
    assert main.validate_cli_request(
        dict(base, action="update_one", package_name=" react")
    ) is not None
    assert main.validate_cli_request(
        dict(base, action="update_one", package_name="react")
    ) is None


def test_resolve_exact_name_and_scope():
    rows = main.collect_rows_demo()

    target, error = main.resolve_cli_target("react", None, rows)
    assert error is None and target["scope"] == "GLOBAL"

    target, error = main.resolve_cli_target("lodash", None, rows)
    assert error is None and target["scope"] == "LOCAL"

    assert main.resolve_cli_target("lod", None, rows) == (None, "not_found")
    assert main.resolve_cli_target("React", None, rows) == (None, "not_found")
    assert main.resolve_cli_target("typescript", None, rows) == (None, "scope")

    target, error = main.resolve_cli_target("typescript", "GLOBAL", rows)
    assert error is None and target["scope"] == "GLOBAL"

    assert main.resolve_cli_target("react", "LOCAL", rows) == (
        None, "not_found"
    )


def test_resolve_preserves_scoped_names():
    rows = [{
        "name": "@scope/pkg",
        "lver": "1.0.0",
        "gver": "",
        "lnew": "",
        "gnew": "",
        "local_outdated": False,
        "global_outdated": False,
    }]
    target, error = main.resolve_cli_target("@scope/pkg", None, rows)
    assert error is None and target["scope"] == "LOCAL"
    assert main.resolve_cli_target("@scope/Pkg", None, rows) == (
        None, "not_found"
    )


def test_confirm_cli_reads_explicit_answer():
    assert _confirm("y\n") == (True, "Question? ")
    assert _confirm("YES\n")[0] is True
    assert _confirm(" y \n")[0] is True
    for text in ("n\n", "\n", "", "s\n", "no\n", "yes please\n"):
        outcome, _ = _confirm(text)
        assert outcome is False, text


def test_usage_error_returns_two():
    code, out, err, calls = _capture_main(["--scope", "local"])
    assert code == 2 and calls == []
    assert "choose an action" in err

    code, out, err, calls = _capture_main(["--list", "--scope", "local"])
    assert code == 2 and calls == []
    assert "--scope" in err


def test_list_is_read_only():
    code, out, err, calls = _capture_main(["--list"])
    assert code == 0
    assert calls == []
    assert "react" in out
    assert "update" in out
    assert err == ""


def test_update_one_exact_name():
    code, out, err, calls = _capture_main(["--update", "express"])
    assert code == 0
    assert calls == [["npm", "update", "express"]]
    assert "express" in out

    code, out, err, calls = _capture_main(["--update", "react"])
    assert code == 0 and calls == []
    assert "already up to date" in out

    code, out, err, calls = _capture_main(["--update", "nope"])
    assert code == 3 and calls == []
    assert "not found" in err

    code, out, err, calls = _capture_main(["--update", "typescript"])
    assert code == 4 and calls == []
    assert "both scopes" in err


def test_update_failure_is_non_zero():
    code, out, err, calls = _capture_main(
        ["--update", "left-pad"], npm_results=lambda args: False
    )
    assert code == 1
    assert calls == [["npm", "update", "-g", "left-pad"]]
    assert "failed" in err.lower()


def test_uninstall_requires_confirmation():
    code, out, err, calls = _capture_main(
        ["--uninstall", "react"], stdin_text="n\n"
    )
    assert code == 5 and calls == []
    assert "Uninstall exactly" in err
    assert "cancelled" in out.lower()

    code, out, err, calls = _capture_main(
        ["--uninstall", "react"], stdin_text="y\n"
    )
    assert code == 0
    assert calls == [["npm", "uninstall", "-g", "react"]]


def test_yes_never_bypasses_uninstall_confirmation():
    code, out, err, calls = _capture_main(
        ["--uninstall", "react", "--yes"], stdin_text="n\n"
    )
    assert code == 5 and calls == []
    assert "[y/N]" in err


def test_uninstall_rejects_row_numbers_and_partial_names():
    code, out, err, calls = _capture_main(["--uninstall", "2"])
    assert code == 2 and calls == []
    assert "row number" in err

    code, out, err, calls = _capture_main(
        ["--uninstall", "reac"], stdin_text="y\n"
    )
    assert code == 3 and calls == []


def test_uninstall_ambiguous_scope_needs_flag():
    code, out, err, calls = _capture_main(
        ["--uninstall", "typescript"], stdin_text="y\n"
    )
    assert code == 4 and calls == []
    assert "--scope" in err

    code, out, err, calls = _capture_main(
        ["--uninstall", "typescript", "--scope", "global"], stdin_text="y\n"
    )
    assert code == 0
    assert calls == [["npm", "uninstall", "-g", "typescript"]]


def test_update_all_prompt_and_yes():
    code, out, err, calls = _capture_main(["--update-all"], stdin_text="n\n")
    assert code == 5 and calls == []
    assert "[y/N]" in err

    code, out, err, calls = _capture_main(["--update-all"], stdin_text="y\n")
    assert code == 0 and calls
    assert "[y/N]" in err

    code, out, err, calls = _capture_main(
        ["--update-all", "--yes"], stdin_text=""
    )
    assert code == 0 and calls
    assert "[y/N]" not in err


def test_update_all_collects_all_failures():
    code, out, err, calls = _capture_main(
        ["--update-all", "--yes"], npm_results=lambda args: False
    )
    assert code == 1
    assert calls
    assert "failed" in err.lower()


def test_update_all_scope_limits_tasks():
    code, out, err, calls = _capture_main(
        ["--update-all", "--yes", "--scope", "local"]
    )
    assert code == 0
    assert calls
    assert all("-g" not in args for args in calls)


def test_outdated_entries_order_and_fields():
    originals = _patch({"DEMO_MODE": True})
    try:
        snapshot = main.collect_cli_snapshot("update_select")
        scoped_snapshot = main.collect_cli_snapshot("update_select", "GLOBAL")
    finally:
        _restore(originals)
    entries = main._cli_outdated_entries(snapshot)
    assert [
        (entry["number"], entry["name"], entry["scope"])
        for entry in entries
    ] == [
        (1, "a-very-long-package-name-for-truncation-demo", "LOCAL"),
        (2, "axios", "GLOBAL"),
        (3, "chalk", "LOCAL"),
        (4, "chalk", "GLOBAL"),
        (5, "commander", "LOCAL"),
        (6, "express", "LOCAL"),
        (7, "left-pad", "GLOBAL"),
    ]
    assert entries[2]["current"] == "4.1.2"
    assert entries[2]["latest"] == "5.3.0"

    scoped = main._cli_outdated_entries(scoped_snapshot)
    assert [entry["name"] for entry in scoped] == ["axios", "chalk", "left-pad"]
    assert all(entry["scope"] == "GLOBAL" for entry in scoped)


def test_parse_cli_selection_accepts_numbers_and_keywords():
    assert main.parse_cli_selection("1", 3) == ([0], None)
    assert main.parse_cli_selection("2,1", 3) == ([0, 1], None)
    assert main.parse_cli_selection(" 3 , 1 ", 3) == ([0, 2], None)
    assert main.parse_cli_selection("2,2", 3) == ([1], None)
    assert main.parse_cli_selection("A", 3) == ([0, 1, 2], None)
    assert main.parse_cli_selection("all", 2) == ([0, 1], None)


def test_parse_cli_selection_cancel_and_invalid():
    for text in ("", "  ", "q", "Q", "quit", None):
        assert main.parse_cli_selection(text, 3) == (None, None), text
    for text in ("0", "4", "-1", "x", "1,a", "1,,2", "1.5"):
        assert main.parse_cli_selection(text, 3) == (None, "invalid"), text


def test_update_select_lists_table_and_prompts_on_stderr():
    code, out, err, calls = _capture_main(["--update"], stdin_text="q\n")
    assert code == 5 and calls == []
    assert "npm-pymanager" not in out
    assert "Outdated packages" not in out
    assert "Collecting package information...\n\n  #  package" in out
    assert "current  >  latest" in out
    assert (
        "  1  a-very-long-package-name-for-truncation-demo  local   2.0.1"
        "    >  2.1.0"
    ) in out
    assert "  7  left-pad" in out
    assert "Select packages to update:" in out
    assert "[a]ll" in out and "[q]uit" in out
    assert err == "  > "
    assert "\x1b" not in out


class _FakeTTY(io.StringIO):
    """StringIO que se identifica como terminal."""

    def isatty(self):
        return True


def _read_choice(keys, stdin_text=""):
    """Executa read_cli_choice com teclas e terminal simulados.

    Args:
        keys: teclas devolvidas por get_key, na ordem
        stdin_text: restante da linha lido por readline

    Returns:
        tupla (answer, stderr)
    """
    queue = list(keys)
    old_stdin = sys.stdin
    err = io.StringIO()

    def _key():
        assert queue, "read_cli_choice leu mais teclas que o esperado"
        return queue.pop(0)

    originals = _patch({"get_key": _key})
    sys.stdin = _FakeTTY(stdin_text)
    try:
        with redirect_stderr(err):
            answer = main.read_cli_choice("  > ")
    finally:
        sys.stdin = old_stdin
        _restore(originals)
    return answer, err.getvalue()


def test_read_cli_choice_letters_act_immediately():
    answer, err = _read_choice(["q"])
    assert answer == "q"
    assert err == "  > q\n"
    assert _read_choice(["A"])[0] == "a"
    assert _read_choice(["Q"])[0] == "q"


def test_read_cli_choice_enter_and_specials():
    assert _read_choice(["\n"])[0] == ""
    assert _read_choice(["\r"])[0] == ""
    assert _read_choice(["", "x"])[0] == "x"
    assert _read_choice(["\x03"])[0] is None


def test_read_cli_choice_digits_keep_reading_line():
    assert _read_choice(["1"], stdin_text="3\n")[0] == "13"
    assert _read_choice([","], stdin_text="2\n")[0] == ",2"


def test_read_cli_choice_falls_back_to_readline_when_piped():
    err = io.StringIO()
    old_stdin = sys.stdin
    originals = _patch({
        "get_key": lambda: (_ for _ in ()).throw(
            AssertionError("piped input must not use get_key")
        ),
    })
    sys.stdin = io.StringIO("a\n")
    try:
        with redirect_stderr(err):
            answer = main.read_cli_choice("  > ")
    finally:
        sys.stdin = old_stdin
        _restore(originals)
    assert answer == "a"
    assert err.getvalue() == "  > "


def test_update_select_answers_single_key_on_terminal():
    code, out, err, calls = _capture_main(["--update"], tty_keys=["q"])
    assert code == 5 and calls == []
    assert err == "  > q\n"

    code, out, err, calls = _capture_main(["--update"], tty_keys=["a"])
    assert code == 0 and len(calls) == 7
    assert "7 succeeded, 0 failed" in out

    code, out, err, calls = _capture_main(
        ["--update"], tty_keys=["2"], stdin_text="\n"
    )
    assert code == 0
    assert calls == [["npm", "update", "-g", "axios"]]


def _render_selection(unicode_ok):
    entries = [
        {
            "number": 1, "name": "axios", "scope": "GLOBAL",
            "current": "1.6.0", "latest": "1.7.4",
        },
        {
            "number": 2, "name": "jsdom", "scope": "LOCAL",
            "current": "30.1.3", "latest": "31.0.1",
        },
    ]
    originals = _patch({"_detect_unicode": lambda: unicode_ok})
    buffer = io.StringIO()
    old_stdout = sys.stdout
    sys.stdout = buffer
    try:
        main.render_cli_selection(entries)
    finally:
        sys.stdout = old_stdout
        _restore(originals)
    return buffer.getvalue().split("\n")


def test_selection_renders_unicode_table():
    lines = _render_selection(True)
    assert lines[0] == "  #  package  scope   current  →  latest"
    assert lines[1].startswith("  _  _")
    assert set(lines[1].replace(" ", "")) == {"_"}
    assert lines[2] == "  1  axios    global  1.6.0    →  1.7.4"
    assert lines[3] == "  2  jsdom    local   30.1.3   →  31.0.1"
    assert lines[4] == ""
    assert lines[5] == "  Select packages to update:"
    assert "npm-pymanager" not in "\n".join(lines)
    assert "Outdated packages" not in "\n".join(lines)
    assert all(line == line.rstrip() for line in lines)


def test_selection_renders_ascii_table():
    lines = _render_selection(False)
    assert lines[0] == "  #  package  scope   current  >  latest"
    assert lines[1].startswith("  _  _")
    assert set(lines[1].replace(" ", "")) == {"_"}
    assert lines[2] == "  1  axios    global  1.6.0    >  1.7.4"
    assert lines[3] == "  2  jsdom    local   30.1.3   >  31.0.1"
    assert "npm-pymanager" not in "\n".join(lines)
    assert "→" not in "\n".join(lines)
    assert all(line == line.rstrip() for line in lines)


def test_list_renders_lowercase_headers_without_panel():
    code, out, err, calls = _capture_main(["--list"])
    assert code == 0 and calls == []
    assert "npm-pymanager" not in out
    assert "Collecting package information...\n\n  package" in out
    assert "  package" in out
    assert "scope" in out and "status" in out
    assert "PACKAGE" not in out
    assert "\x1b" not in out


def test_update_select_runs_only_chosen_numbers():
    code, out, err, calls = _capture_main(["--update"], stdin_text="2,1\n")
    assert code == 0
    assert calls == [
        ["npm", "update", "a-very-long-package-name-for-truncation-demo"],
        ["npm", "update", "-g", "axios"],
    ]
    assert "2 succeeded, 0 failed" in out


def test_update_select_all_and_invalid_and_empty_input():
    code, out, err, calls = _capture_main(["--update"], stdin_text="a\n")
    assert code == 0 and len(calls) == 7

    code, out, err, calls = _capture_main(["--update"], stdin_text="")
    assert code == 5 and calls == []

    code, out, err, calls = _capture_main(["--update"], stdin_text="9\n")
    assert code == 2 and calls == []
    assert "invalid selection" in err


def test_update_select_scope_limits_list_and_tasks():
    code, out, err, calls = _capture_main(
        ["--update", "--scope", "global"], stdin_text="a\n"
    )
    assert code == 0
    assert calls and all("-g" in args for args in calls)
    assert "(LOCAL)" not in out


def test_update_select_ignores_yes():
    code, out, err, calls = _capture_main(
        ["--update", "--yes"], stdin_text="1\n"
    )
    assert code == 0
    assert calls == [
        ["npm", "update", "a-very-long-package-name-for-truncation-demo"]
    ]


def test_update_select_reports_failure():
    code, out, err, calls = _capture_main(
        ["--update"], stdin_text="7\n", npm_results=lambda args: False
    )
    assert code == 1
    assert calls == [["npm", "update", "-g", "left-pad"]]
    assert "failed" in err.lower()


def test_update_select_without_outdated_exits_zero():
    empty = {
        "rows": [],
        "outdated_local": {},
        "outdated_global": {},
        "checks": {},
        "timed_out": False,
        "failed": False,
    }
    request = {
        "action": "update_select",
        "package_name": None,
        "scope": None,
        "assume_yes": False,
    }
    code, out, err = _run_cli_with_snapshot(empty, request=request)
    assert code == 0
    assert "no packages to update" in out


def test_update_progress_spinner_only_on_terminal():
    class _Tty(io.StringIO):
        def isatty(self):
            return True

    def _run(tty):
        buffer = _Tty() if tty else io.StringIO()
        originals = _patch({
            "DEMO_MODE": True,
            "run_npm_cmd": lambda args: True,
        })
        old_stdout = sys.stdout
        sys.stdout = buffer
        try:
            main.run_cli_tasks([("LOCAL", "react")])
        finally:
            sys.stdout = old_stdout
            _restore(originals)
        return buffer.getvalue()

    animated = _run(True)
    assert "LOCAL: react" in animated
    assert "\r" in animated

    plain = _run(False)
    assert "\r" not in plain
    assert plain == (
        "Updating LOCAL: react\n"
        "Update completed: react (LOCAL)\n"
    )


def test_collection_exit_codes():
    empty = {
        "rows": [],
        "outdated_local": {},
        "outdated_global": {},
        "checks": {},
        "timed_out": False,
        "failed": False,
    }
    assert _run_cli_with_snapshot(dict(empty, timed_out=True))[0] == 124
    assert _run_cli_with_snapshot(dict(empty, failed=True))[0] == 6
    assert _run_cli_with_snapshot(empty)[0] == 0
    assert _run_cli_with_snapshot(empty, npm=False)[0] == 1


def test_collection_failure_blocks_mutation():
    snapshot = {
        "rows": [],
        "outdated_local": {},
        "outdated_global": {},
        "checks": {},
        "timed_out": False,
        "failed": True,
    }
    request = {
        "action": "update_all",
        "package_name": None,
        "scope": None,
        "assume_yes": True,
    }
    code, out, err = _run_cli_with_snapshot(snapshot, request=request)
    assert code == 6
    assert "could not be collected" in err


def test_help_and_version_exit_zero():
    for flag, expected in (
        ("--help", "usage:"),
        ("--version", "npm-pymanager"),
    ):
        out, err = io.StringIO(), io.StringIO()
        try:
            with redirect_stdout(out), redirect_stderr(err):
                main.main([flag])
        except SystemExit as exc:
            assert exc.code == 0, flag
        else:
            raise AssertionError("expected SystemExit for %s" % flag)
        assert expected in out.getvalue(), flag


def test_no_action_starts_interactive():
    entered = []
    originals = _patch({"run_interactive": lambda: entered.append(True)})
    try:
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            assert main.main([]) == 0
            assert main.main(["--test"]) == 0
            assert main.main(["--no-color"]) == 0
    finally:
        _restore(originals)
    assert entered == [True, True, True]


if __name__ == "__main__":
    test_parse_actions()
    test_parse_rejects_invalid_usage()
    test_validate_cli_request()
    test_resolve_exact_name_and_scope()
    test_resolve_preserves_scoped_names()
    test_confirm_cli_reads_explicit_answer()
    test_usage_error_returns_two()
    test_list_is_read_only()
    test_update_one_exact_name()
    test_update_failure_is_non_zero()
    test_uninstall_requires_confirmation()
    test_yes_never_bypasses_uninstall_confirmation()
    test_uninstall_rejects_row_numbers_and_partial_names()
    test_uninstall_ambiguous_scope_needs_flag()
    test_update_all_prompt_and_yes()
    test_update_all_collects_all_failures()
    test_update_all_scope_limits_tasks()
    test_outdated_entries_order_and_fields()
    test_parse_cli_selection_accepts_numbers_and_keywords()
    test_parse_cli_selection_cancel_and_invalid()
    test_update_select_lists_table_and_prompts_on_stderr()
    test_read_cli_choice_letters_act_immediately()
    test_read_cli_choice_enter_and_specials()
    test_read_cli_choice_digits_keep_reading_line()
    test_read_cli_choice_falls_back_to_readline_when_piped()
    test_update_select_answers_single_key_on_terminal()
    test_selection_renders_unicode_table()
    test_selection_renders_ascii_table()
    test_list_renders_lowercase_headers_without_panel()
    test_update_select_runs_only_chosen_numbers()
    test_update_select_all_and_invalid_and_empty_input()
    test_update_select_scope_limits_list_and_tasks()
    test_update_select_ignores_yes()
    test_update_select_reports_failure()
    test_update_select_without_outdated_exits_zero()
    test_update_progress_spinner_only_on_terminal()
    test_collection_exit_codes()
    test_collection_failure_blocks_mutation()
    test_help_and_version_exit_zero()
    test_no_action_starts_interactive()
    print("OK")