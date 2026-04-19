---
phase: 10-scheduler-workers
reviewed: 2026-04-18T23:38:17Z
depth: deep
files_reviewed: 6
files_reviewed_list:
  - maestro/multi_agent.py
  - maestro/planner/schemas.py
  - maestro/planner/node.py
  - maestro/agent.py
  - tests/test_scheduler_workers.py
  - tests/test_planner_schemas.py
findings:
  critical: 0
  warning: 1
  info: 0
  total: 1
status: issues_found
---

# Phase 10: Code Review Report (Round 3)

**Verdict:** FAILING  
**Final Score:** 94/100

**Reviewed:** 2026-04-18T23:38:17Z  
**Depth:** deep  
**Files Reviewed:** 6  
**Status:** issues_found

## Summary

Round 2’s functional fixes are present: `worker_node()` now threads `provider`/`model`, `scheduler_node()` validates the DAG before rebuilding topology, `run_multi_agent()` threads provider/model into both planner and worker stages, `dispatch_node` remains a no-op, and `run_multi_agent()` still requires `depth` explicitly. I also verified `_run_agentic_loop()` itself was not modified and no new dependencies were introduced in the reviewed Phase 10 files.

Verification evidence is strong on execution behavior: `pytest tests/test_scheduler_workers.py tests/test_planner_schemas.py` passed with **56/56** tests, and `test_scheduler_workers.py` now contains **26** tests. However, one blocking warning remains: the strengthened path-guard test still does **not actually prove** that an escape-attempt tool call reaches the tool layer and is blocked there.

## Checklist

- ✅ `worker_node()` passes provider/model into `_run_agentic_loop()`
- ✅ `scheduler_node()` calls `validate_dag()` before topology rebuild
- ✅ `run_multi_agent()` threads provider/model to planner and worker stages
- ❌ Path-guard test does **not** prove an escape attempt is blocked by tool execution
- ✅ `scheduler_route()` returns only strings
- ✅ `dispatch_route()` returns only `list[Send]`
- ✅ 26 tests present in `tests/test_scheduler_workers.py`; 56/56 combined tests passed
- ✅ `_run_agentic_loop()` unchanged
- ✅ No new dependencies found in reviewed files
- ✅ `depth` is required on `run_multi_agent()`
- ✅ `dispatch_node` remains a no-op

## Warnings

### WR-01: Path-guard regression test still succeeds without exercising the guarded tool path

**File:** `tests/test_scheduler_workers.py:492-560`  
**Issue:** The test intends to verify that a worker cannot write outside `workdir`, but the mocked provider yields raw OpenAI-style dict chunks (`tool_call_chunk`, `finish_chunk`) instead of the provider contract used by `_run_agentic_loop()`. In `maestro/agent.py:297-316`, `_run_agentic_loop()` only recognizes streamed `str` chunks and a final neutral `Message`; dict chunks are ignored, so the loop raises `RuntimeError("No output received from agent loop")` before any tool call is executed. The test therefore passes even if the path guard in `execute_tool()`/`resolve_path()` were broken.

**Fix:** Make the test drive the real tool-call path by returning a final neutral `Message` with `tool_calls`, or by patching `execute_tool()` directly and asserting it receives the escaping path and returns a `PathOutsideWorkdirError`-backed error. Example shape:

```python
from maestro.providers.base import Message, ToolCall

async def mock_stream(*args, **kwargs):
    yield Message(
        role="assistant",
        content="",
        tool_calls=[
            ToolCall(
                id="call_123",
                name="write_file",
                arguments={"path": "../escape_attempt.txt", "content": "escaped"},
            )
        ],
    )
```

Then assert both:
- the worker fails because the tool layer rejected the path, and
- the returned error mentions the workdir escape, not `No output received from agent loop`.

---

_Reviewed: 2026-04-18T23:38:17Z_  
_Reviewer: the agent (gsd-code-reviewer)_  
_Depth: deep_
