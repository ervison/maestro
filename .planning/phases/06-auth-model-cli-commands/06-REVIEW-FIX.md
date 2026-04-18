---
phase: 06-auth-model-cli-commands
fixed_at: 2026-04-18T19:30:00Z
review_path: .planning/phases/06-auth-model-cli-commands/06-REVIEW.md
iteration: 1
findings_in_scope: 1
fixed: 1
skipped: 0
status: all_fixed
---

# Phase 06: Code Review Fix Report

**Fixed at:** 2026-04-18T19:30:00Z
**Source review:** .planning/phases/06-auth-model-cli-commands/06-REVIEW.md
**Iteration:** 1

**Summary:**
- Findings in scope: 1
- Fixed: 1
- Skipped: 0

## Fixed Issues

### WR-01: Logout CLI tests still depend on the real auth store

**Files modified:** `tests/test_cli_auth.py`
**Commit:** 15f3096
**Applied fix:** Added `patch("maestro.cli.auth.all_providers", return_value=[])` to all three logout test methods to properly isolate them from the user's real auth store.

The following tests were updated:
1. `test_auth_logout_success` - Added patch for `auth.all_providers`
2. `test_auth_logout_not_logged_in` - Added patch for `auth.all_providers`
3. `test_auth_logout_unknown_provider` - Added patch for `auth.all_providers`

This ensures the tests don't read from `~/.maestro/auth.json` and behave consistently regardless of local machine state.

## Skipped Issues

None — all findings were fixed.

---

_Fixed: 2026-04-18T19:30:00Z_
_Fixer: the agent (gsd-code-fixer)_
_Iteration: 1_
