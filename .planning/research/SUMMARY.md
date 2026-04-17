# Research Summary — Maestro

**Synthesized:** 2026-04-17  
**Project:** Brownfield extension of a Python CLI AI agent into a multi-agent DAG engine with multi-provider plugin support  
**Overall confidence:** HIGH — all sources verified against installed packages, official docs, and live codebase

---

## TL;DR

- **Phase order is a hard constraint:** Multi-Provider plugin system (providers/, config.py, auth.py refactor) MUST complete before Multi-Agent DAG — the Planner and Workers depend on `provider.stream()` which doesn't exist until Phase 1 is done.
- **Zero new dependencies needed:** Every required capability is covered by already-installed packages (langgraph 1.1.6, pydantic 2.11.7, httpx 0.28.1, httpx-sse 0.4.1) or Python stdlib (graphlib, importlib.metadata, typing.Protocol). No framework changes.
- **The most dangerous implementation mistake:** Not adding `Annotated[list, operator.add]` reducers to `AgentState` before wiring parallel workers — results in silent last-write-wins data loss with no exception raised.
- **Backward compatibility is non-negotiable:** All 26 existing tests must pass at every step. The `auth.py → providers/chatgpt.py` migration requires a backward-compat shim to avoid `ImportError` regressions before the transition is complete.
- **Workers are thin wrappers:** `_run_agentic_loop` is reused unchanged inside every Worker node — this is the architectural bet that minimizes new bug surface area.

---

## Stack Decisions

| Technology | Use | Version | Critical Gotcha |
|------------|-----|---------|-----------------|
| **LangGraph `StateGraph` + `Send`** | Multi-agent fan-out (Scheduler → Workers) | 1.1.6 ✅ installed | `@task` decorator is incompatible with `Send`/conditional edges — use plain node functions instead |
| **LangGraph `@entrypoint`/`@task`** | Keep as-is on single-agent path | 1.1.6 | Do NOT add DAG logic here; these are for observability/retry on the existing loop |
| **Pydantic v2 `BaseModel`** | DAG plan structured output + validation | 2.11.7 ✅ installed | Use `model_validate_json()` directly, not `json.loads()` + `model_validate()`; use `model_json_schema()` in the Planner prompt |
| **`importlib.metadata.entry_points`** | Provider plugin discovery | stdlib Python 3.12 | Entry points only resolve after `pip install -e .` — always reinstall after editing `pyproject.toml` |
| **`graphlib.TopologicalSorter`** | DAG dependency resolution in Scheduler | stdlib Python 3.9+ | Not reentrant — reconstruct from `dag + completed` on each Scheduler invocation; always catch `CycleError` |
| **`typing.Protocol` (`@runtime_checkable`)** | `ProviderPlugin` interface | stdlib | `isinstance()` only checks method presence, not signatures — add manual `_validate_provider()` in the registry |
| **`httpx.AsyncClient` + `httpx-sse`** | SSE streaming for all providers | 0.28.1 / 0.4.1 ✅ | Create a new `AsyncClient` per worker — never share a global client across concurrent coroutines |
| **GitHub OAuth Device Code Flow** | Copilot authentication | httpx (no new dep) | `slow_down` error must update the running interval (`+=5`), not just continue — ignoring it causes an infinite polling loop and potential token revocation |

**Model config format:** `"provider_id/model_id"` (e.g., `"github-copilot/gpt-4o"`) — validate format on load, never swallow `ValueError` from `parse_model()`.

**Copilot CLIENT_ID:** `Ov23li8tweQw6odWQebz` (from design spec) — MEDIUM confidence; must be validated against actual GitHub OAuth App registration before use.

---

## Feature Priorities

### Table Stakes (must ship — absence = product feels broken)

| Feature | Why | Notes |
|---------|-----|-------|
| Backward compatibility (`maestro run` unchanged) | Trust baseline; zero regressions on 26 tests | `--multi` is purely additive |
| `--multi` flag activates DAG mode | CLI convention | New surface area only |
| Planner → structured JSON DAG | Without explicit DAG, parallelism is opaque | Pydantic validation before scheduler sees it |
| Dependency-respecting execution | Sequential-when-needed is the whole value | Topological sort via `graphlib` |
| Domain specialization (domains.py) | Generic prompts → cross-contaminated output | 6 domains: backend/testing/docs/devops/data/general |
| Exit on error with diagnosis | Silent failure leaves half-baked state | Collect `errors` in state reducer; non-zero exit |
| `--auto` / `--workdir` pass-through to workers | Existing flags must work in multi-agent mode | Inherited via `Send` payload |
| Multi-provider auth (`maestro auth login/logout/status`) | Two providers without clear auth UX = confusion | Device code OAuth; multi-slot `auth.json` |
| `provider/model` config format | Industry convention | Fail loudly on malformed config |
| `maestro models` subcommand | Discoverability | Lists `provider.list_models()` per authenticated provider |
| Recursion depth guard (max 2) | Without it, misbehaving planner = infinite loop | Hard cap; required positional `depth` arg |
| Path guard in every worker | Security — not optional | Verify workdir flows through Send → _run_agentic_loop → tools |

### Differentiators (ship to beat AutoGen/CrewAI for CLI dev automation)

| Feature | Edge |
|---------|------|
| True parallel DAG execution via `Send` API | AutoGen/CrewAI default to sequential; LangGraph gives genuine concurrency |
| Domain-first decomposition (not agent-first) | Plannable, enumerable, testable — vs. free-form agent roles |
| Provider-neutral plugin system (Protocol + entry points) | Third-party providers via `pip install` with no maestro source changes |
| Shared filesystem as IPC bus | Simple, debuggable, inspectable — vs. in-memory message channels |
| Per-agent model config (planner cheap model, worker expensive model) | Cost optimization without code changes |

### Defer to v2 (explicit anti-features for v1)

- Human-in-the-loop DAG approval
- Streaming partial results during multi-agent run
- Persistent DAG state across sessions
- Per-provider retry/rate limiting
- Providers beyond ChatGPT + GitHub Copilot
- GitHub Enterprise Copilot
- Model picker TUI
- Aggregator node running by default (gate on `--aggregate` flag or DAG size)

---

## Architecture Notes

### Component Map (bottom-up build order)

```
TIER 0 — CLI SURFACE
  cli.py: maestro run [--multi] [--model] [--auto] [--workdir]
          maestro auth login/logout/status
          maestro models [--provider]
          ↓ dispatches to →

TIER 1 — PROVIDER INFRASTRUCTURE (new)
  providers/base.py    → ProviderPlugin Protocol, Message, Tool, ToolCall (neutral types)
  providers/__init__.py → discover_providers() [lru_cache], get_provider(id)
  providers/chatgpt.py  → migrated HTTP + SSE from agent.py
  providers/copilot.py  → device code OAuth, Copilot chat completions SSE
  config.py            → resolve_model(agent_name) → (provider_id, model_id)
  auth.py              → multi-slot ~/.maestro/auth.json store

TIER 2 — AGENT CORE (existing, surgically modified)
  agent.py:_run_agentic_loop() → provider.stream() replaces httpx.stream()
  tools.py → unchanged
  domains.py → NEW: DOMAIN_PROMPTS dict

TIER 3 — ORCHESTRATION (new)
  dag.py: AgentState + reducers
          planner_node (calls provider.stream for DAG JSON)
          scheduler_node (topological sort + Send dispatch)
          worker_node (calls _run_agentic_loop with domain prompt)
          aggregator_node (optional)
```

### File Structure

```
maestro/
├── agent.py           # _run_agentic_loop (HTTP stripped), run() (single-agent)
├── auth.py            # multi-slot store: get/set/remove/all_providers()
├── cli.py             # run / auth / models subcommands
├── config.py          # resolve_model(agent_name) → (provider_id, model_id)
├── dag.py             # NEW: build_multi_agent_graph(), AgentState, run_multi()
├── domains.py         # NEW: DOMAIN_PROMPTS dict
├── tools.py           # unchanged
└── providers/
    ├── __init__.py    # discover_providers() lru_cache, get_provider(id)
    ├── base.py        # ProviderPlugin Protocol, Message, ToolCall, Tool
    ├── chatgpt.py     # ChatGPTProvider (migrated from agent.py)
    └── copilot.py     # CopilotProvider (device code OAuth, new)
```

### Critical Integration Points

1. **`agent.py` surgery is minimal:** Only replace `httpx.stream()` with `provider.stream()` — loop logic, tool dispatch, SSE parsing stay structurally identical. Signature change: add `provider` param, remove tokens/HTTP internals.

2. **`dag.py` is a new file, never imported by `agent.py`:** `cli.py` decides which entry point to call (`agent.run()` vs `dag.run_multi()`) based on `--multi`. `agent.py` has zero knowledge of DAG.

3. **`AgentState` reducers are mandatory before any worker runs:**
   ```python
   class AgentState(TypedDict):
       completed: Annotated[list[str], operator.add]
       outputs: Annotated[dict[str, str], merge_dicts]
       errors: Annotated[list[str], operator.add]
       workdir: Path    # read-only
       auto: bool       # read-only
   ```

4. **`Send` payloads must be pure scalars:** Never pass the full parent `AgentState` to a `Send` — shallow copy bugs cause non-deterministic race conditions under parallel load.

5. **Dependency chain is acyclic:** `providers/` → no maestro imports; `agent.py` → `providers/` + `tools.py`; `dag.py` → `agent.py` + `providers/` + `domains.py`; `cli.py` → everything. No cycles.

---

## Pitfalls to Avoid

### P1: Missing AgentState Reducers → Silent Data Loss ⚠️ CRITICAL
**Risk:** Parallel workers silently overwrite each other's `completed` and `outputs` — no exception, just wrong results. Scheduler may loop infinitely.  
**Prevention:** Define `Annotated[list, operator.add]` and `Annotated[dict, merge_dicts]` on shared state fields before wiring ANY workers. Write a 2-worker test that asserts both outputs are present.

### P2: `Send` Payload Carries Mutable References → Race Conditions ⚠️ CRITICAL
**Risk:** Passing `state["config"]` (a nested dict) to multiple `Send` objects shares the same Python object — mutations in one worker affect siblings.  
**Prevention:** `Send` payloads must contain only scalars (`str`, `int`, `bool`, `Path`). Use `copy.deepcopy` on any nested object.

### P3: `auth.py` `TokenSet` Move Breaks 26 Tests ⚠️ CRITICAL
**Risk:** Moving `TokenSet` to `providers/chatgpt.py` causes `ImportError` across the entire test suite.  
**Prevention:** Add a re-export shim in `auth.py` immediately before touching any import: `from maestro.providers.chatgpt import TokenSet`. Run `pytest` first, then migrate incrementally.

### P4: Recursion Depth Guard Bypassed by Missing `depth` Arg → Infinite Loop ⚠️ HIGH
**Risk:** If `_run_agentic_loop` or the worker entry point is called without forwarding `depth`, every recursive call starts at 0 — guard is never triggered.  
**Prevention:** Make `depth` a required positional argument (no default) in the recursive entry point so forgetting it is a `TypeError`, not a silent bypass.

### P5: `slow_down` OAuth Error Not Handled → Infinite Polling + Token Revocation ⚠️ HIGH
**Risk:** Treating `slow_down` the same as `authorization_pending` (just continuing) accumulates GitHub's 5s penalty each time and can result in `access_denied` or a ban.  
**Prevention:** Maintain a `current_interval` variable; on `slow_down`, do `current_interval += 5` and continue. Never reset to the original interval.

### P6: DAG Validation Skipped → Hallucinated IDs / Cycles Crash Scheduler ⚠️ HIGH
**Risk:** LLM-generated DAGs may contain unknown dep IDs, self-references, or cycles. `graphlib.CycleError` or `KeyError` in the scheduler.  
**Prevention:** Run a `validate_dag()` function immediately after Pydantic parsing — before passing to the scheduler. Check all dep IDs exist in the task list; catch `CycleError` from `TopologicalSorter.prepare()`.

### P7: Worker Path Guard Not Inherited → Security Boundary Broken ⚠️ HIGH
**Risk:** Workers receiving `workdir` via `Send` payload but calling `_run_agentic_loop` without forwarding it → tools execute with wrong or absent workdir containment.  
**Prevention:** Verify the full chain: `Send(workdir)` → `worker_node(workdir)` → `_run_agentic_loop(workdir)` → `execute_tool(workdir)`. Integration test: attempt a write outside workdir and assert it's blocked.

### P8: `lru_cache` on `discover_providers()` Poisons Test Suite ⚠️ MODERATE
**Risk:** Cached provider registry from test A leaks into test B — order-dependent failures.  
**Prevention:** Call `discover_providers.cache_clear()` in a `pytest` fixture with `autouse=True` for any test touching provider discovery.

---

## Phase Ordering Implications

### The Required Order

```
Phase 1: Multi-Provider Infrastructure
  └─ Unblocks Phase 2 (Workers need provider.stream())
  └─ Refactors the HTTP layer — biggest risk to existing tests
  └─ Must complete with all 26 tests green before Phase 2 starts

Phase 2: Multi-Agent DAG
  └─ Depends on Phase 1 being stable
  └─ New files (dag.py, domains.py) — low breakage risk
  └─ Internal Phase 2 order is also a dependency chain (see below)
```

### Phase 1 Build Order (14 steps mapped)

1. `providers/base.py` — neutral types; no deps; write first
2. `auth.py` refactor to multi-slot (add backward-compat shim for `TokenSet`)
3. `providers/chatgpt.py` — migrate HTTP from `agent.py`
4. `config.py` — `resolve_model()` priority chain
5. `providers/__init__.py` — registry with `lru_cache` + `_validate_provider()`
6. `agent.py` refactor — replace `httpx.stream()` → `provider.stream()`; **run all 26 tests here**
7. CLI auth/models subcommands
8. `providers/copilot.py` — device code OAuth + Copilot SSE (can run parallel with step 7)

### Phase 2 Build Order

9. `domains.py` — pure data dict; zero deps; can write anytime after Phase 1 starts
10. `dag.py` — `AgentState` (with reducers) + `planner_node`
11. `dag.py` — `scheduler_node` + `Send` dispatch
12. `dag.py` — `worker_node` + recursion depth guard
13. `dag.py` — `aggregator_node` (optional) + `run_multi()` entry point
14. CLI `--multi` flag wired to `run_multi()`

### Research Flags for Roadmapper

| Phase | Research Needed? | Notes |
|-------|-----------------|-------|
| Phase 1 — Provider Infrastructure | ✅ Complete | All patterns verified, HIGH confidence |
| Phase 1 — Copilot OAuth | ⚠️ Verify CLIENT_ID | `Ov23li8tweQw6odWQebz` from design spec — confirm with actual GitHub OAuth App before shipping |
| Phase 1 — Copilot API headers | ⚠️ MEDIUM confidence | `x-initiator` and `Openai-Intent` headers from design spec, not public docs — may need adjustment |
| Phase 2 — LangGraph Send API | ✅ Complete | Verified against LangGraph 1.1.6 docs + installed version |
| Phase 2 — Planner prompt engineering | 🔬 Needs iteration | Max tasks guard + "atomic but not micro" instruction needed; content requires tuning in implementation |
| Phase 2 — Aggregator | ✅ Low risk | Gate on `--aggregate` flag; don't run by default |

### What Cannot Be Parallelized

- Phase 1 must precede Phase 2 (hard)
- Within Phase 1: `providers/base.py` before `chatgpt.py` before `agent.py` refactor (hard)
- Within Phase 2: AgentState + reducers before scheduler before worker (hard)
- `domains.py` is the only step with zero dependencies — can be written at any point

---

## Confidence Assessment

| Area | Confidence | Basis |
|------|------------|-------|
| LangGraph Send API + reducers | HIGH | Official docs (Context7) + verified working in 1.1.6 |
| Pydantic v2 structured output | HIGH | Official docs + installed 2.11.7 |
| `importlib.metadata` entry points | HIGH | Stdlib; live-tested in Python 3.12.7 |
| `graphlib.TopologicalSorter` | HIGH | Stdlib; CycleError handling verified |
| httpx async SSE streaming | HIGH | Official docs + installed 0.28.1 |
| `ProviderPlugin` Protocol pattern | HIGH | Stdlib typing.Protocol; well-understood |
| GitHub device code OAuth flow | HIGH | Official GitHub docs |
| Copilot CLIENT_ID (`Ov23li8tweQw6odWQebz`) | MEDIUM | From design spec only — needs GitHub OAuth App verification |
| Copilot API headers (`x-initiator`, `Openai-Intent`) | MEDIUM | Design spec only; not in public docs |
| Planner system prompt quality | LOW | Requires empirical iteration; no offline source for "correct" LLM prompts |

**Gaps requiring attention during implementation:**
1. Validate Copilot CLIENT_ID against the actual registered GitHub OAuth App before wiring the auth flow
2. Test Copilot API headers against the live endpoint before finalizing `CopilotProvider.stream()`
3. Planner system prompt needs iteration to prevent DAG over-decomposition (>10 micro-tasks for simple inputs)

---

## Sources

| Source | Confidence | Used In |
|--------|------------|---------|
| LangGraph 1.x official docs (Context7) | HIGH | Stack, Architecture, Pitfalls |
| Pydantic 2.x official docs (Context7) | HIGH | Stack |
| GitHub OAuth Device Flow docs | HIGH | Stack, Pitfalls |
| AutoGen, CrewAI, LangGraph Supervisor docs (Context7) | HIGH | Features |
| Python stdlib docs (graphlib, importlib.metadata) | HIGH | Stack |
| `maestro/agent.py` (existing implementation) | HIGH | Architecture |
| `docs/ideas/multi-agent-dag.md` (approved design) | HIGH | All sections |
| `docs/superpowers/specs/2026-04-17-multi-provider-plugin-design.md` | HIGH | Stack, Architecture |
| `.planning/PROJECT.md` (requirements) | HIGH | All sections |
