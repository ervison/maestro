# Roadmap: Maestro

## Overview

Maestro transforms from a single-agent CLI into a multi-agent parallel execution engine. The journey builds bottom-up: first establish the provider plugin system (so every component speaks a neutral interface), then refactor the agent loop onto that abstraction, then layer the multi-agent DAG orchestrator on top. Every phase delivers a coherent, testable capability. Phases 1–7 establish multi-provider infrastructure; phases 8–11 build the multi-agent DAG engine.

## Phases

**Phase Numbering:**
- Integer phases (1, 2, 3): Planned milestone work
- Decimal phases (2.1, 2.2): Urgent insertions (marked with INSERTED)

Decimal phases appear between their surrounding integers in numeric order.

- [ ] **Phase 1: Provider Plugin Protocol** - Define the ProviderPlugin Protocol and neutral streaming types
- [ ] **Phase 2: Multi-Slot Auth Store** - Refactor auth to per-provider storage with backward compatibility
- [ ] **Phase 3: ChatGPT Provider Migration** - Move existing HTTP/SSE logic into ChatGPTProvider
- [ ] **Phase 4: Config & Provider Registry** - Runtime discovery, model resolution, and provider registry
- [ ] **Phase 5: Agent Loop Refactor** - Wire provider.stream() into the agentic loop with zero regressions
- [ ] **Phase 6: Auth & Model CLI Commands** - Expose auth management and model discovery to users
- [ ] **Phase 7: GitHub Copilot Provider** - Second provider with device code OAuth
- [ ] **Phase 8: DAG State, Types & Domains** - Multi-agent type system and domain prompt definitions
- [ ] **Phase 9: Planner** - LLM-driven DAG generation with structured output validation
- [ ] **Phase 10: Scheduler & Workers** - Parallel execution engine with dependency dispatch and recursion guards
- [ ] **Phase 11: Aggregator & Multi-Agent CLI** - Final summary pass and `--multi` flag integration

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

### Phase 3: ChatGPT Provider Migration
**Goal**: Existing ChatGPT HTTP/SSE logic is encapsulated in a provider class implementing the Protocol
**Depends on**: Phase 1, Phase 2
**Requirements**: PROV-03, LOOP-04
**Success Criteria** (what must be TRUE):
  1. `ChatGPTProvider` class exists in `maestro.providers.chatgpt` and implements the full `ProviderPlugin` Protocol
  2. All ChatGPT-specific SSE parsing and HTTP connection logic is moved from `agent.py` to `providers/chatgpt.py`
  3. ChatGPT provider is registered in `pyproject.toml` entry points under `maestro.providers` group
  4. A backward-compat re-export shim exists in `auth.py` for any imported `TokenSet` references
**Plans**: 1 plan

Plans:
- [ ] 03-01-PLAN.md — Create ChatGPTProvider with HTTP/SSE logic, register entry point, add backward-compat shims

### Phase 4: Config & Provider Registry
**Goal**: Providers are discovered at runtime via entry points and models are resolved through a priority chain
**Depends on**: Phase 1, Phase 3
**Requirements**: PROV-02, PROV-04, PROV-05, CONF-01, CONF-02, CONF-05
**Success Criteria** (what must be TRUE):
  1. `get_provider("chatgpt")` returns the ChatGPT provider instance via `importlib.metadata` entry point discovery
  2. `get_provider("nonexistent")` raises `ValueError` with a list of available provider IDs
  3. `resolve_model()` follows the priority chain: `--model` flag → `MAESTRO_MODEL` env → `config.agent.<name>.model` → `config.model` → first model of first authenticated provider
  4. Model string `"provider_id/model_id"` format is validated; invalid format raises `ValueError` with guidance message
  5. Absent `~/.maestro/config.json` falls back gracefully to ChatGPT as default provider
**Plans**: TBD

Plans:
- [ ] 04-01: TBD

### Phase 5: Agent Loop Refactor
**Goal**: The agentic loop delegates all HTTP communication to the provider abstraction with zero regressions
**Depends on**: Phase 3, Phase 4
**Requirements**: LOOP-01, LOOP-02, LOOP-03
**Success Criteria** (what must be TRUE):
  1. `_run_agentic_loop` calls `provider.stream()` instead of direct `httpx.stream()` calls — HTTP layer is fully provider-delegated
  2. Unauthenticated provider raises `RuntimeError` with actionable message: "Run `maestro auth login <provider_id>`"
  3. All 26 existing tests pass without any modification after the refactor
  4. `maestro run "task"` behaves identically to pre-refactor single-agent behavior
**Plans**: TBD

Plans:
- [ ] 05-01: TBD

### Phase 6: Auth & Model CLI Commands
**Goal**: Users can manage authentication and discover models through CLI subcommands
**Depends on**: Phase 2, Phase 4
**Requirements**: AUTH-03, AUTH-05, AUTH-06, CONF-03, CONF-04
**Success Criteria** (what must be TRUE):
  1. `maestro auth login chatgpt` authenticates and stores credentials for the ChatGPT provider
  2. `maestro auth logout chatgpt` removes stored credentials for a specific provider
  3. `maestro auth status` shows all providers and their authentication state (authenticated/not authenticated)
  4. `maestro models` lists available models from all authenticated providers
  5. `maestro run --model github-copilot/gpt-4o "task"` resolves and uses the specified provider/model
**Plans**: TBD

Plans:
- [ ] 06-01: TBD

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
**Plans**: TBD

Plans:
- [ ] 07-01: TBD

### Phase 8: DAG State, Types & Domains
**Goal**: The multi-agent type system and domain specialization prompts are defined and independently validated
**Depends on**: Phase 5 (provider infrastructure stable)
**Requirements**: STATE-01, STATE-02, STATE-03, STATE-04, DOM-01, DOM-02, DOM-03, DOM-04
**Success Criteria** (what must be TRUE):
  1. `AgentState` TypedDict uses `Annotated[list, operator.add]` reducers for `completed` and `errors`, and a dict merge reducer for `outputs` — safe for parallel writes with no silent data loss
  2. `PlanTask` and `AgentPlan` Pydantic models validate structure: `id`, `domain`, `prompt`, `deps` fields accept valid JSON and reject missing/invalid fields
  3. DAG validator rejects cycles (via `graphlib.TopologicalSorter`) and invalid dependency references before any dispatch
  4. `maestro/domains.py` defines 6 built-in domains (backend, testing, docs, devops, data, general) with specialized system prompts
  5. Unrecognized domain values fall back to the `general` domain without error
**Plans**: TBD

Plans:
- [ ] 08-01: TBD

### Phase 9: Planner
**Goal**: The planner node generates a validated task DAG from a user prompt via LLM structured output
**Depends on**: Phase 5, Phase 8
**Requirements**: PLAN-01, PLAN-02, PLAN-03, PLAN-04
**Success Criteria** (what must be TRUE):
  1. Planner receives a user task string and returns a valid `AgentPlan` JSON via LLM structured output
  2. Planner output is validated by `AgentPlan.model_validate_json()` — invalid output is rejected and not passed to the scheduler
  3. Planner uses a configurable model (via `config.agent.planner.model`), separate from worker models
  4. Planner system prompt produces atomic tasks with domain assignments and avoids over-decomposition
**Plans**: TBD

Plans:
- [ ] 09-01: TBD

### Phase 10: Scheduler & Workers
**Goal**: Tasks execute in parallel respecting dependencies with domain-specialized agents and recursion safety
**Depends on**: Phase 8, Phase 9
**Requirements**: SCHED-01, SCHED-02, SCHED-03, SCHED-04, WORK-01, WORK-02, WORK-03, WORK-04, WORK-05, WORK-06, WORK-07, WORK-08
**Success Criteria** (what must be TRUE):
  1. Scheduler dispatches ready tasks (no unmet dependencies) in parallel via LangGraph `Send` API
  2. After a batch completes, scheduler re-evaluates newly unblocked tasks and dispatches the next batch — repeats until all DAG tasks are complete
  3. Each Worker runs `_run_agentic_loop` with a domain-specialized system prompt from `domains.py`
  4. Path guard (workdir containment) is enforced inside every Worker — attempting a write outside workdir is blocked
  5. Worker errors are collected in `AgentState.errors` (non-fatal) and independent tasks continue executing
  6. `depth` is a required argument (no default); Workers at `max_depth` cannot recurse further (default max_depth=2)
  7. Worker output and task ID are appended to shared `AgentState` via reducers — a 2-worker test confirms both outputs are present (no silent last-write-wins)
**Plans**: TBD

Plans:
- [ ] 10-01: TBD

### Phase 11: Aggregator & Multi-Agent CLI
**Goal**: Users activate multi-agent mode via CLI and optionally receive a final aggregated summary
**Depends on**: Phase 10
**Requirements**: AGG-01, AGG-02, CLI-01, CLI-02, CLI-03, CLI-04
**Success Criteria** (what must be TRUE):
  1. `maestro run --multi "task"` activates the full DAG pipeline (planner → scheduler → workers → aggregator)
  2. Without `--multi`, `maestro run` behaves identically to current single-agent behavior (zero regressions)
  3. `--auto` and `--workdir` flags pass through from CLI to all workers
  4. Lifecycle events (planner done, worker started, worker done) print to stdout during `--multi` execution
  5. Aggregator runs after all workers complete and produces a final summary (optional, configurable)
**Plans**: TBD

Plans:
- [ ] 11-01: TBD

## Progress

**Execution Order:**
Phases execute in numeric order: 1 → 2 → 3 → 4 → 5 → 6 → 7 → 8 → 9 → 10 → 11

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Provider Plugin Protocol | 0/? | Not started | - |
| 2. Multi-Slot Auth Store | 0/? | Not started | - |
| 3. ChatGPT Provider Migration | 0/1 | Planned | - |
| 4. Config & Provider Registry | 0/? | Not started | - |
| 5. Agent Loop Refactor | 0/? | Not started | - |
| 6. Auth & Model CLI Commands | 0/? | Not started | - |
| 7. GitHub Copilot Provider | 0/? | Not started | - |
| 8. DAG State, Types & Domains | 0/? | Not started | - |
| 9. Planner | 0/? | Not started | - |
| 10. Scheduler & Workers | 0/? | Not started | - |
| 11. Aggregator & Multi-Agent CLI | 0/? | Not started | - |
