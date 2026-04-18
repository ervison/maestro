---
phase: 09-planner
fixed_at: 2026-04-18T22:30:00Z
review_path: .planning/phases/09-planner/09-REVIEW.md
iteration: 1
findings_in_scope: 4
fixed: 4
skipped: 0
status: all_fixed
---

# Phase 9: Code Review Fix Report

**Fixed at:** 2026-04-18T22:30:00Z
**Source review:** .planning/phases/09-planner/09-REVIEW.md
**Iteration:** 1

**Summary:**
- Findings in scope: 4
- Fixed: 4
- Skipped: 0

## Fixed Issues

### CR-01: Stream output type handling — `str | Message`

**Files modified:** `maestro/planner/node.py`
**Commit:** 0954d6e
**Applied fix:**
- Changed `_call_provider_with_schema()` to handle both `str` chunks and `Message` objects
- Added type checking: `isinstance(chunk, str)` for text deltas, `isinstance(chunk, Message)` for final messages
- Avoids double-appending by only using `Message.content` when no text chunks were collected

### WR-01: `list_models()` returns `list[str]` not objects with `.id`

**Files modified:** `maestro/planner/node.py`
**Commit:** 0954d6e
**Applied fix:**
- Changed line 164 from `models[0].id` to `models[0]`
- `list_models()` contract returns `list[str]` per `maestro/providers/base.py`

### WR-02: Too-broad exception catch in `_call_provider`

**Files modified:** `maestro/planner/node.py`
**Commit:** 0954d6e
**Applied fix:**
- Narrowed exception catch from generic `Exception` to specific `TypeError`
- Only falls back to prompt-only mode when provider doesn't support `extra`/`response_format` kwargs
- Auth/network/runtime errors now propagate correctly instead of being masked

### IN-01: Tests use wrong mock contracts

**Files modified:** `tests/test_planner_node.py`
**Commit:** 0954d6e
**Applied fix:**
- Fixed `MockProvider.__init__` to use `models or ["gpt-4o"]` instead of `[MagicMock(id="gpt-4o")]`
- Added `_mock_stream_with_text_chunks` generator to test `str` chunk handling (CR-01 coverage)
- Added `test_stream_with_text_chunks()` test to verify the fix works correctly

## Test Results

```
tests/test_planner_node.py::test_valid_dag PASSED
tests/test_planner_node.py::test_schema_rejection PASSED
tests/test_planner_node.py::test_cycle_rejection PASSED
tests/test_planner_node.py::test_config_model_resolution PASSED
tests/test_planner_node.py::test_config_provider_resolution PASSED
tests/test_planner_node.py::test_retry_success PASSED
tests/test_planner_node.py::test_markdown_fences_stripped PASSED
tests/test_planner_node.py::test_stream_with_text_chunks PASSED          [NEW]
tests/test_planner_node.py::test_planner_exports_prompt PASSED
tests/test_planner_node.py::test_config_fallback_to_default_provider PASSED

All 10 planner node tests PASSED
All 39 planner-related tests PASSED (including schemas, validator)
```

## Files Changed

| File | Lines Changed | Description |
|------|---------------|-------------|
| `maestro/planner/node.py` | ~8 lines | Stream type handling, list_models contract, exception narrowing |
| `tests/test_planner_node.py` | ~40 lines | Fixed mock contracts, added str chunk test |

---

_Fixed: 2026-04-18T22:30:00Z_
_Fixer: gsd-code-fixer_
_Commit: 0954d6e_
