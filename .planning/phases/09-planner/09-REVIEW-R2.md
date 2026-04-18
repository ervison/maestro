---
phase: 09-planner
reviewed: 2026-04-18T22:45:00Z
depth: deep
files_reviewed: 3
files_reviewed_list:
  - maestro/planner/node.py
  - maestro/planner/__init__.py
  - tests/test_planner_node.py
findings:
  critical: 0
  warning: 2
  info: 1
  total: 3
status: issues_found
score: 90
verdict: FAILING
---

# Phase 9: Code Review Report (Round 2)

**Reviewed:** 2026-04-18T22:45:00Z
**Depth:** deep
**Files Reviewed:** 3
**Score:** 90/100
**Status:** issues_found
**Final Verdict:** FAILING

## Summary

Round 1 fixes materially improved the planner:

- `list_models()` is now consumed as `list[str]`
- schema fallback is narrowed to `TypeError`
- tests now use string model IDs
- planner tests pass locally (`10 passed`)

However, the implementation is not fully ready for approval yet. The CR-01 fix is only partially correct: the planner now accepts `str | Message`, but it still prefers partial streamed chunks over the protocol's required final `Message`, which remains the canonical complete response. There is also still an overly broad retry boundary in `planner_node()` that retries provider/runtime failures instead of only retrying validation failures.

## Warnings

### WR-01: Stream collector ignores the canonical final `Message`

**File:** `maestro/planner/node.py:97-105`

**Issue:** The round-1 fix correctly stops crashing on `str` chunks, but it now keeps chunk text and discards the final `Message.content` whenever any chunk was seen. That is still misaligned with the provider contract in `maestro/providers/base.py:73-87`, which requires the final yield to be a complete `Message`. If a provider emits partial deltas and then a normalized/final complete message, the planner will parse the partial text instead of the authoritative final response.

**Fix:** Preserve both values during streaming and prefer the final `Message.content` when present.

```python
final_content: str | None = None

async for chunk in stream:
    if isinstance(chunk, str):
        chunks.append(chunk)
    elif isinstance(chunk, Message):
        final_content = chunk.content

return final_content if final_content is not None else "".join(chunks)
```

### WR-02: Planner retry loop still retries provider/runtime failures

**File:** `maestro/planner/node.py:182-206`

**Issue:** `_call_provider_with_schema()` now correctly lets auth/network/runtime errors propagate, but `planner_node()` still catches `Exception` around the entire attempt and retries everything up to 3 times. That contradicts the module contract (`Retries up to 3 times on validation failure`) and can turn hard provider failures into repeated calls with mutated prompt state.

**Fix:** Only retry parse/validation failures. Let provider/runtime errors fail immediately.

```python
raw = _call_provider_with_schema(provider, messages, model_id)

try:
    plan = AgentPlan.model_validate_json(raw)
    validate_dag(plan)
except (ValueError, ValidationError) as exc:
    last_error = exc
    ...  # retry path
else:
    return {"dag": plan.model_dump()}
```

## Info

### IN-01: Regression coverage is still incomplete for the round-1 fixes

**File:** `tests/test_planner_node.py:58-63, 303-326`

**Issue:** The tests now correctly use `list[str]` mocks, but the new stream test only covers a provider that yields `str` chunks and never yields the protocol-required final `Message`. There is also no regression test for the narrowed `TypeError` fallback path. That leaves both remaining warning paths unguarded.

**Fix:** Add tests for:

- `str` chunks followed by a final `Message`
- `TypeError` on schema kwargs followed by successful prompt-only retry
- a non-`TypeError` provider failure that should not retry

## Final Verdict

**FAILING** — the round-1 fixes resolved the original crash and contract mismatch on `list_models()`, but two correctness issues remain in the planner's stream handling and retry boundaries. Approval should wait until those are addressed.

---

_Reviewed: 2026-04-18T22:45:00Z_
_Reviewer: gsd-code-reviewer_
_Depth: deep_
