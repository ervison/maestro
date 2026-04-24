---
phase: 17-aggregator-guardrails
fixed_at: 2026-04-24T18:15:00Z
review_path: .planning/phases/17-aggregator-guardrails/17-REVIEW.md
iteration: 3
findings_in_scope: 4
fixed: 4
skipped: 0
status: all_fixed
---

# Phase 17: Code Review Fix Report

**Fixed at:** 2026-04-24T18:15:00Z
**Source review:** .planning/phases/17-aggregator-guardrails/17-REVIEW.md
**Iteration:** 3

**Summary:**
- Findings in scope: 4 (CR-01 Critical; WR-01, WR-02, WR-03 Warning)
- Fixed: 4
- Skipped: 0

## Fixed Issues

### CR-01: `search_in_files()` can read files outside `workdir` through symlinks

**Files modified:** `maestro/tools.py`
**Commit:** `7e52901`
**Applied fix:** Before reading each matched file, resolve it with `fpath.resolve()` and call `resolved_file.relative_to(workdir.resolve())`. Any file whose resolved path escapes `workdir` raises `ValueError` and is skipped via `continue`. Subsequent `read_text()` is called on `resolved_file` (the canonical path) instead of `fpath`, closing the symlink escape vector.

### WR-01: Planner schema fallback does not work for providers that reject `response_format`

**Files modified:** `maestro/planner/node.py`
**Commit:** `74e2fb3`
**Applied fix:** Added an `except RuntimeError as exc` branch after the existing `TypeError` catch in `_call_provider_with_schema()`. If the exception message contains `"response_format"` (case-insensitive), the planner falls back to prompt-only mode and logs at DEBUG level. Other `RuntimeError`s (auth/network failures) are re-raised unchanged.

### WR-02: `/answers` accepts malformed `selected_options` payloads and can corrupt downstream prompts

**Files modified:** `maestro/sdlc/gaps_server.py`
**Commit:** `c4daa85`
**Applied fix:** Replaced the truthy `if selected:` check with an explicit type guard: `isinstance(selected, list) and selected and all(isinstance(opt, str) and opt for opt in selected)`. This rejects scalar strings, empty lists, and mixed-type arrays. The existing `except ValueError` handler returns HTTP 400, so invalid payloads are rejected without leaking the error message format change.

### WR-03: Aggregator guardrail test expects the wrong validation message

**Files modified:** `tests/test_aggregator_guardrails.py`
**Commit:** `4ef1407`
**Applied fix:** Changed the `pytest.raises` match argument from the literal `"expected 'aggregator.max_tokens_per_run' to be an int"` to the regex `r"aggregator\.max_tokens_per_run.*non-negative int"`, which matches the actual runtime error message produced by `maestro/config.py` validation.

---

_Fixed: 2026-04-24T18:15:00Z_
_Fixer: the agent (gsd-code-fixer)_
_Iteration: 3_
