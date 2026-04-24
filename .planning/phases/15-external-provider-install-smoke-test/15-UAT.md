---
<<<<<<< HEAD
status: testing
phase: 15-external-provider-install-smoke-test
source: [15-01-SUMMARY.md]
started: 2026-04-23T12:00:00Z
updated: 2026-04-23T12:00:00Z
=======
status: completed
phase: 15-external-provider-install-smoke-test
source: [15-01-SUMMARY.md]
started: 2026-04-24T00:00:00Z
updated: 2026-04-24T00:00:00Z
>>>>>>> cb08c9129240dc0947992de31c429c3aeb3172d6
---

## Current Test

<<<<<<< HEAD
number: 1
name: Isolated Provider Install
expected: |
  Third-party provider package installs in fresh venv without maestro source changes. Entry point discovery finds the provider.
awaiting: user response

## Tests

### 1. Isolated Provider Install
expected: Third-party provider package installs in fresh venv without maestro source changes. Entry point discovery finds the provider.
result: pending

### 2. Integration Test Passes
expected: MAESTRO_RUN_INTEGRATION=1 pytest tests/test_provider_install_smoke.py passes.
result: pending

### 3. Dependency Fix Verified
expected: httpx-sse>=0.4 added to pyproject.toml dependencies allows maestro import in fresh venv.
result: pending
=======
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
>>>>>>> cb08c9129240dc0947992de31c429c3aeb3172d6

## Summary

total: 3
<<<<<<< HEAD
passed: 0
issues: 0
pending: 3
skipped: 0

## Gaps

[none yet]</content>
<parameter name="filePath">.planning/phases/15-external-provider-install-smoke-test/15-UAT.md
=======
passed: 3
issues: 0
pending: 0
skipped: 0
blocked: 0

## Gaps

[none yet]
>>>>>>> cb08c9129240dc0947992de31c429c3aeb3172d6
