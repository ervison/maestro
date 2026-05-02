# AGENTS.md

## Project

Maestro is a CLI-driven AI agent (Python 3.12, LangGraph 1.1.6, httpx 0.28, Pydantic 2.11) that executes software engineering tasks using file-system tools and shell commands. Entry point: `maestro = "maestro.cli:main"`. Two execution modes: single-agent via LangGraph `@entrypoint/@task` and multi-agent DAG via `StateGraph` + `Send` API. Provider plugins are structural (`typing.Protocol`, `@runtime_checkable`) and discovered via `importlib.metadata` entry points (`"maestro.providers"` group).

---

## Setup & Install

```bash
pip install -e .[dev]
```

After modifying `pyproject.toml` entry points **you must reinstall** (`pip install -e .`). Entry points only resolve after install; tests will fail with `KeyError` otherwise.

Config file: `~/.maestro/config.json` (override with `MAESTRO_CONFIG_FILE`). Written with `0o600` permissions.

---

## Quality Gates

| Gate | Command | Notes |
|------|---------|-------|
| Tests (unit) | `pytest tests/ -v` | Excludes integration/smoke markers |
| Tests (integration) | `MAESTRO_RUN_INTEGRATION=1 pytest tests/ -v -m integration` | Requires real credentials |
| Tests (copilot) | `MAESTRO_COPILOT_SMOKE=1 pytest tests/ -v -m copilot_smoke` | Requires GitHub Copilot credentials |
| Single test file | `pytest tests/test_cli.py -v` | |
| Single test | `pytest tests/test_cli.py::test_name -v` | |
| Coverage | `pytest tests/ --cov=maestro --cov-report=xml` | Writes `coverage.xml` for SonarQube |
| Lint | `ruff check maestro/ tests/` | No ruff config found; defaults apply |
| SonarQube | Project `maestro-python` at `http://192.168.88.11:9001` | `sonar-project.properties` in root |

`asyncio_mode = "auto"` is set in `pyproject.toml` — async test functions are auto-detected; no `@pytest.mark.asyncio` needed.

CI (`planning-consistency.yml`): runs `maestro planning check` then `pytest tests/test_planning_consistency.py tests/test_cli_planning.py -q`.

---

## Architecture

```
maestro/
  cli.py          — argparse entry point (all `maestro *` commands)
  agent.py        — single-agent loop (`@entrypoint/@task`, ChatGPT Responses API)
  multi_agent.py  — multi-agent DAG (StateGraph, Send, scheduler/worker/aggregator)
  tools.py        — file/shell tools with `PathOutsideWorkdirError` path guard
  config.py       — Config dataclass, load/save from ~/.maestro/config.json
  auth.py         — OAuth token store
  models.py       — model listing + resolution
  domains.py      — domain-specialized system prompts for workers
  planning.py     — planning artifact consistency checker
  planner/        — Planner node (LLM → AgentPlan), schemas, DAG validator
  providers/      — Plugin system: base.py (Protocol), registry.py (discovery), chatgpt.py, copilot.py
  sdlc/           — SDLC discovery planner (`maestro discover`)
  dashboard/      — Dashboard server + emitter for --multi mode
```

### Key constraints

- **Path guard**: `resolve_path()` in `tools.py` must apply inside every Worker, not just at CLI level. Use it for ALL file operations.
- **Recursion safety**: `max_depth` guard is mandatory; infinite recursion is a hard failure.
- **Backward compatibility**: `maestro run` (no `--multi`) must behave identically to the single-agent `_run_agentic_loop`. Do not regress on ~20 existing test files.
- **No new dependencies**: No `networkx` (use `graphlib`), no `aiohttp` (use `httpx`), no `pkg_resources` (use `importlib.metadata`). These are banned.

### LangGraph patterns (SEND API)

These are the most error-prone parts of the codebase:

- **`@entrypoint/@task` and `Send` are incompatible**: Keep `@entrypoint/@task` for the single-agent loop only. Multi-agent DAG uses `StateGraph` + `Send`.
- **`Annotated[list, operator.add]` is the ONLY safe reducer for parallel writes**. Without it, workers silently overwrite each other's state.
- **`Send` receives a snapshot** at dispatch time. Workers cannot read each other's in-progress output. Coordinate via shared filesystem, not memory.
- **TopologicalSorter is NOT reentrant** across LangGraph node invocations. Reconstruct it from `dag` + `completed` on each Scheduler call.
- **The routing function must return `list[Send]`** (not a string edge name) for fan-out. Mixing both causes LangGraph runtime errors.
- **`StateGraph.compile()` must be called before `graph.invoke()`**.

### Pydantic v2 (NO v1 patterns)

- `model_validate_json()` for parsing LLM output (not `json.loads()` + manual dict)
- `model_json_schema()` for generating planner prompt schemas
- `ConfigDict(extra="forbid")` for strict parsing
- **NEVER**: `parse_obj`, `schema()`, `__fields__` — these are v1 API

### Provider plugins

- Plugin interface: `ProviderPlugin` Protocol in `providers/base.py` with `@runtime_checkable`
- External providers use `"maestro.providers"` entry point group — no need to `import maestro`
- Registry validates signatures at load time (`registry.py:_is_valid_provider`)
- Provider reset: `discover_providers.cache_clear()` to invalidate the `@lru_cache(maxsize=1)`
- ChatGPT uses the Responses API format; Copilot uses OpenAI chat completions — incompatible wire formats, separate providers

---

## Testing

- **Default markers**: Tests run without markers include unit tests. Integration/copilot tests are opt-in via env vars.
- **Provider fixture tests**: `tests/test_provider_install_smoke.py` installs a real pip package (`tests/fixtures/hello_provider/`) — run `pip install -e .` first.
- **SDLC tests** may open the gap questionnaire server on port 4041 — ensure the port is free or skip those tests.
- **No conftest files** at any level — no shared fixtures or markers defined by default.

---

## Common Mistakes

- **Modifying `pyproject.toml` entry points without reinstalling** — causes `KeyError` in tests. Always `pip install -e .` after entry point changes.
- **Using `parse_obj()` or `schema()`** — these are Pydantic v1 only. Use `model_validate()` / `model_json_schema()`.
- **Sharing a single `AsyncClient` across workers** — each worker gets its own `async with httpx.AsyncClient()` context.
- **Parsing `[DONE]` as JSON** — always check the sentinel before `json.loads()` in SSE streams.
- **Importing `networkx` for topological sort** — `graphlib.TopologicalSorter` is stdlib and already used. Do not add networkx.
- **Forgetting to reconstruct TopologicalSorter** per scheduler invocation — it's not reentrant.
- **Mixing string edges and `Send` returns** in one conditional edge function — LangGraph raises runtime error.

---

## Skill Routing

### Always apply

- `verification-before-completion` — REQUIRED before every completion claim; run tests first
- `systematic-debugging` — REQUIRED before proposing any fix for a bug

### Apply when triggered

- `python-patterns` — when writing or reviewing Python application code (not tests)
- `python-testing` — when writing or reviewing pytest tests, fixtures, mocks
- `brainstorming` — before creative/feature work that lacks an approved spec
- `writing-plans` — when a validated spec must become a step-by-step implementation plan
- `test-driven-development` — when implementing features or bugfixes after behavior is understood

### GSD workflow

Before using Edit, Write, or other file-changing tools, start through a GSD command:
- `/gsd-quick` for small fixes, doc updates, and ad-hoc tasks
- `/gsd-debug` for investigation and bug fixing
- `/gsd-execute-phase` for planned phase work
