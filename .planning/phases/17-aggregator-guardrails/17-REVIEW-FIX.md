---
phase: 17-aggregator-guardrails
fixed_at: 2026-04-24T16:00:00Z
review_path: .planning/phases/17-aggregator-guardrails/17-REVIEW.md
iteration: 1
findings_in_scope: 6
fixed: 4
skipped: 2
status: partial
---

# Phase 17: Code Review Fix Report

**Fixed at:** 2026-04-24T16:00:00Z
**Source review:** .planning/phases/17-aggregator-guardrails/17-REVIEW.md
**Iteration:** 1

**Summary:**
- Findings in scope: 6
- Fixed: 4
- Skipped: 2

## Fixed Issues

### CR-01: Aggregator runtime path crashes with `NameError`

**Files modified:** `maestro/multi_agent.py`
**Commit:** 5dcda17
**Applied fix:** Added `from maestro.models import resolve_model` import at module scope, immediately above the existing `get_default_provider` import. The function at line 525 was calling `resolve_model` without it being in scope.

---

### WR-01: Scheduler routes to aggregator even when tasks are still unfinished

**Files modified:** `maestro/multi_agent.py`
**Commit:** b20a1fe
**Applied fix:** Replaced the fall-through path in `scheduler_route()` (lines 249-254) that incorrectly routed to `"aggregator"` when unfinished tasks remained. It now returns `END` unconditionally in that branch, stopping the run so callers can inspect errors rather than receiving a misleading summary. The `aggregate` flag check that was in that branch was redundant (the earlier `not unfinished` block already covers the normal aggregation path with all guardrail checks).
**Status:** fixed: requires human verification — the routing logic change is simple but affects all cases where tasks are blocked by failures; verify against existing test suite.

---

### WR-02: Config validation accepts booleans as integer guardrail values

**Files modified:** `maestro/config.py`
**Commit:** 6b7c38c
**Applied fix:** Changed both `isinstance(value, int)` checks for `aggregator.max_calls` and `aggregator.max_tokens_per_run` to `type(value) is not int`. This rejects `True`/`False` (which are `bool` and subclass `int`) while accepting actual integers.

---

### WR-03: One guardrail test patches the wrong symbols and fails

**Files modified:** `tests/test_aggregator_guardrails.py`
**Commit:** 8d2776b
**Applied fix:** In `test_run_multi_agent_builds_guardrail_from_config`, changed:
- `@patch('maestro.config.load')` → `@patch('maestro.multi_agent.load_config')`
- `patch('maestro.providers.registry.get_default_provider')` → `patch('maestro.multi_agent.get_default_provider')`
- `patch('maestro.planner.node.planner_node')` → `patch('maestro.multi_agent.planner_node')`

All three are now patched where `run_multi_agent()` looks them up (in `maestro.multi_agent`), so the mocks take effect.

---

## Skipped Issues

### WR-04: `scheduler_node()` has high cyclomatic complexity

**File:** `maestro/multi_agent.py:96-205`
**Reason:** The fix suggestion provides only a skeleton (`_load_valid_plan`, `_compute_ready_tasks`, `_compute_scheduler_errors`). Implementing this refactoring requires careful extraction of the existing validation/dependency-scan logic into helpers with the same semantics. This is a non-trivial restructuring that should be reviewed by a human before committing, as getting the blocked-task/end-state detection wrong would silently break multi-agent runs. Skipped to avoid introducing logic regressions.
**Original issue:** CC=19 in `scheduler_node()` — DAG validation, ready-task selection, blocked-task detection, and end-state handling all in one function.

---

### WR-05: `aggregator_node()` has high cyclomatic complexity

**File:** `maestro/multi_agent.py:474-576`
**Reason:** The fix suggestion provides only a skeleton (`_run_aggregator`, `_emit_aggregator_done`). The function mixes async execution with event-loop bridging logic (three branches for running/stopped/no loop). Extracting these correctly — especially the `concurrent.futures.ThreadPoolExecutor` path — requires careful testing. Given that CR-01 (the missing import that likely stems from this complexity) is now fixed, the remaining risk is manageable but the refactor itself should be human-reviewed. Skipped to avoid regressions in async execution paths.
**Original issue:** CC=19 in `aggregator_node()` — prompt construction, model resolution, async execution, event-loop bridging all mixed together.

---

_Fixed: 2026-04-24T16:00:00Z_
_Fixer: the agent (gsd-code-fixer)_
_Iteration: 1_
