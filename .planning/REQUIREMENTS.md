# Maestro — v1 Requirements

## v1 Requirements

### Provider Plugin System (PROV)

- [x] **PROV-01**: Developer can define a new provider by implementing the `ProviderPlugin` Protocol (id, name, list_models, stream, auth_required, login, is_authenticated)
- [ ] **PROV-02**: Provider instances are discovered via `importlib.metadata` entry points (`maestro.providers` group) at runtime
- [ ] **PROV-03**: Built-in providers (ChatGPT, GitHub Copilot) are registered via `pyproject.toml` entry points
- [ ] **PROV-04**: `get_provider(provider_id)` raises `ValueError` with list of available providers on unknown ID
- [ ] **PROV-05**: Third-party providers are installable via `pip install <package>` without modifying maestro source
- [x] **PROV-06**: `stream()` accepts neutral types (`Message`, `Tool`, `ToolCall`) and yields `str | Message` — provider never exposes wire format to caller

### Auth Store (AUTH)

- [ ] **AUTH-01**: Auth credentials are stored per-provider in `~/.maestro/auth.json` (mode `0o600`)
- [ ] **AUTH-02**: `auth.get(provider_id)`, `auth.set(provider_id, data)`, `auth.remove(provider_id)`, `auth.all_providers()` are the public API
- [ ] **AUTH-03**: User can authenticate with ChatGPT via `maestro auth login chatgpt`
- [ ] **AUTH-04**: User can authenticate with GitHub Copilot via `maestro auth login github-copilot` (OAuth device code flow)
- [ ] **AUTH-05**: User can log out of a provider via `maestro auth logout <provider-id>`
- [ ] **AUTH-06**: User can view all providers and their auth state via `maestro auth status`
- [ ] **AUTH-07**: GitHub Copilot login polls with correct interval + safety margin, handles `authorization_pending` and `slow_down` (incrementing interval on slow_down)
- [ ] **AUTH-08**: Existing `maestro auth login` (ChatGPT OAuth flow) shows deprecation warning and routes to `maestro auth login chatgpt`

### Config & Model Resolution (CONF)

- [ ] **CONF-01**: Model resolution order: `--model` flag → `MAESTRO_MODEL` env → `config.agent.<agent_name>.model` → `config.model` → first model of first authenticated provider
- [ ] **CONF-02**: Model string format is `"<provider_id>/<model_id>"`; invalid format raises `ValueError` with guidance
- [ ] **CONF-03**: User can override model per-invocation via `maestro run --model github-copilot/gpt-4o "task"`
- [ ] **CONF-04**: `maestro models` lists available models (optionally filtered with `--provider <id>`)
- [ ] **CONF-05**: Config file at `~/.maestro/config.json` is optional; absent config falls back gracefully to ChatGPT provider

### Agent Loop Refactor (LOOP)

- [ ] **LOOP-01**: `_run_agentic_loop` uses `provider.stream()` instead of hardwired httpx calls — HTTP layer is fully provider-delegated
- [ ] **LOOP-02**: If provider is not authenticated, loop raises `RuntimeError` with actionable message (`maestro auth login <provider_id>`)
- [ ] **LOOP-03**: All 26 existing tests pass without modification after the refactor
- [ ] **LOOP-04**: ChatGPT provider encapsulates all ChatGPT-specific SSE parsing and HTTP logic (migrated from agent.py)

### GitHub Copilot Provider (COPILOT)

- [ ] **COPILOT-01**: `CopilotProvider` implements `ProviderPlugin` Protocol completely
- [ ] **COPILOT-02**: `stream()` converts neutral `Tool`/`Message` types to OpenAI-compatible wire format and back
- [ ] **COPILOT-03**: Stream calls `POST https://api.githubcopilot.com/chat/completions` with required headers (`Authorization: Bearer`, `x-initiator: user`, `Openai-Intent: conversation-edits`)
- [ ] **COPILOT-04**: `list_models()` returns available Copilot model IDs
- [ ] **COPILOT-05**: `is_authenticated()` returns `False` when no token stored

### Multi-Agent DAG — State & Types (STATE)

- [ ] **STATE-01**: `AgentState` TypedDict uses `Annotated[list, operator.add]` for `completed` and a dict merge reducer for `outputs` — safe for parallel writes
- [ ] **STATE-02**: `PlanTask` Pydantic model validates: `id` (str), `domain` (str), `prompt` (str), `deps` (list[str])
- [ ] **STATE-03**: `AgentPlan` Pydantic model validates: `tasks` (list[PlanTask])
- [ ] **STATE-04**: DAG validator rejects cycles (using `graphlib.TopologicalSorter`) and invalid dep references before dispatch

### Multi-Agent DAG — Planner (PLAN)

- [ ] **PLAN-01**: Planner node receives the user task and returns a validated `AgentPlan` JSON via LLM structured output
- [ ] **PLAN-02**: Planner uses a fast/cheap model (configurable via `config.agent.planner.model`)
- [ ] **PLAN-03**: Planner system prompt instructs: keep tasks atomic, avoid over-decomposition, assign a domain to each task
- [ ] **PLAN-04**: Planner output is validated by `AgentPlan.model_validate_json()` before passing to scheduler

### Multi-Agent DAG — Scheduler (SCHED)

- [ ] **SCHED-01**: Scheduler node computes topological sort of the DAG and dispatches ready tasks (no unmet deps) via LangGraph `Send` API
- [ ] **SCHED-02**: Each `Send` carries a per-task state snapshot including `task_id`, `domain`, `prompt`, and `depth`
- [ ] **SCHED-03**: After all workers for a batch complete, scheduler re-evaluates newly unblocked tasks and dispatches another batch
- [ ] **SCHED-04**: Scheduler repeats until all tasks in the DAG are complete

### Multi-Agent DAG — Workers (WORK)

- [ ] **WORK-01**: Each Worker is an instance of `_run_agentic_loop` with domain-specialized system prompt
- [ ] **WORK-02**: Workers access the shared `--workdir` filesystem and can read each other's output files
- [ ] **WORK-03**: Path guard (workdir containment) is enforced inside every Worker, not just at CLI level
- [ ] **WORK-04**: Worker appends its output and task ID to `AgentState.outputs` and `AgentState.completed` via reducers
- [ ] **WORK-05**: Worker errors are appended to `AgentState.errors` (non-fatal) and execution of independent tasks continues
- [ ] **WORK-06**: A Worker can recursively spawn a sub-Planner on its own subtask (optional, depth-guarded)
- [ ] **WORK-07**: `depth` is a required argument (not optional/defaulted); Workers at `max_depth` cannot recurse further
- [ ] **WORK-08**: Default `max_depth` is 2; configurable via CLI flag or config

### Multi-Agent DAG — Domain System (DOM)

- [ ] **DOM-01**: Domain system is defined in `maestro/domains.py` as a dict mapping domain name → system prompt
- [ ] **DOM-02**: Built-in domains: `backend`, `testing`, `docs`, `devops`, `data`, `general`
- [ ] **DOM-03**: `general` domain is the fallback for unrecognized domain values
- [ ] **DOM-04**: Domain prompts instruct Workers to stay within their domain and write outputs to shared workdir

### Multi-Agent DAG — Aggregator (AGG)

- [ ] **AGG-01**: Aggregator node runs after all workers complete and produces a final summary of all worker outputs
- [ ] **AGG-02**: Aggregator is optional — skipped when not requested (configurable)

### CLI — Multi-Agent Mode (CLI)

- [ ] **CLI-01**: `maestro run --multi "task"` activates the DAG pipeline
- [ ] **CLI-02**: `maestro run --multi --auto "task" --workdir ./project` passes `--auto` and `--workdir` through to all workers
- [ ] **CLI-03**: Without `--multi`, `maestro run` behaves identically to current behavior (zero regressions)
- [ ] **CLI-04**: Lifecycle events (planner done, worker started, worker done) are printed to stdout during `--multi` execution

## v2 Requirements (Deferred)

- Dynamic worker pool sizing / resource limits
- Cross-worker in-memory state communication
- Human-in-the-loop DAG approval before execution
- Streaming partial LLM output to CLI during multi-agent runs
- Persistent DAG state across CLI sessions
- GitHub Enterprise Copilot support
- Token refresh for GitHub Copilot
- Model picker TUI
- Per-provider rate limiting and retry logic
- Providers beyond GitHub Copilot and ChatGPT

## Out of Scope

- Non-Python runtimes — maestro is Python-only
- GUI or web interface — CLI is the only interface
- Cloud orchestration (Kubernetes, Docker Swarm) — local execution only
- Sandboxed execution (Docker per worker) — user's own permissions, confirmation guards are sufficient for v1

## Traceability

| REQ-ID | Phase | Description |
|--------|-------|-------------|
| PROV-01 | Phase 1 | ProviderPlugin Protocol definition |
| PROV-06 | Phase 1 | Neutral types: Message, Tool, ToolCall |
| AUTH-01 | Phase 2 | Per-provider auth.json storage (0o600) |
| AUTH-02 | Phase 2 | Auth public API: get/set/remove/all_providers |
| AUTH-08 | Phase 2 | Backward compat: existing `maestro auth login` routes to chatgpt |
| PROV-03 | Phase 3 | ChatGPT registered via pyproject.toml entry points |
| LOOP-04 | Phase 3 | ChatGPT encapsulates SSE parsing and HTTP logic |
| PROV-02 | Phase 4 | Provider discovery via importlib.metadata entry points |
| PROV-04 | Phase 4 | get_provider() ValueError on unknown ID |
| PROV-05 | Phase 4 | Third-party providers installable via pip |
| CONF-01 | Phase 4 | Model resolution priority chain |
| CONF-02 | Phase 4 | provider_id/model_id format validation |
| CONF-05 | Phase 4 | Optional config file with graceful fallback |
| LOOP-01 | Phase 5 | provider.stream() replaces httpx.stream() |
| LOOP-02 | Phase 5 | RuntimeError with actionable auth message |
| LOOP-03 | Phase 5 | All 26 existing tests pass unchanged |
| AUTH-03 | Phase 6 | `maestro auth login chatgpt` |
| AUTH-05 | Phase 6 | `maestro auth logout <provider-id>` |
| AUTH-06 | Phase 6 | `maestro auth status` |
| CONF-03 | Phase 6 | `--model` flag on run subcommand |
| CONF-04 | Phase 6 | `maestro models` subcommand |
| COPILOT-01 | Phase 7 | CopilotProvider implements ProviderPlugin |
| COPILOT-02 | Phase 7 | Neutral type ↔ OpenAI wire format conversion |
| COPILOT-03 | Phase 7 | Copilot API endpoint with required headers |
| COPILOT-04 | Phase 7 | list_models() returns Copilot model IDs |
| COPILOT-05 | Phase 7 | is_authenticated() returns False when no token |
| AUTH-04 | Phase 7 | `maestro auth login github-copilot` (device code OAuth) |
| AUTH-07 | Phase 7 | slow_down interval handling in OAuth polling |
| STATE-01 | Phase 8 | AgentState with Annotated reducers for parallel writes |
| STATE-02 | Phase 8 | PlanTask Pydantic model |
| STATE-03 | Phase 8 | AgentPlan Pydantic model |
| STATE-04 | Phase 8 | DAG cycle and dep reference validator |
| DOM-01 | Phase 8 | Domain system in maestro/domains.py |
| DOM-02 | Phase 8 | 6 built-in domains |
| DOM-03 | Phase 8 | `general` domain as fallback |
| DOM-04 | Phase 8 | Domain prompts instruct domain scoping |
| PLAN-01 | Phase 9 | Planner node returns validated AgentPlan JSON |
| PLAN-02 | Phase 9 | Planner uses configurable fast/cheap model |
| PLAN-03 | Phase 9 | Planner prompt: atomic tasks, domain assignment |
| PLAN-04 | Phase 9 | Output validated by model_validate_json() |
| SCHED-01 | Phase 10 | Topological sort + Send API dispatch |
| SCHED-02 | Phase 10 | Per-task state snapshot in Send payload |
| SCHED-03 | Phase 10 | Re-evaluate and dispatch newly unblocked tasks |
| SCHED-04 | Phase 10 | Repeat until all tasks complete |
| WORK-01 | Phase 10 | Worker = _run_agentic_loop with domain prompt |
| WORK-02 | Phase 10 | Workers share --workdir filesystem |
| WORK-03 | Phase 10 | Path guard enforced inside every Worker |
| WORK-04 | Phase 10 | Worker output appended via reducers |
| WORK-05 | Phase 10 | Worker errors non-fatal, execution continues |
| WORK-06 | Phase 10 | Recursive sub-Planner on subtask (optional) |
| WORK-07 | Phase 10 | depth is required argument, no default |
| WORK-08 | Phase 10 | Default max_depth=2, configurable |
| AGG-01 | Phase 11 | Aggregator produces final summary |
| AGG-02 | Phase 11 | Aggregator optional, skipped when not requested |
| CLI-01 | Phase 11 | `maestro run --multi "task"` activates DAG |
| CLI-02 | Phase 11 | --auto and --workdir pass-through to workers |
| CLI-03 | Phase 11 | Without --multi, zero regressions |
| CLI-04 | Phase 11 | Lifecycle events printed to stdout |
