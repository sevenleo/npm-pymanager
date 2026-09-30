"""Verificacoes focadas para a coleta progressiva e os tamanhos."""
import io
import json
import os
import queue
import sys
import tempfile
import threading
import time
from contextlib import redirect_stdout
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import main


def test_packages_render_before_enrichment_finishes():
    """Confirma IDs estaveis e status pendente antes dos trabalhos lentos."""
    results = queue.Queue()
    updates_started = threading.Event()
    sizes_started = threading.Event()
    release_updates = threading.Event()
    release_sizes = threading.Event()
    original_list = main._npm_list_result
    original_outdated = main._npm_outdated_result
    original_sizes = main.collect_sizes

    def fake_list(global_mode=False):
        if global_mode:
            return {"global-b": {"version": "2.0"}}, True, False
        return {"local-a": {"version": "1.0"}}, True, False

    def fake_outdated(global_mode=False):
        updates_started.set()
        release_updates.wait(5)
        return {}, True, False

    def fake_sizes(local, global_, names, cancel_event=None, on_result=None):
        sizes_started.set()
        if on_result:
            on_result(("global", "global-b"), "8.0B")
        release_sizes.wait(5)
        return {("global", "global-b"): "8.0B"}

    main._npm_list_result = fake_list
    main._npm_outdated_result = fake_outdated
    main.collect_sizes = fake_sizes
    collection = None
    try:
        collection = main._new_collection(50, results)
        deadline = time.monotonic() + 5
        while not collection["rows_ready"]:
            remaining = deadline - time.monotonic()
            assert remaining > 0, "installed package listings did not finish"
            event = results.get(timeout=remaining)
            results.put(event)
            main._apply_collection_events(collection, results)

        assert updates_started.wait(2)
        assert sizes_started.wait(2)
        rows = main._refresh_rows(collection)
        assert [row["name"] for row in rows] == ["global-b", "local-a"]
        assert [row["id"] for row in rows] == [1, 2]
        assert collection["size_state"] == "pending"
        assert main.status_label_key(rows[0]) == "checking"

        deadline = time.monotonic() + 2
        while ("global", "global-b") not in collection["size_map"]:
            remaining = deadline - time.monotonic()
            assert remaining > 0, "completed package size was not published"
            event = results.get(timeout=remaining)
            results.put(event)
            main._apply_collection_events(collection, results)
        partial_rows = main._refresh_rows(collection)
        assert partial_rows[0]["size"] == "8.0B"
        assert not partial_rows[0]["size_pending"]
        assert partial_rows[1]["size_pending"]
        assert not main._collection_done(collection)

        release_updates.set()
        release_sizes.set()
        deadline = time.monotonic() + 5
        while not main._collection_done(collection):
            remaining = deadline - time.monotonic()
            assert remaining > 0, "background enrichment did not finish"
            event = results.get(timeout=remaining)
            results.put(event)
            main._apply_collection_events(collection, results)

        final_rows = main._refresh_rows(collection)
        assert [row["id"] for row in final_rows] == [1, 2]
        assert all(main.status_label_key(row) == "ok" for row in final_rows)
    finally:
        release_updates.set()
        release_sizes.set()
        main._npm_list_result = original_list
        main._npm_outdated_result = original_outdated
        main.collect_sizes = original_sizes


def test_failed_update_check_is_not_marked_healthy():
    """Falha na verificacao deve aparecer como desconhecida."""
    rows = main.build_rows(
        {"local-a": {"version": "1.0"}},
        {},
        {},
        {},
        size_map={},
        check_states={"outdated_local": "failed"},
    )
    assert main.status_label_key(rows[0]) == "unknown"
    assert main._update_action_state({
        "states": {
            "local": "ready",
            "global": "ready",
            "outdated_local": "failed",
            "outdated_global": "ready",
        }
    }) == "failed"


def test_clear_does_not_emit_terminal_control_for_redirected_output():
    """Saida redirecionada nao recebe sequencias para limpar o terminal."""
    output = io.StringIO()
    with redirect_stdout(output):
        main.clear()
    assert output.getvalue() == ""


def test_pending_status_renders_in_every_locale_and_layout():
    """Confirma mensagens pendentes nos tres modos de tabela e idiomas."""
    original_strings = main.STRINGS
    locale_paths = [Path(main.LOCALES_DIR, name) for name in (
        "en.json", "pt.json", "es.json"
    )]
    try:
        locales = [json.loads(path.read_text(encoding="utf-8"))
                   for path in locale_paths]
        assert all(set(locale) == set(locales[0]) for locale in locales)
        rows = main.build_rows(
            {"local-a": {"version": "1.0"}}, {}, {}, {},
            size_map={}, check_states={"outdated_local": "pending"},
            size_pending=True,
        )
        for strings in locales:
            main.STRINGS = strings
            for width in (40, 70, 100):
                output = io.StringIO()
                with redirect_stdout(output):
                    main.print_header(rows, width)
                    main.print_table_responsive(rows, width)
                rendered = output.getvalue()
                assert strings["checking_version"] in rendered, (width, rendered)
                assert strings["status_checking"] in rendered, (width, rendered)
                if width != 70:
                    assert strings["measuring_size"] in rendered, (width, rendered)
    finally:
        main.STRINGS = original_strings


def test_global_root_is_resolved_once_for_size_workers():
    """Todos os pacotes globais compartilham uma unica raiz npm."""
    calls = []
    original_root = main.npm_root
    names = [
        "progressive-root-check-{}-{}".format(os.getpid(), suffix)
        for suffix in ("one", "two")
    ]
    try:
        with tempfile.TemporaryDirectory() as root:
            for name in names:
                package_path = Path(root, name)
                package_path.mkdir()
                package_path.joinpath("file.txt").write_bytes(b"1234")

            main.npm_root = lambda global_mode=False: calls.append(global_mode) or root
            main.SIZE_CACHE.clear()
            packages = {name: {"version": "1.0"} for name in names}
            sizes = main.collect_sizes({}, packages, names)
            assert calls == [True]
            assert all(sizes[("global", name)] == "4.0B" for name in names)
    finally:
        main.npm_root = original_root
        for name in names:
            main.SIZE_CACHE.pop((True, name, "1.0"), None)


def test_cancelled_sizes_finish_before_the_next_collection():
    """Refresh aguarda o cancelamento e descarta resultados de ciclos antigos."""
    results = queue.Queue()
    first_size_started = threading.Event()
    second_size_started = threading.Event()
    release_second = threading.Event()
    size_calls = []
    original_list = main._npm_list_result
    original_outdated = main._npm_outdated_result
    original_sizes = main.collect_sizes

    def fake_list(global_mode=False):
        return {"global-a": {"version": "1.0"}}, True, False

    def fake_outdated(global_mode=False):
        return {}, True, False

    def fake_sizes(local, global_, names, cancel_event=None, on_result=None):
        size_calls.append(len(size_calls) + 1)
        if len(size_calls) == 1:
            first_size_started.set()
            cancel_event.wait(5)
        else:
            second_size_started.set()
            release_second.wait(5)
        return {}

    def process_until(collection, predicate):
        deadline = time.monotonic() + 5
        while not predicate():
            remaining = deadline - time.monotonic()
            assert remaining > 0, "collection state did not advance"
            event = results.get(timeout=remaining)
            results.put(event)
            main._apply_collection_events(collection, results)

    main._npm_list_result = fake_list
    main._npm_outdated_result = fake_outdated
    main.collect_sizes = fake_sizes
    try:
        first = main._new_collection(60, results)
        process_until(first, lambda: first["rows_ready"])
        assert first_size_started.wait(2)
        first["cancel"].set()
        process_until(first, lambda: main._collection_done(first))

        second = main._new_collection(61, results)
        process_until(second, lambda: second["rows_ready"])
        assert second_size_started.wait(2)
        results.put((60, "sizes_done", {("global", "global-a"): "stale"}))
        main._apply_collection_events(second, results)
        assert second["size_state"] == "pending"
        assert not second["size_map"]

        release_second.set()
        process_until(second, lambda: main._collection_done(second))
        assert len(size_calls) == 2
    finally:
        release_second.set()
        main._npm_list_result = original_list
        main._npm_outdated_result = original_outdated
        main.collect_sizes = original_sizes


if __name__ == "__main__":
    test_packages_render_before_enrichment_finishes()
    test_failed_update_check_is_not_marked_healthy()
    test_clear_does_not_emit_terminal_control_for_redirected_output()
    test_pending_status_renders_in_every_locale_and_layout()
    test_global_root_is_resolved_once_for_size_workers()
    test_cancelled_sizes_finish_before_the_next_collection()
    print("OK: progressive loading checks passed")
