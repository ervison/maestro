---
phase: 17
reviewed: 2026-04-24T16:04:05Z
depth: standard
files_reviewed: 53
files_reviewed_list:
  - .opencode/opencode.json
  - .opencode/plugins/graphify.js
  - AGENTS.md
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
  critical: 1
  warning: 3
  info: 0
  total: 4
status: issues_found
---

# Phase 17: Code Review Report

**Reviewed:** 2026-04-24T16:04:05Z
**Depth:** standard
**Files Reviewed:** 53
**Status:** issues_found

## Summary

Reviewed the phase scope with emphasis on provider streaming, CLI error handling, dashboard/SDLC flows, and test reliability. Most of the earlier Phase 17 findings are fixed, but four issues remain: one critical cyclomatic-complexity hotspot, two runtime correctness problems, and one failing test expectation that now disagrees with the implementation.

## Critical Issues

### CR-01: `CopilotProvider.stream()` is untestably complex

**File:** `maestro/providers/copilot.py:115-265`
**Issue:** `CopilotProvider.stream()` has **CC=22** (static AST count), driven by nested auth checks, SSE parsing, tool-call buffering, finish-reason handling, and post-processing in one method. At this size the function is brittle: small protocol changes in Copilot chunks are easy to break and hard to cover exhaustively.
**Fix:** Extract the major branches into helpers such as credential validation, SSE event parsing, tool-call delta accumulation, and final tool-call materialization.

```python
async def stream(...):
    token = self._require_token()
    payload = self._build_payload(messages, model, tools)
    text_parts, tool_buffers = await self._consume_sse(token, payload)
    return self._final_message(text_parts, tool_buffers)
```

## Warnings

### WR-01: CLI error path can mask the real model-resolution failure

**File:** `maestro/cli.py:426-450`
**Issue:** `_handle_run()` references `model_id` inside the `except` block even when `resolve_model()` fails before `model_id` is assigned. Reproducing with `maestro.models.resolve_model` patched to raise `RuntimeError("model not supported for account")` raises `UnboundLocalError` instead of the original user-facing error.
**Fix:** Initialize `model_id` before the `try`, or avoid referencing it when resolution failed.

```python
model_id: str | None = None
try:
    provider, model_id = resolve_model(model_flag=args.model)
    ...
except (RuntimeError, ValueError) as e:
    if "not supported" in str(e) and model_id is not None:
        ...
```

### WR-02: Gap answer endpoint accepts empty answers as `"unknown"`

**File:** `maestro/sdlc/gaps_server.py:396-413`
**Issue:** `_receive_answers()` falls back to `[item.get("chosen_option", "unknown")]` when `selected_options` is missing. A malformed POST like `[{"question": "Q?"}]` returns HTTP 200 and stores `GapAnswer(question='Q?', selected_options=['unknown'])`, letting the discovery flow continue with fabricated answers.
**Fix:** Reject items that provide neither `selected_options` nor a non-empty legacy `chosen_option`.

```python
selected = item.get("selected_options")
legacy = item.get("chosen_option")
if selected:
    selected_options = selected
elif legacy:
    selected_options = [legacy]
else:
    raise ValueError("answer requires at least one selected option")
```

### WR-03: Config validation test now asserts an unsupported setting

**File:** `tests/test_aggregator_guardrails.py:257-271`
**Issue:** `test_load_accepts_valid_config()` treats `aggregator.max_calls=5` as valid, but `maestro/config.py:144-149` deliberately rejects any value outside `None`, `0`, or `1`. Running `PYTHONPATH=. pytest tests/test_aggregator_guardrails.py::TestConfigValidation::test_load_accepts_valid_config -q` fails with that runtime error, so this test currently produces a false negative.
**Fix:** Align the test with the supported range, or widen the implementation and graph semantics in the same change.

```python
mock_json_loads.return_value = {
    "aggregator": {
        "enabled": True,
        "max_calls": 1,
        "max_tokens_per_run": 1000,
    }
}
```

---

_Reviewed: 2026-04-24T16:04:05Z_
_Reviewer: the agent (gsd-code-reviewer)_
_Depth: standard_
