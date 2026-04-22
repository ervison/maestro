---
phase: 12-dag-planner-hardening
fixed_at: 2026-04-21T00:00:00Z
review_path: .planning/phases/12-dag-planner-hardening/REVIEW.md
iteration: 1
findings_in_scope: 4
fixed: 4
skipped: 0
status: all_fixed
---

# Phase 12: Code Review Fix Report

**Fixed at:** 2026-04-21T00:00:00Z  
**Source review:** `.planning/phases/12-dag-planner-hardening/REVIEW.md`  
**Iteration:** 1

**Summary:**
- Findings in scope: 4
- Fixed: 4
- Skipped: 0

## Fixed Issues

### CR-01: Prompt contract now conflicts with runtime parser

**Files modified:** `maestro/planner/node.py`  
**Commit:** 3b1ef68  
**Applied fix:** Added `<reasoning>...</reasoning>` block stripping BEFORE markdown fence stripping in `planner_node()`. The stripping occurs after `_call_provider_with_schema()` returns and before `AgentPlan.model_validate_json(raw)` is called. Also updated the retry message from `"Please respond with valid JSON only, matching the schema exactly."` to `"Output the <reasoning> block first, then ONLY the JSON matching the schema exactly."` so it no longer contradicts the system prompt contract.

### HI-01 + HI-02: New prompt tests insufficient; planner-node assertions too weak

**Files modified:** `tests/test_planner_prompt.py`  
**Commit:** 3b1ef68  
**Applied fix:** Added 10 new tests covering all rationalization table rows (shared-context, domain-boundary, uncertainty, cleanliness), MERGE verdict presence, cycle prohibition, `</reasoning>` close tag, "ONLY the JSON" post-reasoning instruction, catch-all rule presence, and a unit test (`test_reasoning_block_stripped_from_raw_response`) that directly exercises the stripping logic with `<reasoning>...</reasoning>\n{...}` input and asserts the JSON remainder is returned correctly.

### ME-01: Rationalization table is illustrative, not exhaustive

**Files modified:** `maestro/planner/node.py`  
**Commit:** 3b1ef68  
**Applied fix:** Added catch-all paragraph after the rationalization table in `PLANNER_SYSTEM_PROMPT`: "These examples are not exhaustive. Any split justified by cleanliness, file boundaries, domain boundaries, implementation steps, hypothetical parallelism, or vague future risk is invalid unless the outputs are truly independent under the Independence Test above."

### LO-01: Unused import in new test file

**Files modified:** `tests/test_planner_prompt.py`  
**Commit:** 3b1ef68  
**Applied fix:** Removed `import pytest` from line 8 of `tests/test_planner_prompt.py`.

---

**Test result:** 403 passed, 1 skipped — all tests green after fixes.

---

_Fixed: 2026-04-21T00:00:00Z_  
_Fixer: the agent (gsd-code-fixer)_  
_Iteration: 1_
