# Feature Landscape

**Domain:** Multi-agent AI CLI tool (developer automation)
**Researched:** 2026-04-17
**Confidence:** HIGH (verified against AutoGen, CrewAI, LangGraph Supervisor docs + project design specs)

---

## Table Stakes

Features users expect. Missing = product feels incomplete or users switch to AutoGen/CrewAI.

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| **Backward compatibility** — `maestro run` unchanged | Users break nothing upgrading; trust baseline | Low | Already in design spec; `--multi` is purely additive |
| **`--multi` flag activates DAG mode** | Standard pattern: existing flag = existing behavior, new flag = new behavior | Low | CLI convention already established |
| **Planner produces structured DAG** | Without explicit DAG, parallelism is opaque and unreliable — users can't reason about what's happening | Medium | JSON with id/domain/prompt/deps; validated against schema before dispatch |
| **Dependency-respecting execution** | A testing worker that runs before backend code is written is useless. Topological ordering is the point | Medium | Scheduler topological sort via LangGraph Send API |
| **Domain specialization (system prompts per worker)** | Backend/testing/docs/devops workers with generic prompts produce cross-contaminated output. Specialization is the whole value proposition | Low | `maestro/domains.py`; CrewAI and AutoGen both treat role-specific prompts as non-negotiable |
| **Visible progress / execution trace** | Silent multi-agent run → users don't know if it's working or stuck | Medium | Print worker start/end with domain+task-id; not full streaming, just lifecycle events |
| **Exit on error with diagnosis** | A silent failure leaves the filesystem in a half-baked state; users must know which worker failed and why | Medium | Collect `errors` in state, surface after run; non-zero exit code |
| **`--auto` and `--workdir` pass-through to workers** | Users already rely on these flags; breaking them in multi-agent mode destroys trust | Low | Already designed — workers inherit flags from CLI invocation |
| **Aggregator summary output** | After parallel workers finish, users need a consolidated answer — not N disconnected files | Medium | Optional final pass; failing to summarize leaves users connecting dots manually |
| **Multi-provider auth (`maestro auth login/logout/status`)** | Adding a second provider (Copilot) without a clear auth UX is confusing. CrewAI has `crewai login`; standard expectation | Medium | Device code OAuth flow; multi-slot `~/.maestro/auth.json` |
| **`provider/model` format in config** | Industry convention established by CrewAI (`openai/gpt-4o`), AutoGen (`OpenAIChatCompletionClient(model=…)`), LangGraph — deviation adds friction | Low | `"github-copilot/gpt-4o"` format in `~/.maestro/config.json` |
| **`maestro models` subcommand** | Users need discoverability — what models are available for the authenticated providers? | Low | Lists `provider.list_models()` for all authenticated providers |
| **`--model` flag on `run`** | Per-invocation override; users running different tasks want different models without editing config | Low | `--model github-copilot/gpt-4o-mini` for the fast planner case |
| **Recursion depth guard (max 2)** | Without this, a misbehaving planner produces infinite loops that terminate only on resource exhaustion | Low | Hard cap; workers at max depth cannot spawn sub-planners |
| **Path guard in every worker** | Security regression: workers writing outside `--workdir` would be a critical failure | Low | Existing `path_guard` must be applied in Worker scope, not just CLI scope |

---

## Differentiators

Features that distinguish maestro from AutoGen/CrewAI for the developer-automation terminal use case.

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| **True parallel DAG execution (not sequential round-robin)** | AutoGen and CrewAI default to sequential or turn-based patterns. LangGraph Send API gives genuine concurrency within a single graph run — 3x faster for independent tasks | High | Key architectural bet; verified: LangGraph Send API is the right primitive here |
| **Domain-first decomposition (not agent-first)** | AutoGen assigns tools to agents; CrewAI assigns roles. Maestro assigns *domains* — a conceptual level above tools, below agents. Planner thinks in domains, not in agent identities. Easier to reason about for dev tasks | Medium | `backend/testing/docs/devops/data/general` covers 95% of software engineering tasks |
| **Recursive sub-planning with depth guard** | AutoGen and LangGraph Supervisor support hierarchical agents but require pre-defining the hierarchy. Maestro's workers can dynamically request sub-plans for tasks too complex to execute directly — organic depth | High | Depth guard prevents the obvious failure mode; recursive planning is genuinely novel for CLI tools |
| **Provider-neutral agent loop (Protocol, not ABC)** | CrewAI uses LiteLLM for provider routing (adds a dep); AutoGen requires `OpenAIChatCompletionClient`. Maestro's `ProviderPlugin` Protocol means third-party providers are installable via `pip install` without modifying maestro source | High | Entry points pattern; structural typing avoids import dependency on maestro |
| **Shared filesystem as the inter-worker communication bus** | AutoGen uses in-memory message passing (complex, race-prone). Maestro workers communicate via files in `--workdir` — simple, debuggable, and reviewable by the user post-run | Low | By design limitation that becomes a feature: outputs are inspectable artifacts, not ephemeral messages |
| **Single binary entry point (`maestro run --multi`)** | AutoGen and CrewAI require Python scripts. Maestro stays CLI-first — the developer's natural habitat for automation | Low | No new entry points needed; `--multi` flag is the entire surface area change |
| **Per-agent model configuration** | `config.agent.planner.model = "github-copilot/gpt-4o-mini"` for cheap planning + `config.agent.worker.model = "github-copilot/gpt-4o"` for execution — optimizing cost without code changes | Low | Config hierarchy: CLI flag > env var > agent config > global default > auto |
| **Planner isolation (separate model call, not graph node)** | Keeping DAG generation as a pure function makes it trivially testable and replaceable. CrewAI's planning is baked into the crew execution; hard to unit test | Medium | Planner returns JSON; validated independently before any worker starts |

---

## Anti-Features

Things to explicitly NOT build in v1. Building these creates debt without user value at this scale.

| Anti-Feature | Why Avoid | What to Do Instead |
|--------------|-----------|-------------------|
| **Human-in-the-loop DAG approval** | Interrupts the automation value; maestro's target users run `--auto` specifically to avoid this. AutoGen supports it; that's for different use cases | If users want to inspect the plan, log the DAG JSON to stdout before execution starts |
| **Cross-worker in-memory state sharing** | Creates coordination complexity (locks, channels, race conditions) that makes the system harder to test and debug than the value it provides | Workers share filesystem (`--workdir`); downstream workers read upstream outputs as files |
| **Streaming partial results during multi-agent execution** | Complex to implement correctly with LangGraph's parallel state management. Single-agent streaming already exists; multi-agent streaming requires synchronized stream multiplexing | Log lifecycle events (worker start/end/error) and aggregate final output after all workers complete |
| **Persistent DAG state across CLI sessions** | Adds storage layer, resume logic, state invalidation — a new product category (workflow runner). Maestro is stateless by design | Each `maestro run --multi` is a fresh execution; idempotency is the user's responsibility |
| **Dynamic worker pool sizing / resource limits** | Token counting and rate limiting across providers is complex and provider-specific. Premature optimization at v1 scale | Let LangGraph manage concurrency via its native parallelism; add limits in v2 with real usage data |
| **Model picker TUI** | Interactive terminal UIs are a significant engineering investment (curses/rich). `maestro models` + `--model` flag covers the need adequately | `maestro models` for discovery, `--model` for selection |
| **Per-provider retry / rate limiting** | Each provider has different rate limit headers and backoff contracts. Getting this wrong causes silent data loss | Fail fast with clear error messages; let users retry; add provider-specific retry in v2 |
| **GitHub Enterprise Copilot** | Different auth flow, different API base URL, adds conditional branches throughout the Copilot provider | Regular GitHub Copilot first; Enterprise is v2 with a dedicated provider variant |
| **Providers beyond ChatGPT + GitHub Copilot** | Entry points mechanism already enables third-party providers. Building more builtins dilutes focus and duplicates LiteLLM's job | Document the `ProviderPlugin` Protocol; let the community add Anthropic/Gemini/Ollama via `pip install maestro-provider-*` |
| **Planner user-configurable system prompt (via config)** | Increases surface area; planner prompt stability is critical for structured JSON output. User changes break DAG parsing | Let advanced users fork the planner prompt in v2 behind a documented escape hatch |

---

## Feature Dependencies

The ordering in which features must be built or become meaningful:

```
Multi-Provider Plugin System
    ├── ProviderPlugin Protocol + neutral types (Message, ToolCall, Tool)
    │       └── ChatGPT provider migrated to new interface
    │               └── _run_agentic_loop uses provider.stream() [UNBLOCKS EVERYTHING]
    ├── Config system (~/.maestro/config.json, parse_model, resolve_model)
    │       └── --model flag on run subcommand
    │       └── Per-agent model config (planner vs worker model)
    ├── Auth store multi-slot (~/.maestro/auth.json)
    │       └── maestro auth login/logout/status subcommands
    │               └── GitHub Copilot device code OAuth
    │               └── maestro models subcommand
    └── GitHub Copilot provider (depends on auth store + neutral types)

Multi-Agent DAG Mode (depends on: provider abstraction complete)
    ├── domains.py (backend/testing/docs/devops/data/general prompts)
    │       [no deps — pure data, can build first]
    ├── Planner (structured JSON DAG output)
    │       └── depends on: working provider (chatgpt or copilot)
    ├── Scheduler (topological sort + Send API dispatch)
    │       └── depends on: Planner output shape validated
    │               └── LangGraph state with reducers (Annotated[list, add])
    ├── Worker (agentic loop + domain prompt)
    │       └── depends on: Scheduler dispatches, domain prompts exist
    │               └── path guard applied inside worker [SECURITY DEPENDENCY]
    ├── Recursive sub-planning
    │       └── depends on: Worker stable + depth guard implemented
    └── Aggregator node (optional summary pass)
            └── depends on: all workers complete, outputs in state

Backward Compatibility (cross-cutting, must be verified at every layer)
    └── All 26 existing tests must pass through every phase
```

### Critical Path

**Phase 1 — Multi-Provider** must complete before Phase 2 — Multi-Agent, because:
- Workers must be able to use different providers/models
- Provider abstraction refactor touches `_run_agentic_loop` which workers reuse
- Config system must exist before per-agent model routing is possible

**Within Phase 2 — Multi-Agent:**
1. `domains.py` (zero deps, pure data)
2. Planner (depends on provider)
3. Scheduler + LangGraph state (depends on Planner shape)
4. Worker (depends on Scheduler + domains)
5. Recursion guard (depends on Worker)
6. Aggregator (last, optional)

---

## How Competing Tools Handle the Key Problems

### Domain Specialization

| Tool | Approach | Maestro's Take |
|------|----------|----------------|
| **AutoGen** | Per-agent `system_message` with explicit role description. Planner decides which agent gets which message via handoffs. | Maestro uses the same pattern but names domains explicitly (`backend/testing/docs`) rather than free-form role names. Easier to enumerate and test. |
| **CrewAI** | `Agent(role=..., goal=..., backstory=...)` — rich role definition. LLM selection per-agent via `llm="openai/gpt-4o"`. | Maestro's domain prompts are leaner (system_prompt only, no backstory theater). CrewAI's role richness adds tokens without clear quality improvement for dev tasks. |
| **LangGraph Supervisor** | Agents described in supervisor prompt; supervisor LLM routes tasks. No formal domain concept. | Maestro's DAG makes routing explicit (Planner decides domain at plan time) rather than emergent (supervisor decides at runtime). More predictable for automated tasks. |

### DAG Execution / Parallelism

| Tool | Approach | Maestro's Take |
|------|----------|----------------|
| **AutoGen** | `Swarm` with handoffs — sequential by default. Parallel requires explicit `GroupChat` configuration. | Maestro's Send API fan-out is parallel-by-default for independent tasks. No extra configuration. |
| **CrewAI** | Tasks can be marked `async_execution=True` for parallel processing. Dependencies expressed via `context=[task]`. | Similar intent; CrewAI requires explicit async flags. Maestro's DAG deps field is richer (N:M dependencies vs. single task context). |
| **LangGraph Send API** | Native parallel dispatch via `[Send("worker", {...}) for t in tasks]`. Outputs merged via Annotated reducers. | **Maestro uses this directly** — the right primitive for the job. HIGH confidence. |

### Provider Abstraction

| Tool | Approach | Maestro's Take |
|------|----------|----------------|
| **AutoGen** | `OpenAIChatCompletionClient`, `AzureOpenAIChatCompletionClient`, etc. — per-provider clients, not a unified protocol. | Maestro's `ProviderPlugin` Protocol + entry points is architecturally cleaner. No provider-specific imports in the agent loop. |
| **CrewAI** | LiteLLM routing — `llm="openai/gpt-4o"`, `llm="anthropic/claude-3"` works out of the box. ~20+ providers. | LiteLLM is powerful but adds a heavy dependency and opaque routing. Maestro's approach is lighter and more auditable for 2 providers. Extensible via entry points for more. |
| **LangGraph** | Provider-agnostic by design; uses LangChain's model abstraction layer. | Maestro skips LangChain entirely (correct for a CLI tool). Direct HTTP via httpx gives full control over SSE parsing and auth flows. |

---

## MVP Recommendation

Prioritize (in order):

1. **Multi-provider plugin system** — unblocks everything; refactors the core HTTP layer cleanly
2. **GitHub Copilot provider + auth commands** — delivers the tangible "use Copilot instead of ChatGPT" value
3. **Domain prompts (`domains.py`)** — zero risk, high value, can be written independently
4. **Planner + Scheduler + Workers (DAG mode)** — the headline feature
5. **Recursion guard** — safety, not optional
6. **Aggregator** — quality of life; implement last or skip if DAG outputs are clear enough

**Defer to v2:**
- Streaming partial results during multi-agent execution
- Human-in-the-loop DAG approval
- Providers beyond ChatGPT + GitHub Copilot
- Per-provider retry/rate limiting

---

## Sources

| Source | Confidence | URL |
|--------|------------|-----|
| LangGraph Send API docs | HIGH | Context7 `/websites/langchain_oss_python_langgraph` |
| LangGraph Supervisor docs | HIGH | Context7 `/langchain-ai/langgraph-supervisor-py` |
| AutoGen multi-agent patterns | HIGH | Context7 `/microsoft/autogen` |
| CrewAI agent/task/provider docs | HIGH | Context7 `/crewaiinc/crewai` |
| Project design specs | HIGH | `docs/ideas/multi-agent-dag.md`, `docs/superpowers/specs/2026-04-17-multi-provider-plugin-design.md` |
| PROJECT.md requirements | HIGH | `.planning/PROJECT.md` |
