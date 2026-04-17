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


def test_write_file_creates(tmp_path):
    from maestro.tools import write_file

    result = write_file({"path": "new.py", "content": "print('hi')"}, tmp_path)
    assert result == {"ok": True}
    assert (tmp_path / "new.py").read_text() == "print('hi')"


def test_write_file_overwrites(tmp_path):
    from maestro.tools import write_file

    (tmp_path / "f.py").write_text("old")
    write_file({"path": "f.py", "content": "new"}, tmp_path)
    assert (tmp_path / "f.py").read_text() == "new"


def test_create_file_new(tmp_path):
    from maestro.tools import create_file

    result = create_file({"path": "fresh.py", "content": "x=1"}, tmp_path)
    assert result == {"ok": True}


def test_create_file_exists_fails(tmp_path):
    from maestro.tools import create_file

    (tmp_path / "existing.py").write_text("x")
    result = create_file({"path": "existing.py", "content": "y"}, tmp_path)
    assert "error" in result


def test_delete_file(tmp_path):
    from maestro.tools import delete_file

    f = tmp_path / "del.py"
    f.write_text("x")
    result = delete_file({"path": "del.py"}, tmp_path)
    assert result == {"ok": True}
    assert not f.exists()


def test_move_file(tmp_path):
    from maestro.tools import move_file

    (tmp_path / "src.py").write_text("x")
    result = move_file({"source": "src.py", "destination": "dst.py"}, tmp_path)
    assert result == {"ok": True}
    assert (tmp_path / "dst.py").exists()
    assert not (tmp_path / "src.py").exists()
