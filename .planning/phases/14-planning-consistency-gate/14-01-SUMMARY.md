---
phase: 14-planning-consistency-gate
plan: 01
subsystem: planning
tags: [testing, consistency, requirements, tdd]
dependency_graph:
  requires: []
  provides: [REQUIREMENTS.md milestone alignment check, extended drift path coverage]
  affects: [maestro/planning.py, tests/test_planning_consistency.py]
tech_stack:
  added: []
  patterns: [TDD red-green, regex milestone parsing]
key_files:
  created: []
  modified:
    - maestro/planning.py
    - tests/test_planning_consistency.py
decisions:
  - REQUIREMENTS.md check placed at end of check sequence (after summary checks) to preserve early-return on missing summary
  - _parse_requirements raises ValueError if scope declaration not found (strict, not silent)
  - Fixture updated to include REQUIREMENTS.md scoped to v1.1 so aligned fixture continues to pass
metrics:
  duration: 12m
  completed: "2026-04-23"
  tasks_completed: 2
  files_modified: 2
---

# Phase 14 Plan 01: REQUIREMENTS.md Milestone Alignment Check Summary

**One-liner:** Added `_parse_requirements()` + REQUIREMENTS.md milestone scope check to `check_planning_consistency()`, with 8-test suite covering all drift paths via TDD.

## What Was Built

Extended `maestro/planning.py` with a new `_parse_requirements(path: Path) -> str` helper that extracts the milestone slug from REQUIREMENTS.md's `scoped to milestone \`...\`` declaration. Integrated into `check_planning_consistency()` as the final check: reports an error when REQUIREMENTS.md is missing or when its milestone slug mismatches STATE.md.

Expanded `tests/test_planning_consistency.py` from 3 tests to 8, covering:
- Aligned artifacts → no errors (original)
- STATE.md progress drift → error reported (original)
- Live repo consistency (original)
- Missing REQUIREMENTS.md → error reported (new)
- REQUIREMENTS.md milestone mismatch → error reported (new)
- REQUIREMENTS.md milestone aligned → no requirements error (new)
- Missing phase evidence file → error reported (new)
- Milestone summary missing milestone mention → error reported (new)

## Commits

| Hash | Message |
|------|---------|
| `1dc9ae5` | test(14-01): add failing tests for REQUIREMENTS.md milestone alignment check (RED) |
| `88c2fdc` | feat(14-01): add REQUIREMENTS.md milestone alignment check to check_planning_consistency() (GREEN) |
| `caba9bb` | feat(14-01): fix check order and expand drift path coverage in tests |

## Verification

```
python -m pytest tests/test_planning_consistency.py -v  → 8 passed
python -m pytest tests/ -q                             → 102 passed
maestro planning check                                 → exit 0
```

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] REQUIREMENTS.md check placed in wrong position**
- **Found during:** Task 2 implementation
- **Issue:** My initial edit inserted the `requirements_path` check before `return ConsistencyCheckResult(errors)`, but the `return` statement was inserted too early — the summary and evidence checks were unreachable (dead code after early return).
- **Fix:** Restructured the function to restore the original early-return on missing summary, then append REQUIREMENTS.md check at the correct position after all other checks.
- **Files modified:** `maestro/planning.py`
- **Commit:** `caba9bb`

## Self-Check

- [x] `maestro/planning.py` exists and contains `_parse_requirements`
- [x] `tests/test_planning_consistency.py` has 8 tests (210 lines > 180 min)
- [x] All commits exist in git log
- [x] `maestro planning check` exits 0
