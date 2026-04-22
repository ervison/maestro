# Phase 12 — DAG Planner Hardening: Execution Plan

## Goal
Rewrite `PLANNER_SYSTEM_PROMPT` in `maestro/planner/node.py` with non-negotiable authority language, a rationalization table, a behavioral independence test, a commitment device (pre-JSON reasoning block), and add unit tests that verify prompt content and behavioral correctness.

## Tasks

### T-01: Rewrite PLANNER_SYSTEM_PROMPT in maestro/planner/node.py
**File:** `maestro/planner/node.py`  
**Change:** Replace the current `PLANNER_SYSTEM_PROMPT` constant with a hardened version that includes:

1. **Authority header** — Open with "You are a task decomposition engine. The following rules are ABSOLUTE." (or similar)
2. **Core law section** — Every rule uses MUST/MUST NOT. Forbidden words: "prefer", "try", "avoid", "consider", "generally".
3. **Independence test** — Verbatim: "A task is independent ONLY IF its result does not change based on another task's result."
4. **Rationalization table** — Markdown table with columns: Rationalization | Why It Is Wrong | Verdict
   - Row 1: "These tasks share context, so they must be separate" | "Shared context means they are the SAME task" | MERGE
   - Row 2: "These could run in parallel" | "Parallel execution potential does not create independence; if sequencing is required, they are NOT independent" | MERGE or ADD DEP
   - Row 3: "Separating them is cleaner" | "Cleanliness is NOT a decomposition criterion" | MERGE
   - Row 4: "They belong to different domains" | "Domain boundaries do NOT equal task boundaries" | MERGE
   - Row 5: "They might need separate handling" | "Uncertainty is NOT a valid split reason" | MERGE
5. **Commitment device** — Instruction: Before outputting JSON, output a reasoning block (delimited by `<reasoning>` tags) containing: (a) final task count, (b) domain assignment per task, (c) independence rationale for each split. After the reasoning block, output ONLY the JSON.
6. **Output format** — JSON schema remains unchanged (same as current prompt)
7. **Cycle prohibition** — MUST NOT create cyclic dependencies (keep existing rule, upgrade to MUST NOT)

**No other changes** to `node.py` (function signatures, imports, logic all stay the same).

### T-02: Add unit tests for prompt hardening
**File:** `tests/planner/test_prompt_hardening.py` (new file, or append to existing test file)  
First check if `tests/planner/` exists; if not, use `tests/test_planner_prompt.py`.

**Tests:**
1. `test_prompt_contains_must` — assert `'MUST'` in `PLANNER_SYSTEM_PROMPT`
2. `test_prompt_contains_must_not` — assert `'MUST NOT'` in `PLANNER_SYSTEM_PROMPT`
3. `test_prompt_contains_rationalization_table` — assert `'Rationalization'` in `PLANNER_SYSTEM_PROMPT`
4. `test_prompt_contains_independence_criterion` — assert `"A task is independent ONLY IF its result does not change based on another task's result."` in `PLANNER_SYSTEM_PROMPT`
5. `test_prompt_contains_reasoning_block_instruction` — assert `'<reasoning>'` in `PLANNER_SYSTEM_PROMPT`
6. `test_prompt_forbids_softening_language` — assert none of `['prefer', 'Prefer', 'try to', 'Try to', 'consider', 'Consider', 'generally', 'Generally']` appear in `PLANNER_SYSTEM_PROMPT`
7. `test_over_decomposition_behavioral` — Mock test: given a planner response with 6 tasks for "write a hello world script", verify that the independence criterion (all tasks independent) cannot be satisfied (i.e., at least one task's result depends on another's). This can be implemented as a helper function `check_independence(tasks, deps)` that returns False if deps exist between tasks that could be merged.

### T-03: Run existing tests to confirm no regression
```
pytest tests/ -x -q
```
Must still show 341+ passing, 0 failures.

## Threat Model

| Threat | Mitigation |
|--------|------------|
| Reasoning block breaks JSON extraction | `extract_dag()` or equivalent in `node.py` already uses regex/JSON parse after prompt output; reasoning block uses `<reasoning>` tags which are not valid JSON and will be skipped by any JSON parser looking for `{` |
| LLM ignores pre-JSON instruction | Prompt instruction is authoritative ("MUST output reasoning block"); acceptance test covers this at prompt level |
| Softening language leaks back in | `test_prompt_forbids_softening_language` catches it |
| Existing tests break | T-03 regression gate; `PLANNER_SYSTEM_PROMPT` is a string constant, not a function — no signature change |
| Rationalization table rows are ambiguous | Each row has an explicit Verdict column (MERGE / ADD DEP) |

## Execution Order
T-01 → T-02 → T-03

T-01 and T-02 are independent and can be done in either order, but T-03 depends on both.

## Success Criteria
- All 5 prompt content tests pass
- `test_prompt_forbids_softening_language` passes
- `test_over_decomposition_behavioral` passes
- All pre-existing tests still pass (341+)
- `maestro run` single-agent mode behavior is unaffected
