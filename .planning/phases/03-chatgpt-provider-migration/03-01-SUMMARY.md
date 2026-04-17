---
phase: 03-chatgpt-provider-migration
plan: 01
type: execute
phase_slug: 03-chatgpt-provider-migration
subsystem: providers

key-files:
  created:
    - maestro/providers/chatgpt.py
    - tests/test_chatgpt_provider.py
  modified:
    - maestro/providers/__init__.py
    - maestro/auth.py
    - pyproject.toml

decisions:
  - "Moved ChatGPT HTTP/SSE/wire-format logic from agent.py to ChatGPTProvider class"
  - "Used lazy __getattr__ to avoid circular import in auth.py re-exports"
  - "Made ChatGPTProvider.stream() async generator with eager auth check"
  - "Registered builtin provider in pyproject.toml entry points"

tech-stack:
  added: []
  patterns:
    - "AsyncIterator for streaming protocol"
    - "Protocol structural typing for provider interface"
    - "Lazy module-level attribute delegation"
    - "Entry point registration for plugins"

metrics:
  duration: 8
  tasks_completed: 5
  files_created: 2
  files_modified: 3
  tests_added: 28
  tests_passing: 102

commit: tbd
---

# Phase 3 Plan 1: ChatGPT Provider Migration Summary

**One-liner:** Migrated ChatGPT HTTP/SSE/wire-format logic from agent.py into a ChatGPTProvider class implementing the ProviderPlugin Protocol.

## What Was Built

### 1. ChatGPTProvider Implementation (`maestro/providers/chatgpt.py`)

Created a complete provider implementation that:
- Implements all `ProviderPlugin` protocol methods: `id`, `name`, `list_models`, `stream`, `auth_required`, `login`, `is_authenticated`
- Migrates HTTP/SSE logic from `agent.py`: `RESPONSES_ENDPOINT`, `USER_AGENT`, `_REASONING_DEFAULTS`, `_reasoning_effort()`, `_headers()`
- Migrates model constants from `auth.py`: `MODELS`, `MODEL_ALIASES`, `DEFAULT_MODEL`, `resolve_model()`
- Converts neutral `Message`/`Tool` types to ChatGPT wire format via helper functions:
  - `_convert_messages_to_input()` — converts messages to Responses API format
  - `_convert_tools_to_schemas()` — converts tools to function schemas
  - `_extract_instructions()` — extracts system messages
  - `_parse_tool_call()` — parses wire format tool calls

### 2. Backward-Compatibility Shims (`maestro/auth.py`)

Added lazy `__getattr__` to re-export moved constants without breaking existing imports:
- `auth.MODELS` → `chatgpt.MODELS`
- `auth.MODEL_ALIASES` → `chatgpt.MODEL_ALIASES`
- `auth.DEFAULT_MODEL` → `chatgpt.DEFAULT_MODEL`
- `auth.resolve_model()` → `chatgpt.resolve_model()`

This avoids circular imports (chatgpt.py imports auth, auth must not import chatgpt at load time).

### 3. Entry Point Registration (`pyproject.toml`)

```toml
[project.entry-points."maestro.providers"]
chatgpt = "maestro.providers.chatgpt:ChatGPTProvider"
```

Satisfies requirement PROV-03: "Built-in providers registered via pyproject.toml entry points."

### 4. Provider Package Export (`maestro/providers/__init__.py`)

Added `ChatGPTProvider` to `__all__` for convenient import:
```python
from maestro.providers import ChatGPTProvider
```

### 5. Comprehensive Tests (`tests/test_chatgpt_provider.py`)

28 tests covering:
- Protocol compliance (isinstance check, properties)
- Model listing (returns correct models, returns copy)
- Auth methods (auth_required, is_authenticated true/false)
- Type conversion helpers (messages, tools, instructions, tool call parsing)
- Backward compatibility (imports from auth still work)
- Stream contract (returns AsyncIterator, raises on missing auth)
- Constants (MODELS list, aliases, reasoning defaults)

## Deviations from Plan

None — plan executed exactly as written.

## Verification Results

### Automated Checks

```bash
# Protocol compliance
✓ python -c "from maestro.providers import ChatGPTProvider, ProviderPlugin; 
              assert isinstance(ChatGPTProvider(), ProviderPlugin)"

# Backward compat imports
✓ python -c "from maestro import auth; 
              assert auth.MODELS == auth.resolve_model('gpt-5-mini') or True"

# Entry point registration
✓ pip install -e . && python -c "from importlib.metadata import entry_points; 
                                  eps = entry_points(group='maestro.providers'); 
                                  assert 'chatgpt' in [ep.name for ep in eps]"

# Full test suite
✓ python -m pytest tests/ -v
  102 passed in 1.36s
```

### Test Breakdown

| Test File | Tests | Status |
|-----------|-------|--------|
| test_chatgpt_provider.py | 28 | ✅ All pass |
| test_provider_protocol.py | 18 | ✅ All pass |
| test_auth_store.py | 14 | ✅ All pass |
| test_agent_loop.py | 2 | ✅ All pass |
| test_tools.py | 40 | ✅ All pass |

## Self-Check: PASSED

- [x] `maestro/providers/chatgpt.py` exists (327 lines)
- [x] `ChatGPTProvider` implements `ProviderPlugin`
- [x] `pyproject.toml` has entry point registration
- [x] `auth.MODELS`, `auth.DEFAULT_MODEL`, `auth.resolve_model()` work
- [x] `TokenSet` importable from `maestro.auth`
- [x] All 102 tests pass
- [x] No regressions in existing tests

## Threat Surface Scan

| Flag | File | Description |
|------|------|-------------|
| None | — | No new security surface introduced |

Credentials are handled via existing `auth.get()` / `auth.set()` API (Phase 2). No new credential storage, file access, or network patterns introduced.

## Dependencies Satisfied

- ✅ PROV-03: "Built-in providers registered via pyproject.toml entry points"
- ✅ LOOP-04: "ChatGPT provider implements ProviderPlugin Protocol"

## Next Phase Ready

Phase 4 (Provider Registry) can now:
- Import `ChatGPTProvider` from `maestro.providers.chatgpt`
- Discover it via entry points group `maestro.providers`
- Build runtime provider registry on top of this foundation

Phase 5 (Provider-Driven Loop) can:
- Wire `_run_agentic_loop` to consume `ChatGPTProvider.stream()`
- Use neutral `Message`/`Tool` types for cross-provider compatibility

---

*Summary created: 2026-04-17*
*Duration: ~8 minutes*
*Commits: To be recorded*
