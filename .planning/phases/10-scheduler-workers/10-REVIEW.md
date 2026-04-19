---
phase: 10-scheduler-workers
reviewed: 2026-04-18T23:23:19Z
depth: deep
files_reviewed: 5
files_reviewed_list:
  - maestro/multi_agent.py
  - maestro/planner/schemas.py
  - maestro/planner/__init__.py
  - tests/test_scheduler_workers.py
  - tests/test_planner_schemas.py
findings:
  critical: 1
  warning: 2
  info: 1
  total: 4
status: issues_found
score_overall: 79
decision: FAILING
---

# Phase 10: Code Review Report

**Reviewed:** 2026-04-18T23:23:19Z
**Depth:** deep
**Files Reviewed:** 5
**Status:** issues_found
**Overall Score:** 79/100
**Decision:** FAILING

## Summary

Deep review covered the Phase 10 source files plus cross-file contract checks against `10-CONTEXT.md`, `maestro/agent.py`, `maestro/planner/validator.py`, `maestro/domains.py`, and the tool path-guard implementation. The scheduler/dispatch/worker graph shape, reducer usage for `completed`/`failed`/`errors`/`outputs`, and the string-vs-`Send` routing split are implemented correctly, and the scoped test suite passes (`53 passed`).

However, Phase 10 is not approvable yet. The worker call chain is broken in real runtime because `_run_agentic_loop()` is invoked without the required `provider`/`tokens`, the public `run_multi_agent()` entry point is still a placeholder that seeds an empty DAG and ignores `provider`/`model`, and scheduler validation skips duplicate-ID DAG protection that already exists in `validate_dag()`.

## Critical Issues

### CR-01: Worker runtime always fails outside tests

**File:** `maestro/multi_agent.py:288-294`
**Issue:** `worker_node()` calls `_run_agentic_loop()` without `provider` or `tokens`. Cross-file check: `maestro/agent.py:285-288` raises `RuntimeError("Either provider or tokens must be provided to _run_agentic_loop")` in exactly that case. The Phase 10 tests patch `_run_agentic_loop()`, so this production failure is currently masked.
**Fix:** Thread the selected provider/model through graph state and pass them into the worker call.

```python
# state setup
initial_state["provider"] = provider
initial_state["model"] = model or DEFAULT_MODEL

# dispatch payload
payload["provider"] = state["provider"]
payload["model"] = state["model"]

# worker call
result = _run_agentic_loop(
    messages=messages,
    model=state["model"],
    instructions=system_prompt,
    provider=state["provider"],
    workdir=workdir,
    auto=auto,
)
```

## Warnings

### WR-01: Duplicate task IDs are not rejected before scheduler dict-collapsing

**File:** `maestro/multi_agent.py:55-62, 92-101`
**Issue:** `scheduler_node()` rebuilds the DAG with dict comprehensions keyed by task ID, but never calls `validate_dag()`. Cross-file check: `maestro/planner/validator.py:25-29` already rejects duplicate IDs, yet that validation is currently skipped. With duplicate IDs, later tasks overwrite earlier ones in `deps_map`/`task_map`, causing silent task loss and incorrect execution.
**Fix:** Validate the materialized plan before any scheduler logic.

```python
plan = _materialize_plan(state["dag"])
validate_dag(plan)
```

Add a test that a duplicate-ID DAG fails fast instead of silently dropping one branch.

### WR-02: `run_multi_agent()` does not execute the advertised contract yet

**File:** `maestro/multi_agent.py:363-386`
**Issue:** The public entry point still seeds `{"tasks": []}` as a placeholder DAG, never invokes the planner, ignores `provider`, ignores `model`, and therefore returns `{}` for real calls instead of executing a decomposed task graph. This is a blocking contract gap against `10-CONTEXT.md:22-23`, which defines `run_multi_agent(task, *, workdir, auto, depth, max_depth=2)` as the public entry point for DAG execution.
**Fix:** Either wire planner output into `initial_state["dag"]` before invoking the graph, or keep this function private until the planner handoff is implemented. At minimum, fail loudly instead of silently running an empty graph.

```python
if dag is None:
    raise NotImplementedError("run_multi_agent requires a planned DAG before execution")
```

## Info

### IN-01: The path-guard test does not prove an escape attempt is blocked

**File:** `tests/test_scheduler_workers.py:492-528`
**Issue:** `test_worker_blocks_write_outside_workdir` only asserts that `worker_node()` resolves and forwards the `workdir` path. It never attempts `../escape`, never exercises `execute_tool()`, and never asserts `PathOutsideWorkdirError`. The test name overstates the security evidence.
**Fix:** Add a focused test that drives a tool call with an escaping path and asserts the guard rejects it, or rename this test to match its actual scope.

---

_Reviewed: 2026-04-18T23:23:19Z_
_Reviewer: the agent (gsd-code-reviewer)_
_Depth: deep_
