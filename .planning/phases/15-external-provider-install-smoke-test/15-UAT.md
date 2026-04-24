---
status: completed
phase: 15-external-provider-install-smoke-test
source: [15-01-SUMMARY.md]
started: 2026-04-24T00:00:00Z
updated: 2026-04-24T00:00:00Z
---

## Current Test

<!-- OVERWRITE each test - shows where we are -->

All tests completed.

number: 3
name: Third-party provider discoverable after isolated install
expected: |
  Verified by integration smoke test.
awaiting: none

## Tests

### 1. All existing tests pass
expected: Run pytest tests/ -x -q. All 104 tests pass, 1 skipped.
result: passed

### 2. Integration smoke test passes
expected: Set MAESTRO_RUN_INTEGRATION=1 and run pytest tests/test_provider_install_smoke.py -v. Test passes, subprocess stdout shows "SMOKE_OK".
result: passed

### 3. Third-party provider discoverable after isolated install
expected: The smoke test creates fresh venv, installs maestro and hello_provider, runs discover_providers() in subprocess and verifies 'hello' is in the result.
result: passed

## Summary

total: 3
passed: 3
issues: 0
pending: 0
skipped: 0
blocked: 0

## Gaps

[none yet]