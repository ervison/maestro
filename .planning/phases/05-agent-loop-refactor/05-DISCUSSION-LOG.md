# Phase 5: Agent Loop Refactor - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md - this log preserves the alternatives considered.

**Date:** 2026-04-18
**Phase:** 05-agent-loop-refactor
**Areas discussed:** Provider boundary, auth failure UX, compatibility/tests

---

## Provider boundary

| Option | Description | Selected |
|--------|-------------|----------|
| Registry default path | Use the provider registry's default selection path for `maestro run` when no provider is explicitly selected. | ✓ |
| Hardcode ChatGPT | Keep explicit ChatGPT selection in the loop during the refactor. | |
| Discuss further | Delay the decision pending more design discussion. | |

**User's choice:** Registry default path.
**Notes:** Preserve current ChatGPT-first behavior through registry fallback rules, not a new hardcoded branch in the loop.

---

## Auth failure UX

| Option | Description | Selected |
|--------|-------------|----------|
| Provider raises | Let the selected provider raise the actionable unauthenticated error with provider-specific login guidance. | ✓ |
| Loop raises | Keep auth checks in `agent.run()` or loop code before provider streaming begins. | |
| Shared helper | Introduce a shared helper used by loop and provider. | |

**User's choice:** Provider raises.
**Notes:** This keeps provider-specific auth guidance localized and scales cleanly to additional providers.

---

## Compatibility and tests

| Option | Description | Selected |
|--------|-------------|----------|
| Strictly minimal | Only change code required for provider delegation and provider-aware auth errors. | ✓ |
| Allow small cleanup | Permit minor non-functional cleanup during the refactor. | |
| Discuss further | Delay the implementation boundary decision. | |

**User's choice:** Strictly minimal.
**Notes:** Preserve existing single-agent behavior and let the current tests define the regression boundary as much as possible.

---

## Deferred Ideas

- None.
