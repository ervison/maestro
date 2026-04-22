# Roadmap: Maestro

## Overview

Maestro transforms from a single-agent CLI into a multi-agent parallel execution engine. The journey builds bottom-up: first establish the provider plugin system (so every component speaks a neutral interface), then refactor the agent loop onto that abstraction, then layer the multi-agent DAG orchestrator on top. Every phase delivers a coherent, testable capability. Phases 1–7 establish multi-provider infrastructure; phases 8–11 build the multi-agent DAG engine. Phases 12–13 (milestone v1.1) harden the planner and introduce the SDLC Discovery Planner.

## Phases

**Phase Numbering:**
- Integer phases (1, 2, 3): Planned milestone work
- Decimal phases (2.1, 2.2): Urgent insertions (marked with INSERTED)

Decimal phases appear between their surrounding integers in numeric order.

- [ ] **Phase 1: Provider Plugin Protocol** - Define the ProviderPlugin Protocol and neutral streaming types
- [ ] **Phase 2: Multi-Slot Auth Store** - Refactor auth to per-provider storage with backward compatibility
- [x] **Phase 3: ChatGPT Provider Migration** - Move existing HTTP/SSE logic into ChatGPTProvider
- [x] **Phase 4: Config & Provider Registry** - Runtime discovery, model resolution, and provider registry ✅ COMPLETE (2026-04-18)
- [x] **Phase 5: Agent Loop Refactor** - Wire provider.stream() into the agentic loop with zero regressions ✅ COMPLETE (2026-04-18)
- [x] **Phase 6: Auth & Model CLI Commands** - Expose auth management and model discovery to users ✅ COMPLETE (2026-04-18)
- [ ] **Phase 7: GitHub Copilot Provider** - Second provider with device code OAuth
- [x] **Phase 8: DAG State, Types & Domains** - Multi-agent type system and domain prompt definitions ✅ COMPLETE (2026-04-18)
- [x] **Phase 9: Planner** - LLM-driven DAG generation with structured output validation ✅ COMPLETE (2026-04-18)
- [x] **Phase 10: Scheduler & Workers** - Parallel execution engine with dependency dispatch and recursion guards ✅ COMPLETE (2026-04-19)
- [x] **Phase 11: Aggregator & Multi-Agent CLI** - Final summary pass and `--multi` flag integration ✅ COMPLETE (2026-04-19)
- [ ] **Phase 12: DAG Planner Hardening** *(v1.1)* - Strengthen PLANNER_SYSTEM_PROMPT with authority language, rationalization table, independence test, and commitment device
- [ ] **Phase 13: SDLC Discovery Planner** *(v1.1)* - New planner agent that transforms vague product requests into a full specification package (PRD, API contracts, data model, etc.)

## Phase Details

### Phase 1: Provider Plugin Protocol
**Goal**: Developers can define a new provider by implementing a typed Protocol with neutral streaming types
**Depends on**: Nothing (first phase)
**Requirements**: PROV-01, PROV-06
**Success Criteria** (what must be TRUE):
  1. `ProviderPlugin` Protocol is importable from `maestro.providers.base` with all required methods (id, name, list_models, stream, auth_required, login, is_authenticated)
  2. `Message`, `Tool`, `ToolCall` neutral types are importable and carry all fields needed for provider-neutral communication
  3. A test class implementing the Protocol passes runtime `isinstance()` check
**Plans**: 1 plan

Plans:
- [x] 01-01-PLAN.md — Define ProviderPlugin Protocol and neutral types (Message, Tool, ToolCall, ToolResult)

### Phase 2: Multi-Slot Auth Store
**Goal**: Credentials are stored per-provider in a dedicated auth file with a clean public API
**Depends on**: Phase 1
**Requirements**: AUTH-01, AUTH-02, AUTH-08
**Success Criteria** (what must be TRUE):
  1. `auth.set("chatgpt", data)` and `auth.get("chatgpt")` round-trip credentials correctly
  2. `~/.maestro/auth.json` is created with file mode `0o600` on first write
  3. Existing `maestro auth login` (no provider arg) shows deprecation warning and routes to `maestro auth login chatgpt`
  4. `auth.all_providers()` returns a list of provider IDs with stored credentials
**Plans**: TBD

Plans:
- [ ] 02-01: TBD

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

### Phase 7: GitHub Copilot Provider
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
**Plans**: 1 plan

Plans:
- [ ] 07-01-PLAN.md — Create CopilotProvider with OAuth device code flow, wire format conversion, and comprehensive tests

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

### Phase 12: DAG Planner Hardening *(v1.1)*
**Goal**: The planner prompt is engineered to resist rationalization, enforce independence discipline, and produce tighter DAGs with non-negotiable authority framing
**Depends on**: Phase 9 (Planner)
**Requirements**: PLAN-05, PLAN-06, PLAN-07, PLAN-08
**Success Criteria** (what must be TRUE):
  1. `PLANNER_SYSTEM_PROMPT` uses MUST/non-negotiable framing throughout — no suggestion-style language ("prefer", "try")
  2. A rationalization table (excuse → rebuttal) is embedded in the prompt for the top 5 over-decomposition patterns
  3. An explicit independence test is stated: a subtask is independent only if its result does not change based on another subtask's result
  4. A commitment device is present: planner must declare its reasoning before producing the JSON output
  5. Unit tests verify prompt contains required elements and planner output respects independence criterion
  6. All existing 341+ tests continue to pass (zero regressions)
**Plans**: 1 plan

Plans:
- [ ] 12-01-PLAN.md — Rewrite PLANNER_SYSTEM_PROMPT with authority language, rationalization table, independence test, commitment device, and tests

### Phase 13: SDLC Discovery Planner *(v1.1)*
**Goal**: A new agent transforms vague product requests into a complete specification package before any code execution
**Depends on**: Phase 12
**Requirements**: SDLC-01 through SDLC-12
**Success Criteria** (what must be TRUE):
  1. `maestro discover "Crie um cadastro de imóveis"` triggers the SDLC planner pipeline
  2. SDLC planner produces all 13 artifacts: briefing, hipóteses, lacunas, PRD, especificação funcional, regras de negócio, critérios de aceitação, UX/UI, contratos de API, modelo de dados, matriz de autorização, ADRs, plano de testes, definition of done, execution pack
  3. Planner never invents — facts, hypotheses, and gaps are explicitly separated in every artifact
  4. Brownfield mode detects existing code structures via codebase scan before spec generation
  5. Subagents are specialized per artifact domain (discovery-analyst, product-requirements-writer, api-contract-designer, etc.)
  6. Output is written to `<workdir>/spec/` directory with numbered filenames
  7. Existing `maestro run` and `maestro run --multi` behaviors are completely unaffected
**Plans**: TBD

Plans:
- [ ] 13-01-PLAN.md — SDLC Planner architecture, schemas, and harness
- [ ] 13-02-PLAN.md — Artifact generation subagents (discovery, PRD, functional spec, business rules)
- [ ] 13-03-PLAN.md — Artifact generation subagents (API contracts, data model, authorization, UX spec)
- [ ] 13-04-PLAN.md — CLI integration, brownfield mode, and end-to-end tests

## Progress

**Execution Order:**
Phases execute in numeric order: 1 → 2 → 3 → 4 → 5 → 6 → 7 → 8 → 9 → 10 → 11 → 12 → 13

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Provider Plugin Protocol | 0/? | Not started | - |
| 2. Multi-Slot Auth Store | 0/? | Not started | - |
| 3. ChatGPT Provider Migration | 1/1 | Complete   | 2026-04-17 |
| 4. Config & Provider Registry | 1/1 | Complete | 2026-04-18 |
| 5. Agent Loop Refactor | 1/1 | Complete | 2026-04-18 |
| 6. Auth & Model CLI Commands | 1/1 | Complete | 2026-04-18 |
| 7. GitHub Copilot Provider | 0/? | Not started | - |
| 8. DAG State, Types & Domains | 2/2 | Complete | 2026-04-18 |
| 9. Planner | 1/1 | Complete | 2026-04-18 |
| 10. Scheduler & Workers | 1/1 | Complete | 2026-04-19 |
| 11. Aggregator & Multi-Agent CLI | 1/1 | Complete | 2026-04-19 |
| 12. DAG Planner Hardening *(v1.1)* | 0/1 | Not started | - |
| 13. SDLC Discovery Planner *(v1.1)* | 0/4 | Not started | - |
