---
phase: 15-external-provider-install-smoke-test
plan: "01"
subsystem: provider-registry
tags: [testing, smoke-test, entry-points, plugin-discovery, integration-test]
dependency_graph:
  requires: []
  provides: [PLUGIN-01, PLUGIN-02, PLUGIN-03]
  affects: [maestro/providers/registry.py, pyproject.toml]
tech_stack:
  added: []
  patterns: [subprocess-isolated-venv, pytest-integration-marker, entry-point-discovery]
key_files:
  created:
    - tests/fixtures/hello_provider/pyproject.toml
    - tests/fixtures/hello_provider/hello_provider.py
    - tests/test_provider_install_smoke.py
  modified:
    - pyproject.toml
decisions:
  - "Used setuptools.build_meta backend instead of setuptools.backends.legacy:build to ensure compatibility with setuptools versions bundled in fresh venvs"
  - "Added httpx-sse>=0.4 to pyproject.toml dependencies — was missing, causing maestro import to fail in isolated venvs"
  - "Subprocess-based discovery test avoids lru_cache pollution from the test runner's entry points"
metrics:
  duration: "3 minutes"
  completed: "2026-04-23"
  tasks: 2
  files: 4
---

# Phase 15 Plan 01: External Provider Install Smoke Test Summary

## One-liner

Subprocess-based smoke test proves full isolated-venv install → entry-point discovery path for third-party providers, closing the gap between unit-tested registry logic and real external package installation.

## What Was Built

### Task 1: hello_provider Fixture Package
- `tests/fixtures/hello_provider/pyproject.toml` — minimal installable package declaring `hello = "hello_provider:HelloProvider"` under `[project.entry-points."maestro.providers"]`
- `tests/fixtures/hello_provider/hello_provider.py` — `HelloProvider` class implementing all 7 ProviderPlugin Protocol methods, fully independent of maestro source

### Task 2: Isolated-Install Smoke Test
- `tests/test_provider_install_smoke.py` — `test_third_party_provider_discoverable_after_isolated_install` creates a fresh venv in `tmp_path`, installs maestro and hello_provider, then runs `discover_providers()` in a subprocess to verify `'hello'` is in the result
- Marked `@pytest.mark.integration` and skipped by default (`MAESTRO_RUN_INTEGRATION=1` required)
- All 104 existing tests continue to pass (1 skipped = smoke test in default mode)

## Verification Results

```
Default run:  pytest tests/ -x -q → 104 passed, 1 skipped ✓
Integration:  MAESTRO_RUN_INTEGRATION=1 pytest tests/test_provider_install_smoke.py -v → 1 passed ✓
Subprocess stdout: "SMOKE_OK" ✓
```

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed setuptools.backends.legacy:build compatibility in fixture pyproject.toml**
- **Found during:** Task 2 integration test run
- **Issue:** Fresh venv pip 24.2 ships setuptools that doesn't expose `setuptools.backends.legacy:build` — raises `BackendUnavailable`
- **Fix:** Changed build-backend to `setuptools.build_meta` (works with setuptools >= 42)
- **Files modified:** `tests/fixtures/hello_provider/pyproject.toml`
- **Commit:** 0d66a57

**2. [Rule 2 - Missing Critical Dependency] Added httpx-sse to pyproject.toml dependencies**
- **Found during:** Task 2 integration test run (maestro import failed in fresh venv)
- **Issue:** `httpx_sse` was used by `maestro/providers/copilot.py` but not declared in `[project.dependencies]` — works in dev because it's globally installed, fails in isolated venv
- **Fix:** Added `"httpx-sse>=0.4"` to `pyproject.toml` dependencies
- **Files modified:** `pyproject.toml`
- **Commit:** 0d66a57

## Requirements Closed

| Requirement | Status |
|-------------|--------|
| PLUGIN-01: fixture package installed in isolated venv (tmp_path) | ✓ |
| PLUGIN-02: discovery via entry-point group, no maestro source edits | ✓ |
| PLUGIN-03: global Python environment unchanged (ephemeral tmp_path venv) | ✓ |

## Self-Check: PASSED
