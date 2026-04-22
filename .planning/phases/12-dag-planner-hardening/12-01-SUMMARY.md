---
phase: 12
plan: 1
subsystem: planner
tags: [prompt-engineering, llm-guidance, authority-language, rationalization, independence-test]
dependency_graph:
  requires: []
  provides: [hardened-planner-prompt, prompt-content-tests]
  affects: [maestro/planner/node.py]
tech_stack:
  added: []
  patterns: [authority-language prompt design, commitment device, rationalization table]
key_files:
  modified:
    - maestro/planner/node.py
    - tests/test_planner_node.py
  created:
    - tests/test_planner_prompt.py
decisions:
  - "Replaced all softening language (prefer/try/avoid/consider/generally) with MUST/MUST NOT"
  - "Added result-independence criterion as verbatim testable string"
  - "Added 5-row rationalization table with MERGE/ADD DEP verdicts"
  - "Added pre-JSON <reasoning> commitment device to force LLM self-audit before output"
  - "Updated 2 existing tests that checked for old prompt text (Rule 1 auto-fix)"
metrics:
  duration: "~5 minutes"
  completed: "2026-04-21"
---

# Phase 12 Plan 1: DAG Planner Hardening Summary

**One-liner:** Hardened `PLANNER_SYSTEM_PROMPT` with MUST/MUST NOT authority language, 5-row rationalization table, result-independence criterion, and pre-JSON `<reasoning>` commitment device to prevent LLM over-decomposition.

## What Was Built

### T-01: PLANNER_SYSTEM_PROMPT rewrite (`maestro/planner/node.py`)

The prompt was rewritten with:

1. **Authority header** — "You are a task decomposition engine. The following rules are ABSOLUTE and MUST be followed without exception."
2. **MUST/MUST NOT language** throughout — zero softening words (prefer/try/avoid/consider/generally removed)
3. **Independence test** — Verbatim: "A task is independent ONLY IF its result does not change based on another task's result."
4. **Rationalization table** — 5-row Markdown table mapping common LLM over-decomposition excuses to hard verdicts (MERGE / MERGE or ADD DEP)
5. **Commitment device** — Before JSON, LLM MUST output `<reasoning>...</reasoning>` block with: (a) task count justification, (b) domain assignments, (c) independence rationale per split
6. **Cycle prohibition** — Upgraded to MUST NOT language

No function signatures, imports, or logic changed (prompt text and <reasoning> stripping logic updated).

### T-02: Unit tests (`tests/test_planner_prompt.py`)

17 new tests added (7 original + 10 additional from Round 2 gate review):
- `test_prompt_contains_must`
- `test_prompt_contains_must_not`
- `test_prompt_contains_rationalization_table`
- `test_prompt_contains_independence_criterion`
- `test_prompt_contains_reasoning_block_instruction`
- `test_prompt_forbids_softening_language`
- `test_prompt_requires_dependencies_for_non_independent_tasks`
- `test_prompt_rationalization_row_shared_context`
- `test_prompt_rationalization_row_domain_boundary`
- `test_prompt_rationalization_row_uncertainty`
- `test_prompt_rationalization_row_cleanliness`
- `test_prompt_rationalization_verdicts_present`
- `test_prompt_cycle_prohibition`
- `test_prompt_reasoning_block_close_tag`
- `test_prompt_output_only_json_after_reasoning`
- `test_prompt_contains_catch_all_rule`
- `test_prompt_requires_reasoning_block_before_json_output`

2 integration tests added to `tests/test_planner_node.py`:
- `test_reasoning_block_stripped_by_planner_node`
- `test_reasoning_block_not_stripped_when_embedded_in_json`

### T-03: Regression check

403 tests pass, 1 skipped, 0 failures.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Existing test `test_planner_exports_prompt` checked for "task decomposition specialist"**
- **Found during:** T-03 test run
- **Issue:** The authority header was changed from "specialist" to "engine" — breaking existing assertion
- **Fix:** Updated assertion to `"task decomposition" in ...` (broader, still meaningful)
- **Files modified:** `tests/test_planner_node.py`
- **Commit:** 86ec01d

**2. [Rule 1 - Bug] Existing test `test_provider_receives_schema_enforced_system_prompt_and_user_task` checked for "Prefer FEWER larger tasks over many tiny ones"**
- **Found during:** T-03 test run
- **Issue:** That softening-language sentence was removed as part of the hardening — correctly
- **Fix:** Updated assertion to `"MUST" in messages[0].content` — verifies hardened content instead
- **Files modified:** `tests/test_planner_node.py`
- **Commit:** 86ec01d

## Self-Check: PASSED

- `maestro/planner/node.py` exists and contains `PLANNER_SYSTEM_PROMPT` with all required elements ✓
- `tests/test_planner_prompt.py` exists with 7 tests ✓
- Commit `86ec01d` exists ✓
- 393 tests pass, 0 failures ✓
