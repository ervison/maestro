# Phase 3: ChatGPT Provider Migration - Discussion Log

> Audit trail only. Do not use as input to planning, research, or execution agents.
> Decisions are captured in `03-CONTEXT.md`.

**Date:** 2026-04-17
**Phase:** 03-chatgpt-provider-migration
**Areas discussed:** Migration boundary, Compat surface, Provider API shape, Packaging entry points

---

## Migration Boundary

| Option | Description | Selected |
|--------|-------------|----------|
| HTTP+SSE only | Move ChatGPT request building, headers, streaming parse, and wire-format conversion; keep loop wiring for Phase 5 | ✓ |
| Provider + loop refactor | Also change `run()` / `_run_agentic_loop()` to call the provider now | |
| Big move incl auth | Also move ChatGPT auth/model helpers out of `auth.py` now | |

**User's choice:** HTTP+SSE only
**Notes:** Keep Phase 3 narrow and leave provider-driven loop wiring to Phase 5.

---

## Compat Surface

| Option | Description | Selected |
|--------|-------------|----------|
| Keep broad shims | Keep `TokenSet` and current ChatGPT-facing auth helpers importable from `auth.py` while provider internals migrate | ✓ |
| TokenSet shim only | Re-export only `TokenSet`; move other helpers immediately | |
| No shims | Update all call sites now and stop preserving old imports | |

**User's choice:** Keep broad shims
**Notes:** Backward compatibility remains the default posture during the migration.

---

## Provider API Shape

| Option | Description | Selected |
|--------|-------------|----------|
| Neutral streaming contract | Yield text chunks and final neutral `Message` / `ToolCall` values; provider owns ChatGPT wire details | ✓ |
| Text only | Provider returns only text; tool-call handling stays outside | |
| Raw event passthrough | Expose ChatGPT/OpenAI event JSON and adapt it elsewhere | |

**User's choice:** Neutral streaming contract
**Notes:** Raw provider events should not leak outside `ChatGPTProvider`.

---

## Packaging Entry Points

| Option | Description | Selected |
|--------|-------------|----------|
| Yes, register now | Add builtin ChatGPT provider registration in `pyproject.toml` before registry lookup is used | ✓ |
| Defer to Phase 4 | Only add entry points when registry implementation lands | |
| Use hardcoded import | Avoid entry points for builtins and keep manual imports | |

**User's choice:** Yes, register now
**Notes:** Packaging contract should land in Phase 3 so Phase 4 can focus on discovery/runtime behavior.

---

## the agent's Discretion

- None recorded.

## Deferred Ideas

- Full provider-driven loop refactor deferred to Phase 5.
- Runtime registry/discovery deferred to Phase 4.
