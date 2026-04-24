---
status: testing
phase: 15-external-provider-install-smoke-test
source: [15-01-SUMMARY.md]
started: 2026-04-23T12:00:00Z
updated: 2026-04-23T12:00:00Z
---

## Current Test

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

## Summary

total: 3
passed: 0
issues: 0
pending: 3
skipped: 0

## Gaps

[none yet]</content>
<parameter name="filePath">.planning/phases/15-external-provider-install-smoke-test/15-UAT.md