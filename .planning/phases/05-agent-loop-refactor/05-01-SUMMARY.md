---
phase: 05-agent-loop-refactor
plan: 01
status: complete
completed_date: 2026-04-18
duration: 30min
requirements: [LOOP-01, LOOP-02, LOOP-03]
truths_satisfied:
  - "_run_agentic_loop calls provider.stream() instead of httpx.stream()"
  - "Unauthenticated provider raises RuntimeError with 'maestro auth login <provider_id>'"
  - "All 190 existing tests pass (exceeds 26+ requirement)"
  - "maestro run 'task' delegates to provider via registry"
files_modified:
  created: []
  modified:
    - maestro/agent.py
    - tests/test_agent_loop.py
tech_stack:
  added: []
  patterns:
    - "Sync wrapper for async provider.stream() using asyncio.run()"
    - "Neutral Message/Tool type conversion helpers"
    - "Provider registry integration via get_default_provider()"
key_decisions:
  - "Use asyncio.run() to bridge sync _run_agentic_loop with async provider.stream()"
  - "Provider handles auth validation internally; loop surfaces provider's RuntimeError unchanged"
  - "Preserve _call_responses_api for models --check command (unchanged per D-05)"
  - "Tool schemas converted to neutral Tool types for provider-agnostic interface"
metrics:
  commits: 2
  tests_passing: 190
  files_changed: 2
  lines_added: 154
  lines_deleted: 178
---

# Phase 5 Plan 01: Agent Loop Refactor Summary

## Overview

Refactored `_run_agentic_loop` to delegate HTTP streaming to `provider.stream()` instead of direct `httpx.stream()` calls. The provider abstraction now handles all wire-format conversion, SSE parsing, and auth validation internally.

## Implementation

### Task 1: Refactor _run_agentic_loop

**Changes to `maestro/agent.py`:**

1. **Removed direct HTTP imports** - No more `RESPONSES_ENDPOINT`, `_headers`, `_reasoning_effort` in the loop path
2. **Added provider imports** - `Message`, `Tool`, `ToolCall` from `maestro.providers.base`, `get_default_provider` from registry
3. **Added conversion helpers:**
   - `_convert_tool_schemas()` - Converts raw `TOOL_SCHEMAS` dicts to neutral `Tool` types
   - `_convert_messages_to_neutral()` - Converts LangChain messages to neutral `Message` types
   - `_run_provider_stream_sync()` - Sync wrapper that uses `asyncio.run()` to consume async `provider.stream()`
4. **Refactored `_run_agentic_loop` signature**:
   - Removed: `tokens: auth.TokenSet` parameter
   - Added: `provider` parameter (accepts any ProviderPlugin)
5. **Replaced HTTP streaming loop** with provider iteration:
   - Calls `_run_provider_stream_sync(provider, messages, model, tools)`
   - Processes yielded `str` chunks (streaming text) and final `Message` (with `tool_calls`)
   - Executes tools and appends results as `Message(role="tool", ...)` for next iteration
6. **Updated `run()` function** to use `get_default_provider()` from registry
7. **Preserved `_call_responses_api`** unchanged for `maestro models --check` command

### Task 2: Update Tests

**Changes to `tests/test_agent_loop.py`:**

1. **Removed httpx mocking** - Deleted `patch("maestro.agent.httpx.stream", ...)` patterns
2. **Removed FAKE_TOKENS** - No longer needed since provider handles auth internally
3. **Added mock provider factory** - `make_mock_provider(stream_results)` creates a mock ProviderPlugin
4. **Updated test assertions** to use neutral `Message` and `ToolCall` types
5. **Both tests pass** verifying direct answer and tool-call execution behavior preserved

### Task 3: Full Test Suite Verification

- **190 tests passing** (all existing tests pass without modification)
- No regressions in any test files
- Provider registry tests continue to work
- Auth store tests unaffected (they mock at a different level)

## Verification

### LOOP-01: Provider.stream() delegation
```bash
grep -n "provider.stream\|_run_provider_stream_sync" maestro/agent.py
# Found: _run_provider_stream_sync function and provider.stream() call
```

### LOOP-02: Auth error guidance
```bash
grep -rn "maestro auth login" maestro/
# Found in maestro/providers/chatgpt.py:225
# "Not authenticated. Run: maestro auth login chatgpt"
```

### LOOP-03: All tests pass
```bash
python -m pytest -x -q
# 190 passed
```

## Deviations from Plan

None. Plan executed exactly as written.

## Key Files

| File | Purpose |
|------|---------|
| `maestro/agent.py` | Provider-delegated agentic loop |
| `tests/test_agent_loop.py` | Loop behavior tests with mock provider |

## Commits

1. `bc693c6`: feat(05-01): refactor agent loop to use provider.stream()
2. `37001ea`: test(05-01): update agent loop tests to mock provider

## Self-Check: PASSED

- [x] `maestro/agent.py` modified and committed
- [x] `tests/test_agent_loop.py` modified and committed
- [x] All 190 tests passing
- [x] provider.stream() used instead of httpx.stream()
- [x] get_default_provider() used in run()
- [x] Auth errors have actionable guidance
