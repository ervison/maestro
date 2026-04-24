---
phase: 17
fixed_at: 2026-04-24T17:30:00Z
review_path: 17-REVIEW.md
iteration: 4
findings_in_scope: 5
fixed: 5
skipped: 0
status: all_fixed
---

# Phase 17: Code Review Fix Report

**Fixed at:** 2026-04-24T17:30:00Z
**Source review:** 17-REVIEW.md
**Iteration:** 4

**Summary:**
- Findings in scope: 5
- Fixed: 5
- Skipped: 0

## Fixed Issues

All 5 in-scope findings (CR-01, CR-02, CR-03, WR-01, WR-02) were already fixed and committed in a prior fixer run (iteration 3). Code inspection and `git log` confirm the fixes are present in the codebase.

### CR-01: Scheduler can terminate while parallel workers are still running

**Files modified:** `maestro/multi_agent.py`
**Commit:** `0104c84`
**Applied fix:** Added `in_progress = dispatched - terminal` check in `scheduler_route()`. When dispatched workers haven't yet completed or failed, the function returns `"scheduler"` (loop-back) instead of `END`. `add_conditional_edges` also declares `"scheduler"` as a reachable target so LangGraph does not reject the self-loop at compile time.

### CR-02: Provider contract validator is untestably complex

**Files modified:** `maestro/providers/registry.py`
**Commit:** `6dfcf9d`
**Applied fix:** Extracted three focused helpers from the monolithic `_is_valid_provider()`:
- `_validate_simple_method(instance, method_name, required_args)` — validates zero-extra-arg interface methods
- `_validate_stream_signature(stream_attr)` — validates the `stream` positional signature
- `_validate_stream_return_type(stream_attr)` — validates async-iterator return type

`_is_valid_provider()` is now a thin composer that calls these three helpers in sequence.

### CR-03: Legacy HTTP stream path is too complex for safe maintenance

**Files modified:** `maestro/agent.py`
**Commit:** `df7e76c`
**Applied fix:** Extracted four focused helpers from `_run_httpx_stream_sync()`:
- `_convert_messages_to_input(messages)` — converts neutral Message list to ChatGPT Responses API wire format
- `_convert_tools_to_chatgpt(tools)` — converts neutral Tool list to ChatGPT tool format
- `_parse_sse_events(response)` — parses SSE lines, accumulating text deltas and ToolCall objects
- `_assemble_response(text_parts, tool_calls)` — builds the final result list

The main function is now a thin coordinator of ~20 lines.

### WR-01: Dashboard server is never shut down after `run --multi`

**Files modified:** `maestro/cli.py`
**Commit:** `b474bb1`
**Applied fix:** Captured the return value of `start_dashboard_server()` in `server`. Wrapped `run_multi_agent(...)` in a `try/finally` block that calls `server.shutdown()` and `server.server_close()` to release the listening socket and background thread regardless of success or failure.

### WR-02: Core agent loop needs refactoring before further feature growth

**Files modified:** `maestro/agent.py`
**Commit:** `729ba34`
**Applied fix:** Extracted three focused helpers from `_run_agentic_loop()`:
- `_collect_stream_chunks(stream_results)` — separates text-delta and Message chunks, returns `(final_text, tool_calls)`, raises `RuntimeError` on no output
- `_check_tool_loop(recent_tool_signatures, tool_calls, max_repeated)` — encapsulates the rolling-window repeated-call detection; raises `RuntimeError` on detection
- `_execute_tools_and_append(tool_calls, neutral_messages, final_text, wd, auto, on_tool_start)` — appends the assistant turn and executes each tool, returning updated `auto` flag

`_run_agentic_loop()` main body is now a clean iteration loop of ~30 lines with single-concern phases: stream → extract → check-loop → execute-tools.

---

_Fixed: 2026-04-24T17:30:00Z_
_Fixer: the agent (gsd-code-fixer)_
_Iteration: 4_
