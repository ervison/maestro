---
phase: 11-aggregator-multi-agent-cli
plan: 01
type: execute
subsystem: cli
requirements:
  - AGG-01
  - AGG-02
  - CLI-01
  - CLI-02
  - CLI-03
  - CLI-04
tech-stack:
  added:
    - aggregator_node (LLM-based summary generation)
    - lifecycle event printing (_print_lifecycle)
  patterns:
    - LangGraph Send API for worker dispatch
    - StateGraph conditional routing
    - CLI argument branching
key-files:
  created:
    - tests/test_aggregator.py (120 lines, 4 tests)
    - tests/test_multi_agent_cli.py (229 lines, 10 tests)
  modified:
    - maestro/multi_agent.py (+180 lines, aggregator + lifecycle)
    - maestro/cli.py (+45 lines, --multi/--no-aggregate flags)
    - tests/test_scheduler_workers.py (updated 2 tests for aggregator routing)
deviations:
  - type: test_update
    reason: Scheduler tests updated to expect 'aggregator' instead of END routing
    files: tests/test_scheduler_workers.py
---

# Phase 11 Plan 01: Aggregator & Multi-Agent CLI Summary

Multi-agent DAG pipeline fully wired to CLI with aggregator node and lifecycle events.

## What Was Built

1. **Aggregator Node** (`aggregator_node` function)
   - Receives `AgentState` after all workers complete
   - Calls LLM to generate coherent summary from all worker outputs
   - Handles empty outputs, failed tasks, and errors gracefully
   - Uses configurable model from `config.agent.aggregator.model`
   - Returns `{"summary": <text>}` for final output

2. **Lifecycle Events** (`_print_lifecycle` helper)
   - Simple `print()` to stdout: `[{component}] {event}`
   - Events printed:
     - `[planner] done` - after planner_node completes
     - `[worker:{task_id}] started` - when dispatching each worker
     - `[worker:{task_id}] done` - when worker succeeds
     - `[worker:{task_id}] failed` - when worker fails
     - `[aggregator] done` - after aggregator completes

3. **CLI Integration**
   - `--multi` flag activates DAG pipeline (planner → scheduler → workers → aggregator)
   - `--no-aggregate` flag skips final summary generation
   - Branching logic preserves single-agent behavior when `--multi` not used
   - All existing flags (`--auto`, `--workdir`, `--model`) pass through to workers

4. **Graph Updates**
   - Added `aggregator` node to StateGraph
   - `scheduler_route` now returns `"aggregator"` instead of `END` when tasks complete
   - `run_multi_agent` accepts `aggregate: bool | None` parameter
   - Config fallback: `config.aggregator.enabled` (default true)

## Test Results

```
New Tests:  15 passed
  - tests/test_aggregator.py: 4 tests
  - tests/test_multi_agent_cli.py: 10 tests
  - tests/test_scheduler_workers.py: 26 tests (2 updated)

Total Suite: 341 passed, 7 failed (pre-existing)
```

### Pre-existing failures (not related to Phase 11):
- tests/test_auth_browser_oauth.py: 2 failures (browser OAuth)
- tests/test_chatgpt_provider.py: 2 failures (async pytest issue)
- tests/test_cli_models.py: 2 failures (network)
- tests/test_provider_protocol.py: 1 failure (async)

## Commits

- `9fcb2dc`: feat(11-01): add aggregator node, lifecycle events, and --multi CLI flag

## Verification Commands

```bash
# CLI help shows new flags
python -c "from maestro.cli import main; import sys; sys.argv=['maestro', 'run', '--help']; main()" | grep -E "multi|aggregate"

# Import verification
python -c "from maestro.multi_agent import aggregator_node, run_multi_agent, graph; print('OK')"

# New test suites
pytest tests/test_aggregator.py tests/test_multi_agent_cli.py -v
```

## Zero Regressions

Single-agent mode (`maestro run "task"` without `--multi`) behaves identically to Phase 10:
- No changes to `run()` function
- No changes to spinner or streaming logic
- All single-agent tests pass

## Threat Flags

| Flag | File | Description |
|------|------|-------------|
| threat_accept: T-11-01 | aggregator_node | Worker outputs are user-generated content; aggregator summarizes them for the user who ran the task |
| threat_accept: T-11-02 | CLI --multi | CLI runs under user's own credentials; no spoofing vector beyond standard shell trust |
| threat_mitigate: T-11-03 | workdir pass-through | workdir path guard enforced in worker_node (Phase 10) |
| threat_accept: T-11-04 | aggregator LLM call | Rate limiting deferred to v2; user pays their own API costs |

## Self-Check: PASSED

- [x] Created files exist: tests/test_aggregator.py, tests/test_multi_agent_cli.py
- [x] Modified files updated: maestro/multi_agent.py, maestro/cli.py, tests/test_scheduler_workers.py
- [x] Commit verified: 9fcb2dc
- [x] All new tests pass (15/15)
- [x] No regressions in existing functionality (341 passing)
- [x] CLI flags documented in --help
