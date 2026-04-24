# Maestro

## What This Is

Maestro is a CLI-driven AI agent that executes complex software engineering tasks using file system tools and shell commands. It now ships both a single-agent execution path and a multi-agent parallel execution engine, where a Planner decomposes tasks into a dependency DAG and specialized Workers execute in parallel via LangGraph's Send API. It targets developers who need to automate multi-domain tasks from the terminal without losing direct filesystem and shell control.

## Core Value

A developer runs `maestro run --multi "build a REST API with tests and docs"` and gets all parts done in parallel by specialized agents with cleaner domain separation than a single agent.

## Requirements

### Validated

- [x] Single-agent agentic loop (`_run_agentic_loop`) with file tools
- [x] File system tools, path guard, destructive-action confirmations, `--auto`, and `--workdir`
- [x] Provider plugin system with ChatGPT and GitHub Copilot implementations
- [x] Multi-slot auth store, provider-aware config, `maestro auth ...`, and `maestro models`
- [x] Multi-agent DAG execution via `maestro run --multi` with planner, scheduler, workers, reducers, and optional aggregator
- [x] SDLC discovery flow via `maestro discover` with 13 generated artifacts and brownfield support
- [x] Backward compatibility for legacy `maestro run` behavior across the existing regression suite

### Active Milestone (`v1.2`)

- [ ] Prevent planning artifact drift with an automated consistency gate across `ROADMAP.md`, `STATE.md`, milestone summaries, and scoped requirements
- [ ] Validate third-party provider installation end-to-end in an isolated environment through real `maestro.providers` entry-point discovery
- [ ] Add a release-grade Copilot smoke gate that exercises the real device-code login path and a live authenticated API call
- [ ] Add aggregator spend/rate guardrails so optional summary calls cannot run unbounded in unattended usage

### Out of Scope

- Recursive sub-planner expansion (`TD-02`) during this milestone
- Dynamic worker pool sizing or other broad runtime-optimization work
- Cross-worker in-memory communication
- Human-in-the-loop DAG approval before execution
- Persistent DAG state across CLI sessions
- GitHub Enterprise Copilot and token-refresh support
- Providers beyond GitHub Copilot and ChatGPT

## Context

- **Brownfield project**: core CLI, provider system, multi-agent runtime, and discovery pipeline are already shipped
- **Current baseline**: roadmap Phases 1-13 are complete and milestone `v1.1` closed planner hardening plus SDLC discovery
- **Next milestone**: `v1.2` is a hardening milestone focused on planning integrity, provider contract verification, Copilot release readiness, and aggregator runtime controls
- **Debt-driven scope**: the milestone explicitly pulls in TD-03, TD-04, TD-05, and TD-06 while leaving TD-02 deferred
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
| LangGraph Send API for parallel dispatch | Native LangGraph primitive for fan-out; avoids manual threading | Shipped |
| ProviderPlugin as Protocol (not ABC) | Structural typing keeps the third-party provider contract lightweight | Shipped |
| Workers reuse `_run_agentic_loop` unchanged | Maximizes reuse and minimizes regression risk | Shipped |
| Planner is a separate model call (not a graph node) | Keeps DAG generation isolated and testable | Shipped |
| Milestone `v1.2` prioritizes hardening over new product surface | The highest-value remaining work is reliability and release confidence, not more feature breadth | Active |

## Evolution

This document evolves at phase transitions and milestone boundaries.

**After each phase transition** (via `/gsd-transition`):
1. Requirements invalidated? -> Move to Out of Scope with reason
2. Requirements validated? -> Move to Validated with phase reference
3. New requirements emerged? -> Add to the active milestone scope
4. Decisions to log? -> Add to Key Decisions
5. "What This Is" still accurate? -> Update if drifted

**After each milestone** (via `/gsd-complete-milestone`):
1. Full review of all sections
2. Core Value check - still the right priority?
3. Audit Out of Scope - reasons still valid?
4. Update Context with current state

---
*Last updated: 2026-04-23 for milestone v1.2 initialization*
