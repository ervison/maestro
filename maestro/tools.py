"""
File system and shell tools for the maestro agentic loop.
All paths are validated to remain within workdir.
"""

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


def read_file(args: dict, workdir: Path) -> dict:
    path = resolve_path(args["path"], workdir)
    if not path.exists():
        return {"error": f"File not found: {args['path']}"}
    text = path.read_text(errors="replace")
    lines = text.splitlines()
    start = args.get("start_line")
    end = args.get("end_line")
    if start is not None or end is not None:
        s = (start or 1) - 1
        e = end  # None means slice to end
        selected = lines[s:e]
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
        except OSError:
            continue
    return {"matches": matches, "truncated": False}


def write_file(args: dict, workdir: Path) -> dict:
    path = resolve_path(args["path"], workdir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(args.get("content", ""))
    return {"ok": True}


def create_file(args: dict, workdir: Path) -> dict:
    path = resolve_path(args["path"], workdir)
    if path.exists():
        return {"error": f"File already exists: {args['path']}"}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(args.get("content", ""))
    return {"ok": True}


def delete_file(args: dict, workdir: Path) -> dict:
    path = resolve_path(args["path"], workdir)
    if not path.exists():
        return {"error": f"File not found: {args['path']}"}
    path.unlink()
    return {"ok": True}


def move_file(args: dict, workdir: Path) -> dict:
    src = resolve_path(args["source"], workdir)
    dst = resolve_path(args["destination"], workdir)
    if not src.exists():
        return {"error": f"Source not found: {args['source']}"}
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(src), str(dst))
    return {"ok": True}


def execute_shell(args: dict, workdir: Path) -> dict:
    cmd = args.get("command")
    if not cmd:
        return {"error": "Missing required argument: command"}
    timeout = args.get("timeout", 30)
    try:
        result = subprocess.run(
            cmd,
            shell=True,
            cwd=workdir,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return {
            "stdout": result.stdout,
            "stderr": result.stderr,
            "returncode": result.returncode,
        }
    except subprocess.TimeoutExpired as e:
        return {
            "error": f"Command timed out after {timeout}s",
            "stdout": e.stdout or "",
            "stderr": e.stderr or "",
        }
