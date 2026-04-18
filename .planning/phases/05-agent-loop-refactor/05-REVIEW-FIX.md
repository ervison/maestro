---
phase: 05-agent-loop-refactor
fixed_at: 2026-04-18T12:00:00Z
review_path: .planning/phases/05-agent-loop-refactor/05-REVIEW.md
iteration: 1
findings_in_scope: 3
fixed: 3
skipped: 0
status: all_fixed
---

# Phase 5: Code Review Fix Report

**Fixed at:** 2026-04-18T12:00:00Z
**Source review:** .planning/phases/05-agent-loop-refactor/05-REVIEW.md
**Iteration:** 1

**Summary:**
- Findings in scope: 3
- Fixed: 3
- Skipped: 0

## Fixed Issues

### WR-01: Streamed assistant text is returned twice

**Files modified:** `maestro/agent.py`
**Commit:** eea0760
**Applied fix:** Modified `_run_agentic_loop()` to track streamed text deltas separately from the final Message. When text deltas are present, the loop returns only the joined deltas (`"".join(text_parts)`). When no deltas were streamed, it falls back to `final_message.content`. This prevents the duplication bug where both streamed chunks AND final Message.content were concatenated.

Key changes in `maestro/agent.py`:
- Added `final_message: Message | None = None` tracking variable
- Removed `text_parts.append(chunk.content)` when receiving Message chunks
- Added logic to determine `final_text` based on whether deltas were streamed
- Returns early with `final_text` when no tool calls present

### WR-02: Tool-call follow-up requests lose the model's function-call context

**Files modified:** `maestro/agent.py`, `maestro/providers/chatgpt.py`
**Commit:** eea0760 (agent.py), f76b192 (chatgpt.py)
**Applied fix:** 

1. **In `maestro/agent.py`:** After detecting tool calls in the assistant message, the loop now preserves the assistant message with its `tool_calls` in `neutral_messages` BEFORE appending tool results. This ensures the conversation history includes the full context of what tools were requested.

2. **In `maestro/providers/chatgpt.py`:** Extended `_convert_messages_to_input()` to serialize assistant `tool_calls` as `function_call` items in the ChatGPT Responses API format. Each `ToolCall` is emitted as a `{"type": "function_call", "id": ..., "name": ..., "arguments": ...}` item before the assistant message content.

### IN-01: The updated loop tests no longer cover the real provider streaming contract

**Files modified:** `tests/test_agent_loop.py`
**Commit:** 3b73c91
**Applied fix:** Added three new regression tests:

1. **`test_agentic_loop_streaming_deltas_not_duplicated`**: Verifies that when a provider yields text deltas followed by a final Message, the loop returns text exactly once (regression test for WR-01).

2. **`test_agentic_loop_preserves_tool_call_context`**: Verifies that in a tool-call round-trip, the second iteration receives both the assistant message with `tool_calls` AND the tool result message (regression test for WR-02).

3. **`test_agentic_loop_uses_final_message_when_no_deltas`**: Verifies fallback behavior when provider only yields a final Message without any streaming deltas.

## Skipped Issues

None — all findings were successfully fixed.

## Verification Results

### Syntax Verification
All modified files pass Python syntax checks:
- `maestro/agent.py`: OK
- `maestro/providers/chatgpt.py`: OK  
- `tests/test_agent_loop.py`: OK

### Test Results
```
$ python -m pytest tests/test_agent_loop.py -x -v
============================= test session ==============================
platform linux -- Python 3.12.7, pytest-9.0.3
collected 5 items

tests/test_agent_loop.py::test_agentic_loop_direct_answer PASSED
tests/test_agent_loop.py::test_agentic_loop_one_tool_call PASSED
tests/test_agent_loop.py::test_agentic_loop_streaming_deltas_not_duplicated PASSED
tests/test_agent_loop.py::test_agentic_loop_preserves_tool_call_context PASSED
tests/test_agent_loop.py::test_agentic_loop_uses_final_message_when_no_deltas PASSED

============================== 5 passed in 0.21s ========================
```

### Full Test Suite
```
$ python -m pytest -x -q
................................. (truncated)
============================== 190 passed in 1.56s ========================
```

All 190 existing tests pass without modification, confirming zero regressions.

## Files Changed

| File | Change Type | Lines | Description |
|------|-------------|-------|-------------|
| `maestro/agent.py` | Modified | +20/-6 | Fix text duplication, preserve assistant tool_calls in message history |
| `maestro/providers/chatgpt.py` | Modified | +11/-2 | Serialize assistant tool_calls to function_call items |
| `tests/test_agent_loop.py` | Modified | +125/-1 | Add regression tests for streaming contract and tool-call context |

## Compliance with Phase 5 Decisions

- ✅ **D-01/D-02**: Loop continues to use `provider.stream()` via registry
- ✅ **D-03/D-04**: Auth errors still propagate from provider with actionable guidance
- ✅ **D-05/D-06**: Changes are minimal and strictly fix the identified regressions
- ✅ **LOOP-03**: All 190 tests pass without modification to existing tests

---

_Fixed: 2026-04-18T12:00:00Z_
_Fixer: the agent (gsd-code-fixer)_
_Iteration: 1_
