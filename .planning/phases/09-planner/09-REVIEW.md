---
phase: 09-planner
reviewed: 2026-04-18T22:23:25Z
depth: deep
files_reviewed: 3
files_reviewed_list:
  - maestro/planner/node.py
  - maestro/planner/__init__.py
  - tests/test_planner_node.py
findings:
  critical: 1
  warning: 2
  info: 1
  total: 4
status: issues_found
score: 58
verdict: FAILING
---

# Phase 9: Code Review Report

**Reviewed:** 2026-04-18T22:23:25Z
**Depth:** deep
**Files Reviewed:** 3
**Score:** 58/100
**Status:** issues_found
**Final Verdict:** FAILING

## Summary

I reviewed the Phase 9 planner implementation against the plan, roadmap success criteria, and the provider/state contracts in the surrounding code.

The main blocker is that `planner_node` does not currently work with the real `ProviderPlugin` contract: it assumes streamed items always have `.content`, and it assumes `list_models()` returns objects with `.id`. The current tests pass because their mock provider does not match the production provider behavior.

## CRITICAL

### CR-01: Planner breaks on real streamed provider output

**File:** `maestro/planner/node.py:97-99`

**Severity:** CRITICAL

**Description:** `ProviderPlugin.stream()` is defined to yield `str | Message`, and both real providers stream text deltas as `str` before yielding the final `Message`. `_call_provider_with_schema()` unconditionally reads `msg.content`, so the first streamed text chunk raises `AttributeError`. In practice this makes the planner fail after 3 retries for real providers, so SC-1 is not met outside the test double.

**Evidence:** Reproducing with a provider that yields a text chunk and then a final `Message` causes `Planner failed to produce a valid AgentPlan after 3 attempts. Last error: 'str' object has no attribute 'content'`.

**Recommendation:** Handle both protocol variants explicitly.

```python
async for chunk in stream:
    if isinstance(chunk, str):
        chunks.append(chunk)
    elif isinstance(chunk, Message) and chunk.content:
        chunks.append(chunk.content)
```

If you keep both deltas and the final `Message`, avoid double-appending the full response.

## WARNING

### WR-01: Default model resolution uses the wrong `list_models()` contract

**File:** `maestro/planner/node.py:162-164`

**Severity:** WARNING

**Description:** `ProviderPlugin.list_models()` returns `list[str]`, and both concrete providers implement that contract. `planner_node()` instead assumes items have an `.id` attribute (`models[0].id`). When `config.agent.planner.model` is unset, this raises `AttributeError` before any planner request is made.

**Recommendation:** Treat returned models as strings.

```python
models = provider.list_models()
model_id = models[0] if models else "gpt-4o"
```

Also update the tests to use `list[str]` mocks so this regression is caught.

### WR-02: Schema-enforcement fallback masks real provider/runtime failures

**File:** `maestro/planner/node.py:119-123`

**Severity:** WARNING

**Description:** The code treats any exception from the first provider call as “response_format not supported” and silently retries without schema enforcement. That hides real failures such as auth errors, transport failures, or parsing bugs, and it can trigger a second unnecessary API call. It also relies on passing `extra=...`, which is outside the declared `ProviderPlugin.stream()` contract.

**Recommendation:** Only fall back for explicit capability/signature failures (for example `TypeError` due to an unsupported kwarg, or a provider-specific “unsupported response_format” error). Propagate auth/network/runtime errors immediately. Longer term, either extend the provider protocol to support structured-output options or add a provider capability method instead of sending undeclared kwargs.

## INFO

### IN-01: Tests miss the real provider contract edge cases

**File:** `tests/test_planner_node.py:61-95, 98-202`

**Severity:** INFO

**Description:** The test double returns `list_models()` values as `MagicMock(id=...)` and its stream yields only final `Message` objects. That differs from production, where `list_models()` returns `list[str]` and `stream()` may emit `str` deltas before the final `Message`. As a result, the current suite passes while two production-breaking contract bugs remain undetected.

**Recommendation:** Add coverage for:

- `list_models() -> ["gpt-4o"]`
- stream yielding `str` chunks plus a final `Message`
- fallback behavior when schema kwargs are unsupported
- a hard failure path where the first call errors for reasons other than unsupported schema options

## Final Verdict

**FAILING** — the planner is not yet safe to approve because the current implementation does not adhere to the provider contract used by real providers, so the Phase 9 success criteria are not reliably met.

---

_Reviewed: 2026-04-18T22:23:25Z_
_Reviewer: gsd-code-reviewer_
_Depth: deep_
