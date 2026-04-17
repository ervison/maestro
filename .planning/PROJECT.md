# Maestro

## What This Is

Maestro is a CLI-driven AI agent that executes complex software engineering tasks using file system tools and shell commands. It is being extended from a single-agent agentic loop into a multi-agent parallel execution engine, where a Planner decomposes tasks into a dependency DAG and specialized Worker agents execute in parallel via LangGraph's Send API. It targets developers who need to automate multi-domain tasks (coding + testing + docs + devops) from the terminal.

## Core Value

A developer runs `maestro run --multi "build a REST API with tests and docs"` and gets all parts done in parallel by specialized agents — faster and with cleaner domain separation than a single agent.

## Requirements

### Validated

- ✓ Single-agent agentic loop (`_run_agentic_loop`) with file tools — existing
- ✓ File system tools: `read_file`, `write_file`, `create_file`, `list_directory`, `delete_file`, `move_file`, `search_in_files`, `execute_shell` — existing
- ✓ Path guard (workdir containment, no `..` traversal) — existing
- ✓ Confirmation prompts for destructive tools — existing
- ✓ `--auto` flag (skip confirmations) — existing
- ✓ `--workdir` flag — existing
- ✓ ChatGPT provider (OpenAI Responses API, SSE streaming) — existing

### Active

- [ ] Multi-agent DAG mode via `--multi` flag
- [ ] Planner: structured JSON DAG output (task id, domain, prompt, deps)
- [ ] Scheduler: topological sort + LangGraph Send API for parallel dispatch
- [ ] Worker: domain-specialized system prompt, reuses `_run_agentic_loop`
- [ ] Domain system (`maestro/domains.py`): backend, testing, docs, devops, data, general
- [ ] Recursive workers (max depth guard, configurable, default 2)
- [ ] LangGraph state with reducers for safe parallel writes
- [ ] Aggregator node (optional final summary pass)
- [ ] Multi-provider plugin system (`ProviderPlugin` Protocol, entry points)
- [ ] GitHub Copilot provider (device code OAuth, OpenAI-compatible stream)
- [ ] Config system (`~/.maestro/config.json`, `provider_id/model_id` format)
- [ ] Multi-slot auth store (`~/.maestro/auth.json`)
- [ ] `maestro auth login/logout/status` subcommands
- [ ] `maestro models` subcommand
- [ ] `--model` flag on `run` subcommand
- [ ] Backward compatibility: existing `maestro run` unchanged

### Out of Scope

- Dynamic worker pool sizing / resource limits — v2, premature optimization
- Cross-worker in-memory communication — workers share filesystem, not memory
- Human-in-the-loop DAG approval before execution — keep automation uninterrupted
- Streaming partial results to CLI during multi-agent execution — complex, v2
- Persistent DAG state across CLI sessions — stateless by design
- GitHub Enterprise Copilot — v2 expansion
- Token refresh for GitHub Copilot — token is long-lived
- Model picker TUI — v2 UX improvement
- Per-provider rate limiting / retry — v2 resilience
- Providers beyond GitHub Copilot and ChatGPT — entry points allow third-party plugins

## Context

- **Brownfield project**: codebase already has `agent.py`, `tools.py`, `auth.py`, `cli.py`, `__init__.py`
- **Existing agentic loop**: `_run_agentic_loop` in `agent.py` handles streaming SSE, tool execution, and multi-turn conversation
- **LangGraph already present**: used for `@entrypoint` / `@task` wrapping for observability and retry
- **Single provider**: currently hardwired to ChatGPT (OpenAI Responses API) via `auth.py`
- **Two parallel workstreams**: (1) Multi-Agent DAG extends execution model; (2) Multi-Provider refactors HTTP layer to a plugin interface — these interact but can be phased independently
- **Design docs**: `docs/ideas/multi-agent-dag.md`, `docs/superpowers/specs/2026-04-17-multi-provider-plugin-design.md`, `docs/superpowers/specs/2026-04-17-agentic-file-tools-design.md`

## Constraints

- **Tech stack**: Python, LangGraph, httpx, pyproject.toml entry points — no framework changes
- **Backward compatibility**: `maestro run` (no flags) must behave identically to today — zero regressions on all 26+ existing tests
- **Security**: path guard must apply inside every Worker, not just at CLI level
- **Recursion safety**: max depth guard is mandatory; infinite recursion is a hard failure mode
- **Entry points for providers**: external providers must be installable via `pip install` without touching maestro source

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| LangGraph Send API for parallel dispatch | Native LangGraph primitive for fan-out; avoids manual threading | — Pending |
| ProviderPlugin as Protocol (not ABC) | Structural typing — third-party providers don't need to import maestro base | — Pending |
| Workers reuse `_run_agentic_loop` unchanged | Maximizes reuse, minimizes surface area for new bugs | — Pending |
| Planner is a separate model call (not a graph node) | Keeps DAG generation isolated and testable | — Pending |
| Multi-provider before multi-agent | Provider abstraction must exist before workers can use different models | — Pending |
| Domain prompts in `maestro/domains.py` | Easy to extend without touching core scheduler/worker logic | — Pending |

## Evolution

This document evolves at phase transitions and milestone boundaries.

**After each phase transition** (via `/gsd-transition`):
1. Requirements invalidated? → Move to Out of Scope with reason
2. Requirements validated? → Move to Validated with phase reference
3. New requirements emerged? → Add to Active
4. Decisions to log? → Add to Key Decisions
5. "What This Is" still accurate? → Update if drifted

**After each milestone** (via `/gsd-complete-milestone`):
1. Full review of all sections
2. Core Value check — still the right priority?
3. Audit Out of Scope — reasons still valid?
4. Update Context with current state

---
*Last updated: 2026-04-17 after initialization*
