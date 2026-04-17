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
