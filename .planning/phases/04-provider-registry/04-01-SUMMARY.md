---
phase: 4
plan: 01
subsystem: provider-registry
tags: [config, registry, models, entry-points]
dependency_graph:
  requires: [03-01]
  provides: [05-01]
  affects: [maestro/__init__.py, maestro/cli.py]
tech_stack:
  added: []
  patterns:
    - importlib.metadata entry point discovery
    - lru_cache for static discovery
    - dataclass for config with dot-notation accessors
    - provider_id/model_id format validation
key_files:
  created:
    - maestro/config.py
    - maestro/providers/registry.py
    - maestro/models.py
    - tests/test_config.py
    - tests/test_provider_registry.py
    - tests/test_model_resolution.py
  modified:
    - maestro/__init__.py (added exports)
decisions:
  - Used lru_cache(maxsize=1) for provider discovery since entry points are static
  - Config.get() uses dot notation for nested access (agent.backend.model)
  - Model resolution follows explicit priority chain with clear precedence
  - Graceful fallback to chatgpt when no config exists (backward compatibility)
  - Config file uses 0o600 permissions (consistent with auth store)
metrics:
  duration: 15 min
  completed: 2026-04-17
---

# Phase 4 Plan 01: Config & Provider Registry Summary

**One-liner:** Implemented runtime provider discovery via entry points, config system with dot-notation access, and model resolution following priority chain.

## What Was Built

### 1. Config System (`maestro/config.py`)
- `Config` dataclass with `model` and `agent` fields
- `load()` / `save()` functions with 0o600 file permissions
- `get()` / `set()` methods with dot notation support (e.g., `agent.backend.model`)
- `MAESTRO_CONFIG_FILE` env var override support
- Graceful handling of missing config file (returns defaults)

### 2. Provider Registry (`maestro/providers/registry.py`)
- `discover_providers()` using `importlib.metadata.entry_points(group="maestro.providers")`
- `@lru_cache(maxsize=1)` for efficient repeated access
- `get_provider(provider_id)` returns instance or raises `ValueError` with available providers list
- `list_providers()` returns sorted list of provider IDs
- `get_default_provider()` returns first authenticated provider or chatgpt fallback

### 3. Model Resolution (`maestro/models.py`)
- `parse_model_string()` validates "provider_id/model_id" format with helpful error messages
- `resolve_model()` follows priority chain:
  1. `--model` flag (highest)
  2. `MAESTRO_MODEL` environment variable
  3. `config.agent.<name>.model` (agent-specific)
  4. `config.model` (global default)
  5. First model of first authenticated provider (lowest)
- `get_available_models()` aggregates models from authenticated providers
- `format_model_list()` for CLI display

### 4. Package Exports (`maestro/__init__.py`)
Exported public API:
- `Config`, `load_config`, `save_config`
- `get_provider`, `get_default_provider`, `list_providers`, `discover_providers`
- `resolve_model`, `parse_model_string`, `get_available_models`, `format_model_list`

### 5. Tests
- **19 tests** for config module (load/save, dot notation, permissions)
- **7 tests** for provider registry (discovery, caching, error handling)
- **15 tests** for model resolution (parsing, priority chain, formatting)

## Success Criteria Verification

From ROADMAP.md Phase 4:

| Criteria | Status | Evidence |
|----------|--------|----------|
| `get_provider("chatgpt")` returns ChatGPT provider | ✅ | `test_returns_chatgpt_provider` passes |
| `get_provider("nonexistent")` raises ValueError with list | ✅ | `test_raises_for_unknown_provider` passes |
| `resolve_model()` follows priority chain | ✅ | 5 priority tests pass (01-05) |
| Model string "provider_id/model_id" validated | ✅ | `test_raises_for_missing_slash` etc. pass |
| Absent config falls back gracefully | ✅ | `test_priority_5_fallback` passes |

## Test Results

```
============================= 152 passed in 1.47s ==============================
```

- 152 total tests passing
- 41 new tests added for Phase 4
- 0 regressions in existing 111 tests

## Deviations from Plan

**None** - Plan executed exactly as written.

Minor implementation notes:
- Config file location uses same pattern as auth file (`~/.maestro/config.json`)
- Used `asdict()` for serialization to avoid manual field mapping
- Added `format_model_list()` helper for future CLI commands

## Backward Compatibility

✅ Fully maintained:
- Existing `maestro run` behavior unchanged
- All 26+ original tests still pass
- ChatGPT provider remains default when no config exists
- No breaking changes to any existing APIs

## Files Changed

| File | Lines | Change |
|------|-------|--------|
| `maestro/config.py` | 161 | Created |
| `maestro/providers/registry.py` | 123 | Created |
| `maestro/models.py` | 152 | Created |
| `maestro/__init__.py` | 28 | Created (was empty) |
| `tests/test_config.py` | 180 | Created |
| `tests/test_provider_registry.py` | 109 | Created |
| `tests/test_model_resolution.py` | 173 | Created |

**Total new code:** ~926 lines (implementation + tests)

## Next Steps

Phase 4 is complete. Phase 5 (Agent Loop Refactor) can now proceed to wire `provider.stream()` into the agentic loop.

## Self-Check: PASSED

- [x] All created files exist
- [x] All tests pass
- [x] Imports work correctly
- [x] `get_provider("chatgpt")` returns ChatGPTProvider instance
- [x] Backward compatibility maintained
