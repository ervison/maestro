# Phase 2: Multi-Slot Auth Store - Pattern Map

**Mapped:** 2026-04-17
**Files analyzed:** 3
**Analogs found:** 3 / 3

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `maestro/auth.py` | service | file-I/O | `maestro/auth.py` | exact |
| `maestro/cli.py` | route | request-response | `maestro/cli.py` | role-match |
| `tests/test_auth_store.py` | test | file-I/O | `tests/test_tools.py`, `tests/test_agent_loop.py` | partial |

## Pattern Assignments

### `maestro/auth.py` (service, file-I/O)

**Analog:** `maestro/auth.py`

**Imports pattern** (`maestro/auth.py:7-20`):
```python
import base64
import hashlib
import http.server
import json
import os
import secrets
import threading
import time
import webbrowser
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlparse

import httpx
```

**Store write pattern** (`maestro/auth.py:82-95`):
```python
def _save(tokens: TokenSet):
    AUTH_FILE.parent.mkdir(parents=True, exist_ok=True)
    AUTH_FILE.write_text(
        json.dumps(
            {
                "access": tokens.access,
                "refresh": tokens.refresh,
                "expires": tokens.expires,
                "account_id": tokens.account_id,
                "email": tokens.email,
            }
        )
    )
    AUTH_FILE.chmod(0o600)
```

**Store read + typed return pattern** (`maestro/auth.py:98-102`):
```python
def load() -> TokenSet | None:
    if not AUTH_FILE.exists():
        return None
    data = json.loads(AUTH_FILE.read_text())
    return TokenSet(**data)
```

**Write-through auth flow pattern** (`maestro/auth.py:151-174`, `177-198`):
```python
d = r.json()
access = d["access_token"]
ts = TokenSet(
    access=access,
    refresh=d.get("refresh_token", ""),
    expires=time.time() + d.get("expires_in", 3600),
    account_id=_extract_account_id(access),
    email=_extract_email(d.get("id_token", "")),
)
_save(ts)
return ts
```

```python
new = TokenSet(
    access=access,
    refresh=d.get("refresh_token", ts.refresh),
    expires=time.time() + d.get("expires_in", 3600),
    account_id=_extract_account_id(access),
    email=ts.email or _extract_email(d.get("id_token", "")),
)
_save(new)
return new
```

**Error handling pattern** (`maestro/auth.py:259-262`, `299-306`):
```python
if error:
    raise RuntimeError(f"OAuth error: {error[0]}")
if "code" not in result:
    raise RuntimeError("No authorization code received (timeout?)")
```

```python
if r.status_code in (403, 404):
    continue  # pending
r.raise_for_status()

...

raise RuntimeError("Device code login timed out")
```

**Backward-compat contract to preserve** (`maestro/auth.py:73-102`, `maestro/agent.py:268-271`):
```python
@dataclass
class TokenSet:
    access: str
    refresh: str
    expires: float
    account_id: str = ""
    email: str = ""
```

```python
tokens = auth.load()
if not tokens:
    raise RuntimeError("Not logged in. Run: maestro login")
tokens = auth.ensure_valid(tokens)
```

**Planning notes**
- Keep `TokenSet`, `load()`, `_save()`, and `logout()` in-place as shims.
- New public API should look like a thin extension of the current read/write helpers, not a new module.
- `maestro/agent.py` must keep working unchanged through `auth.load()` and `auth.ensure_valid()`.

---

### `maestro/cli.py` (route, request-response)

**Analog:** `maestro/cli.py`

**Imports pattern** (`maestro/cli.py:3-7`):
```python
import argparse
import sys

from maestro import auth
from maestro.agent import run
```

**Parser construction pattern** (`maestro/cli.py:11-21`, `27-59`):
```python
parser = argparse.ArgumentParser(
    prog="maestro",
    description="LangGraph agent using your ChatGPT Plus/Pro subscription",
)
sub = parser.add_subparsers(dest="command")

login_p = sub.add_parser("login", help="Authenticate with ChatGPT")
login_p.add_argument(
    "--device", action="store_true", help="Use device code flow (headless)"
)
```

```python
run_p = sub.add_parser("run", help="Run the agent")
run_p.add_argument("prompt", help="Prompt to send")
...
models_p = sub.add_parser("models", help="List available models")
...
sub.add_parser("status", help="Show auth status")

args = parser.parse_args()
```

**Dispatch pattern** (`maestro/cli.py:61-68`, `98-129`):
```python
if args.command == "login":
    method = "device" if args.device else "browser"
    ts = auth.login(method)
    print(f"Logged in as: {ts.email or ts.account_id}")

elif args.command == "logout":
    auth.logout()
```

```python
elif args.command == "status":
    ts = auth.load()
    if not ts:
        print("Not logged in.")
        sys.exit(1)
    print(f"Email:      {ts.email or '(unknown)'}")
    print(f"Account ID: {ts.account_id}")
```

```python
elif args.command == "run":
    ...
    try:
        result = run(
            args.model, args.prompt, args.system, workdir=wd, auto=args.auto
        )
        print(result)
    except RuntimeError as e:
        ...
        sys.exit(1)
```

**Planning notes**
- Keep parser setup flat and explicit; current CLI does not use helper functions or command registries.
- Add the new `auth` group by extending the existing `sub = parser.add_subparsers(...)` pattern.
- Keep top-level `logout` and `status` branches intact in this phase.
- Only top-level `login` should become a deprecated alias.

---

### `tests/test_auth_store.py` (test, file-I/O)

**Analog:** `tests/test_tools.py` for tmp-path file tests; `tests/test_agent_loop.py` for auth compatibility imports and mocking style.

**Simple pytest function style** (`tests/test_tools.py:1-23`):
```python
import pytest
from maestro.tools import resolve_path, PathOutsideWorkdirError


def test_resolve_path_allows_valid(tmp_path):
    result = resolve_path("src/main.py", tmp_path)
    assert result == (tmp_path / "src/main.py").resolve()


def test_resolve_path_blocks_traversal(tmp_path):
    with pytest.raises(PathOutsideWorkdirError):
        resolve_path("../../etc/passwd", tmp_path)
```

**File I/O assertion style** (`tests/test_tools.py:26-42`, `65-78`):
```python
f = tmp_path / "hello.txt"
f.write_text("line1\nline2\nline3\n")
result = read_file({"path": "hello.txt"}, tmp_path)
assert result["content"] == "line1\nline2\nline3\n"
```

```python
(tmp_path / "f.py").write_text("old")
write_file({"path": "f.py", "content": "new"}, tmp_path)
assert (tmp_path / "f.py").read_text() == "new"
```

**Monkeypatch / patch style** (`tests/test_tools.py:152-179`, `tests/test_agent_loop.py:37-46`):
```python
def test_execute_tool_destructive_denied(tmp_path, monkeypatch):
    from maestro.tools import execute_tool
    monkeypatch.setattr("builtins.input", lambda _: "n")
    result = execute_tool("write_file", {"path": "x.py", "content": "x"}, tmp_path, auto=False)
    assert result == {"error": "user denied"}
```

```python
with patch("maestro.agent.httpx.stream", return_value=mock_cm):
    result = _run_agentic_loop(
        messages=[HumanMessage(content="say hi")],
        model="gpt-5.4-mini",
        instructions="You are helpful.",
        tokens=FAKE_TOKENS,
        workdir=tmp_path,
        auto=True,
    )
```

**Backward-compat import pattern** (`tests/test_agent_loop.py:6-10`):
```python
from maestro.auth import TokenSet

FAKE_TOKENS = TokenSet(
    access="tok", refresh="ref", expires=9999999999.0, account_id="acc"
)
```

**Planning notes**
- New auth-store tests should stay as plain function tests; no fixtures/classes currently used.
- Use `tmp_path` + `monkeypatch` for `MAESTRO_AUTH_FILE` redirection.
- Add explicit regression coverage that `load()` still returns `TokenSet` and that `maestro login` remains callable as alias behavior.

## Shared Patterns

### Secure file persistence
**Source:** `maestro/auth.py:82-95`
**Apply to:** New `get/set/remove/all_providers` store internals
```python
AUTH_FILE.parent.mkdir(parents=True, exist_ok=True)
AUTH_FILE.write_text(...)
AUTH_FILE.chmod(0o600)
```

### Backward-compat shim boundary
**Source:** `maestro/auth.py:73-102`, `maestro/agent.py:268-271`, `tests/test_agent_loop.py:6-10`
**Apply to:** `auth.load()`, `auth._save()`, `auth.logout()`, `TokenSet`
```python
def load() -> TokenSet | None:
    if not AUTH_FILE.exists():
        return None
    data = json.loads(AUTH_FILE.read_text())
    return TokenSet(**data)
```

```python
tokens = auth.load()
if not tokens:
    raise RuntimeError("Not logged in. Run: maestro login")
```

### CLI error/output handling
**Source:** `maestro/cli.py:61-68`, `74-77`, `98-102`, `122-129`
**Apply to:** New `auth` command dispatch and deprecated top-level `login`
```python
print("Not logged in.")
sys.exit(1)
```

```python
ts = auth.login(method)
print(f"Logged in as: {ts.email or ts.account_id}")
```

## No Analog Found

| File / Concern | Role | Data Flow | Reason |
|----------------|------|-----------|--------|
| Nested `auth` subcommand group in `maestro/cli.py` | route | request-response | Current CLI only has flat top-level commands; use current parser/dispatch layout plus `02-RESEARCH.md` nested-subparser notes. |
| Runtime deprecation warning for legacy `maestro login` | route | request-response | No existing `warnings.warn(...)` pattern in repo; planner should use the Phase 2 research example, only on top-level `login`. |
| Provider-id validation in auth store | service | file-I/O | No existing validation helper in repo; use minimal inline validation if implemented, not a new framework. |

## Metadata

**Locked scope applied:** per-provider auth storage in `maestro/auth.py`; new auth-store public API; minimal CLI change for `AUTH-08`; only deprecate top-level `maestro login`; keep top-level `logout`/`status`; keep `maestro/agent.py` unchanged.

**Analog search scope:** `maestro/*.py`, `tests/*.py`

**Main analog files read:**
- `maestro/auth.py`
- `maestro/cli.py`
- `maestro/agent.py`
- `tests/test_agent_loop.py`
- `tests/test_tools.py`

**Files scanned:** 8
**Pattern extraction date:** 2026-04-17
