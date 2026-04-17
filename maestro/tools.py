"""
File system and shell tools for the maestro agentic loop.
All paths are validated to remain within workdir.
"""

import re
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


def read_file(args: dict, workdir: Path) -> dict:
    path = resolve_path(args["path"], workdir)
    if not path.exists():
        return {"error": f"File not found: {args['path']}"}
    text = path.read_text(errors="replace")
    lines = text.splitlines()
    start = args.get("start_line")
    end = args.get("end_line")
    if start is not None and end is not None:
        selected = lines[start - 1 : end]
        return {"content": "\n".join(selected), "lines": len(selected)}
    return {"content": text, "lines": len(lines)}


def list_directory(args: dict, workdir: Path) -> dict:
    path = resolve_path(args.get("path", "."), workdir)
    if not path.is_dir():
        return {"error": f"Not a directory: {args.get('path', '.')}"}
    entries = []
    for entry in sorted(path.iterdir()):
        entries.append(
            {
                "name": entry.name,
                "type": "directory" if entry.is_dir() else "file",
                "size": entry.stat().st_size if entry.is_file() else None,
            }
        )
    return {"entries": entries, "count": len(entries)}


def search_in_files(args: dict, workdir: Path) -> dict:
    base = resolve_path(args.get("path", "."), workdir)
    pattern = args["pattern"]
    include = args.get("include", "*")
    matches = []
    try:
        regex = re.compile(pattern)
    except re.error as e:
        return {"error": f"Invalid regex: {e}"}
    for fpath in base.rglob(include):
        if not fpath.is_file():
            continue
        try:
            for i, line in enumerate(fpath.read_text(errors="replace").splitlines(), 1):
                if regex.search(line):
                    matches.append(
                        {
                            "file": str(fpath.relative_to(workdir)),
                            "line": i,
                            "text": line,
                        }
                    )
                    if len(matches) >= 100:
                        return {"matches": matches, "truncated": True}
        except (OSError, UnicodeDecodeError):
            continue
    return {"matches": matches, "truncated": False}
