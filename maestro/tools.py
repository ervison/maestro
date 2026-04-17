"""
File system and shell tools for the maestro agentic loop.
All paths are validated to remain within workdir.
"""

import os
import re
import shutil
import subprocess
from pathlib import Path


class PathOutsideWorkdirError(ValueError):
    pass


DESTRUCTIVE_TOOLS = {
    "write_file",
    "create_file",
    "delete_file",
    "move_file",
    "execute_shell",
}


def resolve_path(path: str, workdir: Path) -> Path:
    """Resolve path relative to workdir; raise if it escapes."""
    p = Path(path)
    if p.is_absolute():
        resolved = p.resolve()
    else:
        resolved = (workdir / p).resolve()
    wd_resolved = workdir.resolve()
    try:
        resolved.relative_to(wd_resolved)
    except ValueError:
        raise PathOutsideWorkdirError(f"Path '{path}' escapes workdir '{workdir}'")
    return resolved
