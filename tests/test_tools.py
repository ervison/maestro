from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from maestro.tools import PathOutsideWorkdirError
from maestro import tools


def test_resolve_path_allows_relative_paths_within_workdir(tmp_path: Path) -> None:
    resolved = tools.resolve_path("subdir/file.txt", tmp_path)

    assert resolved == (tmp_path / "subdir" / "file.txt").resolve()


def test_resolve_path_rejects_paths_outside_workdir(tmp_path: Path) -> None:
    with pytest.raises(PathOutsideWorkdirError, match="escapes workdir"):
        tools.resolve_path("../outside.txt", tmp_path)


def test_resolve_path_allows_absolute_path_within_workdir(tmp_path: Path) -> None:
    path = tmp_path / "inside.txt"

    assert tools.resolve_path(str(path), tmp_path) == path.resolve()


def test_read_file_returns_full_content_and_line_count(tmp_path: Path) -> None:
    file_path = tmp_path / "notes.txt"
    file_path.write_text("one\ntwo\n")

    result = tools.read_file({"path": "notes.txt"}, tmp_path)

    assert result == {"content": "one\ntwo\n", "lines": 2}


def test_read_file_returns_selected_line_range(tmp_path: Path) -> None:
    file_path = tmp_path / "notes.txt"
    file_path.write_text("one\ntwo\nthree\n")

    result = tools.read_file({"path": "notes.txt", "start_line": 2, "end_line": 3}, tmp_path)

    assert result == {"content": "two\nthree", "lines": 2}


def test_read_file_returns_error_for_missing_file(tmp_path: Path) -> None:
    assert tools.read_file({"path": "missing.txt"}, tmp_path) == {"error": "File not found: missing.txt"}


def test_list_directory_returns_sorted_entries_with_sizes(tmp_path: Path) -> None:
    (tmp_path / "b.txt").write_text("bbb")
    (tmp_path / "a").mkdir()

    result = tools.list_directory({}, tmp_path)

    assert result["count"] == 2
    assert result["entries"] == [
        {"name": "a", "type": "directory", "size": None},
        {"name": "b.txt", "type": "file", "size": 3},
    ]


def test_list_directory_rejects_non_directory_path(tmp_path: Path) -> None:
    (tmp_path / "file.txt").write_text("x")

    assert tools.list_directory({"path": "file.txt"}, tmp_path) == {"error": "Not a directory: file.txt"}


def test_search_in_files_returns_matches_and_skips_outside_files(tmp_path: Path) -> None:
    nested = tmp_path / "nested"
    nested.mkdir()
    (nested / "app.py").write_text("print('match')\nprint('nope')\n")

    result = tools.search_in_files({"pattern": "match", "path": ".", "include": "*.py"}, tmp_path)

    assert result == {
        "matches": [{"file": "nested/app.py", "line": 1, "text": "print('match')"}],
        "truncated": False,
    }


def test_search_in_files_rejects_invalid_regex(tmp_path: Path) -> None:
    result = tools.search_in_files({"pattern": "[", "path": "."}, tmp_path)

    assert "Invalid regex" in result["error"]


def test_search_single_file_and_search_in_files_skip_errors(tmp_path: Path) -> None:
    regex = tools.re.compile("needle")
    outside = tmp_path.parent / "outside.txt"
    outside.write_text("needle\n")

    assert tools._search_single_file(regex, outside, tmp_path) is None

    broken = tmp_path / "broken.txt"
    broken.write_text("needle\n")
    with patch.object(Path, "read_text", side_effect=OSError("boom")):
        assert tools._search_single_file(regex, broken, tmp_path) is None

    result = tools.search_in_files({"pattern": "needle", "path": "broken.txt"}, tmp_path)
    assert result == {"matches": [], "truncated": False}

    subdir = tmp_path / "subdir"
    subdir.mkdir()
    real_file = subdir / "real.txt"
    real_file.write_text("needle\n")
    with patch("maestro.tools._search_single_file", return_value=None):
        result = tools.search_in_files({"pattern": "needle", "path": ".", "include": "*"}, tmp_path)
    assert result == {"matches": [], "truncated": False}


def test_search_in_files_truncates_after_one_hundred_matches(tmp_path: Path) -> None:
    for index in range(101):
        (tmp_path / f"file{index}.txt").write_text("needle\n")

    result = tools.search_in_files({"pattern": "needle", "path": ".", "include": "*.txt"}, tmp_path)

    assert result["truncated"] is True
    assert len(result["matches"]) >= 100


def test_write_create_delete_and_move_file_round_trip(tmp_path: Path) -> None:
    assert tools.create_file({"path": "a.txt", "content": "alpha"}, tmp_path) == {"ok": True}
    assert tools.create_file({"path": "a.txt", "content": "beta"}, tmp_path)["error"].startswith("File already exists")
    assert tools.write_file({"path": "a.txt", "content": "beta"}, tmp_path) == {"ok": True}
    assert tools.move_file({"source": "a.txt", "destination": "sub/b.txt"}, tmp_path) == {"ok": True}
    assert (tmp_path / "sub" / "b.txt").read_text() == "beta"
    assert tools.delete_file({"path": "sub/b.txt"}, tmp_path) == {"ok": True}
    assert tools.delete_file({"path": "sub/b.txt"}, tmp_path) == {"error": "File not found: sub/b.txt"}


def test_move_file_returns_error_when_source_missing(tmp_path: Path) -> None:
    assert tools.move_file({"source": "missing.txt", "destination": "out.txt"}, tmp_path) == {
        "error": "Source not found: missing.txt"
    }


def test_execute_shell_returns_disabled_error(tmp_path: Path) -> None:
    result = tools.execute_shell({"command": "pwd"}, tmp_path)

    assert "disabled" in result["error"]


def test_execute_tool_rejects_unknown_tool(tmp_path: Path) -> None:
    result, auto = tools.execute_tool("missing", {}, tmp_path)

    assert result == {"error": "Unknown tool: missing"}
    assert auto is False


def test_execute_tool_honors_user_denial_for_destructive_tool(tmp_path: Path) -> None:
    with patch("maestro.tools._confirm", return_value="no"):
        result, auto = tools.execute_tool("delete_file", {"path": "a.txt"}, tmp_path)

    assert result == {"error": "user denied"}
    assert auto is False


def test_execute_tool_escalates_auto_after_always_confirmation(tmp_path: Path) -> None:
    with patch("maestro.tools._confirm", return_value="always"):
        result, auto = tools.execute_tool("write_file", {"path": "a.txt", "content": "x"}, tmp_path)

    assert result == {"ok": True}
    assert auto is True


def test_execute_tool_converts_path_escape_to_error(tmp_path: Path) -> None:
    result, auto = tools.execute_tool("read_file", {"path": "../secret.txt"}, tmp_path, auto=True)

    assert "escapes workdir" in result["error"]
    assert auto is False


def test_execute_tool_wraps_unexpected_exceptions(tmp_path: Path) -> None:
    with patch.dict(tools._TOOL_FNS, {"boom": lambda args, workdir: (_ for _ in ()).throw(RuntimeError("kaboom"))}, clear=False):
        result, auto = tools.execute_tool("boom", {}, tmp_path, auto=True)

    assert result == {"error": "Tool error: kaboom"}
    assert auto is False


def test_confirm_returns_expected_decisions(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("builtins.input", lambda _: "always")
    assert tools._confirm("write_file", {"path": "a.txt"}) == "always"

    monkeypatch.setattr("builtins.input", lambda _: "yes")
    assert tools._confirm("write_file", {"path": "a.txt"}) == "yes"

    monkeypatch.setattr("builtins.input", lambda _: "")
    assert tools._confirm("write_file", {"path": "a.txt"}) == "no"
