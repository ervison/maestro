# Phase 2: Multi-Slot Auth Store - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-04-17
**Phase:** 02-multi-slot-auth-store
**Areas discussed:** CLI shape

---

## Login Default

| Option | Description | Selected |
|--------|-------------|----------|
| Default chatgpt | `maestro auth login` behaves like ChatGPT login and nudges users toward explicit provider IDs | ✓ |
| Require provider | Error unless the user passes `chatgpt` or another provider ID | |
| Agent decides | Let the agent choose the smallest implementation | |

**User's choice:** Default chatgpt
**Notes:** The default should preserve current behavior while establishing the new provider-aware command shape.

---

## Old Commands

| Option | Description | Selected |
|--------|-------------|----------|
| Deprecate login only | Add the new `maestro auth login [provider]`; keep legacy `maestro login` as warned alias, leave `logout/status` alone for now | ✓ |
| Deprecate all three | Warn and preserve top-level `login`, `logout`, and `status` as aliases to the new auth group | |
| Keep old commands quiet | Add the new auth group but do not warn on old top-level commands yet | |

**User's choice:** Deprecate login only
**Notes:** This keeps Phase 2 focused on `AUTH-08` instead of prematurely expanding the CLI migration.

---

## the agent's Discretion

- None.

## Deferred Ideas

- Deprecate top-level `maestro logout` in a later auth/provider phase.
- Deprecate top-level `maestro status` in a later auth/provider phase.
- Expand auth status output once multiple providers and richer state reporting are implemented.
