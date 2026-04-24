---
phase: 17-aggregator-guardrails
reviewed: 2026-04-24T15:19:43Z
depth: deep
files_reviewed: 4
files_reviewed_list:
  - maestro/multi_agent.py
  - maestro/config.py
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

**Reviewed:** 2026-04-24T15:19:43Z
**Depth:** deep
**Files Reviewed:** 4
**Status:** issues_found

## Summary

Reviewed the phase 17 aggregator-guardrail changes across `maestro/multi_agent.py`, `maestro/config.py`, `maestro/planner/schemas.py`, and `tests/test_aggregator_guardrails.py`, including cross-file tracing through `run_multi_agent() -> scheduler_route() -> aggregator_node()` and `resolve_model()`.

The runtime crash and bad test patching from the prior review are fixed, and the targeted guardrail tests now pass. Remaining issues are one functional bug in the call-count guardrail, one provider/model boundary bug in the aggregator path, and three high-complexity functions in `multi_agent.py`. No asymptotic-complexity findings met the deep-review reporting threshold.

## Warnings

### WR-01: `max_calls` is effectively dead configuration

**File:** `maestro/multi_agent.py:240-242, 585-591, 737-738`
**Issue:** `scheduler_route()` reads `agg_calls_done`, but `run_multi_agent()` always initializes it to `0`, `aggregator_node()` never increments it, and the graph routes `aggregator -> END`, so the aggregator can run at most once per invocation. As a result, `max_calls` only changes behavior for `0`; any positive value behaves the same and never enforces a real ceiling.
**Fix:** Either move the call-budget check to the layer that actually performs retries, or constrain the config to the currently-supported semantics (`None`, `0`, or `1`) until repeated aggregator attempts exist.

```python
max_calls = aggregator.get("max_calls")
if max_calls not in (None, 0, 1):
    raise RuntimeError(
        "aggregator.max_calls currently supports only None, 0, or 1 "
        "because the graph invokes the aggregator at most once per run"
    )
```

### WR-02: Aggregator can mix a model from one provider with another provider instance

**File:** `maestro/multi_agent.py:520-529`
**Issue:** `resolve_model(agent_name="aggregator")` returns both the provider and the model selected for the aggregator, but the code then discards that provider whenever `state["provider"]` exists. If the caller injected a ChatGPT provider while config selects a Copilot-only aggregator model (or vice versa), `provider.stream(..., model=aggregator_model)` is called with a model chosen for a different provider.
**Fix:** Reuse the injected provider only when it matches the resolved provider ID; otherwise use the provider returned by `resolve_model()`.

```python
resolved_provider, aggregator_model = resolve_model(agent_name="aggregator")
runtime_provider = state.get("provider")

if runtime_provider is not None and runtime_provider.id == resolved_provider.id:
    provider = runtime_provider
else:
    provider = resolved_provider
```

### WR-03: `scheduler_node()` has high cyclomatic complexity

**File:** `maestro/multi_agent.py:97-206`
**Issue:** Static AST counting puts `scheduler_node()` at **CC=18**. Validation, dependency scanning, blocked-task detection, emitter updates, and end-state handling are all mixed into one function, which raises defect risk around scheduling edge cases.
**Fix:** Extract DAG validation, ready-task selection, and blocked-task/error derivation into helpers so `scheduler_node()` remains a short coordinator.

### WR-04: `aggregator_node()` has high cyclomatic complexity

**File:** `maestro/multi_agent.py:475-577`
**Issue:** Static AST counting puts `aggregator_node()` at **CC=17**. Prompt construction, provider/model resolution, async streaming, event-loop bridging, fallback handling, and emitter updates are all handled in one routine.
**Fix:** Split prompt rendering, provider/model selection, and async execution into private helpers; keep `aggregator_node()` focused on orchestration.

### WR-05: `run_multi_agent()` has high cyclomatic complexity

**File:** `maestro/multi_agent.py:596-753`
**Issue:** Static AST counting puts `run_multi_agent()` at **CC=13**. It combines workdir validation, provider/config bootstrap, planner invocation, event emission, graph execution, and result shaping, making integration behavior harder to reason about and test.
**Fix:** Extract runtime bootstrap and graph-execution setup into helpers, leaving `run_multi_agent()` as a thin composition layer.

---

_Reviewed: 2026-04-24T15:19:43Z_
_Reviewer: the agent (gsd-code-reviewer)_
_Depth: deep_
---
phase: 17-aggregator-guardrails
reviewed: 2026-04-24T15:54:13Z
depth: deep
files_reviewed: 4
files_reviewed_list:
  - maestro/planner/schemas.py
  - maestro/multi_agent.py
  - maestro/config.py
  - tests/test_aggregator_guardrails.py
findings:
  critical: 0
  warning: 3
  info: 0
  total: 3
status: issues_found
---

# Phase 17: Code Review Report

**Reviewed:** 2026-04-24T15:54:13Z
**Depth:** deep
**Files Reviewed:** 4
**Status:** issues_found

## Summary

Reviewed the new aggregator guardrail schema, runtime wiring, config validation, and tests. I found one concrete cross-file logic mismatch and two cyclomatic-complexity findings. I did not find any O(n²) or worse hot-path behavior in the reviewed files; the scheduler scans are linear in the number of planned tasks.

## Warnings

### WR-01: `max_calls` contract is inconsistent across schema, runtime config, and tests

**File:** `maestro/config.py:139-149`  
**Also affects:** `maestro/planner/schemas.py:20-30`, `tests/test_aggregator_guardrails.py:14-30`, `tests/test_aggregator_guardrails.py:55-63`, `tests/test_aggregator_guardrails.py:188-220`, `tests/test_aggregator_guardrails.py:257-272`

**Issue:** The public contract says `max_calls` is a general per-run limit (`max_calls=3`, `max_calls=2`, `max_calls=5` are all exercised in tests and documented in the dataclass), but `load()` rejects every configured value except `None`, `0`, or `1`. That means the shipped config loader cannot accept several values the tests and schema describe as valid, so the feature contract is internally inconsistent and real configs using those examples will fail at runtime.

**Fix:** Pick a single contract and enforce it everywhere. If aggregation is intentionally single-shot, update the schema docs and tests to only allow `None/0/1`. If multi-call limits are intended, relax validation and wire the runtime counter so repeated calls are actually tracked.

```python
# config.py
max_calls = aggregator.get("max_calls")
if max_calls is not None and (type(max_calls) is not int or max_calls < 0):
    raise RuntimeError(
        f"Invalid config file at {CONFIG_FILE}; expected 'aggregator.max_calls' to be a non-negative int"
    )
```

### WR-02: `load()` has elevated cyclomatic complexity (CC=13)

**File:** `maestro/config.py:96-160`

**Issue:** By the review rule set used here, `load()` has **CC=13** (multiple validation branches, compound conditions, and exception paths). That makes a core config-loading path harder to reason about and easier to break as more keys are added.

**Fix:** Extract focused validators for the top-level object and the `aggregator` section, then keep `load()` as a short orchestration function.

```python
def _validate_aggregator_config(aggregator: dict[str, Any]) -> None:
    ...

def load() -> Config:
    data = _load_raw_config()
    _validate_root_config(data)
    _validate_aggregator_config(data.get("aggregator", {}))
    return Config(...)
```

### WR-03: `aggregator_node()` has elevated cyclomatic complexity (CC=13)

**File:** `maestro/multi_agent.py:482-589`

**Issue:** `aggregator_node()` now mixes empty-output handling, prompt construction, provider/model resolution, async streaming, event-loop bridging, and fallback error handling in one function. Under the review rule set, this reaches **CC=13**, which is a refactor threshold and raises defect risk for future changes to aggregation behavior.

**Fix:** Split the function into smaller units such as `_build_aggregator_prompt(...)`, `_resolve_aggregator_provider(...)`, and `_run_aggregator_stream(...)`, then keep `aggregator_node()` as a thin coordinator with early returns.

```python
def aggregator_node(state: AgentState) -> dict:
    if _should_return_empty_summary(state):
        return {"summary": "No worker outputs to summarize."}

    user_message = _build_aggregator_prompt(state)
    provider, model = _resolve_aggregator_provider(state)
    summary = _run_aggregator_stream(provider, model, user_message, state)
    return {"summary": summary}
```

---

_Reviewed: 2026-04-24T15:54:13Z_  
_Reviewer: the agent (gsd-code-reviewer)_  
_Depth: deep_
