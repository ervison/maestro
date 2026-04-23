# Milestone v1.1 - Project Summary

**Generated:** 2026-04-23  
**Purpose:** Team onboarding and project review

---

## 1. Overview

Maestro is a CLI-first AI engineering agent that evolved from a single-agent loop into a multi-agent execution engine with provider abstraction, DAG planning, dependency-aware parallel workers, and an optional aggregator. In this milestone window, the project also added a full SDLC discovery command that generates structured planning artifacts from a natural-language prompt.

Core value remains: `maestro run --multi "build a REST API with tests and docs"` decomposes work, executes specialized tasks in parallel, and returns a coherent result while preserving the legacy `maestro run` behavior.

Current milestone context:
- `gsd-sdk query init.progress` resolves active milestone as `v1.1`
- 13 phases discovered
- 13 phases marked `complete` in roadmap/state artifacts after the reconciliation pass

Primary artifacts used:
- `.planning/PROJECT.md`
- `.planning/ROADMAP.md`
- `.planning/REQUIREMENTS.md`
- `.planning/v1.0-MILESTONE-AUDIT.md`
- `.planning/phases/*/*SUMMARY.md`
- `.planning/phases/*/*VERIFICATION.md`
- `.planning/phases/*/*CONTEXT.md`
- `.planning/phases/02-multi-slot-auth-store/02-RESEARCH.md`

Missing but expected artifact:
- `.planning/RETROSPECTIVE.md` (not present)

## 2. Architecture

Major architecture decisions and why they were chosen:

- **Decision:** Provider abstraction via `ProviderPlugin` protocol and neutral message/tool types  
  **Why:** Decouples transport/auth/wire-format from orchestration and enables third-party providers via entry points.  
  **Phase:** 01, 03, 04

- **Decision:** Runtime provider discovery through `importlib.metadata` entry points and config-based model resolution chain  
  **Why:** Keeps providers pluggable and allows deterministic model selection (`--model` -> env -> config -> authenticated provider fallback).  
  **Phase:** 04

- **Decision:** Keep `_run_agentic_loop` as the execution primitive and delegate transport to `provider.stream()`  
  **Why:** Preserves backward compatibility and reduces migration risk while enabling multi-provider support.  
  **Phase:** 05

- **Decision:** Use LangGraph `StateGraph` + `Send` fan-out with reducer-backed shared state  
  **Why:** Safe parallel writes and deterministic DAG orchestration without manual thread/state synchronization.  
  **Phase:** 08, 10

- **Decision:** Separate planner, scheduler, worker, and aggregator responsibilities  
  **Why:** Clear boundaries improve testability, failure isolation, and phase-by-phase validation.  
  **Phase:** 09, 10, 11

- **Decision:** SDLC discovery as a dedicated command (`maestro discover`) with schema-driven artifact generation  
  **Why:** Expands product value from task execution into project discovery/planning without regressing run paths.  
  **Phase:** 13

## 3. Phases

| Phase | Name | Status | One-Liner |
|-------|------|--------|-----------|
| 01 | provider-plugin-protocol | complete | Defined provider protocol + neutral streaming types as the base contract. |
| 02 | multi-slot-auth-store | complete | Migrated auth to provider-keyed storage with compatibility shims and auth CLI transition path. |
| 03 | chatgpt-provider-migration | complete | Extracted ChatGPT HTTP/SSE logic into provider implementation and registered entry point. |
| 04 | provider-registry | complete | Added provider discovery, registry lookup, and model resolution pipeline. |
| 05 | agent-loop-refactor | complete | Switched loop transport to provider streaming while preserving behavior. |
| 06 | auth-model-cli-commands | complete | Delivered `auth login/logout/status` and `models` CLI surface with tests. |
| 07 | github-copilot-provider | complete | Implemented Copilot OAuth device flow and streaming provider support. |
| 08 | dag-state-types-domains | complete | Introduced reducer-safe state, planner schemas, validator, and domain prompts. |
| 09 | planner | complete | Implemented planner node with structured output validation and retry behavior. |
| 10 | scheduler-workers | complete | Implemented dependency-aware parallel dispatch with worker recursion/path guards. |
| 11 | aggregator-multi-agent-cli | complete | Added `--multi`, lifecycle events, and optional aggregator finalization. |
| 12 | dag-planner-hardening | complete | Hardened planner prompt with strict decomposition and reasoning guardrails. |
| 13 | sdlc-discovery-planner | complete | Added `maestro discover` to generate a 13-artifact SDLC package. |

## 4. Decisions

Key decision log consolidated from phase context artifacts:

- **D-02-P2:** Canonical auth path becomes `maestro auth login [provider]`, defaulting to `chatgpt`; legacy top-level login remains as deprecated alias.  
  **Phase:** 02  
  **Rationale:** Migrate safely to multi-provider auth without breaking existing user flows.

- **D-01-P4:** If model/provider is unspecified, prefer authenticated providers; if none authenticated, fall back to ChatGPT defaults.  
  **Phase:** 04  
  **Rationale:** Preserve legacy no-auth behavior while enabling provider-aware selection.

- **D-02-P5:** `_run_agentic_loop` must consume `provider.stream()` and stop owning direct HTTP/SSE transport.  
  **Phase:** 05  
  **Rationale:** Enforce provider boundary and keep core loop reusable.

- **D-STATE-P8:** `AgentState` uses reducer-backed fields (`Annotated[list, operator.add]`) and strict Pydantic planner schemas.  
  **Phase:** 08  
  **Rationale:** Prevent parallel state loss and reject malformed plan outputs early.

- **D-STRUCT-P9:** Planner attempts API-enforced JSON schema first, then fallback, always validating with `AgentPlan.model_validate_json()`.  
  **Phase:** 09  
  **Rationale:** Improve planner reliability while tolerating provider differences.

- **D-DISPATCH-P10:** Keep scheduler string routing and `Send` routing separated via a no-op dispatch node.  
  **Phase:** 10  
  **Rationale:** Avoid mixed return semantics and keep graph routing explicit/safe.

- **D-AGG-P11:** Aggregator runs by default and can be disabled (`--no-aggregate` or config); lifecycle events are explicit stdout prints.  
  **Phase:** 11  
  **Rationale:** Better UX visibility while allowing lightweight mode.

- **D-01..D-05-P12:** Planner hardening introduces strict MUST/MUST NOT language, anti-overdecomposition rebuttal table, independence criterion, and pre-JSON reasoning block.  
  **Phase:** 12  
  **Rationale:** Reduce fragmented DAGs and improve decision quality before scheduler dispatch.

## 5. Requirements

Requirement coverage synthesized from `REQUIREMENTS.md` + audit/verification evidence:

- ✅ **Met (audit-backed):** All non-optional v1 requirements are wired according to `.planning/v1.0-MILESTONE-AUDIT.md` final verdict (`passed`; 56 non-optional requirements wired).
- ⚠️ **Partially constrained by real-world validation:** `PROV-05` is implemented by entry-point architecture, but phase verification notes external pip-install validation as human-needed evidence.
- ⚠️ **Historical artifact drift:** `.planning/REQUIREMENTS.md` still contains many unchecked boxes despite later phase/audit artifacts demonstrating implementation.
- ❌ **Not implemented by design:** `WORK-06` recursive sub-planner remains deferred and explicitly optional.

Audit verdict reference:
- `.planning/v1.0-MILESTONE-AUDIT.md`: status `passed` after integration fixes; optional recursive worker planner deferred.

## 6. Tech Debt

Open debt and deferred items gathered from verification/context/audit artifacts:

- **TD-02 / WORK-06 (Deferred):** Recursive sub-planner call path is not implemented (optional requirement).
- **Planning consistency follow-up:** Keep `.planning/ROADMAP.md`, `.planning/STATE.md`, and milestone summaries aligned through the automated `maestro planning check` gate.
- **Verification nuance debt:** Some historical verification files reflect temporary failures that were fixed later; onboarding readers should prioritize latest summary + audit context.
- **Retrospective gap:** `.planning/RETROSPECTIVE.md` is absent, so lessons-learned and process improvements are under-documented.

## 7. Getting Started

For new contributors:

- **Run the project:**
  - `maestro run "<task>"` (single-agent)
  - `maestro run --multi "<task>"` (planner + parallel workers + optional aggregator)
  - `maestro discover "<project brief>"` (SDLC package generation)

- **Key directories:**
  - `maestro/` (runtime code)
  - `maestro/providers/` (provider implementations and registry contracts)
  - `maestro/planner/` (schemas, node, DAG validation)
  - `maestro/sdlc/` (discovery pipeline)
  - `tests/` (behavioral and integration coverage)
  - `.planning/phases/` (phase-level context, summaries, verification)

- **Tests:**
  - `python -m pytest tests/ -q --tb=no`

- **Where to look first:**
  - `maestro/cli.py` (entry points and command routing)
  - `maestro/agent.py` (single-agent loop)
  - `maestro/multi_agent.py` (DAG execution graph)
  - `maestro/planner/node.py` (plan generation and hardening logic)
  - `maestro/providers/registry.py` (provider/model resolution)

---

## Stats

- **Timeline:** 2026-04-17 -> 2026-04-23
- **Phases:** 13 complete / 13 total (per `.planning/ROADMAP.md` and `.planning/STATE.md`)
- **Commits in window:** 245 (fallback method: earliest phase commit date)
- **Diff shortstat:** 5332 files changed (+202283 / -629083)
- **Contributors:** Ervison Lima, ervison, copilot-swe-agent[bot]
- **Notes:** Stats computed via git fallback method because a direct `v1.1` tag was not found.
