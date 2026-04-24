---
phase: 17-aggregator-guardrails
reviewed: 2026-04-24T17:38:43Z
depth: deep
files_reviewed: 47
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
  - maestro/sdlc/writer.py
  - maestro/tools.py
  - script.py
  - tests/fixtures/hello_provider/hello_provider.py
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

**Reviewed:** 2026-04-24T17:38:43Z
**Depth:** deep
**Files Reviewed:** 47
**Status:** issues_found

## Summary

Reviewed the requested Python source and reliability-relevant tests at deep depth, including cross-file paths through planner → provider adapters, worker tool execution, dashboard SSE, and SDLC gap resolution.

I found one security issue and three correctness/reliability issues. The most serious is a real workdir escape in `search_in_files()`: a symlink inside the allowed directory can expose files outside the sandbox. I did not find any O(n²) or worse hot-path issues worth flagging in this scope. Note: 4 requested files were missing from the workspace and could not be reviewed: `tests/__init__.py`, `tests/test_agent_loop.py`, `tests/test_provider_protocol.py`, and `tests/test_tools.py`.

## Critical Issues

### CR-01: `search_in_files()` can read files outside `workdir` through symlinks

**File:** `maestro/tools.py:81-96`
**Issue:** `search_in_files()` validates only the base directory, then iterates `base.rglob(include)` and reads each match directly. A symlinked file that lives inside `workdir` but points outside it still passes `is_file()` and `read_text()`, so the tool can exfiltrate arbitrary host files despite the path guard. A local repro returned a match from a symlinked file outside the sandbox (`{'file': 'leak.txt', 'line': 1, 'text': 'TOPSECRET token'}`).
**Fix:** Resolve every discovered file before reading it and skip anything whose resolved target is outside the resolved workdir.

```python
for fpath in base.rglob(include):
    if not fpath.is_file():
        continue

    try:
        resolved_file = fpath.resolve()
        resolved_file.relative_to(workdir.resolve())
    except ValueError:
        continue

    for i, line in enumerate(resolved_file.read_text(errors="replace").splitlines(), 1):
        ...
```

## Warnings

### WR-01: Planner schema fallback does not work for providers that reject `response_format`

**File:** `maestro/planner/node.py:156-163`
**Also affects:** `maestro/providers/copilot.py:224-226`
**Issue:** `_call_provider_with_schema()` only falls back to prompt-only mode on `TypeError`. That misses the more likely failure mode for third-party providers: they accept `extra`, forward `response_format`, and the remote API rejects it with a runtime/API error. `CopilotProvider` already forwards `response_format` unchanged, so planner execution can fail outright instead of using the advertised fallback path when planner/aggregator models are configured to use Copilot.
**Fix:** Treat provider/API “unsupported response_format” failures as a fallback condition, or expose an explicit provider capability flag and only send schema enforcement to supporting providers.

```python
try:
    return _collect_stream(use_response_format=True)
except TypeError:
    return _collect_stream(use_response_format=False)
except RuntimeError as exc:
    if "response_format" not in str(exc).lower():
        raise
    return _collect_stream(use_response_format=False)
```

### WR-02: `/answers` accepts malformed `selected_options` payloads and can corrupt downstream prompts

**File:** `maestro/sdlc/gaps_server.py:403-416`
**Issue:** The handler accepts any truthy `selected_options` value. If a client submits a string instead of `list[str]`, the value is passed straight into `GapAnswer`, and later `", ".join(answer.selected_options)` in `DiscoveryHarness` will join characters instead of options (`"Y, e, s"`). This silently corrupts the resolved prompt instead of rejecting the bad request.
**Fix:** Validate that `selected_options` is a non-empty list of non-empty strings before constructing `GapAnswer`; reject scalar strings and mixed-type arrays with HTTP 400.

```python
selected = item.get("selected_options")
legacy = item.get("chosen_option")

if isinstance(selected, list) and selected and all(isinstance(opt, str) and opt for opt in selected):
    selected_options = selected
elif isinstance(legacy, str) and legacy:
    selected_options = [legacy]
else:
    raise ValueError("answer requires selected_options: list[str]")
```

### WR-03: Aggregator guardrail test expects the wrong validation message

**File:** `tests/test_aggregator_guardrails.py:243-253`
**Issue:** `maestro.config.load()` raises `expected 'aggregator.max_tokens_per_run' to be a non-negative int`, but the test asserts the narrower regex `to be an int`. That makes the test fail even when runtime validation behaves correctly, reducing CI signal for this phase.
**Fix:** Match the real error message or assert on a stable substring such as the field name.

```python
with pytest.raises(
    RuntimeError,
    match=r"aggregator\.max_tokens_per_run.*non-negative int",
):
    load()
```

---

_Reviewed: 2026-04-24T17:38:43Z_
_Reviewer: the agent (gsd-code-reviewer)_
_Depth: deep_
