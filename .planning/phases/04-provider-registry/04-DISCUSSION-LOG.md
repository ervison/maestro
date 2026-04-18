# Phase 4: Config & Provider Registry - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md - this log preserves the alternatives considered.

**Date:** 2026-04-17
**Phase:** 04-provider-registry
**Areas discussed:** Provider fallback

---

## Provider fallback

| Option | Description | Selected |
|--------|-------------|----------|
| Prefer authenticated provider | Use the first authenticated provider discovered and its first listed model when no explicit model is configured. | ✓ |
| Always default ChatGPT | Keep ChatGPT as the default regardless of authenticated providers. | |
| Require explicit config | Raise an error unless the provider/model is configured directly. | |

**User's choice:** Prefer authenticated provider.
**Notes:** This should only apply when a provider is authenticated; otherwise backward compatibility should win.

---

## No-auth fallback

| Option | Description | Selected |
|--------|-------------|----------|
| ChatGPT model fallback | Fall back to ChatGPT's default model when no provider is authenticated. | ✓ |
| ChatGPT provider only | Fall back to provider `chatgpt` but defer model choice. | |
| No fallback error | Fail immediately and require authentication first. | |

**User's choice:** ChatGPT model fallback.
**Notes:** Preserve current `maestro run` behavior when config is absent and no provider is authenticated.

---

## the agent's Discretion

- Registry behavior, model naming rules, and config shape were left to the minimal correct implementation during planning.

## Deferred Ideas

- None.
