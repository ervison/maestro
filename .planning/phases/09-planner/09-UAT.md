---
status: complete
phase: 09-planner
source: [09-01-SUMMARY.md]
started: 2026-04-18T23:00:00Z
updated: 2026-04-18T23:10:00Z
---

## Current Test

[testing complete]

## Tests

### 1. Import and call planner_node
expected: `from maestro.planner import planner_node, PLANNER_SYSTEM_PROMPT` succeeds with no ImportError. `planner_node` is callable. `PLANNER_SYSTEM_PROMPT` is a non-empty string.
result: pass

### 2. PLANNER_SYSTEM_PROMPT contains domain definitions
expected: `PLANNER_SYSTEM_PROMPT` contains all 7 domains: backend, testing, docs, devops, security, data, general. It also contains a `{schema}` placeholder and instructions for atomic task decomposition.
result: pass

### 3. planner_node returns valid DAG structure
expected: Calling `planner_node(state)` with a mocked provider that returns valid JSON produces `{"dag": {"tasks": [...]}}`. The `tasks` list contains items with `id`, `domain`, `prompt`, and `deps` fields.
result: pass

### 4. Invalid LLM output is rejected after 3 retries
expected: When the provider always returns invalid JSON, `planner_node` raises `ValueError` with a message like "Planner failed to produce a valid AgentPlan after 3 attempts". The provider stream is called exactly 3 times.
result: pass

### 5. Cyclic DAG is rejected
expected: When the provider returns a plan where t1 depends on t2 and t2 depends on t1, `planner_node` raises a `ValueError` containing "cycle".
result: pass

### 6. Config model resolution — plain model name
expected: When `config.agent.planner.model` is set to `"custom-model-123"`, the stream is called with `model="custom-model-123"`.
result: pass

### 7. Config model resolution — provider/model format
expected: When `config.agent.planner.model` is set to `"chatgpt/gpt-4o"`, `get_provider("chatgpt")` is called and the stream uses `model="gpt-4o"`.
result: pass

### 8. Markdown fence stripping
expected: When the provider returns JSON wrapped in ```json ... ``` fences, `planner_node` correctly parses the inner JSON and returns a valid dag — no parse error.
result: pass

### 9. Final Message.content is canonical over str deltas
expected: When the provider yields partial str chunks followed by a final `Message(content=valid_json)`, the final `Message.content` wins. The plan is parsed from the complete Message, not from concatenated str deltas.
result: pass

### 10. Non-parse errors propagate without retry
expected: When the provider raises `RuntimeError("Connection refused")`, `planner_node` propagates it immediately without retrying. The stream is called exactly once.
result: pass

### 11. Task length guard
expected: When `state["task"]` exceeds 8000 characters, `planner_node` raises `ValueError` with a message mentioning "too long" before making any provider call.
result: pass

## Summary

total: 11
passed: 11
issues: 0
pending: 0
skipped: 0
blocked: 0

## Gaps

[none]
