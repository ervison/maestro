# Domain Pitfalls

**Domain:** Multi-agent DAG execution + multi-provider plugin system (Python CLI AI agent)
**Researched:** 2026-04-17
**Confidence:** HIGH (LangGraph: official docs; OAuth device flow: official GitHub docs; Plugin/entry-points: verified Python packaging docs; others: high-confidence pattern analysis of the specific codebase)

---

## Critical Pitfalls

Mistakes that cause rewrites, hard-to-debug state corruption, or silent behavioral failures.

---

### Pitfall 1: Send API State — Missing Reducer Causes Last-Write-Wins Corruption

**What goes wrong:**  
`Send` dispatches multiple workers in parallel. Each worker returns `{"outputs": {...}}` or `{"completed": [...]}`. If those state keys have **no reducer annotation**, LangGraph uses last-write-wins — whichever coroutine resolves last silently overwrites all the others. You get a `completed` list with one entry instead of N, and `outputs` with only the last worker's result. No exception is raised.

**Why it happens:**  
LangGraph state defaults to replacement semantics. Reducers must be **explicitly declared** in the `TypedDict` via `Annotated`. It is easy to miss this during initial scaffolding because a single-worker test passes — the bug only manifests with ≥2 concurrent workers.

**Consequences:**  
- Silently dropped worker outputs — tasks appear done but results are missing
- Topological scheduler re-triggers workers because `completed` never grows to full size
- Possible infinite execution loop at the scheduler re-evaluation step

**Prevention:**  
```python
from typing import Annotated
from operator import add

def merge_dicts(a: dict, b: dict) -> dict:
    return {**a, **b}

class AgentState(TypedDict):
    task: str
    dag: dict
    completed: Annotated[list[str], add]          # ← reducer required
    outputs: Annotated[dict[str, str], merge_dicts]  # ← reducer required
    errors: Annotated[list[str], add]             # ← reducer required
```
Add a unit test that runs exactly two workers that write to the same key, then asserts both values are present.

**Detection warning signs:**
- `len(state["completed"]) < expected_tasks` after all workers return
- `outputs` dict has only one entry when multiple workers ran
- Scheduler loops more times than expected

**Phase:** Multi-Agent DAG (Phase 1 of the two-workstream plan). Do not write the scheduler until reducers are defined and tested in isolation.

---

### Pitfall 2: Send API — Passing Mutable State Snapshot to Each Send Creates Shared Reference Bugs

**What goes wrong:**  
The `continue_to_workers` conditional edge function creates `Send("worker", state_slice)` for each task. If `state_slice` is a reference to (or shallow copy of) the parent state dict rather than an isolated payload, mutations inside one worker (e.g., appending to a list) can affect sibling workers mid-execution in the same event loop turn.

**Why it happens:**  
Python dict copies are shallow. `{"task": task, "workdir": state["workdir"]}` is safe, but `{"config": state["config"]}` passes the same nested dict object to all workers.

**Consequences:**  
- Non-deterministic worker behavior that only appears under load (race condition)
- Extremely hard to reproduce in unit tests that mock workers

**Prevention:**  
Always construct `Send` payloads with only the scalar fields each worker needs. Never pass the full parent `AgentState`. Use `copy.deepcopy` on any nested objects included in the payload.

```python
def dispatch_workers(state: AgentState) -> list[Send]:
    return [
        Send("worker", {
            "task_id": task["id"],
            "domain": task["domain"],
            "prompt": task["prompt"],
            "workdir": state["workdir"],   # str — safe
            "depth": state.get("depth", 0),  # int — safe
        })
        for task in ready_tasks(state)
    ]
```

**Detection warning signs:**
- Worker behavior changes depending on how many siblings it has
- Tests pass individually but fail when run together

**Phase:** Multi-Agent DAG. Code review checklist: every `Send()` payload must be pure scalars or deepcopy.

---

### Pitfall 3: Planner Hallucinated Task IDs and Self-Referential / Cyclic Dependencies

**What goes wrong:**  
The Planner LLM produces a DAG JSON where:
- A task references a `dep` ID that does not exist in the `tasks` list (e.g., `"deps": ["t0"]` when IDs start at `t1`)
- A task references itself: `{"id": "t2", "deps": ["t2"]}`
- Two tasks reference each other: `t2 deps t3, t3 deps t2` (cycle)

The topological sort raises a `ValueError` or hangs. If you swallow the exception, the scheduler silently skips tasks.

**Why it happens:**  
`with_structured_output` enforces JSON schema shape (fields present, types match) but **does not validate cross-field references**. The model is unaware of referential integrity constraints. This gets worse with longer task lists or vague user prompts.

**Prevention:**  
Validate the DAG immediately after parsing, before handing it to the scheduler:

```python
def validate_dag(tasks: list[dict]) -> None:
    ids = {t["id"] for t in tasks}
    for t in tasks:
        for dep in t.get("deps", []):
            if dep not in ids:
                raise ValueError(f"Task {t['id']!r} references unknown dep {dep!r}")
    # Cycle detection: Kahn's algorithm
    in_degree = {t["id"]: 0 for t in tasks}
    edges = {t["id"]: t.get("deps", []) for t in tasks}
    for deps in edges.values():
        for d in deps:
            in_degree[d] = in_degree.get(d, 0)  # already covered
    # standard topological sort — if queue empties before all nodes processed → cycle
    ...
```

Add a Pydantic validator on the `DAG` model that runs cross-field checks.

**Detection warning signs:**
- `KeyError` or `networkx.exception.NetworkXUnfeasible` in the scheduler
- DAG JSON has a `deps` list containing an ID not in the tasks list
- Topological sort returns fewer tasks than expected

**Phase:** Multi-Agent DAG. Planner output validation must be its own tested module before the scheduler is wired.

---

### Pitfall 4: Recursive Sub-Planning Bypasses the Depth Guard via Context Loss

**What goes wrong:**  
The depth guard `if current_depth >= max_depth: skip recursion` works correctly when the depth counter is passed explicitly. But if the worker calls `_run_agentic_loop` or instantiates a sub-planner **without forwarding the `depth` parameter**, every recursive call starts at depth 0 again. The guard is bypassed and recursion is unbounded.

**Why it happens:**  
`_run_agentic_loop` has a growing signature. Adding `depth=0` as a keyword argument is easy to miss when calling it from a new worker context. Python has no static enforcement that this parameter is passed.

**Consequences:**  
- Infinite recursion until API rate limit, timeout, or OOM
- Since workers use the real filesystem, runaway recursion can generate gigabytes of files

**Prevention:**  
- Make `depth` a **required positional argument** (not keyword with default) in the recursive worker entry point, so forgetting it is a `TypeError` at call time
- Add a hard guard at the top of any function that can recurse:
  ```python
  MAX_DEPTH = 2

  def run_worker(task, depth: int):  # required, no default
      if depth > MAX_DEPTH:
          return {"error": f"Max recursion depth {MAX_DEPTH} exceeded for task {task['id']!r}"}
      ...
  ```
- Test: write a recursive worker test where the sub-planner is called with `depth=MAX_DEPTH` and assert it returns the guard error rather than recursing.

**Detection warning signs:**
- `RecursionError` in Python (stack overflow)
- Unexpected proliferation of files in workdir during integration tests
- Worker completing but generating far more LLM calls than a flat plan would require

**Phase:** Multi-Agent DAG. Depth guard is mandatory before any recursive worker is wired. Test it as a hard constraint, not an optional check.

---

### Pitfall 5: `lru_cache` on `discover_providers()` Freezes the Registry Across Tests

**What goes wrong:**  
The spec uses `@lru_cache(maxsize=1)` on `discover_providers()`. In the test suite, a test that registers a mock provider will see its result cached. The next test that calls `discover_providers()` gets the stale cached dict including the mock provider — or missing a provider that a later test added.

**Why it happens:**  
`lru_cache` is process-global. In pytest, all tests share the same process. `importlib.metadata.entry_points` is mocked in test A; lru_cache prevents test B from re-invoking the real function.

**Consequences:**  
- Test order–dependent failures (tests pass in isolation, fail together)
- False positives: test using a mock provider accidentally uses a cached real provider

**Prevention:**  
```python
# In tests:
from maestro.providers import discover_providers

def test_my_provider(monkeypatch):
    discover_providers.cache_clear()  # always clear before mocking
    monkeypatch.setattr("importlib.metadata.entry_points", ...)
    ...
    discover_providers.cache_clear()  # clean up after
```

Or: use a fixture with `autouse=True` that calls `cache_clear()` before each test that touches provider discovery.

**Detection warning signs:**
- Tests fail when run in full suite but pass individually (`pytest test_provider_registry.py`)
- Provider registry contains unexpected entries in a test

**Phase:** Multi-Provider Plugin (Phase 2). Add `cache_clear()` calls to the test fixture template before writing any provider tests.

---

### Pitfall 6: Entry Point Discovery Fails Silently in Dev Mode (Editable Install)

**What goes wrong:**  
In a dev environment with `pip install -e .`, `importlib.metadata.entry_points(group="maestro.providers")` returns an empty list if the package was not properly re-installed after `pyproject.toml` changes. The registry is empty, `get_provider()` raises `ValueError: Unknown provider`, and the error message looks like a provider config issue — not a packaging issue.

**Why it happens:**  
Editable installs do not auto-update metadata when `pyproject.toml` changes. The developer adds a new entry point, runs the code, and gets a confusing error.

**Consequences:**  
- Hours lost debugging what appears to be a config or auth failure
- CI passes (clean install) but local dev breaks

**Prevention:**  
- In the error message from `get_provider()`, include a dev hint:
  ```python
  raise ValueError(
      f"Unknown provider: {provider_id!r}. Available: {list(providers)}. "
      "If running in dev mode, try: pip install -e . --force-reinstall"
  )
  ```
- Add `pip install -e .` to the dev setup instructions for the plugin system phase
- Test entry point discovery with a real install in CI (not just mocked)

**Detection warning signs:**
- `discover_providers()` returns `{}` despite correct `pyproject.toml`
- Error appears immediately on first provider call, before any auth check

**Phase:** Multi-Provider Plugin. First thing to verify after wiring entry points.

---

### Pitfall 7: Protocol Structural Typing Allows Silent Interface Drift

**What goes wrong:**  
`ProviderPlugin` is a `Protocol` (structural typing). A provider that forgets to implement `list_models()` is not caught at import time or at registry load time. It is only caught at runtime when `list_models()` is called — potentially in a prod deployment.

**Why it happens:**  
`Protocol` does not enforce implementation at class definition time. There is no `super().__init__()` call or ABC registration check. `isinstance(obj, ProviderPlugin)` returns `True` as long as the object has the right method signatures — but it does not check at import time.

**Consequences:**  
- `maestro models` command raises `AttributeError` against a provider that forgot `list_models()`
- External plugin authors ship broken providers that appear to install correctly

**Prevention:**  
Add a runtime validation step in `discover_providers()`:

```python
REQUIRED_METHODS = ["list_models", "stream", "auth_required", "login", "is_authenticated"]

def _validate_provider(instance: object) -> None:
    for method in REQUIRED_METHODS:
        if not callable(getattr(instance, method, None)):
            raise TypeError(
                f"Provider {instance!r} missing required method: {method!r}. "
                "Check ProviderPlugin Protocol in maestro/providers/base.py"
            )
```

**Detection warning signs:**
- New provider installs without error but `maestro models` fails with `AttributeError`
- Third-party plugin passes `isinstance` check but missing a method

**Phase:** Multi-Provider Plugin. Add validation inside `discover_providers()` on initial implementation, not as a later hardening step.

---

### Pitfall 8: OAuth Device Code — Ignoring `slow_down` Error Doubles Polling Rate and Triggers Hard Ban

**What goes wrong:**  
GitHub's device flow returns `slow_down` when the poller hits the interval limit. Each `slow_down` adds 5 seconds to the minimum interval. If the poller treats `slow_down` the same as `authorization_pending` (i.e., just continues with the original interval), it keeps hitting the limit, accumulates `slow_down` penalties, and eventually gets `access_denied` or a temporary ban.

**Why it happens:**  
The spec documents `POLLING_SAFETY_MARGIN = 3` (polling at `interval + 3`) but does not show explicit handling of `slow_down` as a separate branch that *updates the running interval*.

**Consequences:**  
- Login command runs forever without completing
- GitHub may revoke the device code early
- User sees no clear error message

**Prevention:**  
```python
current_interval = interval + POLLING_SAFETY_MARGIN

while True:
    await asyncio.sleep(current_interval)
    response = await poll_token(device_code)

    error = response.get("error")
    if error == "authorization_pending":
        continue
    elif error == "slow_down":
        current_interval += 5   # ← update running interval, not the original
        continue
    elif error == "expired_token":
        raise RuntimeError("Device code expired. Please run 'maestro auth login' again.")
    elif error == "access_denied":
        raise RuntimeError("Authorization cancelled by user.")
    elif "access_token" in response:
        return response["access_token"]
    else:
        raise RuntimeError(f"Unexpected OAuth response: {response}")
```

**Detection warning signs:**
- `maestro auth login github-copilot` hangs indefinitely after user authorized in browser
- GitHub API returns 200 with `{"error": "slow_down"}` in response body repeatedly
- Token never appears even after user completes browser step

**Phase:** Multi-Provider Plugin (Copilot provider). This is a hard requirement for the polling loop — test with a mock that returns `slow_down` twice before returning the token.

---

### Pitfall 9: Backward Compatibility — Existing `auth.py` TokenSet Usage Breaks When Moved to Provider Module

**What goes wrong:**  
The existing `agent.py` calls `auth.py` directly (e.g., `auth.get_token()`, `auth.TokenSet`). The refactor moves `TokenSet` to `providers/chatgpt.py` and turns `auth.py` into a generic key-value store. Any test or code that imports `from maestro.auth import TokenSet` or calls `auth.get_token()` will raise `ImportError` or `AttributeError` after the move.

**Why it happens:**  
Brownfield refactor. The old interface is coupled to the ChatGPT-specific data structure. Moving it is correct, but it breaks existing import paths.

**Consequences:**  
- All 26 existing tests fail immediately after the refactor
- The failure message (`ImportError`) is cryptic if the developer forgot about the import path change

**Prevention:**  
Keep a backward-compatibility shim in `auth.py` during the transition:

```python
# auth.py — backward compat shim, remove after Phase 2 complete
from maestro.providers.chatgpt import TokenSet  # re-export
```

Run the full test suite (`pytest`) as the first step of the provider refactor, before writing any new code. If it passes, the shim is working. Only remove the shim after all tests have been updated to use the new import path.

**Detection warning signs:**
- `ImportError: cannot import name 'TokenSet' from 'maestro.auth'`
- Tests fail immediately after restructuring `auth.py`, before any logic changes

**Phase:** Multi-Provider Plugin — first task. Never break the import path without a shim in place.

---

### Pitfall 10: Worker Path Guard Not Inherited — Workers Execute Shell Commands Outside Workdir

**What goes wrong:**  
The existing path guard (`workdir` containment, no `..` traversal) is enforced at the CLI level and inside `tools.py`. When workers are spawned via `Send`, they receive a `workdir` payload field, but if `_run_agentic_loop` is called without passing the workdir through to the tool executor, the path guard defaults to `cwd` or is absent — letting a worker write to arbitrary paths.

**Why it happens:**  
`_run_agentic_loop` was designed for single-agent use where workdir is set once at CLI startup. Multi-agent reuse may assume it "just works" without verifying that each worker's tool calls are scoped to the right directory.

**Consequences:**  
- Worker writes files outside the intended project directory
- Security boundary broken — a malicious or hallucinating prompt can escape the workdir

**Prevention:**  
- Explicitly verify that the `workdir` parameter flows from `Send` payload → worker invocation → `_run_agentic_loop` → tool executor
- Add an integration test: `worker(workdir="/tmp/test_project")` attempts to write to `/tmp/outside` via `execute_shell "touch /tmp/outside"` and assert it is blocked

**Detection warning signs:**
- Files appearing in `$HOME` or project root during multi-agent tests
- Worker error logs mentioning path outside the configured workdir

**Phase:** Multi-Agent DAG. This is a security invariant — verify it in the first worker integration test.

---

## Moderate Pitfalls

### Pitfall 11: Testing LangGraph Send — Mocking the Graph Prevents Catching Integration Bugs

**What goes wrong:**  
Tests that mock the entire graph or replace the scheduler with a stub don't exercise the actual `Send` dispatch, reducer merge, or scheduler loop. The tests pass but the real graph has an untested reducer or a missing edge.

**Prevention:**  
Use a **real LangGraph graph in tests** but mock only the LLM calls and HTTP calls:
- Mock `provider.stream()` to return canned responses immediately
- Let the graph run with `graph.invoke({...})` end-to-end
- Assert on `state["completed"]`, `state["outputs"]` — the actual merged state

For fast unit tests, keep graph tests separate from LLM/HTTP tests. Graph topology tests should run without network calls.

**Phase:** Multi-Agent DAG testing phase.

---

### Pitfall 12: Testing SSE Streams — `httpx` MockTransport Requires Exact Byte Framing

**What goes wrong:**  
When mocking SSE streams with `httpx.MockTransport`, returning a plain string response does not simulate a streaming response. The existing `_run_agentic_loop` iterates over SSE events; a mock that returns a bulk response will either fail to parse or return all content in one chunk, hiding bugs in chunk reassembly logic.

**Prevention:**  
Build a test SSE helper that yields properly framed `data:` lines:

```python
def make_sse_response(chunks: list[str]) -> bytes:
    lines = []
    for chunk in chunks:
        payload = json.dumps({"choices": [{"delta": {"content": chunk}}]})
        lines.append(f"data: {payload}\n\n")
    lines.append("data: [DONE]\n\n")
    return "".join(lines).encode()
```

**Phase:** Multi-Provider Plugin — `test_copilot_stream.py` and `test_chatgpt_provider.py`.

---

### Pitfall 13: Config Resolution — Missing `provider_id/` Prefix in Model String Fails Silently

**What goes wrong:**  
If `~/.maestro/config.json` contains `"model": "gpt-4o"` (missing provider prefix), `parse_model()` raises `ValueError`. But if this is caught too broadly (e.g., `except Exception: use_default()`), the system silently falls back to the default model — masking a misconfiguration.

**Prevention:**  
- `parse_model()` must raise with a clear message: `"Model must be in format provider/model, got: 'gpt-4o'"`
- Never swallow this error with a broad except — let it propagate to the user
- Validate config format on first load, not lazily on first use

**Phase:** Multi-Provider Plugin — `config.py` and `test_config.py`.

---

### Pitfall 14: DAG Over-Decomposition — Planner Creates Too Many Fine-Grained Tasks

**What goes wrong:**  
For a simple task, the Planner may create 8–10 micro-tasks (e.g., "create file", "add import", "write function", "add test file") that are all trivially sequential. This defeats parallelism, multiplies LLM API calls, and makes the output harder to read.

**Prevention:**  
- The system prompt for the Planner must explicitly instruct: "keep tasks atomic but not micro; each task should represent a meaningful unit of work that takes 1-3 agent turns"
- Add a max-task guard: reject DAGs with more than N tasks and ask the planner to consolidate
- Test: send a simple single-domain task to the planner and assert it produces ≤ 3 tasks

**Phase:** Multi-Agent DAG — Planner system prompt engineering.

---

## Minor Pitfalls

### Pitfall 15: `auth.json` File Permissions Not Enforced on Read

**What goes wrong:**  
The spec says `auth.json` is written with `mode 0o600`. But if `auth.get()` reads the file without checking permissions, a file with world-readable permissions (e.g., copied without preserving mode) leaks tokens silently.

**Prevention:**  
On `auth.get()`, warn if the file permissions are broader than `0o600`:
```python
import stat
mode = oct(os.stat(path).st_mode)[-3:]
if mode != "600":
    warnings.warn(f"~/.maestro/auth.json has insecure permissions: {mode}. Run: chmod 600 ~/.maestro/auth.json")
```

**Phase:** Multi-Provider Plugin — `auth.py` implementation.

---

### Pitfall 16: Aggregator Node — Running Always Adds Unnecessary LLM Call for Simple Tasks

**What goes wrong:**  
If the Aggregator node always runs (even for 2-task DAGs), it adds a full LLM call just to summarize two worker outputs. For simple tasks, this doubles execution time with no value.

**Prevention:**  
Gate the Aggregator on a flag (`--aggregate`) or on DAG size (only run if `len(tasks) > threshold`). Default: skip Aggregator for MVP (matches the "optional" spec).

**Phase:** Multi-Agent DAG — Aggregator implementation decision.

---

## Phase-Specific Warnings

| Phase Topic | Likely Pitfall | Mitigation |
|-------------|---------------|------------|
| LangGraph AgentState definition | Missing reducers → last-write-wins (#1) | Define and test reducers before wiring any workers |
| `Send()` payload construction | Shared mutable reference (#2) | Payload must be pure scalars or deepcopy |
| Planner output parsing | Hallucinated IDs, cycles (#3) | DAG validation layer with cycle detection |
| Worker recursion | Depth guard bypass via missing arg (#4) | Make `depth` a required positional param; test the guard |
| Provider registry loading | `lru_cache` poisons test suite (#5) | Add `cache_clear()` to every test fixture touching discovery |
| Entry point wiring | Empty registry in editable install (#6) | Include `pip install -e .` step in test setup; enhance error message |
| ProviderPlugin Protocol | Silent interface drift (#7) | Runtime validation in `discover_providers()` |
| Copilot OAuth polling | `slow_down` not handled → infinite loop (#8) | Update running interval on each `slow_down` response |
| `auth.py` refactor | Import path break → all 26 tests fail (#9) | Shim before touching imports; run tests first |
| Worker tool execution | Path guard not inherited by workers (#10) | Verify workdir flows through Send payload → tool executor |
| SSE stream mocking | Bulk mock hides chunk parsing bugs (#12) | Build proper SSE byte-framing helper for tests |
| `config.py` model string | Missing prefix silently falls back (#13) | Raise clearly, never swallow the error |

---

## Sources

- LangGraph official docs — Send API, reducers, subgraphs: https://docs.langchain.com/oss/python/langgraph/ (HIGH confidence)
- GitHub OAuth Device Flow official docs: https://docs.github.com/en/apps/oauth-apps/building-oauth-apps/authorizing-oauth-apps#device-flow (HIGH confidence)
- Project spec files: `docs/ideas/multi-agent-dag.md`, `docs/superpowers/specs/2026-04-17-multi-provider-plugin-design.md`, `.planning/PROJECT.md` (HIGH confidence — primary source)
- Python `importlib.metadata` entry points: https://docs.python.org/3/library/importlib.metadata.html (HIGH confidence)
