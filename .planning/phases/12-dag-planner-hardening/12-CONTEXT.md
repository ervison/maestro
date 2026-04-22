# Phase 12 — DAG Planner Hardening: Context

## Goal

Rewrite `PLANNER_SYSTEM_PROMPT` in `maestro/planner/node.py` with:
- Non-negotiable authority language (MUST/MUST NOT throughout)
- Rationalization table (5 over-decomposition patterns + sharp rebuttals)
- Behavioral independence test (result-independence criterion)
- Commitment device (pre-JSON reasoning block)
- New unit tests verifying prompt content and behavioral correctness

## Decisions Made (from /discuss)

### D-01: Prompt authority style
**Decision:** Hard MUST/MUST NOT throughout  
Every rule uses MUST/MUST NOT. Zero softening language ("prefer", "try", "avoid" are banned). Use prohibition sections instead of guidelines.

### D-02: Rationalization table design
**Decision:** 5 patterns with sharp rebuttals  
Patterns: shared-context splitting, sequential-becomes-parallel, cleaner-separation, domain-boundary splitting, uncertainty-hedging.  
Each row: excuse → concrete hard rebuttal (NOT soft guidance).

### D-03: Independence test wording
**Decision:** Behavioral result-independence criterion  
Exact wording: "A task is independent ONLY IF its result does not change based on another task's result."

### D-04: Commitment device mechanism
**Decision:** Pre-JSON reasoning block  
Planner must output a brief reasoning block BEFORE the JSON output:
- Task count
- Domain assignments
- Independence rationale for each split
The reasoning block is ignored at runtime — JSON is extracted after it.

### D-05: Test coverage approach
**Decision:** Substring + behavioral mock tests  
- Assert `PLANNER_SYSTEM_PROMPT` contains: `'MUST'`, rationalization table markers, independence test string, reasoning block instruction
- Plus a behavioral unit test: mock planner output with too many tasks for a simple request fails the independence criterion

## Files to Change

- `maestro/planner/node.py` — rewrite `PLANNER_SYSTEM_PROMPT`
- `tests/test_planner.py` (or new `tests/planner/test_prompt_hardening.py`) — new tests

## Constraints

- Must not break existing 341+ passing tests
- `maestro run` (no flags) must behave identically
- Path guard and max depth guard remain untouched
