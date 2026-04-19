---
phase: 10-scheduler-workers
reviewed: 2026-04-18T23:59:00Z
depth: deep
files_reviewed: 6
files_reviewed_list:
  - maestro/multi_agent.py
  - maestro/planner/schemas.py
  - maestro/planner/__init__.py
  - tests/test_scheduler_workers.py
  - tests/test_planner_schemas.py
  - maestro/agent.py
findings:
  critical: 0
  warning: 2
  info: 1
  total: 3
status: issues_found
score_overall: 92
decision: FAILING
---

# Phase 10: Code Review Report (Round 2)

**Reviewed:** 2026-04-18T23:59:00Z
**Depth:** deep
**Files Reviewed:** 6
**Status:** issues_found
**Overall Score:** 92/100
**Decision:** FAILING

## Summary

Round-2 fixes addressed the three round-1 blockers in code:

- `worker_node()` now resolves and passes `provider` into `_run_agentic_loop()` (`maestro/multi_agent.py:303-318`), which satisfies the actual `_run_agentic_loop()` contract in `maestro/agent.py:258-288` because it requires **either** `provider` **or** `tokens`.
- `scheduler_node()` now calls `validate_dag()` before rebuilding scheduler topology (`maestro/multi_agent.py:56-63`).
- `run_multi_agent()` is now a real planner→graph wrapper instead of an empty-DAG stub (`maestro/multi_agent.py:395-439`).
- `dispatch_node()` remains a no-op (`maestro/multi_agent.py:182-194`).
- `scheduler_route()` still returns only strings and `dispatch_route()` still returns only `list[Send]` (`maestro/multi_agent.py:149-179, 197-235`).

Verification evidence is mixed. The scoped suites pass locally:

- `pytest tests/test_scheduler_workers.py -q` → `23 passed`
- `pytest tests/test_planner_schemas.py -q` → `30 passed`

But approval still is not justified under the requested conservative rubric. The remaining problems are no longer runtime-breakers, but there is still a contract gap around planner override handling and the claimed security regression coverage is overstated.

## Warnings

### WR-01: `run_multi_agent()` does not apply caller-supplied provider/model to the planning step

**File:** `maestro/multi_agent.py:388-413` and `maestro/planner/node.py:150-173`

**Issue:** `run_multi_agent()` accepts `provider` and `model`, but those values are only threaded into worker execution (`maestro/multi_agent.py:419-433`). The planning call is still `planner_node(planner_state)` with no override state, and `planner_node()` resolves provider/model from config/default discovery instead of the caller's chosen runtime override. That means one `run_multi_agent()` invocation can plan with provider/model A and execute with provider/model B, which is a contract mismatch for a public entry point that advertises `provider` and `model` parameters.

**Fix:** Thread explicit planner overrides through state and have `planner_node()` honor them before falling back to config/default resolution.

```python
# maestro/multi_agent.py
planner_state["provider"] = provider
planner_state["model"] = model

# maestro/planner/node.py
provider = state.get("provider") or resolved_provider_from_config
model_id = state.get("model") or resolved_model_from_config
```

Also add a positive test that a custom provider/model passed to `run_multi_agent()` is used by both planning and worker execution.

### WR-02: The path-guard test still does not prove that an escape attempt is blocked

**File:** `tests/test_scheduler_workers.py:492-528`

**Issue:** `test_worker_blocks_write_outside_workdir` still does not attempt an escaping path, does not drive `execute_tool()`, and does not assert a rejection such as `PathOutsideWorkdirError`. It only proves that `worker_node()` resolves and forwards a `Path` object. Because Phase 10 has an explicit security requirement that path guard apply inside every worker, this test is not strong enough to support approval.

**Fix:** Add a focused worker-level security test that causes the agent loop to issue a tool call against `../escape.txt` (or equivalent) and assert the write is rejected.

```python
def test_worker_rejects_escape_attempt_inside_agent_loop(...):
    # mock provider returns a write_file tool call for ../escape.txt
    # run real _run_agentic_loop path
    # assert worker result records failure / error mentioning outside workdir
```

At minimum, rename the current test so it matches what it actually verifies.

## Info

### IN-01: Regression coverage still misses the explicit provider/model threading fix

**File:** `tests/test_scheduler_workers.py:303-342, 368-403, 534-567`

**Issue:** Round 2 fixed provider/model threading in implementation, but the tests still do not assert that `dispatch_route()` forwards provider/model, that `worker_node()` passes provider into `_run_agentic_loop()`, or that `run_multi_agent()` preserves those overrides end-to-end. This makes the round-1 failure mode easy to reintroduce.

**Fix:** Add direct assertions on `_run_agentic_loop(..., provider=..., model=...)` call kwargs and one happy-path `run_multi_agent()` test with planner + worker patches.

---

_Reviewed: 2026-04-18T23:59:00Z_
_Reviewer: the agent (gsd-code-reviewer)_
_Depth: deep_
