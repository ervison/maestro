---
task: 260422-t7
subsystem: sdlc
tags: [reflect-loop, quality-evaluation, llm-scoring, sdlc-discover]
key-files:
  created:
    - maestro/sdlc/reflect.py
    - tests/test_sdlc_reflect.py
  modified:
    - maestro/sdlc/schemas.py
    - maestro/sdlc/harness.py
    - maestro/cli.py
    - tests/test_sdlc_harness.py
    - tests/test_sdlc_generators.py
decisions:
  - Guard reflect loop with hasattr(provider, 'stream') to tolerate stub/object providers in tests
  - Use FakeProvider with pre-set responses list for deterministic async generator mocking in reflect tests
metrics:
  duration: ~15 min
  completed: 2026-04-22
---

# Quick Task 260422-t7: SDLC Reflect Loop Summary

**One-liner:** LLM-based iterative quality evaluation loop with 10-dimension rubric, surgical JSON patches, and in-place spec file correction after discover-phase generation.

## Commits

| Hash | Task | Message |
|------|------|---------|
| 6a52f68 | Task 1 | feat(260422-t7): add ReflectReport dataclasses to schemas.py |
| 5d4b139 | Task 2 | feat(260422-t7): implement ReflectLoop in maestro/sdlc/reflect.py |
| fa1c791 | Task 3 | feat(260422-t7): wire reflect loop into harness.py and cli.py |
| cefede6 | Task 4 | test(260422-t7): add tests for reflect loop and harness integration |

## What Was Built

### Task 1 — Schemas (schemas.py)
Added four dataclasses to `maestro/sdlc/schemas.py`:
- `ReflectDimensionScore`: dimension, score, justification
- `ReflectCorrection`: cycle, file, dimension, description
- `ReflectCycle`: cycle, scores, mean, corrections
- `ReflectReport`: cycles, final_mean, passed
- Extended `DiscoveryResult` with `reflect_report: ReflectReport | None = None`

### Task 2 — ReflectLoop (reflect.py)
Created `maestro/sdlc/reflect.py` with:
- `DIMENSIONS` list of 10 quality dimensions in Portuguese
- `TARGET_MEAN = 8.0`
- `ReflectLoop` class with:
  - `_read_spec_files()` — reads all *.md files from spec_dir
  - `_build_eval_prompt()` — builds evaluation prompt expecting JSON `{scores, problems}`
  - `_build_fix_prompt()` — builds correction prompt expecting JSON patch array
  - `_apply_patches()` — validates `old` exists before replacing, skips + warns if not found
  - `run()` — main loop: eval → check mean → fix → repeat up to max_cycles
- `_extract_json()` helper handles ```json ... ``` code fences
- `run_reflect_loop()` convenience entry point

### Task 3 — Wiring (harness.py + cli.py)
- `DiscoveryHarness.__init__` now accepts `reflect: bool = True` and `reflect_max_cycles: int = 5`
- Reflect loop fires after generation when `provider is not None AND hasattr(provider, 'stream') AND reflect`
- Prints `[reflect] Cycle N/max — mean: X.X/10` to stderr per cycle
- `maestro discover` gains `--no-reflect` and `--reflect-max-cycles INT` flags
- Fixed `test_harness_with_provider_calls_generators`: added `reflect=False` to isolate generation-only assertion

### Task 4 — Tests
- `tests/test_sdlc_reflect.py`: 4 tests
  - `test_reflect_report_dataclass` — dataclass instantiation
  - `test_reflect_loop_passes_when_scores_high` — stops at cycle 1 when mean ≥ 8.0
  - `test_reflect_loop_applies_patches` — 2-cycle run, patches applied to tmp file
  - `test_reflect_loop_stops_at_max_cycles` — passed=False after max_cycles
- `tests/test_sdlc_harness.py`: appended `test_harness_reflect_disabled_produces_no_report`

## Verification

```
python -m pytest tests/ -q          → 73 passed (68 existing + 5 new)
maestro discover --help | grep -E "no-reflect|reflect-max"
  --no-reflect / --reflect-max-cycles INT  ✓ visible
```

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] hasattr guard on provider before running reflect**
- **Found during:** Task 3 — existing tests use `provider=object()` as a sentinel
- **Issue:** `object()` passes `is not None` check but crashes when `reflect.py` calls `provider.stream()`
- **Fix:** Added `hasattr(self._provider, "stream")` guard in harness.py
- **Files modified:** `maestro/sdlc/harness.py`
- **Commit:** fa1c791

**2. [Rule 1 - Bug] test_harness_with_provider_calls_generators assertion broken by reflect calls**
- **Found during:** Task 3 test run — test asserts `len(calls) == 13` but reflect adds 5 more eval calls
- **Fix:** Pass `reflect=False` to `DiscoveryHarness` in that test (generation-only concern)
- **Files modified:** `tests/test_sdlc_generators.py`
- **Commit:** fa1c791

## Self-Check: PASSED

Files exist:
- maestro/sdlc/reflect.py ✓
- tests/test_sdlc_reflect.py ✓

Commits exist: 6a52f68, 5d4b139, fa1c791, cefede6 ✓
Tests: 73 passed ✓
