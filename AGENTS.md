<!-- GSD:project-start source:PROJECT.md -->
## Project

**Maestro**

Maestro is a CLI-driven AI agent that executes complex software engineering tasks using file system tools and shell commands. It is being extended from a single-agent agentic loop into a multi-agent parallel execution engine, where a Planner decomposes tasks into a dependency DAG and specialized Worker agents execute in parallel via LangGraph's Send API. It targets developers who need to automate multi-domain tasks (coding + testing + docs + devops) from the terminal.

**Core Value:** A developer runs `maestro run --multi "build a REST API with tests and docs"` and gets all parts done in parallel by specialized agents — faster and with cleaner domain separation than a single agent.

### Constraints

- **Tech stack**: Python, LangGraph, httpx, pyproject.toml entry points — no framework changes
- **Backward compatibility**: `maestro run` (no flags) must behave identically to today — zero regressions on all 26+ existing tests
- **Security**: path guard must apply inside every Worker, not just at CLI level
- **Recursion safety**: max depth guard is mandatory; infinite recursion is a hard failure mode
- **Entry points for providers**: external providers must be installable via `pip install` without touching maestro source
<!-- GSD:project-end -->

<!-- GSD:stack-start source:research/STACK.md -->
## Technology Stack

## Existing Stack (Confirmed)
| Component | Version | Status |
|-----------|---------|--------|
| Python | 3.12.7 | ✅ Locked — no change needed |
| langgraph | 1.1.6 | ✅ Already installed — both `@entrypoint/@task` AND `StateGraph` APIs available |
| httpx | 0.28.1 | ✅ Already installed — AsyncClient + streaming confirmed |
| httpx-sse | 0.4.1 | ✅ Already installed |
| anyio | 4.10.0 | ✅ Available |
| pydantic | 2.11.7 | ✅ Already installed — use for structured output |
| openai | 2.32.0 | ✅ Already installed |
## Recommended Stack for New Features
### 1. Multi-Agent DAG — LangGraph Send API
- The existing `@entrypoint/@task` wrappers are for single-agent observability/retry — keep them as-is for `_run_agentic_loop`.
- `StateGraph` + `Send` is the correct primitive for the Planner→Scheduler→Workers fan-out pattern. The `@task` decorator does not support conditional edges or the `Send` API.
- `Send` API is LangGraph's native map-reduce primitive — allows a routing function to return `list[Send]`, each targeting the same worker node with different per-task state. This is exactly what the Scheduler needs.
- `Annotated[list, operator.add]` is the ONLY safe pattern for parallel writes. Without reducers, parallel workers overwrite each other's state — silent data loss.
- `Send` receives a *snapshot* of state at dispatch time. Workers cannot read each other's in-progress output. This is by design and matches the spec (shared filesystem, not memory).
- The routing function must return `list[Send]` (not a string edge name) when using `Send`. If you mix `Send` and string returns in one function, LangGraph raises a runtime error.
- `add_conditional_edges("scheduler", scheduler_routing, ["worker"])` — the third arg is the list of possible target nodes. Required when returning `Send` objects (tells LangGraph what nodes are reachable).
- Workers loop back to `scheduler` after completion so the scheduler can re-evaluate newly unblocked tasks. Include a termination check: if no more tasks are ready AND all are complete → route to `END`.
- `StateGraph.compile()` must be called before `graph.invoke()` or `graph.ainvoke()`.
- `asyncio.gather` / manual threading for parallel execution — redundant with Send API and creates state sync problems.
- `@task` decorator for the Scheduler/Worker graph nodes — it doesn't integrate with `StateGraph` conditional edges.
### 2. Structured Output for DAG Planning — Pydantic v2
- `BaseModel.model_validate(json_dict)` gives field-level validation errors with clear messages — critical when an LLM-generated DAG has a missing `deps` field or wrong type.
- `model_json_schema()` generates the JSON Schema to include in the planner prompt — the LLM sees exact field names, types, and required fields, producing fewer malformed outputs.
- Works directly with OpenAI `response_format={"type": "json_schema", "json_schema": {...}}` (enforces schema at the API level for supported models).
# Generate schema for planner prompt:
# Parse and validate LLM output:
# or
- Use `model_validate_json()` directly on the raw string — faster than `json.loads()` + `model_validate()` and gives better error messages.
- Use `response_format` JSON schema enforcement when using OpenAI-compatible APIs (ChatGPT via Responses API, Copilot via `/chat/completions`). This is NOT the same as tool calling — it constrains the entire response to match the schema.
- Pydantic v2 `model_json_schema()` generates Draft 2020-12 compatible JSON Schema by default. OpenAI's `json_schema` response format accepts this.
- **Do NOT** use Pydantic v1 patterns (`parse_obj`, `schema()`, `__fields__`) — codebase is on v2.11.7 and v1 compatibility mode is off by default.
- `typing.TypedDict` alone for validation — no runtime enforcement, no schema generation.
- Manual JSON regex parsing of LLM output — brittle, fails on whitespace/formatting variations.
### 3. Plugin Discovery — `importlib.metadata` (stdlib)
- `pkg_resources` (setuptools) is deprecated for entry point discovery. `importlib.metadata` is the stdlib replacement since Python 3.8, stabilized in 3.12.
- `entry_points(group="maestro.providers")` returns only the requested group — efficient, no full package scan.
- `lru_cache(maxsize=1)` on `discover_providers()` is correct — entry points are static after process start; caching avoids repeated disk I/O on every agent call.
- Entry points only resolve after `pip install -e .` (or equivalent). Running tests without reinstalling after adding a new entry point = `KeyError`. Always reinstall after modifying `pyproject.toml` entry points in development.
- `ep.load()` returns the **class**, not an instance. The pattern `cls()` is correct — each load produces a fresh instance. Use `lru_cache` if singletons are needed (as shown above).
- External provider packages must use the same group name `"maestro.providers"` in their own `pyproject.toml`. The string is a contract — document it.
- `entry_points(group=...)` with a keyword argument is Python 3.9+ API. In Python 3.8, you'd need `entry_points().get(group, [])`. This project targets 3.12+ — use the keyword form.
- `pkg_resources.iter_entry_points()` — deprecated, heavy setuptools dependency, slower.
- `importlib_metadata` (backport PyPI package) — unnecessary on Python 3.12.
### 4. GitHub Copilot OAuth Device Code Flow
# From design spec (Ov23li8tweQw6odWQebz confirmed in spec doc)
# Step 1: Request device code
# Step 2: Show user_code to user
# Step 3: Poll for token
# Token ghu_xxxx is used directly as Bearer token — no second exchange needed
# Endpoint: POST https://api.githubcopilot.com/chat/completions
# Format: standard OpenAI chat completions (messages, tools, stream: true)
- `grant_type` must be exactly `"urn:ietf:params:oauth:grant-type:device_code"` — any other value returns `unsupported_grant_type`.
- `interval` from GitHub is the MINIMUM — always add a safety margin (spec uses +3s, GitHub docs say slow_down adds +5s — use +5s to be safe).
- `slow_down` error does NOT mean auth failed — it means poll slower. Update `interval += 5` and continue looping.
- Token format is `ghu_...` (GitHub user token). Unlike ChatGPT OAuth, there's no refresh token and no expiry — the token is long-lived (until the user revokes it in GitHub settings).
- The Copilot API base `https://api.githubcopilot.com` is NOT the same as `https://api.github.com`. Different base, same auth token.
- `POST /chat/completions` uses standard OpenAI chat format (not Responses API format). The existing ChatGPT provider uses the Responses API — Copilot provider uses the simpler completions format. These are incompatible wire formats and must be separate provider implementations.
- Web application flow (browser redirect) for Copilot auth — CLI tool, no browser available during agent execution.
- `client_secret` in device flow — GitHub's device flow doesn't use or need it.
### 5. AsyncIterator + httpx SSE Streaming
- Raw SSE is `data: {...}\n\n` text. `httpx-sse` handles `data:` prefix stripping, multi-line events, `[DONE]` termination, and reconnect logic (if needed). Manual parsing is error-prone and already done by `httpx-sse`.
- The existing `agent.py` already streams — `httpx-sse` 0.4.1 is present. Copilot provider should use the same pattern.
- `AsyncClient` must be created inside `async with` — do not share a single global `AsyncClient` across multiple concurrent workers. Each worker gets its own client instance to avoid connection pool contention.
- `aconnect_sse` wraps `client.stream()` — the connection is kept open for the duration of the `async with` block. Exiting the block closes the stream.
- The `[DONE]` sentinel is sent by OpenAI-compatible APIs (including Copilot) to signal end of stream. Always check for it before `json.loads()` — parsing `[DONE]` raises `JSONDecodeError`.
- Tool call chunks come as partial JSON across multiple SSE events. Buffer `tool_calls` deltas until the `finish_reason == "tool_calls"` chunk, then yield the complete `Message`.
- `httpx_sse` 0.4.1 does not support automatic reconnection on disconnect. For the use case here (short-lived agent calls), this is fine — no reconnect logic needed.
- `response.aiter_lines()` for SSE manually — misses event boundaries, `data:` prefix handling, and multi-line events.
- `aiohttp` — project is already on httpx; mixing two HTTP clients adds dependency weight and inconsistency.
### 6. ProviderPlugin Protocol (Structural Typing)
- `ABC` (Abstract Base Class) requires third-party providers to `import maestro.providers.base` and explicitly `class MyProvider(ProviderPlugin)`. This couples external plugins to maestro's package at import time.
- `typing.Protocol` is structural — external providers satisfy the interface if they have the right methods/attributes, even without importing or subclassing. Third-party providers install via `pip install` and declare the entry point; no `import maestro` needed.
- `@runtime_checkable` decorator on the Protocol enables `isinstance(instance, ProviderPlugin)` checks at runtime for registry validation.
- `@runtime_checkable` only checks that the methods/attributes *exist* — it does NOT verify signatures. A provider that defines `def stream(self, foo)` passes `isinstance` but will fail at call time. Add integration tests to catch this.
- Protocol `__init__` is NOT checked by structural typing. Each provider can have a different constructor signature (e.g., loading config from different files). This is fine — providers are instantiated by the registry via `cls()`.
- `AsyncIterator` as a return type annotation on a Protocol method requires the actual implementation to be an `async def` with `yield` or explicit `return`. A regular `def` returning an `AsyncIterator` satisfies the Protocol's structural check but `await ... async for` calls will break.
### 7. Topological Sort — stdlib only
- `networkx` is a heavy dependency (~2MB) for a single topological sort. `graphlib.TopologicalSorter` is stdlib, zero overhead, and handles the exact use case: incremental readiness detection.
- `TopologicalSorter` supports streaming: `ts.get_ready()` returns nodes with all deps satisfied, `ts.done(node)` marks completion and unlocks dependents. This matches the Scheduler's re-evaluation loop exactly.
- `CycleError` is raised by `ts.prepare()` if the graph has cycles. Always catch it — a cyclic Planner output would otherwise cause infinite recursion.
- `ts.get_ready()` returns nodes whose deps are ALL done, not just started. Coordinate with the Scheduler's `completed` list (state reducer) — only call `ts.done(tid)` for tasks in `completed`.
- `TopologicalSorter` is not reentrant across LangGraph node invocations — reconstruct it from `dag` + `completed` on each Scheduler call.
- `networkx` — overkill for this use case.
- Manual Kahn's algorithm — `graphlib` already implements it correctly.
## Alternatives Considered
| Category | Recommended | Alternative | Why Not |
|----------|-------------|-------------|---------|
| Parallel fan-out | LangGraph `Send` API | `asyncio.gather` | `asyncio.gather` bypasses LangGraph state machine; no reducers, no graph observability |
| Structured output | Pydantic v2 `BaseModel` | `TypedDict` + manual validation | `TypedDict` has no runtime validation; no JSON schema generation |
| Plugin discovery | `importlib.metadata` | `pkg_resources` | `pkg_resources` is deprecated; slower; heavy setuptools dependency |
| Topo sort | `graphlib.TopologicalSorter` | `networkx` | `networkx` is 50x heavier for a single graph operation; stdlib is sufficient |
| SSE parsing | `httpx-sse` | Manual `aiter_lines()` | Manual parsing misses edge cases; `httpx-sse` already in project |
| Provider interface | `typing.Protocol` | `ABC` | `ABC` forces third-party providers to import maestro; Protocol is structural |
| HTTP client | `httpx.AsyncClient` | `aiohttp` | Project already on httpx; two HTTP clients = unnecessary complexity |
| DAG planning schema | Pydantic `BaseModel` → `model_json_schema()` | Raw system prompt description | Schema in prompt reduces malformed outputs; API-level enforcement possible |
## No New Dependencies Required
## Installation (Verification Commands)
# Verify all required packages are present at correct versions:
## Confidence Assessment
| Area | Confidence | Source | Notes |
|------|------------|--------|-------|
| LangGraph Send API pattern | HIGH | LangGraph 1.x official docs (Context7) + installed 1.1.6 | Verified imports work in project |
| Pydantic v2 structured output | HIGH | Pydantic 2.x official docs (Context7) + installed 2.11.7 | `model_json_schema()` API verified |
| `importlib.metadata` entry_points | HIGH | Python 3.12 stdlib + live test in project | `entry_points(group=...)` confirmed working |
| `graphlib.TopologicalSorter` | HIGH | Python 3.9+ stdlib | CycleError handling verified in docs |
| httpx async streaming | HIGH | httpx official docs + installed 0.28.1 | `aconnect_sse` pattern confirmed |
| GitHub Copilot CLIENT_ID | MEDIUM | Design spec (`Ov23li8tweQw6odWQebz`) + GitHub device flow docs | CLIENT_ID must be validated against actual GitHub OAuth App registration before use |
| Copilot API endpoint + headers | MEDIUM | Design spec only | `x-initiator` and `Openai-Intent` headers not in public docs — derived from existing implementations |
| LangGraph StateGraph vs @entrypoint for DAG | HIGH | Context7 docs + code review | `@entrypoint/@task` confirmed incompatible with `Send` conditional edges |
## Sources
- LangGraph Send API: https://docs.langchain.com/oss/python/langgraph/use-graph-api (Context7, verified 2026-04-17)
- LangGraph orchestrator-worker: https://docs.langchain.com/oss/python/langgraph/workflows-agents (Context7)
- Pydantic v2 model_json_schema: https://pydantic.dev/docs/validation/latest/api/pydantic/json_schema (Context7)
- GitHub Device Flow: https://docs.github.com/en/apps/oauth-apps/building-oauth-apps/authorizing-oauth-apps#device-flow (official, verified 2026-04-17)
- httpx async streaming: https://www.encode.io/httpx/async/ (official, verified 2026-04-17)
- Python graphlib: https://docs.python.org/3/library/graphlib.html (stdlib, Python 3.9+)
- Python importlib.metadata: stdlib, Python 3.9+ (live-tested in Python 3.12.7)
<!-- GSD:stack-end -->

<!-- GSD:conventions-start source:CONVENTIONS.md -->
## Conventions

Conventions not yet established. Will populate as patterns emerge during development.
<!-- GSD:conventions-end -->

<!-- GSD:architecture-start source:ARCHITECTURE.md -->
## Architecture

Architecture not yet mapped. Follow existing patterns found in the codebase.
<!-- GSD:architecture-end -->

<!-- GSD:skills-start source:skills/ -->
## Project Skills

No project skills found. Add skills to any of: `.claude/skills/`, `.agents/skills/`, `.cursor/skills/`, or `.github/skills/` with a `SKILL.md` index file.
<!-- GSD:skills-end -->

<!-- GSD:workflow-start source:GSD defaults -->
## GSD Workflow Enforcement

Before using Edit, Write, or other file-changing tools, start work through a GSD command so planning artifacts and execution context stay in sync.

Use these entry points:
- `/gsd-quick` for small fixes, doc updates, and ad-hoc tasks
- `/gsd-debug` for investigation and bug fixing
- `/gsd-execute-phase` for planned phase work

Do not make direct repo edits outside a GSD workflow unless the user explicitly asks to bypass it.
<!-- GSD:workflow-end -->



<!-- GSD:profile-start -->
## Developer Profile

> Profile not yet configured. Run `/gsd-profile-user` to generate your developer profile.
> This section is managed by `generate-claude-profile` -- do not edit manually.
<!-- GSD:profile-end -->
