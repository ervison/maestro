# Phase 3: ChatGPT Provider Migration - Context

## Phase Boundary

- Scope is limited to roadmap Phase 3: migrate ChatGPT-specific HTTP, SSE, and wire-format logic out of `maestro/agent.py` into `maestro.providers.chatgpt.ChatGPTProvider`.
- This phase is not a UI/frontend phase.
- This phase should not refactor the main agent loop to consume providers yet; that belongs to Phase 5.
- This phase should preserve current runtime behavior through compatibility shims while preparing Phase 4 registry work.

## Implementation Decisions

### Migration Boundary

- Move ChatGPT request payload building, header construction, streaming response parsing, and ChatGPT/OpenAI wire-format conversion into `maestro.providers.chatgpt`.
- Keep loop wiring changes out of this phase: `run()`, `_run_agentic_loop()`, and the broader provider-driven orchestration stay for Phase 5.
- Keep the change set narrow so Phase 3 delivers a provider implementation without altering current CLI behavior more than necessary.

### Backward Compatibility

- Keep broad ChatGPT-facing shims in `maestro/auth.py` during this phase.
- Preserve `TokenSet` importability from `maestro.auth` even if the canonical ChatGPT implementation moves into `maestro.providers.chatgpt`.
- Keep current auth/model helper imports working while the provider module becomes the main home for ChatGPT behavior.

### Provider Stream Contract

- `ChatGPTProvider.stream()` should expose the neutral provider contract from `maestro.providers.base`.
- The provider owns conversion between neutral `Message` / `Tool` / `ToolCall` values and the ChatGPT/OpenAI wire format.
- Streaming should yield text chunks plus final neutral assistant messages/tool calls instead of leaking raw provider event JSON.

### Packaging And Registration

- Register the builtin ChatGPT provider in `pyproject.toml` under the `maestro.providers` entry-point group during this phase.
- Do this now even if runtime entry-point discovery lands in Phase 4, so Phase 3 satisfies `PROV-03` and Phase 4 can build on the packaging contract directly.

## Canonical References

- `.planning/PROJECT.md`
- `.planning/REQUIREMENTS.md`
- `.planning/ROADMAP.md`
- `.planning/STATE.md`
- `.planning/phases/02-multi-slot-auth-store/02-CONTEXT.md`
- `.planning/phases/02-multi-slot-auth-store/02-RESEARCH.md`
- `.planning/DEPENDENCY_ANALYSIS.md`
- `docs/superpowers/specs/2026-04-17-multi-provider-plugin-design.md`
- `maestro/agent.py`
- `maestro/auth.py`
- `maestro/providers/base.py`
- `maestro/cli.py`
- `pyproject.toml`

## Existing Code Insights

- `maestro/agent.py` currently owns ChatGPT request construction, header logic, streaming SSE parsing, tool-call extraction, and direct `httpx.stream()` usage.
- `maestro/auth.py` now contains the multi-slot credential store from Phase 2 but still also owns ChatGPT-specific models, token lifecycle helpers, and login/logout shims.
- `maestro/providers/base.py` already defines the neutral provider protocol and types that Phase 3 should target.
- `pyproject.toml` does not yet declare `maestro.providers` entry points, so builtin provider packaging is still missing.
- `maestro/cli.py` currently only knows about ChatGPT directly; Phase 3 should avoid broad CLI/provider-registry refactors beyond what is required for compatibility.

## Specific Ideas

- Introduce `maestro/providers/chatgpt.py` as the canonical home for ChatGPT transport logic and provider-neutral conversions.
- Leave `maestro/agent.py` behavior stable by reusing provider helpers or shims rather than rewriting the whole loop now.
- Use the Phase 2 compatibility pattern again: move internals conservatively while keeping public imports stable.

## Deferred Ideas

- Full provider-driven `run()` / `_run_agentic_loop()` wiring belongs to Phase 5.
- Runtime provider discovery/registry behavior belongs to Phase 4.
- Broader CLI/provider abstraction (`maestro models --provider`, provider selection, auth status across providers) belongs to later phases.

---

*Phase: 03-chatgpt-provider-migration*
*Context gathered: 2026-04-17*
