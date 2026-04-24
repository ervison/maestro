---
phase: 14-planning-consistency-gate
plan: 02
subsystem: planning
tags: [testing, cli, documentation, workflow]
dependency_graph:
  requires: [14-01]
  provides: [CLI error-exit coverage, --root flag test, milestone workflow documentation]
  affects: [tests/test_cli_planning.py, .planning/MILESTONE-WORKFLOW.md]
tech_stack:
  added: []
  patterns: [unittest.mock.patch for CLI integration testing]
key_files:
  created:
    - .planning/MILESTONE-WORKFLOW.md
  modified:
    - tests/test_cli_planning.py
decisions:
  - Import main at module level in test file for cleaner test structure
  - Patch maestro.planning.check_planning_consistency (not maestro.cli) since handler imports it locally
  - MILESTONE-WORKFLOW.md kept under 40 lines — concise developer reference
metrics:
  duration: 8m
  completed: "2026-04-23"
  tasks_completed: 2
  files_modified: 2
---

# Phase 14 Plan 02: CLI Error-Exit Coverage and Milestone Workflow Doc Summary

**One-liner:** Extended `test_cli_planning.py` with non-zero exit and --root flag tests, plus created `MILESTONE-WORKFLOW.md` documenting the `maestro planning check` gate in open/close milestone procedures.

## What Was Built

**tests/test_cli_planning.py** expanded from 2 to 4 tests:
- `test_planning_check_exits_nonzero_when_inconsistent` — mocks `check_planning_consistency` to return errors, asserts CLI exits non-zero
- `test_planning_check_root_flag_passes_path` — asserts `--root /tmp/fake` is forwarded to `check_planning_consistency` as call argument

**`.planning/MILESTONE-WORKFLOW.md`** created with:
- "Opening a New Milestone" procedure (5 steps including `maestro planning check`)
- "Closing a Milestone" procedure (4 steps including `maestro planning check`)
- Consistency Gate Reference section explaining what each artifact is checked for
- Reference to CI workflow `.github/workflows/planning-consistency.yml`

## Commits

| Hash | Message |
|------|---------|
| `044ea2a` | feat(14-02): add error-exit and --root flag tests to test_cli_planning.py |
| `d29b900` | docs(14-02): create MILESTONE-WORKFLOW.md with consistency gate steps |

## Verification

```
python -m pytest tests/test_cli_planning.py -v  → 4 passed
python -m pytest tests/ -q                     → 104 passed
maestro planning check                         → exit 0
```

## Deviations from Plan

None — plan executed exactly as written.

## Self-Check

- [x] `tests/test_cli_planning.py` has 4 tests (all passing)
- [x] `.planning/MILESTONE-WORKFLOW.md` exists with "maestro planning check" in both sections
- [x] All commits exist in git log
- [x] `maestro planning check` exits 0
