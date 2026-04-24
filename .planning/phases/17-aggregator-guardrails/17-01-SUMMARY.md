# Phase 17-01 Summary: Aggregator Guardrails

## What Was Built

`AggregatorGuardrail` dataclass and `check_aggregator_guardrail()` function in `maestro/multi_agent.py`, wired into `scheduler_route` so the optional aggregator LLM call is bounded by explicit policy before running.

## Artifacts

| File | Change | Purpose |
|------|--------|---------|
| `maestro/planner/schemas.py` | +20 lines | `AggregatorGuardrail` dataclass with `max_calls` and `max_tokens_per_run` fields |
| `maestro/multi_agent.py` | +68 lines | `check_aggregator_guardrail()`, guardrail enforcement in `scheduler_route`, imports fixed (`load_config`, `planner_node`, `validate_dag`, `get_domain_prompt`, `get_default_provider`, `HumanMessage/BaseMessage`, `logger`) |
| `maestro/config.py` | +11 lines | Config validation for `aggregator.max_calls` and `aggregator.max_tokens_per_run` (type-checked as int) |
| `tests/test_aggregator_guardrails.py` | new | 15 tests covering allow, block-by-call-count, block-by-token-budget, config validation, scheduler integration, and `run_multi_agent` integration paths |

## Requirements Satisfied

| ID | Description | Status |
|----|-------------|--------|
| AGG-GUARD-01 | Explicit call-count and token-budget guardrails | ✅ |
| AGG-GUARD-02 | Repeated aggregation bounded in unattended runs | ✅ |
| AGG-GUARD-03 | CLI prints `[aggregator] skipped — <reason>` when blocked | ✅ |
| AGG-GUARD-04 | Tests cover allow, block, and skip paths | ✅ |

## Key Decisions

- `AggregatorGuardrail` lives in `maestro/planner/schemas.py` (alongside `AgentState`/`AgentPlan`) so it's importable without circular deps
- `max_calls=0` = explicitly disabled (not "no limit") — matches user intuition
- `max_calls=None` = no call-count limit (opt-in, backward compatible)
- Token estimation: `sum(len(v) // 4 for v in outputs.values())` — cheap proxy, not a billing counter
- `load_config` aliased from `maestro.config.load` to match test patch target `maestro.multi_agent.load_config`
- `cfg = load_config()` moved before the `aggregate is None` branch so `cfg` is always in scope for guardrail construction

## Test Results

```
119 passed, 2 skipped in 6.97s
```

15 new guardrail tests, zero regressions across full suite.

## Import Fixes Applied

The implementation had several missing imports that were added during this plan's execution:
- `from maestro.config import load as load_config`
- `from maestro.planner.node import planner_node`
- `from maestro.planner.validator import validate_dag`
- `from maestro.domains import get_domain_prompt`
- `from maestro.providers.registry import get_default_provider`
- `from langchain_core.messages import BaseMessage, HumanMessage, AIMessage`
- `logger = logging.getLogger(__name__)`
