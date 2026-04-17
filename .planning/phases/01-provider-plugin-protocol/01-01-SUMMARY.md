---
phase: 01-provider-plugin-protocol
plan: 01
type: execute
subsystem: providers
tags: [provider, protocol, interface, foundation]
requires: []
provides: [ProviderPlugin interface for all providers]
affects: [maestro/providers/base.py, maestro/providers/__init__.py, tests/test_provider_protocol.py]
tech-stack:
  added:
    - typing.Protocol (stdlib structural typing)
    - @runtime_checkable decorator
    - dataclasses for neutral types
  patterns:
    - "Structural typing for third-party plugin compatibility"
    - "Provider-neutral types decoupled from provider implementations"
key-files:
  created:
    - maestro/providers/__init__.py
    - maestro/providers/base.py
    - tests/test_provider_protocol.py
  modified:
    - pyproject.toml (dev dependencies)
decisions:
  - "Use dataclass (not Pydantic) for neutral types - internal containers, not API schemas"
  - "Use typing.Protocol (not ABC) - structural typing for third-party providers"
  - "@runtime_checkable enables isinstance() validation at registry time"
  - "stream() yields str | Message - matches PROV-06 requirement"
metrics:
  duration: 20 minutes
  completed: 2026-04-17
---

# Phase 01 Plan 01: Provider Plugin Protocol Summary

**One-liner:** Define `ProviderPlugin` Protocol and neutral streaming types (`Message`, `Tool`, `ToolCall`, `ToolResult`) that all LLM providers must implement.

## What Was Built

Created the foundation for the multi-provider system by establishing a clean, provider-neutral interface:

1. **Neutral Types** (`maestro/providers/base.py`):
   - `Message`: Conversation message with role (user/assistant/system), content, optional tool_calls
   - `Tool`: Tool definition matching OpenAI function calling schema
   - `ToolCall`: Request from LLM to invoke a tool
   - `ToolResult`: Result of tool execution to send back to LLM

2. **ProviderPlugin Protocol** (`maestro/providers/base.py`):
   - `@runtime_checkable` structural Protocol (not ABC)
   - 7 required members: `id`, `name`, `list_models()`, `stream()`, `auth_required()`, `login()`, `is_authenticated()`
   - Async `stream()` yields `str | Message` for streaming completions

3. **Public API** (`maestro/providers/__init__.py`):
   - Re-exports all types for convenient imports: `from maestro.providers import ProviderPlugin, Message, ...`

4. **Test Suite** (`tests/test_provider_protocol.py`):
   - 27 tests covering all neutral types, Protocol isinstance() checks, import paths
   - MockProvider validates complete implementation passes isinstance()
   - IncompleteProvider validates partial implementation fails isinstance()

## Verification Results

```bash
# Import verification
✓ from maestro.providers import ProviderPlugin, Message, Tool, ToolCall, ToolResult
✓ from maestro.providers.base import ProviderPlugin  # Protocol is Protocol

# isinstance() verification
✓ isinstance(MockProvider(), ProviderPlugin) == True
✓ isinstance(IncompleteProvider(), ProviderPlugin) == False

# Test suite
✓ 27 new tests pass
✓ 26 existing tests pass (no regressions)
```

## Deviations from Plan

None - plan executed exactly as written.

## Design Decisions

1. **dataclass over Pydantic**: Neutral types are internal data containers, not API validation schemas. Pydantic is reserved for LLM structured output (Phase 8+).

2. **Protocol over ABC**: Structural typing allows third-party providers to implement the interface without importing maestro (loose coupling).

3. **@runtime_checkable**: Enables `isinstance()` validation at registry time for dynamic provider discovery.

4. **stream() signature**: Yields `str | Message` where strings are streaming chunks and final Message contains complete response.

## Key Links

- Protocol spec: RESEARCH/STACK.md (ProviderPlugin Protocol section)
- Requirements: PROV-01, PROV-06
- Next phase: Phase 2 - ChatGPT Provider (implements ProviderPlugin)

## Self-Check: PASSED

- [x] All files exist: maestro/providers/__init__.py, maestro/providers/base.py, tests/test_provider_protocol.py
- [x] All commits verified: adf9c1a, 69ba1a6, d266d09
- [x] All 53 tests pass
- [x] All imports work from both maestro.providers and maestro.providers.base
