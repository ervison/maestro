---
phase: 10
title: Scheduler & Workers
status: discussed
date: 2026-04-18
---

# Phase 10 — Implementation Context

## Locked Decisions

1. **Plan accepted as-is**: No changes to 10-01-PLAN.md structure or scope.
2. **`ready_tasks` stays plain `list[dict]`**: Scheduler-owned, never written by workers. No reducer needed.
3. **No-op `dispatch_node`**: Keeps `Send`-returning routing (`dispatch_route`) strictly separated from string routing (`scheduler_route`). The dispatch node returns `{}` — its only purpose is to host the `dispatch_route` conditional edge.

## Architecture Summary

- New file: `maestro/multi_agent.py`
- 3-node StateGraph: `scheduler → dispatch → worker → scheduler` (loop)
- `scheduler_route`: returns string (`"dispatch"` or `END`) — never `Send`
- `dispatch_route`: returns `list[Send("worker", payload)]` — never strings
- Workers: reuse `_run_agentic_loop()` unchanged
- `run_multi_agent(task, *, workdir, auto, depth, max_depth=2)` as public entry point

## State Shape Additions (to `maestro/planner/schemas.py`)

- `failed: Annotated[list[str], operator.add]` — reducer-backed terminal-task list
- `ready_tasks: list[dict]` — plain, scheduler-owned
- `current_task_id: NotRequired[str]` — worker-local
- `current_task_domain: NotRequired[str]` — worker-local
- `current_task_prompt: NotRequired[str]` — worker-local

## Constraints

- Do not modify `_run_agentic_loop()`
- No new dependencies
- `depth` is required (no default) on `run_multi_agent()`
- Path guard enforced inside every worker (resolve workdir from state)
