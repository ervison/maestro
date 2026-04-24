---
phase: 17
reviewed: 2026-04-24T15:29:13Z
depth: standard
files_reviewed: 51
files_reviewed_list:
  - maestro/__init__.py
  - maestro/agent.py
  - maestro/auth.py
  - maestro/cli.py
  - maestro/config.py
  - maestro/dashboard/__init__.py
  - maestro/dashboard/emitter.py
  - maestro/dashboard/server.py
  - maestro/domains.py
  - maestro/models.py
  - maestro/multi_agent.py
  - maestro/planner/__init__.py
  - maestro/planner/node.py
  - maestro/planner/schemas.py
  - maestro/planner/validator.py
  - maestro/planning.py
  - maestro/providers/__init__.py
  - maestro/providers/base.py
  - maestro/providers/chatgpt.py
  - maestro/providers/copilot.py
  - maestro/providers/registry.py
  - maestro/sdlc/__init__.py
  - maestro/sdlc/gaps_server.py
  - maestro/sdlc/generators.py
  - maestro/sdlc/harness.py
  - maestro/sdlc/prompts.py
  - maestro/sdlc/reflect.py
  - maestro/sdlc/schemas.py
  - maestro/sdlc/static/gaps.html
  - maestro/sdlc/writer.py
  - maestro/tools.py
  - pyproject.toml
  - run-phase.sh
  - script.py
  - tests/fixtures/hello_provider/hello_provider.py
  - tests/fixtures/hello_provider/pyproject.toml
  - tests/test_aggregator_guardrails.py
  - tests/test_cli_discover.py
  - tests/test_cli_planning.py
  - tests/test_copilot_smoke.py
  - tests/test_dashboard_emitter.py
  - tests/test_dashboard_integration.py
  - tests/test_dashboard_server.py
  - tests/test_planning_consistency.py
  - tests/test_provider_install_smoke.py
  - tests/test_sdlc_gaps_server.py
  - tests/test_sdlc_generators.py
  - tests/test_sdlc_harness.py
  - tests/test_sdlc_reflect.py
  - tests/test_sdlc_schemas.py
  - tests/test_sdlc_writer.py
findings:
  critical: 3
  warning: 3
  info: 0
  total: 6
status: issues_found
---

# Phase 17: Code Review Report

**Reviewed:** 2026-04-24T15:29:13Z
**Depth:** standard
**Files Reviewed:** 51
**Status:** issues_found

## Summary

Reviewed the requested Python, shell, HTML, TOML, and relevant test files with focus on multi-agent correctness, provider streaming, dashboard safety, and SDLC pipeline behavior. The highest-risk issues are in multi-agent scheduling and dashboard event retention: the scheduler can redispatch still-running tasks, and the dashboard keeps an unbounded in-memory event log on a hot path. I also found one high-complexity CLI function and two streaming-consumer bugs in the SDLC path.

Three requested files were not present in this worktree and could not be reviewed: `tests/test_agent_loop.py`, `tests/test_provider_protocol.py`, and `tests/test_tools.py`.

## Critical Issues

### CR-01: Scheduler can dispatch the same worker task multiple times

**File:** `maestro/multi_agent.py:124-154`, `maestro/multi_agent.py:284-324`
**Issue:** `scheduler_node()` only excludes tasks that are already in `completed` or `failed`. It does not track tasks that were already dispatched but are still running. After one worker finishes and routes back to `scheduler`, any sibling task whose dependencies are already satisfied is still considered ready and can be sent again. In multi-agent mode that can duplicate tool execution, duplicate file writes, and produce inconsistent shared-workdir state.
**Fix:** Track in-flight task IDs and exclude them from readiness until the worker returns success or failure.
```python
# state
in_progress: Annotated[list[str], operator.add]

# when dispatching
return {
    "ready_tasks": ready_tasks,
    "in_progress": [task["id"] for task in ready_tasks],
}

# scheduler readiness
in_progress = set(state.get("in_progress", []))
if tid not in terminal and tid not in in_progress and deps.issubset(completed):
    ready_ids.add(tid)

# worker completion/failure should remove task_id from in_progress
```

### CR-02: Dashboard event history grows without bounds

**File:** `maestro/dashboard/emitter.py:27-30`, `maestro/dashboard/emitter.py:61-64`
**Issue:** Every emitted event is appended to `_history`, and the list is never trimmed. Workers emit text chunks and tool logs on the hot path, so long runs or repeated sessions can accumulate unbounded in-memory state. This is a static memory leak in a high-frequency code path.
**Fix:** Replace `_history` with a bounded ring buffer or store only replay-safe snapshots.
```python
from collections import deque

def __init__(self) -> None:
    self._subscribers = []
    self._history = deque(maxlen=1000)
    self._lock = threading.Lock()
```

### CR-03: `main()` has critical cyclomatic complexity

**File:** `maestro/cli.py:56-553`
**Issue:** `main()` has estimated **CC=31** (static count; `radon` unavailable in this environment). It mixes parser construction, auth flows, model listing, run execution, planning, and discover handling in one function. At this complexity level, small CLI changes are likely to introduce unreachable branches or inconsistent exit behavior.
**Fix:** Split command handling into dedicated functions (`_handle_auth`, `_handle_models`, `_handle_run`, `_handle_legacy_login`, etc.) and dispatch from a small command router.

## Warnings

### WR-01: Gap enrichment breaks on real streaming providers

**File:** `maestro/sdlc/gaps_server.py:230-235`
**Issue:** `_llm_enrich()` assumes every stream item has `.content`. Real providers yield `str` chunks before the final `Message`, so `msg.content` raises `AttributeError` on the first chunk. Because `enrich_gap_items()` swallows the exception and falls back, LLM-based option enrichment never works with normal streaming providers.
**Fix:** Handle string chunks and final messages explicitly.
```python
collected_parts: list[str] = []
async for msg in provider.stream(messages, model=model):
    if isinstance(msg, str):
        collected_parts.append(msg)
    elif isinstance(msg, Message) and msg.content:
        collected_parts = [msg.content]
collected = "".join(collected_parts)
```

### WR-02: Reflect loop can double-append streamed JSON and skip corrections

**File:** `maestro/sdlc/reflect.py:173-179`
**Issue:** `_call_provider()` appends both incremental `str` chunks and the final assistant message content. For providers that emit deltas plus a full final message, JSON replies become duplicated (`<json><json>`), which makes `_extract_json()` fail and causes reflection cycles to be skipped as “malformed eval/fix JSON”.
**Fix:** Treat the final `Message` as canonical and replace previously collected deltas when it arrives.
```python
parts: list[str] = []
async for msg in provider.stream(messages, tools=None, model=model):
    if isinstance(msg, str):
        parts.append(msg)
    elif hasattr(msg, "role") and msg.role == "assistant" and msg.content:
        parts = [msg.content]
return "".join(parts).strip()
```

### WR-03: Dashboard server is exposed on all network interfaces by default

**File:** `maestro/dashboard/server.py:93-95`
**Issue:** The dashboard binds to `0.0.0.0`, but it serves unauthenticated live task data, logs, and outputs. On a shared machine or reachable dev network, other hosts can connect to the dashboard even though the CLI advertises `localhost`.
**Fix:** Bind to loopback by default and require explicit opt-in for remote exposure.
```python
server = ThreadingHTTPServer(("127.0.0.1", port), _make_handler(emitter))
```

---

_Reviewed: 2026-04-24T15:29:13Z_
_Reviewer: the agent (gsd-code-reviewer)_
_Depth: standard_
