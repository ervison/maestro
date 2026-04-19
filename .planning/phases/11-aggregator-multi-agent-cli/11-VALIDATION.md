# Phase 11 Validation

- **Phase:** 11 — Aggregator & Multi-Agent CLI
- **Auditor:** gsd-nyquist-auditor
- **Date:** 2026-04-19
- **Status:** PASSED
- **Gate:** green

## Required Reading Loaded

- `.planning/phases/11-aggregator-multi-agent-cli/11-01-SUMMARY.md`
- `.planning/ROADMAP.md`
- `.planning/phases/11-aggregator-multi-agent-cli/11-REVIEW.md`

## Commands Run

```bash
python -m pytest tests/test_aggregator.py tests/test_multi_agent_cli.py -v
# Result: 20 passed
```

## Coverage by Success Criterion

| # | Success criterion | Coverage | Evidence | Status |
|---|-------------------|----------|----------|--------|
| 1 | `maestro run --multi "task"` activates planner → scheduler → workers → aggregator | `test_run_multi_agent_executes_full_pipeline_and_emits_lifecycle_events` | summary returned in result | green |
| 2 | Without `--multi`, `maestro run` preserves single-agent behavior | Existing CLI tests | `test_run_without_multi_uses_single_agent`, `test_zero_regressions_single_agent_path` | green |
| 3 | `--auto` and `--workdir` pass through from CLI to all workers | CLI passthrough + graph integration tests | `test_multi_passes_auto_flag`, `test_multi_passes_workdir` | green |
| 4 | Lifecycle events print to stdout during `--multi` execution | CLI output test + graph integration test | `test_lifecycle_events_printed`, `test_run_multi_agent_executes_full_pipeline_and_emits_lifecycle_events` | green |
| 5 | Aggregator runs after all workers complete and produces a final summary (optional, configurable) | Aggregator tests + config toggle | `test_aggregator_returns_summary_from_outputs`, `test_run_multi_agent_can_disable_aggregation_via_config` | green |

## Bugs Fixed (commit 679f7a5)

1. **VL-01a** — `summary: NotRequired[str]` added to `AgentState` in `maestro/planner/schemas.py` so aggregator output is persisted across graph invocation
2. **VL-01b** — `END` added to `add_conditional_edges("scheduler", ...)` targets in `maestro/multi_agent.py` so `aggregate=False` path terminates cleanly

## Pre-existing Failures (excluded)

The following test files have failures that pre-date phase 11 and are outside its scope:
- `tests/test_copilot_provider.py`
- `tests/test_chatgpt_provider.py`
- `tests/test_cli_models.py`
- `tests/test_provider_protocol.py`
- `tests/test_auth_browser_oauth.py`

## Latest Test Result

```text
20 collected, 20 passed
```

- **Phase:** 11 — Aggregator & Multi-Agent CLI
- **Auditor:** gsd-nyquist-auditor
- **Date:** 2026-04-19
- **Status:** BLOCKED
- **Gate:** blocked

## Required Reading Loaded

- `.planning/phases/11-aggregator-multi-agent-cli/11-01-SUMMARY.md`
- `.planning/ROADMAP.md`
- `.planning/phases/11-aggregator-multi-agent-cli/11-REVIEW.md`

## Commands Run

```bash
python -m pytest tests/test_aggregator.py tests/test_multi_agent_cli.py -v
```

## Coverage by Success Criterion

| # | Success criterion | Coverage | Evidence | Status |
|---|-------------------|----------|----------|--------|
| 1 | `maestro run --multi "task"` activates planner → scheduler → workers → aggregator | Added behavioral integration test in `tests/test_aggregator.py::test_run_multi_agent_executes_full_pipeline_and_emits_lifecycle_events` | Lifecycle output shows planner/worker/aggregator nodes executed | **blocked** — implementation drops `summary` from `run_multi_agent()` result |
| 2 | Without `--multi`, `maestro run` preserves single-agent behavior | Existing CLI tests | `test_run_without_multi_uses_single_agent`, `test_zero_regressions_single_agent_path` | green |
| 3 | `--auto` and `--workdir` pass through from CLI to all workers | Existing CLI passthrough tests + added graph-level integration test | `test_multi_passes_auto_flag`, `test_multi_passes_workdir`, `test_run_multi_agent_executes_full_pipeline_and_emits_lifecycle_events` | green |
| 4 | Lifecycle events print to stdout during `--multi` execution | Existing CLI output test + added graph-level integration test | `test_lifecycle_events_printed`, `test_run_multi_agent_executes_full_pipeline_and_emits_lifecycle_events` | green |
| 5 | Aggregator runs after all workers complete and produces a final summary (optional, configurable) | Existing aggregator tests + added config toggle test | `test_aggregator_returns_summary_from_outputs`, `test_run_multi_agent_executes_full_pipeline_and_emits_lifecycle_events`, `test_run_multi_agent_can_disable_aggregation_via_config` | **blocked** — two implementation bugs below |

## Gaps Found

1. Phase tests did not previously validate the real planner → graph → worker → aggregator flow.
2. Phase tests did not previously validate config-driven aggregation disablement (`aggregate=None` + `config.aggregator.enabled=false`).

## Gaps Filled

Added to `tests/test_aggregator.py`:

- `test_run_multi_agent_executes_full_pipeline_and_emits_lifecycle_events`
- `test_run_multi_agent_can_disable_aggregation_via_config`

## Debug / Escalations

### Escalation 1 — Aggregated summary is lost from `run_multi_agent()` result

- **Requirement:** Success criteria 1 and 5
- **Test:** `tests/test_aggregator.py::TestAggregatorNode::test_run_multi_agent_executes_full_pipeline_and_emits_lifecycle_events`
- **Iteration:** 1/3
- **Observed behavior:** Graph executes fully and prints `[aggregator] done`, but `run_multi_agent()` returns no `summary` key.
- **Expected behavior:** Final result should include the aggregated summary so CLI can print it.
- **Likely implementation reference:** `maestro/planner/schemas.py` omits `summary` from `AgentState`, so LangGraph state drops aggregator output before `run_multi_agent()` reads it.

### Escalation 2 — Config-disabled aggregation crashes the graph

- **Requirement:** Success criterion 5 (optional/configurable aggregation)
- **Test:** `tests/test_aggregator.py::TestAggregatorNode::test_run_multi_agent_can_disable_aggregation_via_config`
- **Iteration:** 1/3
- **Observed behavior:** When `aggregate=None` and config returns `aggregator.enabled = false`, execution crashes with `KeyError: '__end__'` from LangGraph branch resolution.
- **Expected behavior:** Execution should end cleanly without calling the aggregator and return worker outputs only.
- **Likely implementation reference:** `maestro/multi_agent.py:scheduler_route()` returns `END`, but `_builder.add_conditional_edges("scheduler", scheduler_route, ["dispatch", "aggregator"])` does not map the END branch.

## Latest Test Result

```text
20 collected, 18 passed, 2 failed

FAILED tests/test_aggregator.py::TestAggregatorNode::test_run_multi_agent_executes_full_pipeline_and_emits_lifecycle_events
FAILED tests/test_aggregator.py::TestAggregatorNode::test_run_multi_agent_can_disable_aggregation_via_config
```

## Recommendation

1. Add `summary` to the persisted graph state contract so aggregator output survives `graph.invoke()`.
2. Fix the scheduler conditional edge mapping so `aggregate=False` can terminate at `END` without raising `KeyError`.
3. Re-run:

```bash
python -m pytest tests/test_aggregator.py tests/test_multi_agent_cli.py -v
```
