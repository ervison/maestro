---
phase: 17
reviewed: 2026-04-24T17:29:41Z
depth: standard
files_reviewed: 52
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
  - tmp/gaps-snapshot.txt
findings:
  critical: 0
  warning: 3
  info: 0
  total: 3
status: issues_found
---

# Phase 17: Code Review Report

**Reviewed:** 2026-04-24T17:29:41Z
**Depth:** standard
**Files Reviewed:** 52
**Status:** issues_found

## Summary

Reviewed the listed Maestro source and supporting test files at standard depth, with focus on provider/plugin compatibility, CLI error handling, concurrency, and dashboard/SDLC flows. I found three warning-level issues: one plugin-contract break across multiple call sites, one dashboard event-order race, and one uncaught runtime failure path in `maestro discover`.

Note: three files listed in the review request were not present in this worktree and therefore could not be reviewed: `tests/test_agent_loop.py`, `tests/test_provider_protocol.py`, and `tests/test_tools.py`.

## Warnings

### WR-01: Structurally valid third-party providers can still fail at runtime

**File:** `maestro/planner/node.py:127-129`
**Issue:** The registry explicitly validates provider `stream()` by positional shape, not parameter names (`maestro/providers/registry.py:171-199`), but several call sites invoke `provider.stream(...)` with keyword arguments such as `messages=`, `model=`, and `tools=` (`maestro/planner/node.py:127-129`, `maestro/sdlc/generators.py:53`, `maestro/sdlc/reflect.py:179`, `maestro/sdlc/gaps_server.py:231`, `maestro/multi_agent.py:563`). A third-party provider with a structurally compatible signature like `stream(self, msgs, mdl, tools=None, **kwargs)` passes discovery and then fails with `TypeError: got an unexpected keyword argument 'messages'` at runtime. That breaks the advertised entry-point plugin contract.
**Fix:** Call `stream()` positionally everywhere unless the registry also enforces exact parameter names.

```python
stream = provider.stream(messages, model, [])

async for msg in provider.stream(messages, model, None):
    ...
```

### WR-02: New dashboard subscribers can receive events out of order

**File:** `maestro/dashboard/emitter.py:35-42`
**Issue:** `subscribe()` snapshots `_history`, immediately appends the handler to `_subscribers`, then replays history outside the lock. If a new event is emitted between registration and replay completion, the subscriber can observe a newer live event before older replayed events. For SSE consumers this can produce non-monotonic state updates and inconsistent UI reconstruction.
**Fix:** Finish replay before exposing the handler to live delivery, or buffer live events for that subscriber until replay completes.

```python
with self._lock:
    past = list(self._history)

for event in past:
    handler(event)

with self._lock:
    self._subscribers.append(handler)
```

If replay must remain outside the lock, wrap the handler with a temporary queue so live events are drained only after replay finishes.

### WR-03: `maestro discover` misses `RuntimeError` from model resolution

**File:** `maestro/cli.py:587-591`
**Issue:** `_handle_discover()` only catches `ValueError` around `resolve_model(...)`, but `resolve_model()` can also raise `RuntimeError` when the selected/default provider has no models or cannot produce a usable default (`maestro/models.py:126-130`). In that case the CLI will exit with a traceback instead of a clean user-facing error, unlike `_handle_run()` which already handles both exception types.
**Fix:** Match `_handle_run()` and catch both `RuntimeError` and `ValueError`.

```python
try:
    provider, model_id = resolve_model(model_flag=getattr(args, "model", None))
except (RuntimeError, ValueError) as exc:
    print(f"Error: {exc}", file=sys.stderr)
    sys.exit(1)
```

---

_Reviewed: 2026-04-24T17:29:41Z_
_Reviewer: the agent (gsd-code-reviewer)_
_Depth: standard_
