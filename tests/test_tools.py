import pytest
from pathlib import Path
from maestro.tools import resolve_path, PathOutsideWorkdirError


def test_resolve_path_allows_valid():
    wd = Path("/tmp/workdir")
    result = resolve_path("src/main.py", wd)
    assert result == wd / "src/main.py"


def test_resolve_path_blocks_traversal():
    wd = Path("/tmp/workdir")
    with pytest.raises(PathOutsideWorkdirError):
        resolve_path("../../etc/passwd", wd)


def test_resolve_path_absolute_inside_ok():
    wd = Path("/tmp/workdir")
    result = resolve_path("/tmp/workdir/foo.py", wd)
    assert result == wd / "foo.py"


def test_resolve_path_absolute_outside_raises():
    wd = Path("/tmp/workdir")
    with pytest.raises(PathOutsideWorkdirError):
        resolve_path("/etc/passwd", wd)
