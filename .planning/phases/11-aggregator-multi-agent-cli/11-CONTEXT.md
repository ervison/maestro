# Phase 11 Context: Aggregator & Multi-Agent CLI

## Phase Summary

**Goal**: Users activate multi-agent mode via CLI and optionally receive a final aggregated summary.
**Phase branch**: gsd/phase-11-aggregator-multi-agent-cli
**Depends on**: Phase 10 (Scheduler & Workers — complete)

---

## Decisions (Locked)

### AGG-01/AGG-02: Aggregator
- **Mode**: LLM call — send all worker outputs to the LLM and ask for a coherent final summary
- **Default**: On by default — aggregator runs unless `config.aggregator.enabled = false` or `--no-aggregate` flag is passed
- **Placement**: Runs as final node after all workers complete, receives `AgentState.results` list

### CLI-01: `--multi` flag wiring
- **Integration point**: Branch in CLI handler (`maestro/cli.py`) — `if args.multi → call run_multi_agent()`, else keep existing `run()` call
- **No changes** to `agent.py` or `agent.run()` — zero regression risk on 26+ existing tests
- `--auto` and `--workdir` flags must pass through to all workers (already required by CLI-03)

### CLI-02/CLI-03: Lifecycle events
- **Format**: Simple `print()` lines to stdout
- Examples: `[planner] done`, `[worker:backend] started`, `[worker:backend] done`, `[aggregator] done`
- Consistent with existing CLI output style

### Error handling
- If `--multi` runs but zero workers complete: print error and exit with non-zero code
- Worker errors go into `AgentState.errors` (already implemented in Phase 10)

---

## Implementation Scope

Files to create/modify:
1. `maestro/cli.py` — add `--multi` flag to `run` subcommand, branch to `run_multi_agent()`
2. `maestro/multi_agent.py` — add aggregator node, wire lifecycle print events, add configurable skip
3. `tests/test_multi_agent_cli.py` — CLI integration tests for `--multi` flag
4. `tests/test_aggregator.py` — unit tests for aggregator node

## Out of Scope
- No UI/frontend changes
- No new providers
- No changes to `agent.py` internals
