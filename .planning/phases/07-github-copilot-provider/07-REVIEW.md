---
phase: 07-github-copilot-provider
reviewed: 2026-04-18T20:30:57Z
depth: deep
files_reviewed: 2
files_reviewed_list:
  - maestro/providers/copilot.py
  - tests/test_copilot_provider.py
findings:
  critical: 0
  warning: 2
  info: 1
  total: 3
status: issues_found
score_overall: 76
---

# Phase 07: Code Review Report

**Reviewed:** 2026-04-18T20:30:57Z
**Depth:** deep
**Files Reviewed:** 2
**Status:** issues_found
**Score Overall:** 76

## Summary

Reviewed the Copilot provider implementation and its dedicated test suite, using the phase plan plus the provider/base/auth/registry integration points for cross-file tracing. The provider is close to the intended contract, but two correctness gaps remain: API failures can be misreported as successful empty completions, and authentication state is overstated for malformed stored credentials.

## Warnings

### WR-01: SSE path does not fail fast on non-2xx Copilot responses

**File:** `maestro/providers/copilot.py:128-141`
**Issue:** `stream()` enters the SSE loop without checking the HTTP response status first. In the ChatGPT provider, non-success responses are turned into `RuntimeError`s before parsing begins, but the Copilot provider does not do that. If Copilot returns `401`, `403`, or `500`, this path can fall through and still yield a final empty `Message`, which the agent loop treats as a valid model response instead of an API failure.
**Fix:** Check `event_source.response.is_success` (or call `raise_for_status()`) immediately after entering the SSE context and raise a `RuntimeError` with the response body on failure.

```python
async with aconnect_sse(...) as event_source:
    response = event_source.response
    if not response.is_success:
        body = await response.aread()
        raise RuntimeError(
            f"API error {response.status_code}: {body[:800].decode()}"
        )

    async for sse in event_source.aiter_sse():
        ...
```

### WR-02: `is_authenticated()` reports true for unusable credential blobs

**File:** `maestro/providers/copilot.py:298-300`
**Issue:** `is_authenticated()` only checks whether `auth.get("github-copilot")` returns a non-`None` object. That diverges from `stream()`, which requires a truthy `access_token`. Cross-file impact: `maestro/providers/registry.py:260-265` uses `is_authenticated()` to select the default provider, so a malformed auth record like `{}` can cause Maestro to prefer Copilot and then fail later at runtime.
**Fix:** Validate the stored token shape in `is_authenticated()` so provider selection and actual stream eligibility stay consistent.

```python
def is_authenticated(self) -> bool:
    creds = auth.get("github-copilot")
    return bool(creds and creds.get("access_token"))
```

## Info

### IN-01: Unused helper left behind in provider module

**File:** `maestro/providers/copilot.py:373-407`
**Issue:** `_parse_tool_call_delta()` is defined but never used. The active tool-call assembly logic is implemented inline in `stream()`, so this helper is currently dead code and can drift out of sync with the real parsing path.
**Fix:** Either remove the helper or refactor `stream()` to use it so there is only one tool-call parsing implementation.

---

_Reviewed: 2026-04-18T20:30:57Z_
_Reviewer: the agent (gsd-code-reviewer)_
_Depth: deep_
