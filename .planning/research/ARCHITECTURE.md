# Architecture Patterns

**Domain:** Multi-agent AI CLI tool (brownfield extension)
**Researched:** 2026-04-17
**Source basis:** Existing `agent.py`, `multi-agent-dag.md`, `multi-provider-plugin-design.md`, `agentic-file-tools-design.md`, `PROJECT.md`

---

## Recommended Architecture

Three tiers, built bottom-up:

```
┌──────────────────────────────────────────────────────────────────────┐
│  TIER 3 — ORCHESTRATION (LangGraph DAG)                              │
│                                                                      │
│   ┌──────────┐   DAG JSON   ┌───────────┐  Send API  ┌──────────┐  │
│   │ Planner  │ ────────────▶│ Scheduler │ ──────────▶│ Worker N │  │
│   │  node    │              │   node    │            │  (×N)    │  │
│   └──────────┘              └───────────┘            └──────────┘  │
│        │                          │                       │         │
│        └──────────────────────────┴───────────────────────┘         │
│                            AgentState (reducers)                     │
└──────────────────────────────────────────────────────────────────────┘
         ↕ invokes
┌──────────────────────────────────────────────────────────────────────┐
│  TIER 2 — AGENT CORE (existing, lightly modified)                    │
│                                                                      │
│   agent.py: _run_agentic_loop()                                      │
│      ├─ calls: provider.stream(model, messages, tools, system)       │
│      ├─ calls: execute_tool(name, args, workdir, auto)               │
│      └─ returns: str (final answer)                                  │
│                                                                      │
│   tools.py: execute_tool(), TOOL_SCHEMAS, DESTRUCTIVE_TOOLS          │
│   domains.py: DOMAIN_PROMPTS[domain] → system prompt str            │
└──────────────────────────────────────────────────────────────────────┘
         ↕ depends on
┌──────────────────────────────────────────────────────────────────────┐
│  TIER 1 — PROVIDER INFRASTRUCTURE (new)                              │
│                                                                      │
│   providers/__init__.py: discover_providers(), get_provider(id)      │
│   providers/base.py:     ProviderPlugin Protocol, Message, Tool,    │
│                          ToolCall (neutral types)                    │
│   providers/chatgpt.py:  ChatGPTProvider (migrated from agent.py)   │
│   providers/copilot.py:  CopilotProvider (new, device code OAuth)   │
│                                                                      │
│   config.py:  resolve_model(agent_name) → (provider_id, model_id)  │
│   auth.py:    get/set/remove/all_providers() (multi-slot JSON store) │
└──────────────────────────────────────────────────────────────────────┘
         ↕ exposed via
┌──────────────────────────────────────────────────────────────────────┐
│  TIER 0 — CLI SURFACE                                                │
│                                                                      │
│   cli.py: maestro run [--multi] [--model] [--auto] [--workdir]      │
│           maestro auth login/logout/status                           │
│           maestro models [--provider]                                │
└──────────────────────────────────────────────────────────────────────┘
```

---

## Component Boundaries

| Component | Responsibility | Communicates With |
|-----------|---------------|-------------------|
| `cli.py` | Argument parsing, subcommand dispatch, user I/O | `agent.py:run()`, `providers/__init__`, `config.py`, `auth.py` |
| `agent.py:run()` | LangGraph `@entrypoint`/`@task` wrapper; creates graph and invokes | `_run_agentic_loop()` |
| `agent.py:_run_agentic_loop()` | Multi-turn agentic loop, streaming, tool dispatch | `providers/__init__:get_provider()`, `tools.py:execute_tool()` |
| `dag.py` (new) | LangGraph multi-agent graph: Planner → Scheduler → Worker nodes | `_run_agentic_loop()`, `domains.py`, `AgentState` |
| `providers/__init__.py` | Entry-point discovery; provider registry (lru_cache) | All consumers of providers |
| `providers/base.py` | `ProviderPlugin` Protocol + neutral types (`Message`, `Tool`, `ToolCall`) | All providers, `agent.py` |
| `providers/chatgpt.py` | HTTP to OpenAI Responses API + SSE parsing | `auth.py`, `providers/base.py` |
| `providers/copilot.py` | HTTP to Copilot chat API + device code OAuth | `auth.py`, `providers/base.py` |
| `config.py` | Model resolution (`provider_id/model_id`) with priority chain | `providers/__init__`, `auth.py` |
| `auth.py` | Multi-slot `~/.maestro/auth.json` credential store | `providers/chatgpt.py`, `providers/copilot.py`, `cli.py` |
| `tools.py` | Tool implementations, `TOOL_SCHEMAS`, `execute_tool()`, path guard | `_run_agentic_loop()`, Workers |
| `domains.py` (new) | Domain → system prompt mapping | Workers, Planner |

---

## Data Flow

### Single-agent path (existing, unchanged)

```
CLI args
  → agent.py:run(model, prompt, system, workdir, auto)
    → config.resolve_model("default")  → ("chatgpt", "gpt-5-codex")
    → providers.get_provider("chatgpt") → ChatGPTProvider instance
    → @entrypoint / @task (LangGraph wrapper)
      → _run_agentic_loop(messages, model_id, instructions, provider, workdir, auto)
        loop:
          → provider.stream(model_id, messages, TOOLS, system)
            → yields: str | Message (neutral types)
          → if Message with tool_calls:
              → execute_tool(name, args, workdir, auto) → dict
              → append tool result to messages
              → continue loop
          → if str only: return final text
    → return str to CLI
```

### Multi-agent path (new)

```
CLI args [--multi]
  → dag.py:run_multi(task, model_flag, workdir, auto)
    → LangGraph multi-agent graph invoked:

    [planner_node]
      → provider.stream(planner_model, [task_message], [], PLANNER_SYSTEM)
      → parse DAG JSON → list[TaskSpec{id, domain, prompt, deps}]
      → update AgentState.dag

    [scheduler_node]
      → topological sort of DAG
      → identify ready tasks (deps all in AgentState.completed)
      → for each ready task: Send("worker", WorkerInput{task_spec, depth, workdir, auto})
      → LangGraph executes all Sends in parallel

    [worker_node] (runs ×N concurrently)
      → system = domains.DOMAIN_PROMPTS[task_spec.domain]
      → _run_agentic_loop(messages=[task_spec.prompt], ..., system=system)
        (same loop as single-agent, with domain system prompt)
      → optional recursion: if task_spec.depth < max_depth AND worker decides to sub-plan:
          → call planner on subtask → inner DAG → inner scheduler → child workers
      → update AgentState.completed += [task_id]
                AgentState.outputs  += {task_id: result_text}

    [aggregator_node] (optional)
      → collect AgentState.outputs
      → provider.stream(aggregator_model, [summary_task], [], AGGREGATOR_SYSTEM)
      → return final summary
```

### Provider plugin resolution path

```
config.resolve_model(agent_name)
  priority chain:
    1. --model CLI flag
    2. MAESTRO_MODEL env var
    3. config.json#agent.<agent_name>.model
    4. config.json#model
    5. first model of first authenticated provider
  → returns ("provider_id", "model_id")

providers.get_provider("provider_id")
  → entry_points(group="maestro.providers")
  → load + instantiate + cache (lru_cache)
  → returns ProviderPlugin instance
```

---

## Critical Integration Points

### Q1: New graph or extend existing?

**New graph.** The existing `@entrypoint`/`@task` in `agent.py:run()` is a thin single-agent wrapper. The multi-agent DAG is a fundamentally different graph topology (fan-out via Send, reducer state, multiple node types). Building it as a separate `dag.py` module keeps the single-agent path completely untouched and the two paths independently testable.

The existing `run()` function in `agent.py` is NOT modified — it stays as the single-agent entry point. `dag.py` creates its own LangGraph `StateGraph` and calls `_run_agentic_loop()` from within worker nodes.

```python
# dag.py (new file)
from langgraph.graph import StateGraph, START
from langgraph.types import Send

def build_multi_agent_graph() -> CompiledStateGraph:
    graph = StateGraph(AgentState)
    graph.add_node("planner", planner_node)
    graph.add_node("scheduler", scheduler_node)
    graph.add_node("worker", worker_node)
    graph.add_node("aggregator", aggregator_node)
    graph.add_edge(START, "planner")
    graph.add_edge("planner", "scheduler")
    graph.add_conditional_edges("scheduler", dispatch_workers)  # uses Send
    graph.add_edge("worker", "scheduler")   # re-evaluate after each worker completes
    graph.add_edge("scheduler", "aggregator")  # when all tasks done
    return graph.compile()
```

### Q2: LangGraph Send API and @task interaction

**Send API lives in the DAG graph, NOT inside @task.** The existing `@task` wrapper in `agent.py` is a single-task decorator — it cannot fan out. The Send API is used from a `scheduler_node` function that returns `Send` objects as conditional edge targets:

```python
def scheduler_node(state: AgentState) -> list[Send]:
    ready = [t for t in state.dag["tasks"]
             if t["id"] not in state.completed
             and all(d in state.completed for d in t["deps"])]
    if not ready:
        return []   # → aggregator
    return [Send("worker", {"task_spec": t, "depth": 0,
                            "workdir": state.workdir, "auto": state.auto})
            for t in ready]
```

Workers do NOT use `@task` — they are plain `StateGraph` node functions that call `_run_agentic_loop()` directly. The `@task` decorator is LangGraph's task primitive for the functional API; the `StateGraph` API uses plain node functions.

### Q3: ProviderPlugin integration without breaking agent loop

**Surgical replacement of HTTP layer only.** The `_run_agentic_loop` signature changes minimally:

```python
# BEFORE
def _run_agentic_loop(messages, model, instructions, tokens, workdir, auto):
    # httpx.stream() call here

# AFTER
def _run_agentic_loop(messages, model_id, instructions, provider, workdir, auto):
    # provider.stream() call here — same loop logic
```

The `run()` function in `agent.py` absorbs the `config.resolve_model()` + `providers.get_provider()` calls and passes the resolved `provider` instance down. No other change to loop logic — iteration count, tool dispatch, SSE parsing (now inside provider), message accumulation all stay identical in structure.

**Migration path:**
1. Extract all HTTP + SSE logic from `_run_agentic_loop` → `providers/chatgpt.py:ChatGPTProvider.stream()`
2. `_run_agentic_loop` now calls `async for item in provider.stream(...)` instead
3. Existing tests pass against the same observable behavior
4. `TokenSet` and `_headers()` move to `providers/chatgpt.py` — internal details

### Q4: Module structure for providers/ and config.py

```
maestro/
├── agent.py           # _run_agentic_loop (HTTP stripped), run() (single-agent entry)
├── auth.py            # multi-slot store: get/set/remove/all_providers()
├── cli.py             # maestro run / auth / models subcommands
├── config.py          # resolve_model(agent_name) → (provider_id, model_id)
├── dag.py             # NEW: build_multi_agent_graph(), AgentState, run_multi()
├── domains.py         # NEW: DOMAIN_PROMPTS dict, domain validation
├── tools.py           # execute_tool, TOOL_SCHEMAS, DESTRUCTIVE_TOOLS (unchanged)
└── providers/
    ├── __init__.py    # discover_providers() lru_cache, get_provider(id)
    ├── base.py        # ProviderPlugin Protocol, Message, ToolCall, Tool
    ├── chatgpt.py     # ChatGPTProvider (migrates HTTP from agent.py)
    └── copilot.py     # CopilotProvider (device code OAuth, new)
```

**Key rule:** `providers/` knows nothing about `dag.py` or `tools.py`. It is a pure I/O layer. `dag.py` knows about `providers/` (to resolve the planner's provider) and `agent.py` (to call `_run_agentic_loop`). `agent.py` knows about `providers/` and `tools.py`. This is a clean dependency DAG with no cycles.

### Q5: Workers sharing state safely

**Two separate sharing mechanisms:**

1. **Filesystem sharing** (reads + writes across workers): Workers share a `workdir` (same `Path` passed to all). LangGraph runs workers in the same process concurrently via `asyncio` event loop. File system operations in `tools.py` are inherently serialized at the OS level for most cases. No additional locking needed for v1 — workers should operate on different files (domain separation ensures this).

2. **LangGraph state sharing** (results aggregation): `AgentState` uses reducers to safely merge parallel writes:

```python
from typing import Annotated
from operator import add

def merge_dicts(a: dict, b: dict) -> dict:
    return {**a, **b}

class AgentState(TypedDict):
    task: str
    dag: dict
    completed: Annotated[list[str], add]          # safe: list append reducer
    outputs: Annotated[dict[str, str], merge_dicts]  # safe: dict merge reducer
    errors: Annotated[list[str], add]             # safe: list append reducer
    workdir: Path                                  # read-only after init
    auto: bool                                     # read-only after init
    depth: int                                     # per-worker, not shared
```

Reducers guarantee that concurrent writes to `completed` and `outputs` from parallel workers are merged deterministically without races, because LangGraph applies reducers after each node completes.

**Depth tracking:** `depth` is passed as worker input, not stored in shared state. Each `Send` carries its own `depth` value. Workers increment it before recursing.

### Q6: Phase ordering — multi-provider first, then multi-agent

**Multi-provider MUST precede multi-agent.** This is a hard dependency:

```
Multi-Provider (Phase A)        Multi-Agent DAG (Phase B)
─────────────────────────       ───────────────────────────────
providers/base.py               dag.py (uses provider.stream() for planner)
providers/chatgpt.py            domains.py
providers/copilot.py            AgentState with reducers
auth.py (multi-slot)            scheduler_node with Send API
config.py resolve_model()       worker_node calling _run_agentic_loop()
_run_agentic_loop refactored    Planner uses config.resolve_model("planner")
CLI: auth / models
```

Phase B's Planner node calls `config.resolve_model("planner")` → `providers.get_provider(...)` → `provider.stream()`. Without Phase A's infrastructure, the Planner has nowhere to call. Workers similarly need the provider-abstracted `_run_agentic_loop`.

**They cannot be parallel** because Phase B's implementation directly depends on Phase A's interfaces being stable and tested.

---

## Build Order (Dependency Chain)

```
Step 1: providers/base.py
        ← defines neutral types (Message, Tool, ToolCall)
        ← no dependencies on anything else in maestro

Step 2: auth.py refactored (multi-slot)
        ← replaces single-user store
        ← no dependency on providers/base.py

Step 3: providers/chatgpt.py
        ← depends on: providers/base.py, auth.py
        ← migrates HTTP logic from agent.py

Step 4: config.py
        ← depends on: providers/__init__.py (for fallback to first provider)
        ← resolve_model() priority chain

Step 5: providers/__init__.py (registry)
        ← depends on: providers/base.py, pyproject.toml entry points
        ← discover_providers() wires chatgpt + copilot as builtins

Step 6: agent.py refactored
        ← _run_agentic_loop: replace httpx.stream() → provider.stream()
        ← depends on: providers/__init__.py, config.py
        ← all existing tests must pass at this step

Step 7: CLI auth/models subcommands
        ← depends on: providers/__init__.py, auth.py, config.py
        ← maestro auth login/logout/status, maestro models

Step 8: providers/copilot.py
        ← depends on: providers/base.py, auth.py
        ← device code OAuth flow, Copilot chat completions SSE

Step 9: domains.py
        ← standalone: DOMAIN_PROMPTS dict, no cross-dependencies
        ← can be built in parallel with steps 7-8

Step 10: dag.py — AgentState + planner_node
         ← depends on: providers/__init__.py, config.py, agent.py (step 6)

Step 11: dag.py — scheduler_node + Send API dispatch
         ← depends on: step 10 (AgentState established)

Step 12: dag.py — worker_node + recursion guard
         ← depends on: step 11, domains.py (step 9), _run_agentic_loop (step 6)

Step 13: dag.py — aggregator_node + run_multi() entry point
         ← depends on: steps 10-12

Step 14: CLI --multi flag wired to run_multi()
         ← depends on: step 13
```

---

## Anti-Patterns to Avoid

### Anti-Pattern 1: Modifying `_run_agentic_loop` signature drastically
**What:** Adding DAG state, Send API calls, or Planner logic inside `_run_agentic_loop`
**Why bad:** Breaks backward compatibility, conflates agent loop with orchestration
**Instead:** Keep `_run_agentic_loop` as a pure "given messages + provider, produce text" function. DAG orchestration lives entirely in `dag.py`.

### Anti-Pattern 2: Importing from `dag.py` inside `agent.py`
**What:** `agent.py` imports `AgentState` or `scheduler_node` to support `--multi`
**Why bad:** Creates a circular dependency. `dag.py` must import `agent.py`, not the reverse.
**Instead:** `cli.py` decides which entry point to call (`agent.run()` vs `dag.run_multi()`) based on `--multi` flag. `agent.py` has zero knowledge of `dag.py`.

### Anti-Pattern 3: Provider instances held as module globals
**What:** `PROVIDER = ChatGPTProvider()` at module level in `agent.py`
**Why bad:** Prevents testing with mock providers; makes parallel workers unable to use different providers
**Instead:** `providers.get_provider(id)` is `lru_cache` — same instance returned per process, but injected at call time into `_run_agentic_loop`. Workers can pass different `provider_id` strings.

### Anti-Pattern 4: Storing `depth` in shared AgentState
**What:** `AgentState.depth: int` incremented by workers
**Why bad:** Parallel workers would race on the same field; meaning is per-worker, not global
**Instead:** `depth` is carried in the `Send` payload (`WorkerInput.depth`) and never written back to shared state.

### Anti-Pattern 5: Workers communicating via in-memory state
**What:** Workers read each other's partial results from `AgentState.outputs` mid-execution
**Why bad:** LangGraph only commits state between node executions, not during. Leads to stale reads.
**Instead:** Workers communicate only via the shared filesystem (`workdir`). A worker that needs another's output declares a dependency (`deps`), which the Scheduler enforces by serializing execution order.

---

## Scalability Considerations

| Concern | At current (1 agent) | With multi-agent (N workers) |
|---------|---------------------|------------------------------|
| Parallelism | Sequential LLM calls | Concurrent `asyncio` tasks (LangGraph manages) |
| File contention | None | Domain separation prevents overlap; no locking needed v1 |
| Token usage | 1 context window | N context windows (each worker has its own) |
| Recursion safety | N/A | Max depth guard (default 2); hard fail at limit |
| State size | Single message list | `AgentState.outputs` grows linearly with tasks |
| Provider coupling | Hardwired to chatgpt | Plugin registry decouples; each worker can use a different model |

---

## Sources

- `/home/ervison/Documents/PROJETOS/labs/timeIA/maestro/maestro/agent.py` — existing implementation (verified)
- `/home/ervison/Documents/PROJETOS/labs/timeIA/maestro/docs/ideas/multi-agent-dag.md` — DAG design doc (approved)
- `/home/ervison/Documents/PROJETOS/labs/timeIA/maestro/docs/superpowers/specs/2026-04-17-multi-provider-plugin-design.md` — provider plugin spec (approved)
- `/home/ervison/Documents/PROJETOS/labs/timeIA/maestro/docs/superpowers/specs/2026-04-17-agentic-file-tools-design.md` — agentic file tools spec (approved)
- `/home/ervison/Documents/PROJETOS/labs/timeIA/maestro/.planning/PROJECT.md` — project requirements and constraints
- LangGraph Send API: https://langchain-ai.github.io/langgraph/concepts/low_level/#send (functional API vs StateGraph API distinction)
