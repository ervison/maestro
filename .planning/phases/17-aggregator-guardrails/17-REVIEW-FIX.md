---
phase: 17-aggregator-guardrails
fixed_at: 2026-04-24T15:30:00Z
review_path: .planning/phases/17-aggregator-guardrails/17-REVIEW.md
iteration: 1
findings_in_scope: 5
fixed: 4
skipped: 1
status: partial
---

# Phase 17: Code Review Fix Report

**Fixed at:** 2026-04-24T15:30:00Z
**Source review:** .planning/phases/17-aggregator-guardrails/17-REVIEW.md
**Iteration:** 1

**Summary:**
- Findings in scope: 5
- Fixed: 4
- Skipped: 1

## Fixed Issues

### CR-01: `execute_shell` bypasses the worker path guard

**Files modified:** `maestro/tools.py`
**Commit:** 451a904
**Applied fix:** Replaced the `execute_shell` implementation with a stub that returns an error message explaining it is disabled. The original `subprocess.run(shell=True)` body was removed. The function signature is preserved so existing call sites do not break at parse time.

---

### WR-01: Gap enrichment sends the wrong message type to providers

**Files modified:** `maestro/sdlc/gaps_server.py`
**Commit:** 3fd0497
**Applied fix:** Added `from maestro.providers.base import Message` import and replaced the two raw `dict` entries in `_llm_enrich()` with `Message(role=..., content=...)` objects so the provider's `stream()` method receives the expected type.

---

### WR-02: `GapsServer.stop()` does not close the listening socket

**Files modified:** `maestro/sdlc/gaps_server.py`
**Commit:** 4c48907
**Applied fix:** Added `self._server.server_close()` call immediately after `self._server.shutdown()` in `GapsServer.stop()` so the socket is released when the server is stopped.

---

### WR-03: Duplicate test classes silently disable half of the guardrail tests

**Files modified:** `tests/test_aggregator_guardrails.py`
**Commit:** 079cf17
**Applied fix:** Removed the second (duplicate) copy of `TestAggregatorGuardrail`, `TestSchedulerRouteIntegration`, and `TestRunMultiAgentGuardrailIntegration` that started at line 275. The first copy (lines 11–272) is the canonical version and is preserved unchanged.

---

## Skipped Issues

### CR-02: `main()` has critical cyclomatic complexity

**File:** `maestro/cli.py:56-553`
**Reason:** The fix requires splitting a 500-line function into 8+ dedicated handler functions plus a dispatch table. Applying this mechanically without understanding every branch's shared state (parser references, `_print_help` fallback, interactive spinner lifecycle) carries a high regression risk. This finding requires human review and an intentional refactoring session rather than automated application.
**Original issue:** `main()` has CC well above 20 by static count; hard to reason about and easy to break when adding new commands or compatibility branches.

---

_Fixed: 2026-04-24T15:30:00Z_
_Fixer: the agent (gsd-code-fixer)_
_Iteration: 1_
