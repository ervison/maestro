# Phase 9 Context: Planner

## Phase Goal
Implement the LLM-driven planner node that generates a validated task DAG from a user task string.

## Decisions Locked

### Plan Count
- **1 plan**: single cohesive plan covering `planner/node.py`, system prompt, config integration, and tests.

### Module Location
- `maestro/planner/node.py` — adds `planner_node()` to the existing `maestro/planner/` package alongside `schemas.py` and `validator.py`.

### Structured Output Strategy
- **Try api-level first, fall back to prompt-only**:
  1. Attempt `response_format={"type": "json_schema", "json_schema": AgentPlan.model_json_schema()}` for OpenAI-compatible providers.
  2. If the provider raises an error or doesn't support it, retry with a prompt-only approach (no `response_format` param).
  3. Always validate with `AgentPlan.model_validate_json()` regardless of the approach.
  4. Max 3 retries on invalid JSON before raising.

### Config Integration
- Planner model resolved via `config.agent.planner.model` (separate from worker models).
- Falls back to the default resolved model if the planner key is absent.

### Input/Output Contract
- Input: `AgentState` (reads `task` field and `workdir`).
- Output: `AgentState` update — populates `dag` field with the serialized `AgentPlan.model_dump()`.

### Planner System Prompt Design
- Must instruct the LLM to:
  - Decompose the task into atomic, domain-specialized subtasks.
  - Assign correct `domain` values from the `DomainName` literal.
  - Set `deps` correctly (no cycles, valid IDs only).
  - Avoid over-decomposition (prefer fewer, larger tasks over many tiny ones).
- Includes the `AgentPlan` JSON schema inline in the prompt as reference.

### Error Handling
- `AgentPlan.model_validate_json()` failure: retry up to 3 times.
- Cycle detection: `validate_dag()` from `maestro/planner/validator.py` runs after schema validation.
- If all retries fail: raise `ValueError` with the last validation error — do not pass invalid DAG to scheduler.

### Tests
- Unit tests in `tests/test_planner_node.py`.
- Mock the provider/LLM call; test valid DAG, schema validation rejection, cycle rejection, config model resolution.
- Must not break existing 26+ tests.

## Existing Infrastructure (Phase 8)
- `maestro/planner/schemas.py` — `AgentState`, `PlanTask`, `AgentPlan`, `_merge_dicts`
- `maestro/planner/validator.py` — `validate_dag(plan: AgentPlan) -> None`
- `maestro/domains.py` — 7 domain system prompts
- `maestro/config.py` — `get(key, default)` for config resolution
- `maestro/providers/base.py` — `ProviderPlugin` Protocol with `stream()` method

## Out of Scope for Phase 9
- Scheduler, Workers, Send API (Phase 10)
- `--multi` CLI flag (Phase 11)
- Aggregator (Phase 11)
