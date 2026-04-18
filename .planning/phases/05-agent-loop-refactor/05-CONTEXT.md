# Phase 5: Agent Loop Refactor - Context

**Gathered:** 2026-04-18
**Status:** Ready for planning

<domain>
## Phase Boundary

Phase 5 is limited to refactoring the existing single-agent loop so HTTP streaming is delegated through the provider abstraction instead of hardwired ChatGPT transport calls. The scope is intentionally narrow: preserve current `maestro run` behavior, keep the registry-driven default provider path introduced earlier, and surface provider-specific unauthenticated errors without widening the CLI or execution model. This phase is not a UI/frontend phase.

</domain>

<decisions>
## Implementation Decisions

### Provider Boundary
- **D-01:** `maestro run` should use the registry default-provider resolution path when no provider is specified explicitly; do not hardcode ChatGPT in the loop.
- **D-02:** `_run_agentic_loop` should consume `provider.stream()` as the transport boundary and stop owning direct HTTP/SSE request logic.

### Auth Failure Behavior
- **D-03:** The selected provider should raise the actionable unauthenticated `RuntimeError`, and the loop should surface that error rather than reimplement provider-specific auth checks.
- **D-04:** The user-facing guidance must remain provider-aware in the form `maestro auth login <provider_id>`.

### Compatibility Bar
- **D-05:** Phase 5 should be strictly minimal: only changes required to satisfy `LOOP-01`, `LOOP-02`, and `LOOP-03` are in scope.
- **D-06:** Incidental cleanup is not a goal; preserve existing single-agent behavior and test expectations unless a change is required by the provider delegation refactor itself.

### the agent's Discretion
- Planning and implementation may choose the smallest correct way to adapt the loop, tests, and auth handoff so long as the provider registry remains the source of default-provider selection and no new capabilities are introduced.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Product And Phase Scope
- `.planning/PROJECT.md` - project goals, constraints, and zero-regression expectations
- `.planning/REQUIREMENTS.md` - Phase 5 requirements `LOOP-01`, `LOOP-02`, `LOOP-03`
- `.planning/ROADMAP.md` - Phase 5 goal, dependencies, and success criteria
- `.planning/STATE.md` - current project status and phase handoff point

### Prior Phase Decisions
- `.planning/phases/03-chatgpt-provider-migration/03-CONTEXT.md` - ChatGPT transport logic moved into provider and loop wiring deferred to Phase 5
- `.planning/phases/04-provider-registry/04-CONTEXT.md` - registry default selection and backward-compatible no-auth fallback decisions

### Code Paths
- `maestro/agent.py` - current loop still owns direct HTTP streaming and auth entry behavior
- `maestro/providers/chatgpt.py` - current provider-owned ChatGPT streaming implementation
- `maestro/providers/registry.py` - default provider resolution and registry lookup behavior
- `maestro/providers/base.py` - canonical provider protocol and neutral message/tool types
- `maestro/auth.py` - auth store helpers and legacy compatibility layer
- `tests/test_agent_loop.py` - current loop behavior contract
- `tests/test_auth_store.py` - current auth-facing behavior expectations touching `agent.run`
- `tests/test_chatgpt_provider.py` - provider streaming contract already covered separately

### Design Docs
- `docs/superpowers/specs/2026-04-17-multi-provider-plugin-design.md` - provider abstraction and migration intent
- `docs/ideas/multi-agent-dag.md` - broader roadmap context; not implementation scope for this phase

</canonical_refs>

<code_context>
## Existing Code Insights

### Current State
- `maestro/agent.py` still imports ChatGPT transport helpers and performs direct `httpx.stream(...)` calls plus manual SSE parsing inside `_run_agentic_loop(...)`.
- `maestro/providers/chatgpt.py` already exposes `ChatGPTProvider.stream(...)` as an async generator yielding deltas and a final neutral assistant message.
- `maestro/providers/registry.py` already provides `get_provider(...)` and `get_default_provider()` so Phase 5 can reuse central selection logic instead of introducing new resolution code.

### Integration Constraints
- Backward compatibility is the primary constraint: `maestro run "task"` must continue behaving like the pre-refactor single-agent flow.
- The no-provider path should stay registry-driven, which in practice preserves the existing ChatGPT-first experience through prior fallback decisions rather than a new hardcoded special case.
- Auth failures should come from the provider so later providers can supply correct provider-specific login guidance without special loop branches.

### Test Surface
- `tests/test_agent_loop.py` is the main behavior contract for stream handling, tool-call execution, and loop sequencing.
- `tests/test_auth_store.py` likely needs compatibility review because it still references the older auth guidance path around `agent.run`.
- Existing provider tests already cover provider-side streaming behavior; Phase 5 should avoid duplicating that logic in the loop.

</code_context>

<specifics>
## Specific Ideas

- Prefer the smallest possible refactor in `maestro/agent.py`: replace direct transport ownership with provider acquisition plus iteration over `provider.stream(...)` outputs.
- Keep provider/model resolution flowing through the existing registry/config path rather than adding a Phase 5-only lookup layer.
- Let tests define the compatibility boundary and only update assertions that are necessarily changed by the provider-aware auth message contract.

</specifics>

<deferred>
## Deferred Ideas

- CLI expansion for multi-provider auth/model commands remains Phase 6 work.
- Any multi-agent DAG behavior remains out of scope until later phases.

</deferred>

---

*Phase: 05-agent-loop-refactor*
*Context gathered: 2026-04-18*
