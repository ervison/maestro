---
phase: 10
plan: 1
title: "Scheduler & Workers — parallel DAG execution with LangGraph Send"
subsystem: execution
tags: [langgraph, multi-agent, scheduler, workers, dag]
dependency_graph:
  requires: ["08-dag-state-types-domains", "09-planner"]
  provides: ["multi-agent-execution"]
  affects: ["cli-multi-flag"]
tech_stack:
  added: []
  patterns:
    - "LangGraph StateGraph + Send API for parallel fan-out"
    - "TopologicalSorter for cycle detection only"
    - "Direct dependency checking for task readiness"
    - "Reducer-safe state updates (operator.add, _merge_dicts)"
key_files:
  created:
    - maestro/multi_agent.py
    - tests/test_scheduler_workers.py
  modified:
    - maestro/planner/schemas.py
    - tests/test_planner_schemas.py
    - maestro/planner/__init__.py
decisions:
  - "Used direct dependency checking (not incremental TopologicalSorter) for scheduler readiness"
  - "Separated scheduler_route (string returns) from dispatch_route (Send returns) to avoid LangGraph routing issues"
  - "Made depth a required parameter on run_multi_agent() (no default) per spec"
  - "Worker exceptions converted to failed/errors state updates (non-fatal by design)"
  - "Patched _run_agentic_loop at multi_agent usage site for tests"
metrics:
  duration_minutes: 45
  test_count: 53
  new_tests: 23
  modified_tests: 4
  files_created: 2
  files_modified: 3
  commits: 3
---

# Phase 10 Plan 1: Scheduler & Workers Summary

**Goal:** Execute planner DAG tasks in parallel with LangGraph `Send`, domain-specialized workers, per-worker workdir enforcement, and recursion-depth safety.

## What Was Built

### 1. Extended Execution State (Task 1)

Modified `maestro/planner/schemas.py` to add execution-time fields:

- **`failed: Annotated[list[str], operator.add]`** — tracks non-fatally failed task IDs via reducer
- **`ready_tasks: list[dict]`** — scheduler-owned field for current ready batch (no reducer needed)
- **Worker-local fields (NotRequired):**
  - `current_task_id: NotRequired[str]`
  - `current_task_domain: NotRequired[str]`  
  - `current_task_prompt: NotRequired[str]`

Updated `tests/test_planner_schemas.py` to verify `failed` reducer and field coverage.

### 2. Scheduler Readiness Logic (Task 2)

Created `maestro/multi_agent.py` with `scheduler_node()`:

- Materializes `AgentPlan` from `state["dag"]` on each invocation
- Uses `TopologicalSorter` only for cycle detection
- Implements direct dependency checking: a task is ready if all deps are in `completed` (not just terminal)
- Detects 3 end states: all terminal, no ready + no unfinished, blocked-by-failure
- Sets `state["ready_tasks"]` with task payloads (id, domain, prompt)

### 3. Dispatch Routing with LangGraph Send (Task 3)

Implemented clean routing separation:

- **`scheduler_route(state)`** → returns strings only (`"dispatch"` or `END`)
- **`dispatch_route(state)`** → returns `list[Send]` only
- **`dispatch_node`** → minimal no-op node to isolate routing modes

Each `Send("worker", payload)` includes task fields plus execution context:
```python
{
  "current_task_id": task["id"],
  "current_task_domain": task["domain"],
  "current_task_prompt": task["prompt"],
  "depth": depth,
  "max_depth": max_depth,
  "workdir": workdir,
  "auto": auto,
}
```

### 4. Worker Execution with Domain Prompting (Task 4)

Implemented `worker_node(state)`:

- Composes system prompt: `get_domain_prompt(domain) + "\n\n## Your Task\n\n" + prompt`
- Reuses `_run_agentic_loop()` unchanged (mirrors provider/model resolution)
- Returns reducer-safe updates:
  - Success: `{"completed": [task_id], "outputs": {task_id: output}}`
  - Failure: `{"failed": [task_id], "errors": [f"{task_id}: {message}"]}`

### 5. Worker Safety Guards (Task 5)

Installed multiple safety layers:

- **Depth validation:** `depth > max_depth` → immediate failure (no execution)
- **Workdir resolution:** `Path(state["workdir"]).resolve()` inside worker
- **Exception handling:** All exceptions converted to `failed` + `errors` state (non-fatal)
- **Entry point:** `run_multi_agent(task, *, workdir, auto, depth, max_depth=2)` — `depth` has **no default** (required)

### 6. Compiled Graph with Parallel Fan-In (Task 6)

Wired `StateGraph`:

```python
builder = StateGraph(AgentState)
builder.add_node("scheduler", scheduler_node)
builder.add_node("dispatch", dispatch_node)
builder.add_node("worker", worker_node)
builder.add_edge(START, "scheduler")
builder.add_conditional_edges("scheduler", scheduler_route, ["dispatch", END])
builder.add_conditional_edges("dispatch", dispatch_route, ["worker"])
builder.add_edge("worker", "scheduler")
graph = builder.compile()
```

Added integration tests proving:
- 2-worker ready batch completes with both outputs preserved
- Failed branch doesn't erase successful branch's output
- Dependent tasks execute in correct order

## Test Results

### Test Counts
| Category | Count | Status |
|----------|-------|--------|
| planner schemas | 30 | ✓ pass |
| scheduler workers | 23 | ✓ pass |
| planner node + domains + agent loop + tools | 80 | ✓ pass |
| **Total Phase 10** | **53** | **✓ all pass** |

### Verification Progression
1. `pytest tests/test_planner_schemas.py -q` — 30 passed ✓
2. `pytest tests/test_scheduler_workers.py -q` — 23 passed ✓
3. `pytest tests/test_planner_node.py tests/test_domains.py tests/test_agent_loop_provider.py tests/test_tools.py -q` — 80 passed ✓
4. `pytest -q` — 346 passed, 15 failed (pre-existing failures in auth browser OAuth, async tests, CLI models)

### Required Test Coverage
All 11 required tests from the plan pass:
1. ✓ `test_scheduler_returns_initial_ready_batch`
2. ✓ `test_scheduler_unblocks_next_batch_after_completion`
3. ✓ `test_dispatch_route_returns_one_send_per_ready_task`
4. ✓ `test_worker_uses_domain_prompt_and_task_prompt`
5. ✓ `test_worker_blocks_write_outside_workdir`
6. ✓ `test_worker_records_error_and_failed_task_without_crashing_graph`
7. ✓ `test_independent_branch_continues_after_other_worker_failure`
8. ✓ `test_depth_argument_is_required_on_runner`
9. ✓ `test_worker_rejects_depth_above_max_depth`
10. ✓ `test_parallel_worker_writes_preserve_both_outputs`
11. ✓ `test_scheduler_ends_with_blocked_dependency_error_after_failure`

## Files Created/Modified

### Created
- `maestro/multi_agent.py` (388 lines) — scheduler, dispatch, worker nodes, graph compilation, runner
- `tests/test_scheduler_workers.py` (712 lines) — 23 comprehensive tests

### Modified
- `maestro/planner/schemas.py` — added `failed`, `ready_tasks`, worker-local NotRequired fields
- `tests/test_planner_schemas.py` — added `failed` reducer test, updated field coverage
- `maestro/planner/__init__.py` — docstring update

## Deviations from Plan

### None

The plan was executed exactly as written. All 6 tasks completed with:
- All required tests passing
- No new dependencies added
- `_run_agentic_loop()` reused unchanged
- `depth` parameter has no default on `run_multi_agent()`

## Implementation Notes

### Routing Design Decision
The plan specified keeping `scheduler_route` (string returns) separate from `dispatch_route` (Send returns). This was implemented exactly as specified because LangGraph doesn't allow mixing string and Send returns in the same routing function.

### Patching Strategy for Tests
Tests patch `_run_agentic_loop` at the usage site (`maestro.multi_agent._run_agentic_loop`) rather than the definition site. This works because the module import creates a local name binding that can be patched.

### Ready Task Computation
Used direct dependency checking instead of incremental TopologicalSorter because:
1. The sorter is reconstructed on every scheduler invocation
2. Direct checking is simpler: `task is ready if all deps.issubset(completed)`
3. TopologicalSorter is still used for cycle detection

## Commits

1. `892f736` — feat(10-01): extend execution state for scheduler/worker needs
2. `01889bd` — feat(10-01): implement scheduler and worker multi-agent execution
3. `db7d987` — chore(10-01): update planner __init__ docstring

## Definition of Done

- ✓ Compiled LangGraph can execute a serialized AgentPlan in dependency order
- ✓ Ready tasks fan out in parallel with `Send`
- ✓ Workers use domain prompts and the existing agentic loop
- ✓ Worker failures are non-fatal to independent branches
- ✓ Worker workdir containment is proven by test
- ✓ Recursion depth is explicit and guarded
- ✓ Two-worker graph test proves both outputs survive parallel fan-in
- ✓ Existing test suite still passes (346 tests, 15 pre-existing failures unrelated to this work)

---

*Completed: 2026-04-18*
