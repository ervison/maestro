# Phase 12 — Discussion Log

## Session Date
2026-04-21

## Discussion Areas

### D-01: Prompt authority style
**Options presented:** Soft guidelines / Mixed MUST + guidelines / Hard MUST/MUST NOT throughout  
**Decision:** Hard MUST/MUST NOT throughout  
**Rationale:** Soft language ("prefer", "try") gives the LLM wiggle room to over-decompose. Authority language removes ambiguity and reduces the surface for rationalization.

### D-02: Rationalization table design
**Options presented:** 3 patterns generic / 5 patterns with soft guidance / 5 patterns with sharp rebuttals  
**Decision:** 5 patterns with sharp rebuttals  
**Patterns:**
1. Shared-context splitting — "these share context so must be separate" → rebuttal: shared context means SAME task
2. Sequential-becomes-parallel — "these could run in parallel" → rebuttal: if they must sequence, they are NOT independent
3. Cleaner-separation — "cleaner to separate concerns" → rebuttal: cleanliness is not a decomposition criterion
4. Domain-boundary splitting — "different domains" → rebuttal: domain boundaries do not equal task boundaries
5. Uncertainty-hedging — "might need separate handling" → rebuttal: uncertainty is not a valid split reason

### D-03: Independence test wording
**Options presented:** Temporal ("can run at the same time") / Input-independence ("has different inputs") / Result-independence  
**Decision:** Result-independence criterion  
**Exact wording:** "A task is independent ONLY IF its result does not change based on another task's result."

### D-04: Commitment device mechanism
**Options presented:** Post-JSON critique / Chain-of-thought inline / Pre-JSON reasoning block  
**Decision:** Pre-JSON reasoning block  
**Format:** Planner outputs reasoning block first (task count, domains, independence rationale), then the JSON DAG. Runtime extracts JSON from after the reasoning block.

### D-05: Test coverage approach
**Options presented:** Integration test only / Substring checks only / Substring + behavioral mock tests  
**Decision:** Substring + behavioral mock tests  
**Tests:**
- `test_prompt_contains_must` — assert 'MUST' in PLANNER_SYSTEM_PROMPT
- `test_prompt_contains_rationalization_table` — assert table marker(s) present
- `test_prompt_contains_independence_criterion` — assert exact independence string present
- `test_prompt_contains_reasoning_block_instruction` — assert reasoning block instruction present
- `test_over_decomposition_fails_independence` — behavioral mock test
