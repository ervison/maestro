# Phase 2: Multi-Slot Auth Store - Context

## Phase Boundary

- Scope is limited to roadmap Phase 2: per-provider auth storage, public auth store API, and the minimum CLI change required for `AUTH-08`.
- This phase is not a UI/frontend phase.
- This phase should preserve current agent behavior by keeping `maestro/agent.py` working through backward-compatible `auth.py` shims.
- This phase should not pull in later auth-provider work such as provider-specific logout behavior, richer auth status reporting, or broader multi-provider CLI coverage beyond the login path required now.

## Implementation Decisions

### CLI Shape

- Add a new canonical command path: `maestro auth login [provider]`.
- If no provider is passed to `maestro auth login`, default to `chatgpt`.
- Keep top-level `maestro login` working as a deprecated alias that routes to the same ChatGPT login behavior.
- Do not deprecate top-level `maestro logout` or `maestro status` in this phase; leave them unchanged for now.

### Planning Corrections

- Existing phase 2 plans were created before phase context existed and assume broader CLI deprecation than the locked decision above.
- Replanning is required before execution so phase 2 work aligns with the current context instead of the older assumptions.

### Backward Compatibility

- Keep `TokenSet`, `load()`, `_save()`, and `logout()` in `maestro/auth.py` as delegating shims during Phase 2.
- `maestro/agent.py` should remain unchanged in this phase and continue using `auth.load()` / `auth.ensure_valid()`.

## Canonical References

- `.planning/PROJECT.md`
- `.planning/REQUIREMENTS.md`
- `.planning/ROADMAP.md`
- `.planning/STATE.md`
- `.planning/phases/02-multi-slot-auth-store/02-RESEARCH.md`
- `.planning/research/ARCHITECTURE.md`
- `.planning/research/PITFALLS.md`
- `maestro/auth.py`
- `maestro/cli.py`
- `maestro/agent.py`

## Existing Code Insights

- `maestro/auth.py` currently stores a single flat ChatGPT token payload directly in `~/.maestro/auth.json` and exposes ChatGPT-specific login/logout/load helpers.
- `maestro/cli.py` currently exposes top-level `login`, `logout`, and `status` commands only; there is no nested `auth` command group yet.
- `maestro/agent.py` still depends on `auth.load()` returning `TokenSet | None` and raises `RuntimeError("Not logged in. Run: maestro login")` when no credentials exist.
- Existing phase 2 research already identified the smallest-safe refactor shape: add generic auth store functions while preserving old ChatGPT-facing shims.

## Specific Ideas

- Add internal auth store helpers that read and write a provider-keyed JSON object in `~/.maestro/auth.json`.
- Keep the user-visible Phase 2 CLI change narrow: add `maestro auth login [provider]`, default to `chatgpt`, and emit a deprecation warning only for legacy top-level `maestro login`.
- Rework existing phase 2 plans so CLI tasks reflect the locked scope above instead of deprecating `logout` and `status` early.

## Deferred Ideas

- Deprecate top-level `maestro logout` in a later auth/provider phase.
- Deprecate top-level `maestro status` in a later auth/provider phase.
- Expand `maestro auth status` to richer per-provider details in a later phase.
- Add broader provider-aware auth command behavior once additional providers exist.

---

*Phase: 02-multi-slot-auth-store*
*Context gathered: 2026-04-17*
