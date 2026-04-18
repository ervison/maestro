---
phase: 07-github-copilot-provider
plan: 01
type: execute
completed: "2026-04-18"
requires: []
provides: [COPILOT-01, COPILOT-02, COPILOT-03, COPILOT-04, COPILOT-05, AUTH-04, AUTH-07]
affects: [maestro/providers/copilot.py, tests/test_copilot_provider.py, pyproject.toml]
tech-stack:
  added: [httpx-sse]
  patterns: [OAuth device code flow, OpenAI chat completions API, SSE streaming]
key-files:
  created:
    - maestro/providers/copilot.py: 351 lines - CopilotProvider implementation
    - tests/test_copilot_provider.py: 805 lines - Comprehensive test suite
  modified:
    - pyproject.toml: Added github-copilot entry point, httpx-sse dependency
    - maestro/providers/__init__.py: Added CopilotProvider export
decisions:
  - Used httpx-sse library for SSE streaming (per STACK.md)
  - Implemented OpenAI chat completions wire format (not Responses API)
  - CLIENT_ID "Ov23li8tweQw6odWQebz" per user decision D-01
  - Headers x-initiator/user and Openai-Intent/conversation-edits per D-02
  - slow_down error increases interval by 5 seconds (AUTH-07)
metrics:
  duration: "~45 min"
  files-created: 2
  files-modified: 2
  tests-added: 26 (1 integration skipped)
  tests-passing: 118 (provider-related)
---

# Phase 7 Plan 1: GitHub Copilot Provider Implementation - Summary

## One-Liner

Implemented GitHub Copilot provider with OAuth device code flow, SSE streaming, and full test coverage validating the multi-provider architecture.

## What Was Built

### 1. CopilotProvider (`maestro/providers/copilot.py`)

Full ProviderPlugin implementation for GitHub Copilot:

- **OAuth Device Code Flow (`login()`)**:
  - POST to `github.com/login/device/code` with CLIENT_ID
  - Display user_code and instructions to user
  - Poll `github.com/login/oauth/access_token` with interval + 5s safety margin
  - Handle `authorization_pending`, `slow_down` (interval += 5), `expired_token`, `access_denied`
  - Store `ghu_...` access token via `auth.set()`

- **Streaming Completions (`stream()`)**:
  - Convert neutral Message/Tool to OpenAI chat completions format
  - POST to `api.githubcopilot.com/chat/completions` with required headers
  - Parse SSE stream using `httpx_sse.aconnect_sse()`
  - Yield text deltas and final Message with tool_calls

- **Wire Format Helpers**:
  - `_convert_messages_to_wire()`: Maps neutral types to OpenAI chat format
  - `_convert_tools_to_wire()`: Maps Tool to function schema format
  - Tool-call deltas are parsed inline while processing SSE events and assembled into the final `Message.tool_calls`

### 2. Test Suite (`tests/test_copilot_provider.py`)

26 comprehensive tests covering:

- **Protocol compliance** (2 tests): isinstance check, id/name properties
- **Authentication** (7 tests): auth_required, is_authenticated, login flow with error handling
- **Model listing** (2 tests): returns known models, returns copy
- **Wire format** (6 tests): user, assistant, system, tool messages; tools conversion
- **Streaming** (5 tests): auth error, headers, text deltas, final message, tool calls
- **Integration** (1 test, skipped): Real API call with credentials
- **Regression guard** (1 test): Marker for full suite

### 3. Entry Point Registration

```toml
[project.entry-points."maestro.providers"]
chatgpt = "maestro.providers.chatgpt:ChatGPTProvider"
github-copilot = "maestro.providers.copilot:CopilotProvider"
```

## Requirements Satisfied

| Requirement | Status | Evidence |
|-------------|--------|----------|
| COPILOT-01 | ✅ | `isinstance(CopilotProvider(), ProviderPlugin)` passes |
| COPILOT-02 | ✅ | `test_convert_*` tests verify wire format |
| COPILOT-03 | ✅ | `test_stream_sends_correct_headers` verifies headers |
| COPILOT-04 | ✅ | `test_list_models_returns_known_models` passes |
| COPILOT-05 | ✅ | `test_is_authenticated_*` tests pass |
| AUTH-04 | ✅ | `login()` implements full device code flow |
| AUTH-07 | ✅ | `test_login_handles_slow_down` verifies interval += 5 |

## Test Results

```bash
$ pytest tests/test_copilot_provider.py -v
26 passed, 1 skipped, 1 warning

$ pytest tests/ (provider-related)
118 passed, 1 skipped, 1 warning
```

## Verification Commands

```bash
# 1. Protocol compliance
python -c "from maestro.providers.copilot import CopilotProvider; from maestro.providers import ProviderPlugin; assert isinstance(CopilotProvider(), ProviderPlugin)"

# 2. Provider discovery
python -c "from maestro.providers.registry import get_provider; p = get_provider('github-copilot'); assert p.id == 'github-copilot'"

# 3. Run Copilot tests
pytest tests/test_copilot_provider.py -v

# 4. Run all provider tests
pytest tests/test_copilot_provider.py tests/test_provider_registry.py tests/test_provider_protocol.py tests/test_chatgpt_provider.py tests/test_agent_loop_provider.py -v
```

## Deviations from Plan

None - plan executed exactly as written.

## Threat Surface Scan

| Flag | File | Description |
|------|------|-------------|
| None | - | No new threat surface beyond what was modeled in PLAN.md |

All threats from T-07-01 through T-07-05 are mitigated as specified:
- Hardcoded GitHub URLs (no user input)
- auth.set() with 0o600 permissions
- No token logging
- 15-minute timeout on polling
- Minimal read:user scope

## Key Implementation Details

### OAuth Device Code Flow

The flow follows GitHub's device code specification exactly:
1. Request device code with `client_id` and `scope`
2. Display `user_code` to user with URL
3. Poll access token endpoint with `interval + 5s` delay
4. Handle `slow_down` by incrementing interval (AUTH-07 requirement)

### SSE Streaming

Uses `httpx_sse.aconnect_sse()` for robust SSE parsing:
- Handles `data:` prefix stripping
- Parses `[DONE]` termination
- Buffers partial tool_call deltas across events
- Yields text chunks progressively, final Message at end

### Wire Format

OpenAI Chat Completions API (NOT Responses API):
- Messages: `{"role": "user|assistant|system|tool", "content": "..."}`
- Tools: `{"type": "function", "function": {...}}`
- Headers: `x-initiator: user`, `Openai-Intent: conversation-edits`

## Commits

- `4fe5997`: feat(07-01): implement GitHub Copilot provider with OAuth device code flow

## Self-Check

- [x] Created files exist: `maestro/providers/copilot.py`, `tests/test_copilot_provider.py`
- [x] Modified files updated: `pyproject.toml`, `maestro/providers/__init__.py`
- [x] Entry point registered: `github-copilot`
- [x] All Copilot tests pass (26 passed, 1 skipped)
- [x] Provider discovery works: `get_provider('github-copilot')` returns instance
- [x] No circular imports verified
- [x] No regressions in provider-related tests (118 passed)

## Self-Check: PASSED
