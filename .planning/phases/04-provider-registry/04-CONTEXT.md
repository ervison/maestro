# Phase 4: Config & Provider Registry - Context

**Gathered:** 2026-04-17
**Status:** Ready for planning

<domain>
## Phase Boundary

Phase 4 delivers runtime provider discovery plus config-driven provider/model resolution for the existing single-agent CLI. The scope is limited to registry behavior, provider lookup, model resolution order, and graceful fallback behavior when config is absent or incomplete. This phase is not a UI/frontend phase.

</domain>

<decisions>
## Implementation Decisions

### Provider Fallback
- **D-01:** `resolve_model()` should prefer the first authenticated provider discovered and that provider's first listed model when no explicit model is supplied by CLI flag, environment variable, or config.
- **D-02:** If no provider is authenticated, Phase 4 should fall back gracefully to ChatGPT's default model to preserve current `maestro run` behavior.
- **D-03:** Backward compatibility is the priority for the no-auth path: absence of config must not break the current ChatGPT-first experience.

### the agent's Discretion
- Registry validation strictness, model-string parsing edge cases, and the exact config-reader shape were not discussed in detail during this session.
- Planning and implementation may choose the smallest approach that satisfies Phase 4 requirements (`PROV-02`, `PROV-04`, `PROV-05`, `CONF-01`, `CONF-02`, `CONF-05`) without expanding scope into later CLI or provider features.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Product And Phase Scope
- `.planning/PROJECT.md` - project goals, constraints, and backward-compatibility expectations
- `.planning/REQUIREMENTS.md` - Phase 4 requirements and model resolution contract
- `.planning/ROADMAP.md` - Phase 4 goal, dependencies, and success criteria
- `.planning/STATE.md` - current project status and phase handoff point
- `.planning/DEPENDENCY_ANALYSIS.md` - dependency expectations around the provider registry

### Prior Phase Decisions
- `.planning/phases/03-chatgpt-provider-migration/03-CONTEXT.md` - Phase 3 deferred runtime registry work into Phase 4
- `.planning/phases/03-chatgpt-provider-migration/03-01-SUMMARY.md` - handoff notes describing what Phase 4 can build on

### Code Paths
- `maestro/providers/base.py` - canonical ProviderPlugin Protocol and neutral types
- `maestro/providers/__init__.py` - current provider exports
- `maestro/providers/chatgpt.py` - current built-in provider implementation and model list
- `maestro/auth.py` - current auth store API and ChatGPT compatibility helpers
- `maestro/cli.py` - current CLI defaults and ChatGPT-specific behavior that Phase 4 must preserve
- `pyproject.toml` - provider entry-point registration contract

### Design Docs
- `docs/superpowers/specs/2026-04-17-multi-provider-plugin-design.md` - multi-provider architecture decisions

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `maestro/providers/base.py` already defines the provider protocol Phase 4 should discover and validate.
- `maestro/providers/chatgpt.py` already provides a concrete built-in provider with `id`, `list_models()`, and auth checks.
- `maestro/auth.py` already exposes per-provider auth store helpers (`get`, `set`, `remove`, `all_providers`) that registry/model resolution can consult.

### Established Patterns
- The CLI is still ChatGPT-specific: `maestro run` defaults to `auth.DEFAULT_MODEL`, `maestro auth login` only accepts `chatgpt`, and `maestro models` prints ChatGPT models directly.
- Entry-point packaging already exists for the builtin ChatGPT provider in `pyproject.toml`, so runtime discovery can build on that contract instead of inventing a new registration mechanism.

### Integration Points
- Phase 4 will need a central registry/config module that later phases can call from `cli.py` and `agent.py` without duplicating provider lookup logic.
- The Phase 4 fallback policy must preserve the current default run path until later phases finish the CLI/provider refactor.

</code_context>

<specifics>
## Specific Ideas

- Prefer authenticated-provider selection only when the user has actually authenticated providers; otherwise preserve the existing ChatGPT default path.
- Keep the implementation narrow and reusable so Phase 5 can swap the agent loop over to provider-driven streaming with minimal extra logic.

</specifics>

<deferred>
## Deferred Ideas

None - discussion stayed within phase scope.

</deferred>

---

*Phase: 04-provider-registry*
*Context gathered: 2026-04-17*
