# Roadmap: Maestro

## Overview

Maestro transformed from a single-agent CLI into a multi-agent parallel execution engine in Phases 1-13. The next milestone focuses on hardening the shipped system instead of adding a new product surface. Phases 14-17 (milestone `v1.2`) convert the highest-priority debt items into planned work: planning artifact integrity, external provider install validation, Copilot release readiness, and aggregator runtime guardrails.

## Phases

**Phase Numbering:**
- Integer phases (1, 2, 3): Planned milestone work
- Decimal phases (2.1, 2.2): Urgent insertions (marked with INSERTED)

Decimal phases appear between their surrounding integers in numeric order.

- [x] **Phase 1: Provider Plugin Protocol** - Define the ProviderPlugin Protocol and neutral streaming types ✅ COMPLETE (2026-04-17)
- [x] **Phase 2: Multi-Slot Auth Store** - Refactor auth to per-provider storage with backward compatibility ✅ COMPLETE (2026-04-17)
- [x] **Phase 3: ChatGPT Provider Migration** - Move existing HTTP/SSE logic into ChatGPTProvider
- [x] **Phase 4: Config & Provider Registry** - Runtime discovery, model resolution, and provider registry ✅ COMPLETE (2026-04-18)
- [x] **Phase 5: Agent Loop Refactor** - Wire provider.stream() into the agentic loop with zero regressions ✅ COMPLETE (2026-04-18)
- [x] **Phase 6: Auth & Model CLI Commands** - Expose auth management and model discovery to users ✅ COMPLETE (2026-04-18)
- [x] **Phase 7: GitHub Copilot Provider** - Second provider with device code OAuth ✅ COMPLETE (2026-04-18)
- [x] **Phase 8: DAG State, Types & Domains** - Multi-agent type system and domain prompt definitions ✅ COMPLETE (2026-04-18)
- [x] **Phase 9: Planner** - LLM-driven DAG generation with structured output validation ✅ COMPLETE (2026-04-18)
- [x] **Phase 10: Scheduler & Workers** - Parallel execution engine with dependency dispatch and recursion guards ✅ COMPLETE (2026-04-19)
- [x] **Phase 11: Aggregator & Multi-Agent CLI** - Final summary pass and `--multi` flag integration ✅ COMPLETE (2026-04-19)
- [x] **Phase 12: DAG Planner Hardening** - Harden planner decomposition rules and prompt compliance ✅ COMPLETE (2026-04-21)
- [x] **Phase 13: SDLC Discovery Planner** - `maestro discover` generates 13-artifact specification packages ✅ COMPLETE (2026-04-22)
- [ ] **Phase 14: Planning Consistency Gate** - Enforce automated alignment checks across roadmap, state, and milestone artifacts
- [ ] **Phase 15: External Provider Install Smoke Test** - Verify third-party `maestro.providers` packages in an isolated install path
- [ ] **Phase 16: Copilot Release Smoke Gate** - Add a release-grade real-auth smoke check for GitHub Copilot
- [ ] **Phase 17: Aggregator Guardrails** - Bound optional aggregator spend and rate behavior in unattended runs

## Phase Details

### Phase 1: Provider Plugin Protocol ✅ COMPLETE
**Goal**: Developers can define a new provider by implementing a typed Protocol with neutral streaming types
**Depends on**: Nothing (first phase)
**Requirements**: PROV-01, PROV-06
**Success Criteria** (what must be TRUE):
  1. `ProviderPlugin` Protocol is importable from `maestro.providers.base` with all required methods (id, name, list_models, stream, auth_required, login, is_authenticated)
  2. `Message`, `Tool`, `ToolCall` neutral types are importable and carry all fields needed for provider-neutral communication
  3. A test class implementing the Protocol passes runtime `isinstance()` check
**Plans**: 1 plan (COMPLETE)

**Artifacts**:
  - `.planning/phases/01-provider-plugin-protocol/01-01-SUMMARY.md`
  - `.planning/phases/01-provider-plugin-protocol/01-VERIFICATION.md`

Plans:
- [x] 01-01-PLAN.md — Define ProviderPlugin Protocol and neutral types (Message, Tool, ToolCall, ToolResult)

### Phase 2: Multi-Slot Auth Store ✅ COMPLETE
**Goal**: Credentials are stored per-provider in a dedicated auth file with a clean public API
**Depends on**: Phase 1
**Requirements**: AUTH-01, AUTH-02, AUTH-08
**Success Criteria** (what must be TRUE):
  1. `auth.set("chatgpt", data)` and `auth.get("chatgpt")` round-trip credentials correctly
  2. `~/.maestro/auth.json` is created with file mode `0o600` on first write
  3. Existing `maestro auth login` (no provider arg) shows deprecation warning and routes to `maestro auth login chatgpt`
  4. `auth.all_providers()` returns a list of provider IDs with stored credentials
**Plans**: 3 plans (COMPLETE)

**Artifacts**:
  - `.planning/phases/02-multi-slot-auth-store/02-01-SUMMARY.md`
  - `.planning/phases/02-multi-slot-auth-store/02-02-SUMMARY.md`
  - `.planning/phases/02-multi-slot-auth-store/02-03-SUMMARY.md`
  - `.planning/phases/02-multi-slot-auth-store/02-VERIFICATION.md`

Plans:
- [x] 02-01-PLAN.md — Define Phase 2 auth-store acceptance tests and CLI migration constraints
- [x] 02-02-PLAN.md — Implement provider-keyed auth store, secure writes, migration, and compatibility shims
- [x] 02-03-PLAN.md — Add canonical `maestro auth login [provider]` CLI path and deprecation behavior

### Phase 3: ChatGPT Provider Migration ✅ COMPLETE
**Goal**: Existing ChatGPT HTTP/SSE logic is encapsulated in a provider class implementing the Protocol
**Depends on**: Phase 1, Phase 2
**Requirements**: PROV-03, LOOP-04
**Success Criteria** (what must be TRUE):
  1. ✅ `ChatGPTProvider` class exists in `maestro.providers.chatgpt` and implements the full `ProviderPlugin` Protocol
  2. ✅ All ChatGPT-specific SSE parsing and HTTP connection logic is moved from `agent.py` to `providers/chatgpt.py`
  3. ✅ ChatGPT provider is registered in `pyproject.toml` entry points under `maestro.providers` group
  4. ✅ A backward-compat re-export shim exists in `auth.py` for any imported `TokenSet` references
**Plans**: 1 plan (COMPLETE)
**Artifacts**:
  - `maestro/providers/chatgpt.py` (331 lines) - ChatGPTProvider implementation
  - `tests/test_chatgpt_provider.py` (374 lines) - 28 tests
  - 6 commits, 102 total tests passing

Plans:
- [x] 03-01-PLAN.md — Create ChatGPTProvider with HTTP/SSE logic, register entry point, add backward-compat shims

### Phase 4: Config & Provider Registry ✅ COMPLETE
**Goal**: Providers are discovered at runtime via entry points and models are resolved through a priority chain
**Depends on**: Phase 1, Phase 3
**Requirements**: PROV-02, PROV-04, PROV-05, CONF-01, CONF-02, CONF-05
**Success Criteria** (what must be TRUE):
  1. ✅ `get_provider("chatgpt")` returns the ChatGPT provider instance via `importlib.metadata` entry point discovery
  2. ✅ `get_provider("nonexistent")` raises `ValueError` with a list of available provider IDs
  3. ✅ `resolve_model()` follows the priority chain: `--model` flag → `MAESTRO_MODEL` env → `config.agent.<name>.model` → `config.model` → first model of first authenticated provider
  4. ✅ Model string `"provider_id/model_id"` format is validated; invalid format raises `ValueError` with guidance message
  5. ✅ Absent `~/.maestro/config.json` falls back gracefully to ChatGPT as default provider
**Plans**: 1 plan (COMPLETE)
**Artifacts**:
  - `.planning/phases/04-provider-registry/04-01-SUMMARY.md`
  - `.planning/phases/04-provider-registry/04-SHIP.md`

Plans:
- [x] 04-01-PLAN.md — Provider registry discovery and config-driven model resolution

### Phase 5: Agent Loop Refactor
**Goal**: The agentic loop delegates all HTTP communication to the provider abstraction with zero regressions
**Depends on**: Phase 3, Phase 4
**Requirements**: LOOP-01, LOOP-02, LOOP-03
**Success Criteria** (what must be TRUE):
  1. `_run_agentic_loop` calls `provider.stream()` instead of direct `httpx.stream()` calls — HTTP layer is fully provider-delegated
  2. Unauthenticated provider raises `RuntimeError` with actionable message: "Run `maestro auth login <provider_id>`"
  3. All 26 existing tests pass without any modification after the refactor
  4. `maestro run "task"` behaves identically to pre-refactor single-agent behavior
**Plans**: 1 plan

Plans:
- [x] 05-01-PLAN.md — Refactor _run_agentic_loop to use provider.stream() with zero regressions

### Phase 6: Auth & Model CLI Commands ✅ COMPLETE
**Goal**: Users can manage authentication and discover models through CLI subcommands
**Depends on**: Phase 2, Phase 4
**Requirements**: AUTH-03, AUTH-05, AUTH-06, CONF-03, CONF-04
**Success Criteria** (what must be TRUE):
  1. ✅ `maestro auth login chatgpt` authenticates and stores credentials for the ChatGPT provider
  2. ✅ `maestro auth logout chatgpt` removes stored credentials for a specific provider
  3. ✅ `maestro auth status` shows all providers and their authentication state (authenticated/not authenticated)
  4. ✅ `maestro models` lists available models from all authenticated providers
  5. ✅ `maestro run --model github-copilot/gpt-4o "task"` resolves and uses the specified provider/model
**Plans**: 1 plan (COMPLETE)
**Artifacts**:
  - `maestro/cli.py` (+98/-31 lines) — Auth and models subcommands
  - `tests/test_cli_auth.py` (170 lines, 11 tests) — Auth CLI tests
  - `tests/test_cli_models.py` (132 lines, 8 tests) — Models CLI tests
  - 6 commits, 225 total tests passing

Plans:
- [x] 06-01-PLAN.md — Add auth login/logout/status and models CLI subcommands with multi-provider support

### Phase 7: GitHub Copilot Provider ✅ COMPLETE
**Goal**: Users can authenticate with GitHub Copilot via device code OAuth and use it as an alternative provider
**Depends on**: Phase 1, Phase 2, Phase 4
**Requirements**: COPILOT-01, COPILOT-02, COPILOT-03, COPILOT-04, COPILOT-05, AUTH-04, AUTH-07
**Success Criteria** (what must be TRUE):
  1. `maestro auth login github-copilot` initiates the device code OAuth flow, displays the code + URL, and stores the resulting token
  2. `CopilotProvider.stream()` sends requests to `https://api.githubcopilot.com/chat/completions` with required headers (`Authorization`, `x-initiator`, `Openai-Intent`)
  3. Neutral `Tool`/`Message` types are converted to OpenAI-compatible wire format on send and parsed back on receive
  4. `slow_down` OAuth error increments the polling interval by 5 seconds (not ignored); `authorization_pending` continues at current interval
  5. `maestro models --provider github-copilot` lists available Copilot model IDs
  6. `is_authenticated()` returns `False` when no Copilot token is stored
**Plans**: 1 plan (COMPLETE)

**Artifacts**:
  - `.planning/phases/07-github-copilot-provider/07-01-SUMMARY.md`
  - `.planning/phases/07-github-copilot-provider/07-VERIFICATION.md`
  - `.planning/phases/07-github-copilot-provider/07-REVIEW-FIX.md`

Plans:
- [x] 07-01-PLAN.md — Create CopilotProvider with OAuth device code flow, wire format conversion, and comprehensive tests

### Phase 8: DAG State, Types & Domains ✅ COMPLETE
**Goal**: The multi-agent type system and domain specialization prompts are defined and independently validated
**Depends on**: Phase 5 (provider infrastructure stable)
**Requirements**: STATE-01, STATE-02, STATE-03, STATE-04, DOM-01, DOM-02, DOM-03, DOM-04
**Success Criteria** (what must be TRUE):
  1. ✅ `AgentState` TypedDict uses `Annotated[list, operator.add]` reducers for `completed` and `errors`, and a dict merge reducer for `outputs` — safe for parallel writes with no silent data loss
  2. ✅ `PlanTask` and `AgentPlan` Pydantic models validate structure: `id`, `domain`, `prompt`, `deps` fields accept valid JSON and reject missing/invalid fields
  3. ✅ DAG validator rejects cycles (via `graphlib.TopologicalSorter`) and invalid dependency references before any dispatch
  4. ✅ `maestro/domains.py` defines 7 built-in domains (backend, testing, docs, devops, data, security, general) with specialized system prompts
  5. ✅ Unrecognized domain values fall back to the `general` domain without error
**Plans**: 2 plans (COMPLETE)
**Artifacts**:
  - `.planning/phases/08-dag-state-types-domains/08-01-SUMMARY.md`
  - `.planning/phases/08-dag-state-types-domains/08-02-SUMMARY.md`

Plans:
- [x] 08-01-PLAN.md — AgentState TypedDict with reducers, PlanTask/AgentPlan Pydantic schemas, DAG validator
- [x] 08-02-PLAN.md — Domain system with 6 built-in domains and fallback behavior

### Phase 9: Planner ✅ COMPLETE
**Goal**: The planner node generates a validated task DAG from a user prompt via LLM structured output
**Depends on**: Phase 5, Phase 8
**Requirements**: PLAN-01, PLAN-02, PLAN-03, PLAN-04
**Success Criteria** (what must be TRUE):
  1. ✅ Planner receives a user task string and returns a valid `AgentPlan` JSON via LLM structured output
  2. ✅ Planner output is validated by `AgentPlan.model_validate_json()` — invalid output is rejected and not passed to the scheduler
  3. ✅ Planner uses a configurable model (via `config.agent.planner.model`), separate from worker models
  4. ✅ Planner system prompt produces atomic tasks with domain assignments and avoids over-decomposition
**Plans**: 1 plan (COMPLETE)
**Artifacts**:
  - `.planning/phases/09-planner/09-01-SUMMARY.md`

Plans:
- [x] 09-01-PLAN.md — Implement planner node with structured output validation and retry logic

### Phase 10: Scheduler & Workers ✅ COMPLETE
**Goal**: Tasks execute in parallel respecting dependencies with domain-specialized agents and recursion safety
**Depends on**: Phase 8, Phase 9
**Requirements**: SCHED-01, SCHED-02, SCHED-03, SCHED-04, WORK-01, WORK-02, WORK-03, WORK-04, WORK-05, WORK-06, WORK-07, WORK-08
**Success Criteria** (what must be TRUE):
  1. ✅ Scheduler dispatches ready tasks (no unmet dependencies) in parallel via LangGraph `Send` API
  2. ✅ After a batch completes, scheduler re-evaluates newly unblocked tasks and dispatches the next batch — repeats until all DAG tasks are complete
  3. ✅ Each Worker runs `_run_agentic_loop` with a domain-specialized system prompt from `domains.py`
  4. ✅ Path guard (workdir containment) is enforced inside every Worker — attempting a write outside workdir is blocked
  5. ✅ Worker errors are collected in `AgentState.errors` (non-fatal) and independent tasks continue executing
  6. ✅ `depth` is a required argument (no default); Workers at `max_depth` cannot recurse further (default max_depth=2)
  7. ✅ Worker output and task ID are appended to shared `AgentState` via reducers — a 2-worker test confirms both outputs are present (no silent last-write-wins)
**Plans**: 1 plan (COMPLETE)
**Artifacts**:
  - `.planning/phases/10-scheduler-workers/10-01-SUMMARY.md`
  - `maestro/multi_agent.py` (388 lines) — scheduler, dispatch, worker nodes, compiled graph
  - `tests/test_scheduler_workers.py` (712 lines, 23 tests)
  - 53 Phase 10 tests passing, 3 commits

Plans:
- [x] 10-01-PLAN.md — Scheduler & Workers implementation with parallel DAG execution

### Phase 11: Aggregator & Multi-Agent CLI ✅ COMPLETE
**Goal**: Users activate multi-agent mode via CLI and optionally receive a final aggregated summary
**Depends on**: Phase 10
**Requirements**: AGG-01, AGG-02, CLI-01, CLI-02, CLI-03, CLI-04
**Success Criteria** (what must be TRUE):
  1. ✅ `maestro run --multi "task"` activates the full DAG pipeline (planner → scheduler → workers → aggregator)
  2. ✅ Without `--multi`, `maestro run` behaves identically to current single-agent behavior (zero regressions)
  3. ✅ `--auto` and `--workdir` flags pass through from CLI to all workers
  4. ✅ Lifecycle events (planner done, worker started, worker done) print to stdout during `--multi` execution
  5. ✅ Aggregator runs after all workers complete and produces a final summary (optional, configurable)
**Plans**: 1 plan (COMPLETE)
**Artifacts**:
  - `.planning/phases/11-aggregator-multi-agent-cli/11-01-SUMMARY.md`
  - `maestro/multi_agent.py` - aggregator_node + lifecycle events
  - `maestro/cli.py` - --multi and --no-aggregate flags
  - 15 new tests, 341 total passing

Plans:
- [x] 11-01-PLAN.md — CLI --multi flag, aggregator node, lifecycle events, and comprehensive tests

### Phase 12: DAG Planner Hardening ✅ COMPLETE
**Goal**: The planner prompt uses strict decomposition rules that reduce over-splitting and improve DAG quality
**Depends on**: Phase 11
**Requirements**: PLAN-01, PLAN-03, PLAN-04
**Success Criteria** (what must be TRUE):
  1. ✅ `PLANNER_SYSTEM_PROMPT` uses MUST/MUST NOT language instead of soft guidance
  2. ✅ Prompt includes an explicit task-independence rule and rationalization table to reduce over-decomposition
  3. ✅ Planner safely strips the required pre-JSON `<reasoning>` block before `AgentPlan.model_validate_json()`
  4. ✅ Prompt-content and planner-node regression tests cover the new hardening behavior
**Plans**: 1 plan (COMPLETE)
**Artifacts**:
  - `.planning/phases/12-dag-planner-hardening/12-01-SUMMARY.md`
  - `.planning/phases/12-dag-planner-hardening/12-VERIFICATION.md`

Plans:
- [x] 12-01-PLAN.md — Harden planner prompt authority rules and add regression coverage

### Phase 13: SDLC Discovery Planner ✅ COMPLETE
**Goal**: `maestro discover "<prompt>"` generates a complete 13-artifact specification package
**Depends on**: Phase 11
**Requirements**: SDLC-01 through SDLC-09
**Success Criteria** (what must be TRUE):
  1. ✅ `maestro discover "Crie um cadastro de imóveis"` produces 13 artifact files in `./spec/`
  2. ✅ All 13 artifact types generated: briefing, hypotheses, gaps, PRD, functional spec, business rules, acceptance criteria, UX spec, API contracts, data model, auth matrix, ADRs, test plan
  3. ✅ Hypotheses marked [HYPOTHESIS], gaps marked [GAP] — planner never invents facts
  4. ✅ Brownfield mode enabled via `--brownfield` flag (opt-in only, not automatic)
  5. ✅ `maestro run` and `maestro run --multi` completely unaffected (zero regressions)
**Plans**: 4 plans (COMPLETE)
**Artifacts**:
  - `maestro/sdlc/__init__.py` — package exports
  - `maestro/sdlc/schemas.py` — ArtifactType enum, SDLCRequest, SDLCArtifact, DiscoveryResult
  - `maestro/sdlc/harness.py` — DiscoveryHarness orchestrator
  - `maestro/sdlc/generators.py` — LLM artifact generation dispatch
  - `maestro/sdlc/prompts.py` — 13 system prompts
  - `maestro/sdlc/writer.py` — spec/ filesystem writer
  - `maestro/cli.py` — `discover` subcommand
  - 41 new tests (444 total, zero regressions)

Plans:
- [x] 13-01-PLAN.md — Schemas, ArtifactType enum, DiscoveryHarness skeleton
- [x] 13-02-PLAN.md — 13 artifact generators and system prompts
- [x] 13-03-PLAN.md — Writer module and brownfield detection
- [x] 13-04-PLAN.md — `maestro discover` CLI subcommand

### Phase 14: Planning Consistency Gate
**Goal**: Planning artifacts fail fast when roadmap, state, summary, and scoped milestone requirements drift out of sync
**Depends on**: Phase 13
**Requirements**: META-01, META-02, META-03
**Success Criteria** (what must be TRUE):
  1. Repository verification fails when `.planning/ROADMAP.md`, `.planning/STATE.md`, the active milestone summary, or referenced phase evidence drift out of alignment.
  2. The consistency gate runs in normal automated verification for the repository.
  3. Milestone workflow documentation points future updates through the same gate.
**Plans**: 0 plans (ready for planning)

### Phase 15: External Provider Install Smoke Test
**Goal**: Maestro proves the third-party provider contract through a real isolated install path instead of only local/static evidence
**Depends on**: Phase 4
**Requirements**: PLUGIN-01, PLUGIN-02, PLUGIN-03
**Success Criteria** (what must be TRUE):
  1. A minimal third-party provider package can be installed in an isolated environment without editing Maestro source.
  2. Maestro discovers the installed package through the `maestro.providers` entry-point group at runtime.
  3. The smoke path is repeatable in automation and does not mutate a developer's global environment.
**Plans**: 0 plans (ready for planning)

### Phase 16: Copilot Release Smoke Gate
**Goal**: The most user-sensitive provider path has a release-grade real-world verification gate
**Depends on**: Phase 7, Phase 15
**Requirements**: COP-SMOKE-01, COP-SMOKE-02, COP-SMOKE-03
**Success Criteria** (what must be TRUE):
  1. The smoke gate exercises the real GitHub Copilot device-code login path.
  2. The same path verifies at least one live authenticated Copilot API request.
  3. The gate is explicitly skippable when credentials, a real account, or network access are unavailable.
**Plans**: 0 plans (ready for planning)

### Phase 17: Aggregator Guardrails
**Goal**: Optional aggregator LLM calls stay bounded by explicit runtime policy
**Depends on**: Phase 11
**Requirements**: AGG-GUARD-01, AGG-GUARD-02, AGG-GUARD-03, AGG-GUARD-04
**Success Criteria** (what must be TRUE):
  1. Aggregator calls are protected by explicit spend or call-count guardrails.
  2. Repeated aggregation attempts are bounded during unattended usage.
  3. The CLI explains when aggregation is blocked or skipped by policy.
  4. Automated tests cover the allow, block, and skip paths.
**Plans**: 0 plans (ready for planning)

## Progress

**Execution Order:**
Phases execute in numeric order: 1 → 2 → 3 → 4 → 5 → 6 → 7 → 8 → 9 → 10 → 11 → 12 → 13 → 14 → 15 → 16 → 17

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Provider Plugin Protocol | 1/1 | Complete | 2026-04-17 |
| 2. Multi-Slot Auth Store | 3/3 | Complete | 2026-04-17 |
| 3. ChatGPT Provider Migration | 1/1 | Complete   | 2026-04-17 |
| 4. Config & Provider Registry | 1/1 | Complete | 2026-04-18 |
| 5. Agent Loop Refactor | 1/1 | Complete | 2026-04-18 |
| 6. Auth & Model CLI Commands | 1/1 | Complete | 2026-04-18 |
| 7. GitHub Copilot Provider | 1/1 | Complete | 2026-04-18 |
| 8. DAG State, Types & Domains | 2/2 | Complete | 2026-04-18 |
| 9. Planner | 1/1 | Complete | 2026-04-18 |
| 10. Scheduler & Workers | 1/1 | Complete | 2026-04-19 |
| 11. Aggregator & Multi-Agent CLI | 1/1 | Complete | 2026-04-19 |
| 12. DAG Planner Hardening | 1/1 | Complete | 2026-04-21 |
| 13. SDLC Discovery Planner | 4/4 | Complete | 2026-04-22 |
| 14. Planning Consistency Gate | 0/0 | Planned | - |
| 15. External Provider Install Smoke Test | 0/0 | Planned | - |
| 16. Copilot Release Smoke Gate | 0/0 | Planned | - |
| 17. Aggregator Guardrails | 0/0 | Planned | - |
