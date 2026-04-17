---
phase: 02-multi-slot-auth-store
plan: 01
type: tdd
subsystem: auth
tags: [auth, testing, pytest, cli]
requires:
  - phase: 01-provider-plugin-protocol
    provides: [stable baseline test suite and provider protocol foundation]
provides:
  - failing Phase 2 acceptance tests for multi-slot auth storage and CLI migration
affects: [maestro/auth.py, maestro/cli.py, phase-2-validation]
tech-stack:
  added: []
  patterns:
    - "pytest function-style tests with tmp_path and monkeypatch"
    - "test CLI behavior by patching sys.argv into maestro.cli.main()"
key-files:
  created:
    - tests/test_auth_store.py
  modified: []
key-decisions:
  - "Use direct cli.main() invocation in tests because the repo exposes a console script, not python -m maestro"
  - "Keep the RED step focused on missing Phase 2 API and CLI behavior, not package-entrypoint concerns"
patterns-established:
  - "Phase tests cover new API, backward-compatible shims, and CLI compatibility in one focused file"
requirements-completed: [AUTH-01, AUTH-02, AUTH-08]
duration: local-session
completed: 2026-04-17
---

# Phase 2 Plan 01 Summary

**A focused Phase 2 test suite now defines the expected multi-slot auth store behavior, backward-compatible shims, and login-only CLI deprecation before implementation.**

## Performance

- **Duration:** local session
- **Started:** 2026-04-17
- **Completed:** 2026-04-17
- **Tasks:** 3
- **Files modified:** 1

## Accomplishments

- Added `tests/test_auth_store.py` covering `get`, `set`, `remove`, `all_providers`, permissions, and flat-file migration.
- Added backward-compatibility tests for `TokenSet`, `load()`, and `_save()` to protect `agent.py` and existing imports.
- Added CLI behavior tests that lock the Phase 2 scope: `maestro auth login` is canonical, `maestro login` is deprecated, `logout` and `status` are unchanged.

## Files Created/Modified

- `tests/test_auth_store.py` - Phase 2 acceptance tests for auth-store and CLI behavior

## Decisions Made

- Tested the CLI through `maestro.cli.main()` with patched `sys.argv` because this repo currently exposes `maestro` through `[project.scripts]` only.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

- The initial red run failed during collection because `maestro.auth` did not yet export `get`, `set`, `remove`, or `all_providers`. That was the expected TDD failure and confirmed the tests were targeting the missing Phase 2 API.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- The auth-store and CLI implementation work had precise failing tests to turn green.
- The tests established the locked context boundary and prevented broader CLI scope creep.

---
*Phase: 02-multi-slot-auth-store*
*Completed: 2026-04-17*
