from contextlib import redirect_stdout
import io
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import main


def read_with_keys(keys, initial=""):
    original_get_key = main.get_key
    main.get_key = lambda: next(keys)
    output = io.StringIO()
    try:
        with redirect_stdout(output):
            value = main._read_input_line(initial)
    finally:
        main.get_key = original_get_key
    return value, output.getvalue()


def test_backspace_edits_input_and_echo():
    value, output = read_with_keys(
        iter(["\x7f", "3", ",", "x", "\x08", "2", "\r"]),
        initial="1",
    )
    assert value == "3,2"
    assert output == "1\b \b3,x\b \b2\n"

    value, output = read_with_keys(iter(["\x08", "3", "\r"]))
    assert value == "3"
    assert output == "3\n"


def test_package_selection_is_validated_before_use():
    rows = [{"id": number} for number in range(1, 7)]
    selected = main._selected_rows_from_input("1, 3,5,3,6", rows)
    assert [row["id"] for row in selected] == [1, 3, 5, 6]
    assert main._selected_rows_from_input("1,x", rows) is None
    assert main._selected_rows_from_input("1,,3", rows) is None
    assert main._selected_rows_from_input("1,99", rows) is None


if __name__ == "__main__":
    test_backspace_edits_input_and_echo()
    test_package_selection_is_validated_before_use()
    print("OK")
