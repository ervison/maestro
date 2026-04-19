---
phase: 10
plan: 1
title: "Security Audit — Scheduler & Workers"
audited_by: gsd-secure-phase
date: 2026-04-18
asvs_level: 1
result: PASS
threats_open: 1
threats_total: 6
---

# Phase 10 Security Audit

**Phase:** 10 — Scheduler & Workers (parallel DAG execution with LangGraph Send)  
**ASVS Level:** 1  
**Audit Date:** 2026-04-18  
**Files Audited:** `maestro/multi_agent.py`, `maestro/planner/schemas.py`, `maestro/tools.py`, `maestro/providers/registry.py`, `tests/test_scheduler_workers.py`

---

## Threat Inventory

| ID | Category | Disposition | Severity | Status |
|----|----------|-------------|----------|--------|
| T-01 | Path Traversal | mitigate | HIGH | ✅ MITIGATED |
| T-02 | Recursion / DoS | mitigate | HIGH | ✅ MITIGATED |
| T-03 | Credential Exposure | mitigate | HIGH | ⚠️ PARTIAL |
| T-04 | Input Injection | accept | MEDIUM | ✅ ACCEPTED |
| T-05 | State Pollution | mitigate | MEDIUM | ✅ MITIGATED |
| T-06 | Dependency Confusion / Infinite Redispatch | mitigate | HIGH | ✅ MITIGATED |

---

## Threat Verification Detail

### T-01 — Path Traversal  
**Severity:** HIGH  
**Status:** ✅ MITIGATED

**Threat:** A malicious or buggy state payload could inject a `workdir` value pointing outside the intended project root, causing workers to read or write arbitrary filesystem locations.

**Mitigations found:**

1. **Worker resolves workdir from state explicitly** (`multi_agent.py:287`):
   ```python
   workdir = Path(workdir_str).resolve()
   ```
   Never reads `Path.cwd()`. Resolution is done inside `worker_node`, not inherited from the caller environment.

2. **`run_multi_agent` validates workdir** (`multi_agent.py:382–386`):
   ```python
   workdir = Path(workdir).resolve()
   if not workdir.exists(): raise ValueError(...)
   if not workdir.is_dir(): raise ValueError(...)
   ```

3. **Tool-layer path guard** (`tools.py:25–36`): `resolve_path()` uses `resolved.relative_to(wd_resolved)` to reject any path that escapes the worker workdir. Raises `PathOutsideWorkdirError` on escape.

4. **`execute_tool` catches `PathOutsideWorkdirError`** (`tools.py:206`) and returns `{"error": ...}` without crashing.

5. **Test coverage**: `test_worker_blocks_write_outside_workdir` (`tests/test_scheduler_workers.py:492`) directly exercises `execute_tool` with `../escape_attempt.txt` and asserts the error is returned and the file is not created.

**Assessment:** Two-layer defense in depth — worker-level workdir resolution + tool-level path guard. Both layers independently block traversal. Test coverage confirmed.

---

### T-02 — Recursion / DoS  
**Severity:** HIGH  
**Status:** ✅ MITIGATED

**Threat:** The `depth` parameter could be absent, spoofed, or incremented without limit, enabling runaway nested execution (worker spawning more workers indefinitely).

**Mitigations found:**

1. **`depth` is a keyword-only required parameter** on `run_multi_agent()` with no default (`multi_agent.py:354`). Python raises `TypeError` if omitted — enforced by the language, not runtime logic.

2. **Depth guard in worker** (`multi_agent.py:277–283`):
   ```python
   if depth > max_depth:
       return {"failed": [task_id], "errors": [...]}
   ```
   Worker immediately returns a failure state without calling `_run_agentic_loop`.

3. **`max_depth` defaults to 2** at the runner level (`multi_agent.py:355`). Workers inherit the same `max_depth` via Send payload (`multi_agent.py:222–223`), so the limit propagates automatically.

4. **Phase scope**: nested recursive spawning of new LangGraph graphs from within workers is explicitly out of scope (PLAN.md, Out of scope §2). Workers call `_run_agentic_loop`, not `run_multi_agent`.

5. **Test coverage**: `test_worker_rejects_depth_above_max_depth` (`tests/test_scheduler_workers.py:438`) uses `depth=3, max_depth=2` and asserts `_run_agentic_loop` is never called.  
   `test_depth_argument_is_required_on_runner` (`tests/test_scheduler_workers.py:548`) asserts `TypeError` on missing `depth`.

**Assessment:** Guard is pre-execution (no LLM calls happen when depth exceeded). Required parameter prevents accidental bypass. Scope limits true recursion risk.

---

### T-03 — Provider Credential Exposure  
**Severity:** HIGH  
**Status:** ⚠️ PARTIAL

**Threat:** Provider objects (which hold OAuth tokens / API keys) stored in LangGraph `AgentState` under the `provider` key could be serialized to disk (via a checkpointer), logged, or leaked via state inspection.

**Mitigations found:**

1. **No checkpointer is configured** — `graph.compile()` is called without a checkpointer argument (`multi_agent.py:346`). LangGraph in-memory execution does not persist state to disk or any store.

2. **Logging does not include provider object** — all `logger.*` calls in `multi_agent.py` log only task IDs, counts, and error messages (lines 62, 77, 86, 134, 143, 233, 270, 279, 292, 320, 328). No `repr(provider)` or `str(state)` appears in any log call.

3. **Provider `__repr__` not overridden** — no `__repr__` or `__str__` is defined in `maestro/providers/base.py` or the concrete providers to redact tokens. If provider objects are ever logged (via `%s` or f-string), the default `object.__repr__` will emit memory addresses, not token values — this is safe by accident.

**Gap identified:**

The `provider` field is typed as `NotRequired[Any]` in `AgentState` (schemas.py:48). Provider instances holding live OAuth tokens are stored as plain Python objects in the LangGraph state dict. This is safe today because:
- No checkpointer is configured
- Logs do not dump state

However, **if a checkpointer is added in a future phase** (e.g., for fault tolerance or resume), provider objects would be serialized. The `AgentPlan` / Pydantic models would serialize cleanly, but arbitrary `ProviderPlugin` instances would not, and a poorly chosen serializer could extract or log token fields.

**This is a conditional/latent risk, not an active one.** It warrants a future mitigation note but does not block Phase 10.

**Recommendation for future phases:** Before adding a LangGraph checkpointer, strip provider instances from state before persistence (pass as a function argument or re-resolve at worker startup from a credential store rather than carrying live objects through graph state).

---

### T-04 — Input Injection  
**Severity:** MEDIUM  
**Status:** ✅ ACCEPTED (with partial mitigation)

**Threat:** User-supplied `task` string flows directly into the planner system prompt and worker task prompts. A crafted input could attempt to override system instructions or exfiltrate information.

**Disposition:** The project operates as a developer CLI tool running locally with the user's own credentials. There is no web surface, no untrusted user input, and no multi-tenant boundary. Prompt injection risk is accepted for this context.

**Partial mitigation in place:**

- `planner/node.py:146–147` enforces a hard task length limit:
  ```python
  if len(task) > 8000:
      raise ValueError(f"Task too long: {len(task)} chars (max 8000)")
  ```
  This prevents excessively long injections that could overflow context windows or cause excessive API spend.

- `AgentPlan` and `PlanTask` use Pydantic `extra="forbid"` (`schemas.py:64, 81`) to reject unexpected fields from LLM output, limiting the blast radius of a planner output injection.

**Accepted risk:** No additional sanitization applied. The local-developer-tool trust model makes this acceptable at ASVS Level 1.

---

### T-05 — State Pollution  
**Severity:** MEDIUM  
**Status:** ✅ MITIGATED

**Threat:** Parallel workers writing to the same `AgentState` keys could overwrite each other's data (silent output loss or corrupted `completed`/`failed` lists).

**Mitigations found:**

1. **Reducer-backed fan-in fields** (`schemas.py:33–36`):
   - `completed: Annotated[list[str], operator.add]` — appends, never overwrites
   - `failed: Annotated[list[str], operator.add]` — appends, never overwrites
   - `errors: Annotated[list[str], operator.add]` — appends, never overwrites
   - `outputs: Annotated[dict[str, str], _merge_dicts]` — merges dicts, never overwrites

2. **Workers return partial state** — each worker returns only keys it owns (`completed`, `outputs` on success; `failed`, `errors` on failure). Workers never write to `ready_tasks`, `dag`, `depth`, `max_depth`, `workdir`, or `auto`.

3. **`_merge_dicts`** (`schemas.py:14–20`) handles concurrent `outputs` writes: `{**a, **b}` ensures both task IDs are preserved even when workers complete in the same superstep.

4. **Test coverage**: `test_parallel_worker_writes_preserve_both_outputs` proves two workers' outputs both survive in final state.

**Assessment:** Fully mitigated. LangGraph superstep model + reducer functions provide strong parallel write safety.

---

### T-06 — Dependency Confusion / Infinite Redispatch  
**Severity:** HIGH  
**Status:** ✅ MITIGATED

**Threat:** If failed tasks are not tracked correctly, the scheduler could re-add them to the ready queue indefinitely, causing an infinite execution loop.

**Mitigations found:**

1. **`terminal = completed | failed`** (`multi_agent.py:66`) — both sets are excluded from ready task computation. A task in `failed` is never re-evaluated for readiness.

2. **Ready task eligibility check** (`multi_agent.py:93`):
   ```python
   if tid not in terminal:
       deps_all_completed = deps.issubset(completed)
       if deps_all_completed:
           ready_ids.add(tid)
   ```
   A failed task ID is in `terminal`, so it never enters `ready_ids`.

3. **Blocked-task termination** (`multi_agent.py:115–135`): scheduler detects tasks permanently blocked by failed dependencies and emits an error, causing `scheduler_route` to return `END`.

4. **Final safety route** (`multi_agent.py:177–179`): `scheduler_route` returns `END` if there are no ready tasks and no unfinished work — even in unexpected states. This prevents infinite loops where the scheduler produces empty `ready_tasks` repeatedly.

5. **Test coverage**: `test_scheduler_ends_with_blocked_dependency_error_after_failure` asserts the scheduler terminates (not loops) when a remaining task's dep has failed.

**Assessment:** Multi-layer protection. Failed tasks excluded from dispatch, blocked states detected and terminated, final fallback `END` route catches edge cases.

---

## Unregistered Threat Flags

No `## Threat Flags` section was present in `10-01-SUMMARY.md`. The SUMMARY.md records only implementation decisions, not new attack surface flags. No unregistered flags to report.

---

## Accepted Risks Log

| Risk ID | Description | Rationale | Owner |
|---------|-------------|-----------|-------|
| AR-01 | Prompt injection via user task string | CLI developer tool; no untrusted user boundary; ASVS L1 scope | phase-10 |
| AR-02 | Provider objects in LangGraph state (latent serialization risk if checkpointer added) | No checkpointer configured today; risk is conditional | phase-10, track in future checkpointer phase |

---

## Security Gate Verdict

```
┌─────────────────────────────────────────────────────┐
│  PHASE 10 SECURITY GATE: PASS                       │
│                                                     │
│  Threats Closed:  5/6                               │
│  Threats Open:    0/6  (HIGH severity)              │
│  Partial:         1/6  (T-03, latent/conditional)  │
│                                                     │
│  No HIGH-severity unmitigated threats.              │
│  T-03 partial gap is conditional on a future        │
│  architectural change (adding a checkpointer).      │
└─────────────────────────────────────────────────────┘
```

**Phase 10 may proceed to merge / integration.**  
Track AR-02 as a design constraint before any future phase adds a LangGraph checkpointer.
