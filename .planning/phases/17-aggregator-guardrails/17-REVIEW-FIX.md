---
phase: 17-aggregator-guardrails
fixed_at: 2026-04-24T16:30:00Z
review_path: .planning/phases/17-aggregator-guardrails/17-REVIEW.md
iteration: 1
findings_in_scope: 3
fixed: 3
skipped: 0
status: all_fixed
---

# Phase 17: Code Review Fix Report

**Fixed at:** 2026-04-24T16:30:00Z
**Source review:** .planning/phases/17-aggregator-guardrails/17-REVIEW.md
**Iteration:** 1

**Summary:**
- Findings in scope: 3 (WR-01, WR-02, WR-03 from the latest iteration)
- Fixed: 3
- Skipped: 0

> Note: The first-iteration warnings WR-03 (scheduler complexity), WR-04 (aggregator complexity), WR-05 (run_multi_agent complexity) overlap with the second-iteration WR-02/WR-03; the second review supersedes the first. First-iteration WR-02 (provider/model mismatch) was already fixed before this review cycle and was confirmed present in the code.

## Fixed Issues

### WR-01: `max_calls` contract inconsistent across schema, runtime config, and tests

**Files modified:** `maestro/config.py`, `tests/test_aggregator_guardrails.py`
**Commits:** `41c3578`, `37ce50f`
**Applied fix:**
- Removed the `max_calls not in (None, 0, 1)` gate that rejected any value greater than 1.
- Replaced the two-step int-type + allow-list check with a single combined guard: `type(max_calls) is not int or max_calls < 0`.
- Updated the test assertion regex from `"to be an int"` to `"to be a non-negative int"` to match the revised error message.
- All 15 guardrail tests pass after the change.

### WR-02: `load()` has elevated cyclomatic complexity (CC=13)

**Files modified:** `maestro/config.py`
**Commit:** `29ebdf2`
**Applied fix:**
- Extracted `_validate_root_config(data)` — validates top-level JSON shape, `model` string type, and `agent` dict type.
- Extracted `_validate_aggregator_config(aggregator)` — validates aggregator dict type, `max_calls` non-negative int, and `max_tokens_per_run` int.
- Reduced `load()` to: parse JSON → `_validate_root_config` → `_validate_aggregator_config` → construct `Config`. Cyclomatic complexity drops from ~13 to ~3.

### WR-03: `aggregator_node()` has elevated cyclomatic complexity (CC=13)

**Files modified:** `maestro/multi_agent.py`
**Commit:** `70670c5`
**Applied fix:**
- Extracted `_build_aggregator_prompt(task, outputs, failed, errors) -> str` — builds the formatted LLM user message.
- Extracted `_resolve_aggregator_provider(state) -> (provider, model)` — resolves provider with the caller-injected vs. config-resolved matching logic (preserves the WR-02 fix from the first review).
- Extracted `_run_aggregator_stream(provider, model, user_message, task) -> Coroutine[str]` — async function that streams tokens from the provider.
- Extracted `_run_aggregator_sync(provider, model, user_message, task) -> str` — bridges the event loop (running loop, non-running loop, no loop) and calls `_run_aggregator_stream`.
- `aggregator_node()` is now a thin coordinator: emit active → early-return on empty → build prompt → resolve provider → stream sync → emit done/log → return summary. Cyclomatic complexity drops from ~13 to ~4.

---

_Fixed: 2026-04-24T16:30:00Z_
_Fixer: the agent (gsd-code-fixer)_
_Iteration: 1_
