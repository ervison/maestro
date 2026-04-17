# Agentic File Tools Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add file system and shell tools to the maestro agent so it can autonomously create, read, edit, delete, move files, search in files, and run shell commands in an agentic loop via the ChatGPT Responses API.

**Architecture:** Extend `agent.py` to run a multi-turn loop: send tools JSON schemas with each API call, parse `function_call` events from the SSE stream, execute the corresponding Python tool function, and feed results back until the model sends a final text message. A new `tools.py` module holds all tool definitions, JSON schemas, path validation, and the `execute_tool` dispatcher.

**Tech Stack:** Python 3.12, httpx (streaming SSE), langgraph `@entrypoint`/`@task`, stdlib (pathlib, subprocess, re)

---

## File Map

| File                       | Action     | Responsibility                                                              |
| -------------------------- | ---------- | --------------------------------------------------------------------------- |
| `maestro/tools.py`         | **Create** | Tool functions, JSON schemas, path guard, execute_tool dispatcher           |
| `maestro/agent.py`         | **Modify** | Replace single-call with agentic loop, SSE parsing for function_call events |
| `maestro/cli.py`           | **Modify** | Add `--auto` and `--workdir` flags to `run` command                         |
| `tests/test_tools.py`      | **Create** | Unit tests for all tool functions and path guard                            |
| `tests/test_agent_loop.py` | **Create** | Integration test for the agentic loop (mocked API)                          |

---

## Task 1: Path guard and tool scaffolding in `tools.py`

**Files:**

- Create: `maestro/tools.py`
- Create: `tests/test_tools.py`

- [ ] **Step 1: Write failing test for path guard**

```python
# tests/test_tools.py
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
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd /home/ervison/Documents/PROJETOS/labs/timeIA/maestro
python -m pytest tests/test_tools.py::test_resolve_path_allows_valid -v
```

Expected: `ModuleNotFoundError` or `ImportError` (file doesn't exist yet)

- [ ] **Step 3: Create `maestro/tools.py` with path guard**

```python
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


DESTRUCTIVE_TOOLS = {"write_file", "create_file", "delete_file", "move_file", "execute_shell"}


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
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
python -m pytest tests/test_tools.py -v
```

Expected: 4 tests PASS

- [ ] **Step 5: Commit**

```bash
git add maestro/tools.py tests/test_tools.py
git commit -m "feat: add tools.py with path guard"
```

---

## Task 2: Read, list, search tool functions

**Files:**

- Modify: `maestro/tools.py`
- Modify: `tests/test_tools.py`

- [ ] **Step 1: Write failing tests**

```python
# append to tests/test_tools.py
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
```

- [ ] **Step 2: Run to verify they fail**

```bash
python -m pytest tests/test_tools.py -k "test_read or test_list or test_search" -v
```

Expected: `ImportError` for each function

- [ ] **Step 3: Implement read_file, list_directory, search_in_files in `tools.py`**

```python
# Append to maestro/tools.py

def read_file(args: dict, workdir: Path) -> dict:
    path = resolve_path(args["path"], workdir)
    if not path.exists():
        return {"error": f"File not found: {args['path']}"}
    lines = path.read_text(errors="replace").splitlines()
    start = args.get("start_line")
    end = args.get("end_line")
    if start is not None and end is not None:
        selected = lines[start - 1 : end]
        return {"content": "\n".join(selected), "lines": len(selected)}
    return {"content": "\n".join(lines), "lines": len(lines)}


def list_directory(args: dict, workdir: Path) -> dict:
    path = resolve_path(args.get("path", "."), workdir)
    if not path.is_dir():
        return {"error": f"Not a directory: {args.get('path', '.')}"}
    entries = []
    for entry in sorted(path.iterdir()):
        entries.append({
            "name": entry.name,
            "type": "directory" if entry.is_dir() else "file",
            "size": entry.stat().st_size if entry.is_file() else None,
        })
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
                    matches.append({
                        "file": str(fpath.relative_to(workdir)),
                        "line": i,
                        "text": line,
                    })
                    if len(matches) >= 100:
                        return {"matches": matches, "truncated": True}
        except (OSError, UnicodeDecodeError):
            continue
    return {"matches": matches, "truncated": False}
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
python -m pytest tests/test_tools.py -v
```

Expected: all tests PASS

- [ ] **Step 5: Commit**

```bash
git add maestro/tools.py tests/test_tools.py
git commit -m "feat: add read_file, list_directory, search_in_files tools"
```

---

## Task 3: Write, create, delete, move file tools

**Files:**

- Modify: `maestro/tools.py`
- Modify: `tests/test_tools.py`

- [ ] **Step 1: Write failing tests**

```python
# append to tests/test_tools.py

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
```

- [ ] **Step 2: Run to verify they fail**

```bash
python -m pytest tests/test_tools.py -k "test_write or test_create or test_delete or test_move" -v
```

Expected: `ImportError` for each

- [ ] **Step 3: Implement write_file, create_file, delete_file, move_file**

```python
# Append to maestro/tools.py

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
```

- [ ] **Step 4: Run all tests**

```bash
python -m pytest tests/test_tools.py -v
```

Expected: all tests PASS

- [ ] **Step 5: Commit**

```bash
git add maestro/tools.py tests/test_tools.py
git commit -m "feat: add write_file, create_file, delete_file, move_file tools"
```

---

## Task 4: execute_shell tool

**Files:**

- Modify: `maestro/tools.py`
- Modify: `tests/test_tools.py`

- [ ] **Step 1: Write failing test**

```python
# append to tests/test_tools.py

def test_execute_shell_success(tmp_path):
    from maestro.tools import execute_shell
    result = execute_shell({"command": "echo hello"}, tmp_path)
    assert result["returncode"] == 0
    assert "hello" in result["stdout"]

def test_execute_shell_failure(tmp_path):
    from maestro.tools import execute_shell
    result = execute_shell({"command": "false"}, tmp_path)
    assert result["returncode"] != 0

def test_execute_shell_timeout(tmp_path):
    from maestro.tools import execute_shell
    result = execute_shell({"command": "sleep 60", "timeout": 1}, tmp_path)
    assert "error" in result
    assert "timed out" in result["error"]
```

- [ ] **Step 2: Run to verify they fail**

```bash
python -m pytest tests/test_tools.py -k "test_execute_shell" -v
```

Expected: `ImportError`

- [ ] **Step 3: Implement execute_shell**

```python
# Append to maestro/tools.py

def execute_shell(args: dict, workdir: Path) -> dict:
    cmd = args["command"]
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
    except subprocess.TimeoutExpired:
        return {"error": f"Command timed out after {timeout}s", "stdout": "", "stderr": ""}
```

- [ ] **Step 4: Run all tests**

```bash
python -m pytest tests/test_tools.py -v
```

Expected: all tests PASS

- [ ] **Step 5: Commit**

```bash
git add maestro/tools.py tests/test_tools.py
git commit -m "feat: add execute_shell tool"
```

---

## Task 5: execute_tool dispatcher + confirmation + JSON schemas

**Files:**

- Modify: `maestro/tools.py`
- Modify: `tests/test_tools.py`

- [ ] **Step 1: Write failing tests for dispatcher**

```python
# append to tests/test_tools.py

def test_execute_tool_read(tmp_path):
    from maestro.tools import execute_tool
    (tmp_path / "f.txt").write_text("hello")
    result = execute_tool("read_file", {"path": "f.txt"}, tmp_path, auto=True)
    assert result["content"] == "hello"

def test_execute_tool_unknown(tmp_path):
    from maestro.tools import execute_tool
    result = execute_tool("nonexistent_tool", {}, tmp_path, auto=True)
    assert "error" in result

def test_execute_tool_destructive_denied(tmp_path, monkeypatch):
    from maestro.tools import execute_tool
    monkeypatch.setattr("builtins.input", lambda _: "n")
    result = execute_tool("write_file", {"path": "x.py", "content": "x"}, tmp_path, auto=False)
    assert result == {"error": "user denied"}
    assert not (tmp_path / "x.py").exists()

def test_execute_tool_destructive_auto(tmp_path):
    from maestro.tools import execute_tool
    result = execute_tool("write_file", {"path": "x.py", "content": "x"}, tmp_path, auto=True)
    assert result == {"ok": True}
```

- [ ] **Step 2: Run to verify they fail**

```bash
python -m pytest tests/test_tools.py -k "test_execute_tool" -v
```

Expected: `ImportError`

- [ ] **Step 3: Implement execute_tool dispatcher and add TOOL_SCHEMAS**

```python
# Append to maestro/tools.py

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


def _confirm(tool_name: str, args: dict) -> bool:
    summary = ", ".join(f"{k}={v!r}" for k, v in list(args.items())[:3])
    print(f"\n  [maestro] {tool_name}({summary})")
    ans = input("  Execute? [y/N]: ").strip().lower()
    return ans in ("y", "yes")


def execute_tool(name: str, args: dict, workdir: Path, auto: bool = False) -> dict:
    fn = _TOOL_FNS.get(name)
    if fn is None:
        return {"error": f"Unknown tool: {name}"}
    if name in DESTRUCTIVE_TOOLS and not auto:
        if not _confirm(name, args):
            return {"error": "user denied"}
    try:
        return fn(args, workdir)
    except PathOutsideWorkdirError as e:
        return {"error": str(e)}
    except Exception as e:
        return {"error": f"Tool error: {e}"}


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
```

- [ ] **Step 4: Run all tests**

```bash
python -m pytest tests/test_tools.py -v
```

Expected: all tests PASS

- [ ] **Step 5: Commit**

```bash
git add maestro/tools.py tests/test_tools.py
git commit -m "feat: add execute_tool dispatcher, confirmation, TOOL_SCHEMAS"
```

---

## Task 6: Agentic loop in `agent.py`

**Files:**

- Modify: `maestro/agent.py`
- Create: `tests/test_agent_loop.py`

- [ ] **Step 1: Write failing test with mocked API**

```python
# tests/test_agent_loop.py
import json
import pytest
from unittest.mock import patch, MagicMock
from pathlib import Path
from langchain_core.messages import HumanMessage
from maestro.auth import TokenSet
from maestro.agent import _run_agentic_loop

FAKE_TOKENS = TokenSet(access="tok", refresh="ref", expires=9999999999.0, account_id="acc")

def _sse_lines(*events):
    """Build fake SSE line iterator from list of event dicts."""
    lines = []
    for e in events:
        lines.append(f"data: {json.dumps(e)}")
    lines.append("data: [DONE]")
    return iter(lines)


def test_agentic_loop_direct_answer(tmp_path):
    """Model answers directly without any tool calls."""
    events = [
        {"type": "response.output_text.delta", "delta": "Hello"},
        {"type": "response.output_text.delta", "delta": " world"},
    ]

    mock_response = MagicMock()
    mock_response.is_success = True
    mock_response.iter_lines.return_value = _sse_lines(*events)
    mock_cm = MagicMock()
    mock_cm.__enter__ = MagicMock(return_value=mock_response)
    mock_cm.__exit__ = MagicMock(return_value=False)

    with patch("maestro.agent.httpx.stream", return_value=mock_cm):
        result = _run_agentic_loop(
            messages=[HumanMessage(content="say hi")],
            model="gpt-5.4-mini",
            instructions="You are helpful.",
            tokens=FAKE_TOKENS,
            workdir=tmp_path,
            auto=True,
        )
    assert result == "Hello world"


def test_agentic_loop_one_tool_call(tmp_path):
    """Model calls write_file once then answers."""
    (tmp_path / "dummy").mkdir(exist_ok=True)

    tool_call_event = {
        "type": "response.output_item.done",
        "item": {
            "type": "function_call",
            "id": "call_1",
            "name": "write_file",
            "arguments": json.dumps({"path": "out.txt", "content": "done"}),
        },
    }
    final_events = [
        {"type": "response.output_text.delta", "delta": "File written."},
    ]

    call_count = 0

    def fake_stream(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        mock_response = MagicMock()
        mock_response.is_success = True
        if call_count == 1:
            mock_response.iter_lines.return_value = _sse_lines(tool_call_event)
        else:
            mock_response.iter_lines.return_value = _sse_lines(*final_events)
        mock_cm = MagicMock()
        mock_cm.__enter__ = MagicMock(return_value=mock_response)
        mock_cm.__exit__ = MagicMock(return_value=False)
        return mock_cm

    with patch("maestro.agent.httpx.stream", side_effect=fake_stream):
        result = _run_agentic_loop(
            messages=[HumanMessage(content="write a file")],
            model="gpt-5.4-mini",
            instructions="You are helpful.",
            tokens=FAKE_TOKENS,
            workdir=tmp_path,
            auto=True,
        )
    assert result == "File written."
    assert (tmp_path / "out.txt").read_text() == "done"
    assert call_count == 2
```

- [ ] **Step 2: Run to verify they fail**

```bash
python -m pytest tests/test_agent_loop.py -v
```

Expected: `ImportError` for `_run_agentic_loop`

- [ ] **Step 3: Rewrite `agent.py` with agentic loop**

Replace `_call_responses_api` and `run` with the following:

```python
"""
LangGraph agent that uses ChatGPT Plus/Pro subscription
via the Codex Responses API backend — with agentic tool loop.
"""

import json
from pathlib import Path
from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage, AIMessage
from langgraph.func import entrypoint, task

from maestro import auth
from maestro.tools import execute_tool, TOOL_SCHEMAS

RESPONSES_ENDPOINT = f"{auth.CODEX_API_BASE}/codex/responses"

USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

_REASONING_DEFAULTS: dict[str, str] = {
    "gpt-5-codex": "high",
    "gpt-5.1-codex-max": "high",
    "gpt-5.1-codex-mini": "medium",
    "gpt-5.4": "high",
    "gpt-5.4-mini": "high",
    "gpt-5.4-nano": "high",
    "gpt-5.4-pro": "medium",
    "gpt-5.2": "high",
    "gpt-5.1": "medium",
}


def _reasoning_effort(model: str) -> str:
    return _REASONING_DEFAULTS.get(model, "medium")


def _headers(tokens: auth.TokenSet) -> dict:
    h = {
        "Authorization": f"Bearer {tokens.access}",
        "Content-Type": "application/json",
        "Accept": "text/event-stream",
        "User-Agent": USER_AGENT,
        "originator": "codex_cli_rs",
        "OpenAI-Beta": "responses=experimental",
    }
    if tokens.account_id:
        h["chatgpt-account-id"] = tokens.account_id
    return h


def _run_agentic_loop(
    messages: list[BaseMessage],
    model: str,
    instructions: str,
    tokens: auth.TokenSet,
    workdir: Path,
    auto: bool = False,
    max_iterations: int = 20,
) -> str:
    import httpx

    api_model = auth.resolve_model(model)

    # Build initial input list (user/assistant messages only — no developer)
    input_items: list[dict] = []
    for msg in messages:
        if isinstance(msg, HumanMessage):
            input_items.append({
                "type": "message",
                "role": "user",
                "content": [{"type": "input_text", "text": msg.content}],
            })
        elif isinstance(msg, AIMessage):
            input_items.append({
                "type": "message",
                "role": "assistant",
                "content": [{"type": "output_text", "text": msg.content}],
            })

    for iteration in range(max_iterations):
        payload = {
            "model": api_model,
            "instructions": instructions or "You are a helpful assistant.",
            "input": input_items,
            "tools": TOOL_SCHEMAS,
            "stream": True,
            "store": False,
            "reasoning": {
                "effort": _reasoning_effort(api_model),
                "summary": "auto",
            },
            "text": {"verbosity": "medium"},
            "include": ["reasoning.encrypted_content"],
        }

        text_parts: list[str] = []
        tool_calls: list[dict] = []

        with httpx.stream(
            "POST",
            RESPONSES_ENDPOINT,
            json=payload,
            headers=_headers(tokens),
            timeout=120,
        ) as r:
            if not r.is_success:
                body = r.read().decode()
                raise RuntimeError(f"API error {r.status_code} (iter {iteration}): {body[:800]}")

            for line in r.iter_lines():
                if not line.startswith("data: "):
                    continue
                raw = line[6:]
                if raw == "[DONE]":
                    break
                try:
                    event = json.loads(raw)
                except json.JSONDecodeError:
                    continue

                etype = event.get("type", "")
                if etype == "response.output_text.delta":
                    text_parts.append(event.get("delta", ""))
                elif etype == "response.output_item.done":
                    item = event.get("item", {})
                    if item.get("type") == "function_call":
                        tool_calls.append(item)
                elif etype == "response.done":
                    resp = event.get("response", {})
                    for out in resp.get("output", []):
                        if out.get("type") == "message" and not text_parts:
                            for part in out.get("content", []):
                                if part.get("type") == "output_text":
                                    text_parts.append(part["text"])

        # No tool calls → final answer
        if not tool_calls:
            if text_parts:
                return "".join(text_parts)
            raise RuntimeError("No output received from agent loop")

        # Execute tool calls and build next input
        # Append model's function_call items to input
        for tc in tool_calls:
            input_items.append({
                "type": "function_call",
                "id": tc.get("id", ""),
                "call_id": tc.get("id", ""),
                "name": tc["name"],
                "arguments": tc["arguments"],
            })

        # Execute each tool and append results
        for tc in tool_calls:
            try:
                args = json.loads(tc["arguments"])
            except json.JSONDecodeError:
                args = {}
            result = execute_tool(tc["name"], args, workdir, auto=auto)
            input_items.append({
                "type": "function_call_output",
                "call_id": tc.get("id", ""),
                "output": json.dumps(result),
            })

    raise RuntimeError(f"Agent loop exceeded max_iterations={max_iterations}")


def run(
    model_name: str,
    prompt: str,
    system: str | None = None,
    workdir: Path | None = None,
    auto: bool = False,
) -> str:
    """Run the agentic loop with the given model and prompt."""
    tokens = auth.load()
    if not tokens:
        raise RuntimeError("Not logged in. Run: maestro login")
    tokens = auth.ensure_valid(tokens)

    wd = workdir or Path.cwd()
    instructions = system or "You are a helpful assistant with access to file system tools."

    @task
    def call_agent(msgs: list[BaseMessage]) -> AIMessage:
        text = _run_agentic_loop(
            messages=msgs,
            model=model_name,
            instructions=instructions,
            tokens=tokens,
            workdir=wd,
            auto=auto,
        )
        return AIMessage(content=text)

    @entrypoint()
    def agent(msgs: list[BaseMessage]) -> list[BaseMessage]:
        response = call_agent(msgs).result()
        return [*msgs, response]

    msgs: list[BaseMessage] = [HumanMessage(content=prompt)]
    result = agent.invoke(msgs)
    return result[-1].content
```

- [ ] **Step 4: Run all tests**

```bash
python -m pytest tests/ -v
```

Expected: all tests PASS

- [ ] **Step 5: Commit**

```bash
git add maestro/agent.py tests/test_agent_loop.py
git commit -m "feat: implement agentic tool loop in agent.py"
```

---

## Task 7: Update CLI with `--auto` and `--workdir` flags

**Files:**

- Modify: `maestro/cli.py`

- [ ] **Step 1: Add flags to `run` subcommand and pass them through**

Replace the `run` subcommand block in `cli.py`:

```python
    # run
    run_p = sub.add_parser("run", help="Run the agent")
    run_p.add_argument("prompt", help="Prompt to send")
    run_p.add_argument(
        "-m", "--model",
        default=auth.DEFAULT_MODEL,
        help=f"Model to use (default: {auth.DEFAULT_MODEL}). Run 'maestro models' for list.",
    )
    run_p.add_argument("-s", "--system", default=None, help="System prompt / instructions")
    run_p.add_argument(
        "--auto",
        action="store_true",
        help="Skip confirmation prompts for destructive actions",
    )
    run_p.add_argument(
        "--workdir",
        default=None,
        metavar="PATH",
        help="Working directory for file tools (default: current directory)",
    )
```

Replace the `run` command handler block:

```python
    elif args.command == "run":
        import os
        from pathlib import Path
        wd = Path(args.workdir).resolve() if args.workdir else Path.cwd()
        try:
            result = run(args.model, args.prompt, args.system, workdir=wd, auto=args.auto)
            print(result)
        except RuntimeError as e:
            msg = str(e)
            if "not supported" in msg:
                print(f"Error: model '{args.model}' is not available for your account.")
                print("Run 'maestro models --check' to see which models work for you.")
            else:
                print(f"Error: {msg}")
            sys.exit(1)
```

- [ ] **Step 2: Smoke test CLI**

```bash
cd /home/ervison/Documents/PROJETOS/labs/timeIA/maestro
python -m maestro.cli run "list the files in the current directory" --auto 2>&1
```

Expected: agent calls `list_directory`, receives results, returns a text summary of files.

- [ ] **Step 3: Run all tests**

```bash
python -m pytest tests/ -v
```

Expected: all tests PASS

- [ ] **Step 4: Commit**

```bash
git add maestro/cli.py
git commit -m "feat: add --auto and --workdir flags to run command"
```

---

## Task 8: End-to-end smoke test

- [ ] **Step 1: Test file creation**

```bash
cd /tmp && mkdir maestro-test && cd maestro-test
maestro run "Create a file called hello.py that prints Hello World" --auto
cat hello.py
```

Expected: `hello.py` exists with `print("Hello World")` content.

- [ ] **Step 2: Test file editing**

```bash
maestro run "Add a second print statement to hello.py that says Goodbye" --auto
cat hello.py
```

Expected: `hello.py` has two print statements.

- [ ] **Step 3: Test shell execution**

```bash
maestro run "Run hello.py using python3 and tell me the output" --auto
```

Expected: agent runs `python3 hello.py`, reads stdout, reports the output.

- [ ] **Step 4: Clean up test dir**

```bash
rm -rf /tmp/maestro-test
```

- [ ] **Step 5: Final commit**

```bash
cd /home/ervison/Documents/PROJETOS/labs/timeIA/maestro
git add .
git commit -m "chore: finalize agentic file tools implementation"
```
