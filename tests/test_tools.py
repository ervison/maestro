import pytest
from maestro.tools import resolve_path, PathOutsideWorkdirError


def test_resolve_path_allows_valid(tmp_path):
    result = resolve_path("src/main.py", tmp_path)
    assert result == (tmp_path / "src/main.py").resolve()


def test_resolve_path_blocks_traversal(tmp_path):
    with pytest.raises(PathOutsideWorkdirError):
        resolve_path("../../etc/passwd", tmp_path)


def test_resolve_path_absolute_inside_ok(tmp_path):
    target = tmp_path / "foo.py"
    result = resolve_path(str(target), tmp_path)
    assert result == target.resolve()


def test_resolve_path_absolute_outside_raises(tmp_path):
    with pytest.raises(PathOutsideWorkdirError):
        resolve_path("/etc/passwd", tmp_path)


import tempfile


def test_read_file(tmp_path):
    from maestro.tools import read_file

    f = tmp_path / "hello.txt"
    f.write_text("line1\nline2\nline3\n")
    result = read_file({"path": "hello.txt"}, tmp_path)
    assert result["content"] == "line1\nline2\nline3\n"
    assert result["lines"] == 3


def test_read_file_with_range(tmp_path):
    from maestro.tools import read_file

    f = tmp_path / "hello.txt"
    f.write_text("line1\nline2\nline3\n")
    result = read_file({"path": "hello.txt", "start_line": 2, "end_line": 2}, tmp_path)
    assert result["content"] == "line2"


def test_list_directory(tmp_path):
    from maestro.tools import list_directory

    (tmp_path / "a.py").write_text("")
    (tmp_path / "sub").mkdir()
    result = list_directory({"path": "."}, tmp_path)
    names = [e["name"] for e in result["entries"]]
    assert "a.py" in names
    assert "sub" in names


def test_search_in_files(tmp_path):
    from maestro.tools import search_in_files

    (tmp_path / "main.py").write_text("def hello():\n    return 'hello'\n")
    result = search_in_files({"pattern": "hello", "path": "."}, tmp_path)
    assert len(result["matches"]) >= 1
    assert result["matches"][0]["file"] == "main.py"
