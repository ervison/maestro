---
phase: 16-copilot-release-smoke-gate
plan: "01"
subsystem: provider-testing
tags: [smoke-test, copilot, oauth, integration-test, release-gate]
dependency_graph:
  requires: [Phase 7 CopilotProvider, Phase 15 smoke test pattern]
  provides: [COP-SMOKE-01, COP-SMOKE-02, COP-SMOKE-03]
  affects: [tests/test_copilot_smoke.py, pyproject.toml]
tech_stack:
  added: []
  patterns: [pytest-monkeypatch-auth-isolation, skipif-env-guard, asyncio-run-in-sync-test, token-seeded-ci-mode]
key_files:
  created:
    - tests/test_copilot_smoke.py
  modified:
    - pyproject.toml
decisions:
  - "Auth isolation uses monkeypatch on maestro.auth.AUTH_FILE (the module-level Path constant set from MAESTRO_AUTH_FILE env var) — cleaner than env var injection because it works even if auth module caches the path at import time"
  - "Partial stream chunks (str) and final Message chunks both accumulate into collected[] so the assertion works regardless of which chunk type the provider emits last"
  - "Default model set to gpt-4o-mini — lightweight, fast, available on most Copilot tiers; overridable via MAESTRO_COPILOT_MODEL"
  - "MAESTRO_COPILOT_MODEL env var added (not in plan) to allow CI to override model without code changes — minor Rule 2 addition"
metrics:
  duration: "4 minutes"
  completed: "2026-04-24"
  tasks: 1
  files: 2
---

# Phase 16 Plan 01: Copilot Release Smoke Gate Summary

## One-liner

Release-grade pytest smoke gate for GitHub Copilot that exercises real device-code OAuth and one live API call, skipped by default, with full auth isolation via monkeypatched AUTH_FILE.

## What Was Built

### Task 1: Copilot smoke gate test

**`tests/test_copilot_smoke.py`** — single integration test `test_copilot_smoke_login_and_api_call` covering:

- **Skip guard (COP-SMOKE-03):** `@pytest.mark.skipif(not _is_smoke_enabled(), ...)` — skips cleanly with clear reason unless `MAESTRO_COPILOT_SMOKE=1` is set. Module docstring enumerates all 3 skip conditions (no env var, no Copilot subscription, no network).
- **Interactive mode (COP-SMOKE-01):** When `MAESTRO_COPILOT_TOKEN` is absent, calls `provider.login()` which runs the GitHub device-code OAuth flow end-to-end — prints `user_code` + URL, polls until authorized.
- **Token-seeded mode (CI-friendly):** When `MAESTRO_COPILOT_TOKEN=<ghu_...>` is set, seeds the token directly into the isolated auth store and bypasses interactive login. Enables CI pipelines to run the gate with a stored secret.
- **Live API assertion (COP-SMOKE-02):** Calls `provider.stream(messages=[...], model=model)` via `asyncio.run()` and asserts at least one non-empty chunk is returned from `api.githubcopilot.com`.
- **Auth isolation (T-16-02 mitigation):** `monkeypatch.setattr(auth, "AUTH_FILE", tmp_path / "auth.json")` redirects all reads/writes to a throwaway file — `~/.maestro/auth.json` is never touched.

**`pyproject.toml`** — added `copilot_smoke` to `[tool.pytest.ini_options] markers`.

## Verification Results

```
Default run (no credentials):
  pytest tests/ -x -q → 104 passed, 2 skipped ✓

Smoke gate skip dry-run:
  pytest tests/test_copilot_smoke.py -v
  → SKIPPED: Set MAESTRO_COPILOT_SMOKE=1 to run Copilot release smoke gate ✓

Marker registered:
  grep "copilot_smoke" pyproject.toml → found ✓
```

## Deviations from Plan

### Auto-added

**1. [Rule 2 - Missing Critical Functionality] MAESTRO_COPILOT_MODEL env var**
- **Found during:** Task 1 — `stream()` requires a model name; plan didn't specify how to override it in CI
- **Issue:** Hardcoding `gpt-4o-mini` would break if a Copilot subscription doesn't include that model
- **Fix:** Added `MAESTRO_COPILOT_MODEL` env var with `gpt-4o-mini` default; overridable without code changes
- **Files modified:** `tests/test_copilot_smoke.py`

## Requirements Closed

| Requirement | Status |
|-------------|--------|
| COP-SMOKE-01: Real device-code login path exercised | ✓ (`provider.login()` call in interactive mode branch) |
| COP-SMOKE-02: Live authenticated Copilot API request + non-empty response assertion | ✓ (`provider.stream()` + `assert collected`) |
| COP-SMOKE-03: Explicit safe-skip with documented conditions | ✓ (skipif guard + module docstring) |

## Self-Check: PASSED

- `tests/test_copilot_smoke.py` exists ✓
- `pytest tests/test_copilot_smoke.py -v` → 1 skipped with correct reason ✓
- `pytest tests/ -x -q` → 104 passed, 2 skipped (zero regressions) ✓
- `grep "copilot_smoke" pyproject.toml` → found ✓
- commit `4bdbab2` exists ✓
