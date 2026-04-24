---
phase: 17-aggregator-guardrails
reviewed: 2026-04-24T16:34:14Z
depth: deep
files_reviewed: 4
files_reviewed_list:
  - maestro/config.py
  - maestro/multi_agent.py
  - maestro/planner/schemas.py
  - tests/test_aggregator_guardrails.py
findings:
  critical: 0
  warning: 5
  info: 0
  total: 5
status: issues_found
---

# Phase 17: Code Review Report

**Reviewed:** 2026-04-24T16:34:14Z
**Depth:** deep
**Files Reviewed:** 4
**Status:** issues_found

## Summary

Reviewed the phase 17 guardrail changes across config loading, scheduler/aggregator flow, shared state schema, and the new tests. The main risks are a non-functional call-count counter, permissive config validation for token budgets, and tests that over-mock the graph so they miss real integration regressions. Cross-file tracing (`run_multi_agent -> scheduler_route -> aggregator_node` and `config.load -> AggregatorGuardrail`) found no O(n²)+ asymptotic issues, but two runtime functions now exceed the CC warning threshold.

## Warnings

### WR-01: Aggregator call-count guardrail is never statefully updated

**File:** `maestro/multi_agent.py:247-250,600-645,806-807`
**Issue:** `agg_calls_done` is initialized and read, but never incremented anywhere in the graph. Today that means `max_calls=0` works, but any future retry/re-entry into the aggregator path will still see `0` and bypass the intended call-count ceiling. The code advertises a per-run counter, but the state machine never mutates it.
**Fix:** Increment the counter as part of entering or finishing the aggregator path, ideally in a dedicated pre-aggregator node so retries are counted before the LLM call starts.

```python
def aggregator_node(state: AgentState) -> dict:
    calls_done = state.get("agg_calls_done", 0) + 1
    # ... existing summary generation ...
    return {
        "summary": summary,
        "agg_calls_done": calls_done,
    }
```

### WR-02: Negative token budgets are accepted and silently disable aggregation

**File:** `maestro/config.py:143-147`
**Issue:** `_validate_aggregator_config()` rejects non-ints for `aggregator.max_tokens_per_run`, but it still accepts negative integers. Any negative value causes `check_aggregator_guardrail()` to block almost every aggregation attempt (`estimated > negative_limit`), turning a malformed config into confusing runtime behavior instead of a clear config error.
**Fix:** Validate `max_tokens_per_run` the same way `max_calls` is validated: require a non-negative integer.

```python
max_tokens = aggregator.get("max_tokens_per_run")
if max_tokens is not None and (type(max_tokens) is not int or max_tokens < 0):
    raise RuntimeError(
        f"Invalid config file at {CONFIG_FILE}; expected 'aggregator.max_tokens_per_run' to be a non-negative int"
    )
```

### WR-03: Guardrail “integration” tests bypass the graph they claim to validate

**File:** `tests/test_aggregator_guardrails.py:151-175,205-220`
**Issue:** Both `test_run_multi_agent_respects_max_calls_zero()` and `test_run_multi_agent_builds_guardrail_from_config()` patch `maestro.multi_agent.graph.invoke`, so they never exercise `scheduler_route()`, never verify the `agg_guardrail` values passed into the graph, and cannot detect whether the aggregator path was really skipped. These tests currently pass even if the guardrail state is wrong.
**Fix:** Either assert on the actual initial state passed to `graph.invoke`, or avoid mocking `graph.invoke` and instead patch the planner plus aggregator provider call.

```python
state = mock_invoke.call_args.args[0]
guardrail = state["agg_guardrail"]
assert guardrail.max_calls == 5
assert guardrail.max_tokens_per_run == 2000
```

### WR-04: `worker_node()` is over the cyclomatic-complexity threshold

**File:** `maestro/multi_agent.py:343-466`
**Issue:** `worker_node()` has estimated **CC=11**. It combines input validation, depth guarding, filesystem setup, provider resolution, lifecycle logging, emitter wiring, success handling, and failure handling in one method. That branching level is already above the review threshold and makes worker error paths harder to reason about.
**Fix:** Extract private helpers for state validation, workdir resolution, and success/failure event emission, or use early returns to flatten the nested control flow.

### WR-05: `run_multi_agent()` is over the cyclomatic-complexity threshold

**File:** `maestro/multi_agent.py:664-822`
**Issue:** `run_multi_agent()` has estimated **CC=13**. It now handles provider resolution, config/guardrail construction, planner orchestration, dashboard event shaping, initial graph state assembly, and result normalization in a single function. That makes this entry point a refactor candidate and increases defect risk as more phase-specific policy is added.
**Fix:** Split the function into helpers such as `_load_runtime_settings()`, `_build_planner_state()`, `_emit_dag_ready()`, and `_build_initial_graph_state()`, then keep `run_multi_agent()` as a thin coordinator.

---

_Reviewed: 2026-04-24T16:34:14Z_
_Reviewer: the agent (gsd-code-reviewer)_
_Depth: deep_
