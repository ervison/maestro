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
            resolved_file = fpath.resolve()
            resolved_file.relative_to(workdir.resolve())
        except ValueError:
            continue
        try:
            for i, line in enumerate(resolved_file.read_text(errors="replace").splitlines(), 1):
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
        return {"error": f"File already exists: {args['path']}. Use write_file to overwrite, or choose a different filename."}
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


def execute_shell(args: dict, workdir: Path) -> dict:  # noqa: ARG001
    """Disabled: shell=True bypasses the workdir path guard (resolve_path).

    Free-form shell execution allows absolute paths and directory traversal
    (e.g. ``cat /etc/passwd``, ``rm ../file``) regardless of *workdir*.
    Re-enable only after sandboxing with shell=False and per-argument
    resolve_path validation.
    """
    return {
        "error": "execute_shell is disabled because it bypasses the workdir path guard"
    }


_TOOL_FNS = {
    "read_file": read_file,
    "write_file": write_file,
    "create_file": create_file,
    "list_directory": list_directory,
    "delete_file": delete_file,
    "move_file": move_file,
    "search_in_files": search_in_files,
    "execute_shell": execute_shell,
}


def _confirm(tool_name: str, args: dict) -> str:
    """Prompt user for confirmation. Returns 'yes', 'no', or 'always'."""
    summary = ", ".join(f"{k}={v!r}" for k, v in list(args.items())[:3])
    print(f"\n  [maestro] {tool_name}({summary})")
    ans = input("  Execute? [y/N/always]: ").strip().lower()
    if ans in ("a", "always"):
        return "always"
    if ans in ("y", "yes"):
        return "yes"
    return "no"


def execute_tool(
    name: str, args: dict, workdir: Path, auto: bool = False
) -> tuple[dict, bool]:
    """Execute a tool and return (result, auto_escalated).

    auto_escalated is True when the user answered 'always' during this call,
    signalling that the caller should set auto=True for all subsequent tools.
    """
    fn = _TOOL_FNS.get(name)
    if fn is None:
        return {"error": f"Unknown tool: {name}"}, False
    if name in DESTRUCTIVE_TOOLS and not auto:
        decision = _confirm(name, args)
        if decision == "no":
            return {"error": "user denied"}, False
        auto_escalated = decision == "always"
    else:
        auto_escalated = False
    try:
        return fn(args, workdir), auto_escalated
    except PathOutsideWorkdirError as e:
        return {"error": str(e)}, auto_escalated
    except Exception as e:
        return {"error": f"Tool error: {e}"}, auto_escalated


TOOL_SCHEMAS = [
    {
        "type": "function",
        "name": "read_file",
        "description": "Read the contents of a file. Optionally specify a line range.",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Path to the file (relative to workdir)"},
                "start_line": {"type": "integer", "description": "First line to read (1-indexed, inclusive)"},
                "end_line": {"type": "integer", "description": "Last line to read (1-indexed, inclusive)"},
            },
            "required": ["path"],
        },
    },
    {
        "type": "function",
        "name": "write_file",
        "description": "Create or overwrite a file with the given content.",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Path to the file (relative to workdir)"},
                "content": {"type": "string", "description": "Full file content to write"},
            },
            "required": ["path", "content"],
        },
    },
    {
        "type": "function",
        "name": "create_file",
        "description": "Create a new file. Fails if the file already exists.",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "content": {"type": "string"},
            },
            "required": ["path", "content"],
        },
    },
    {
        "type": "function",
        "name": "list_directory",
        "description": "List files and directories at the given path.",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Directory path relative to workdir (default '.')"},
            },
            "required": [],
        },
    },
    {
        "type": "function",
        "name": "delete_file",
        "description": "Delete a file.",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string"},
            },
            "required": ["path"],
        },
    },
    {
        "type": "function",
        "name": "move_file",
        "description": "Move or rename a file.",
        "parameters": {
            "type": "object",
            "properties": {
                "source": {"type": "string"},
                "destination": {"type": "string"},
            },
            "required": ["source", "destination"],
        },
    },
    {
        "type": "function",
        "name": "search_in_files",
        "description": "Search for a regex pattern across files. Returns up to 100 matches.",
        "parameters": {
            "type": "object",
            "properties": {
                "pattern": {"type": "string", "description": "Regex pattern to search for"},
                "path": {"type": "string", "description": "Directory to search (default '.')"},
                "include": {"type": "string", "description": "Glob pattern for files (default '*')"},
            },
            "required": ["pattern"],
        },
    },
    {
        "type": "function",
        "name": "execute_shell",
        "description": "Run a shell command in the workdir. Returns stdout, stderr, and returncode.",
        "parameters": {
            "type": "object",
            "properties": {
                "command": {"type": "string", "description": "Shell command to execute"},
                "timeout": {"type": "integer", "description": "Timeout in seconds (default 30)"},
            },
            "required": ["command"],
        },
    },
]
