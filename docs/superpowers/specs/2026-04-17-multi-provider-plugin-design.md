# Multi-Provider Plugin System — Design Spec

**Date:** 2026-04-17  
**Status:** Approved  
**Scope:** Add a plugin-based provider system to maestro, starting with GitHub Copilot as the first new builtin provider alongside the existing ChatGPT provider.

---

## Problem

The maestro agent is hardwired to a single provider (OpenAI ChatGPT via unofficial OAuth2). Every concern — auth flow, token storage, HTTP calls, SSE parsing, tool schema format, model names — is coupled to one provider. Adding a second provider (GitHub Copilot, Anthropic, Gemini, etc.) would require forking the entire agent loop.

---

## Solution

A plugin-based provider system where:

- A `ProviderPlugin` Protocol defines the interface every provider must implement
- Providers are discovered via Python entry points (`maestro.providers` group)
- The agent loop operates on neutral internal types (`Message`, `ToolCall`, `Tool`) — providers convert to/from their wire format internally
- Auth is stored per-provider in `~/.maestro/auth.json`
- Model selection is config-driven per agent, with a `provider_id/model_id` string format

---

## Architecture

```
maestro run "task"
      │
      ▼
config.resolve_model(agent_name)
      │  "github-copilot/gpt-4o"
      ▼
providers.get_provider("github-copilot")  ← registry from entry points
      │  CopilotProvider instance
      ▼
provider.stream(messages, model_id, tools)
      │  async iterator of str | Message
      ▼
_run_agentic_loop  ← consumes chunks, executes tool calls, builds message history
      │
      ▼
stdout / caller
```

---

## File Structure

```
maestro/
  providers/
    __init__.py      ← registry: discover_providers(), get_provider(id)
    base.py          ← Protocol ProviderPlugin + types: Message, ToolCall, Tool
    chatgpt.py       ← existing provider migrated from agent.py
    copilot.py       ← new GitHub Copilot provider
  config.py          ← reads ~/.maestro/config.json, resolves model per agent
  auth.py            ← multi-slot credential store (keyed by provider_id)
  agent.py           ← _run_agentic_loop uses Provider, no direct HTTP
  cli.py             ← maestro auth login/logout/status subcommands
pyproject.toml       ← entry-points for builtin providers
```

---

## Neutral Types (`providers/base.py`)

```python
from typing import Protocol, AsyncIterator
from dataclasses import dataclass, field

@dataclass
class Tool:
    name: str
    description: str
    parameters: dict        # JSON Schema

@dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict

@dataclass
class Message:
    role: Literal["user", "assistant", "system", "tool"]
    content: str
    tool_calls: list[ToolCall] = field(default_factory=list)
    tool_call_id: str | None = None

class ProviderPlugin(Protocol):
    id: str                 # e.g. "github-copilot"
    name: str               # e.g. "GitHub Copilot"

    def list_models(self) -> list[str]: ...

    def stream(
        self,
        messages: list[Message],
        model: str,
        tools: list[Tool] | None = None,
    ) -> AsyncIterator[str | Message]:
        # yields: str (text chunk) or Message (complete assistant message)
        ...

    def auth_required(self) -> bool: ...
    def login(self) -> None: ...
    def is_authenticated(self) -> bool: ...
```

Each provider implements `stream()` by converting neutral types to its wire format, performing the HTTP SSE call, and yielding neutral types back. The agent loop never sees provider-specific JSON.

---

## Plugin Discovery (`providers/__init__.py`)

```python
from importlib.metadata import entry_points
from functools import lru_cache

@lru_cache(maxsize=1)
def discover_providers() -> dict[str, ProviderPlugin]:
    result = {}
    for ep in entry_points(group="maestro.providers"):
        cls = ep.load()
        instance = cls()
        result[instance.id] = instance
    return result

def get_provider(provider_id: str) -> ProviderPlugin:
    providers = discover_providers()
    if provider_id not in providers:
        raise ValueError(f"Unknown provider: {provider_id!r}. Available: {list(providers)}")
    return providers[provider_id]
```

Builtin providers are registered in `pyproject.toml`:

```toml
[project.entry-points."maestro.providers"]
chatgpt = "maestro.providers.chatgpt:ChatGPTProvider"
github-copilot = "maestro.providers.copilot:CopilotProvider"
```

External providers install via `pip install maestro-provider-gemini` and declare the same entry point group. No config change needed.

---

## Config (`config.py`)

Config file location: `~/.maestro/config.json`

```json
{
  "model": "github-copilot/gpt-4o",
  "agent": {
    "explorer": {
      "model": "github-copilot/grok-code-fast-1"
    },
    "planner": {
      "model": "github-copilot/gpt-4o-mini"
    }
  }
}
```

Model resolution order (highest priority first):

1. `--model` CLI flag
2. `MAESTRO_MODEL` environment variable
3. `config.agent.<agent_name>.model` (when running a named agent)
4. `config.model` (global default)
5. First model of first authenticated provider (automatic fallback)

Model string format: `"<provider_id>/<model_id>"`. Parser:

```python
def parse_model(model: str) -> tuple[str, str]:
    provider_id, _, model_id = model.partition("/")
    if not model_id:
        raise ValueError(f"Model must be in format provider/model, got: {model!r}")
    return provider_id, model_id
```

---

## Auth (`auth.py`)

Multi-slot credential store at `~/.maestro/auth.json` (mode `0o600`):

```json
{
  "github-copilot": {
    "access": "ghu_xxxxxxxxxxxx",
    "expires": 0
  },
  "chatgpt": {
    "access": "...",
    "refresh": "...",
    "expires": 1713400000.0,
    "account_id": "...",
    "email": "..."
  }
}
```

Public API:

```python
def get(provider_id: str) -> dict | None: ...
def set(provider_id: str, data: dict) -> None: ...
def remove(provider_id: str) -> None: ...
def all_providers() -> dict[str, dict]: ...
```

The existing `TokenSet` dataclass is kept for the ChatGPT provider and moved to `providers/chatgpt.py`. The `auth.py` module becomes a generic key-value credential store.

---

## GitHub Copilot Provider (`providers/copilot.py`)

### OAuth Device Code Flow

Uses GitHub's device authorization grant. No second token exchange — the raw GitHub OAuth token (`ghu_...`) is used directly as the Copilot API Bearer token.

```
CLIENT_ID = "Ov23li8tweQw6odWQebz"
DEVICE_CODE_URL = "https://github.com/login/device/code"
ACCESS_TOKEN_URL = "https://github.com/login/oauth/access_token"
COPILOT_API_BASE = "https://api.githubcopilot.com"
SCOPE = "read:user"
POLLING_SAFETY_MARGIN = 3  # seconds
```

Login flow (`login()`):

1. POST device code request → get `verification_uri`, `user_code`, `device_code`, `interval`
2. Print `verification_uri` and `user_code` to stdout
3. Poll `access_token` endpoint every `interval + 3` seconds
4. On success, call `auth.set("github-copilot", {"access": token, "expires": 0})`

### Stream implementation

Calls `POST https://api.githubcopilot.com/chat/completions` with:

- Standard OpenAI chat completions format (`messages`, `tools`, `stream: true`)
- Tool schemas converted from `Tool` neutral type to OpenAI function-calling format
- Headers: `Authorization: Bearer <token>`, `x-initiator: user`, `Openai-Intent: conversation-edits`

Parses SSE stream, yields:

- `str` for `choices[0].delta.content` text chunks
- `Message(role="assistant", tool_calls=[...])` when a tool call is complete

---

## Changes to `agent.py`

`_run_agentic_loop` changes:

**Before:** builds HTTP payload dict, calls `httpx.stream` directly, parses SSE events.

**After:**

```python
async def _run_agentic_loop(task, agent_name=None, ...):
    provider_id, model_id = config.resolve_model(agent_name)
    provider = providers.get_provider(provider_id)

    if not provider.is_authenticated():
        raise RuntimeError(f"Not authenticated with {provider_id}. Run: maestro auth login {provider_id}")

    messages = [Message(role="user", content=task)]

    while True:
        chunks = []
        tool_calls = []
        async for item in provider.stream(messages, model_id, TOOLS):
            if isinstance(item, str):
                chunks.append(item)
                print(item, end="", flush=True)
            elif isinstance(item, Message):
                tool_calls.extend(item.tool_calls)

        # execute tool calls, append results, continue loop or break
        ...
```

The loop structure is identical to the current implementation — only the HTTP layer is replaced by `provider.stream()`.

---

## CLI Changes (`cli.py`)

New `auth` subcommand group:

```bash
maestro auth login <provider-id>    # runs provider.login()
maestro auth logout <provider-id>   # removes credentials
maestro auth status                 # lists all providers + auth state
maestro models [--provider <id>]    # lists available models
```

Existing `run` subcommand gains `--model` flag:

```bash
maestro run --model github-copilot/gpt-4o "task"
```

---

## Backward Compatibility

- Existing `maestro run` behavior is unchanged if `~/.maestro/config.json` is absent (falls back to ChatGPT provider with current default model)
- Existing `maestro auth login` (ChatGPT OAuth flow) becomes `maestro auth login chatgpt` — the old command is kept as an alias with a deprecation warning
- All 26 existing tests must pass without modification

---

## Testing

New tests required:

| Test                        | What it covers                                                                         |
| --------------------------- | -------------------------------------------------------------------------------------- |
| `test_config.py`            | `parse_model`, `resolve_model` priority order, missing config fallback                 |
| `test_auth_multislot.py`    | `get`/`set`/`remove`/`all_providers`, file permissions                                 |
| `test_provider_registry.py` | `discover_providers` finds builtins, `get_provider` raises on unknown                  |
| `test_copilot_auth.py`      | Device code flow (mocked HTTP), polling with `authorization_pending` and `slow_down`   |
| `test_copilot_stream.py`    | `stream()` converts neutral types to wire format and back (mocked SSE)                 |
| `test_chatgpt_provider.py`  | Existing agent loop logic migrated to ChatGPT provider (replaces `test_agent_loop.py`) |

---

## Out of Scope (v1)

- Providers other than GitHub Copilot and ChatGPT
- GitHub Enterprise Copilot support
- Token refresh for GitHub Copilot (token is long-lived, no refresh needed)
- Model picker TUI (interactive model selection)
- Per-provider rate limiting or retry logic
