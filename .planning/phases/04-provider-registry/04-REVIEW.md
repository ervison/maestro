---
phase: 04-provider-registry
reviewed: 2026-04-17T23:29:18Z
depth: deep
files_reviewed: 14
files_reviewed_list:
  - maestro/__init__.py
  - maestro/auth.py
  - maestro/cli.py
  - maestro/config.py
  - maestro/models.py
  - maestro/providers/__init__.py
  - maestro/providers/base.py
  - maestro/providers/chatgpt.py
  - maestro/providers/registry.py
  - pyproject.toml
  - tests/test_auth_store.py
  - tests/test_config.py
  - tests/test_model_resolution.py
  - tests/test_provider_registry.py
findings:
  critical: 0
  warning: 3
  info: 0
  total: 3
status: issues_found
---

# Phase 4: Code Review Report

**Reviewed:** 2026-04-17T23:29:18Z
**Depth:** deep
**Files Reviewed:** 14
**Status:** issues_found

## Summary

Reviewed the current Phase 4 worktree after the latest review-fix pass, with deep focus on provider discovery, config/model resolution, and CLI compatibility boundaries. The prior three findings were addressed, and targeted Phase 4 tests currently pass, but the branch is still **not approvable** under the conservative gate: default-provider selection still violates the documented ChatGPT fallback contract when only auth-free providers are present, registry validation still accepts providers that do not actually satisfy the async `ProviderPlugin.stream()` contract, and `Config.set()` exposes an inconsistent exception contract for invalid nested keys.

## Warnings

### WR-01: No-auth default resolution still violates the documented ChatGPT fallback contract

**File:** `maestro/providers/registry.py:140-152`, `maestro/models.py:116-130`
**Issue:** Phase 4's context and roadmap say the empty-config/no-auth path must fall back to ChatGPT when no provider is authenticated. The current implementation instead returns the first *usable* provider, so an auth-free third-party provider becomes the default even when no provider is authenticated. This reproduces today (`resolve_model()` returns `auth-free/free-model` with an auth-free plugin plus unauthenticated ChatGPT), which breaks the phase contract and leaves non-CLI callers with behavior that disagrees with the documented fallback policy.
**Fix:** Make `get_default_provider()` prefer authenticated providers only. If none are authenticated, explicitly fall back to ChatGPT when installed; only use auth-free providers when the product decision is updated and documented accordingly. Add a regression test covering `auth-free + unauthenticated chatgpt => chatgpt/DEFAULT_MODEL`.

```python
authenticated: list[ProviderPlugin] = []

for provider_class in providers.values():
    instance = provider_class()
    if instance.is_authenticated():
        authenticated.append(instance)

if authenticated:
    return authenticated[0]
if "chatgpt" in providers:
    return providers["chatgpt"]()
raise ValueError("No authenticated provider found and no ChatGPT fallback is installed.")
```

### WR-02: Registry validation still accepts providers that violate the async streaming contract

**File:** `maestro/providers/registry.py:62-67`, `maestro/providers/base.py:55-56`
**Issue:** Discovery uses `isinstance(instance, ProviderPlugin)` as its only contract check. Because `@runtime_checkable` Protocols only verify attribute presence, a provider with a synchronous `def stream(...)` passes discovery even though Phase 5 will need an async iterator-compatible `stream()` implementation. I verified this by registering a mock provider with sync `stream()`; `discover_providers()` accepted it. That means Phase 4 still admits invented/broken provider interfaces into the registry and defers failure until runtime.
**Fix:** Add explicit validation for the `stream` callable during discovery (for example, `inspect.isasyncgenfunction` / `inspect.iscoroutinefunction` plus a tighter smoke-test contract), and add a registry test that rejects a sync `stream()` implementation.

```python
import inspect

stream_fn = getattr(provider_class, "stream", None)
if stream_fn is None or not inspect.iscoroutinefunction(stream_fn):
    raise TypeError(
        f"Provider entry point '{ep.name}' must define async stream(...)"
    )
```

### WR-03: `Config.set()` raises `AttributeError` instead of `KeyError` for invalid nested roots

**File:** `maestro/config.py:72-82`
**Issue:** `Config.set()` documents invalid keys as `KeyError`, and top-level invalid keys already behave that way, but nested invalid roots like `unknown.child` currently call `getattr(self, part)` directly and leak `AttributeError`. This makes the config API inconsistent and forces callers/tests to handle two exception types for the same category of input error.
**Fix:** Guard `getattr()` with `hasattr()` (or `try/except AttributeError`) and normalize invalid nested roots to `KeyError`. Add a regression test for `cfg.set("unknown.child", 1)`.

```python
if isinstance(current, Config):
    if not hasattr(current, part):
        raise KeyError(f"Invalid config key: {key}")
    current = getattr(current, part)
```

---

_Reviewed: 2026-04-17T23:29:18Z_
_Reviewer: the agent (gsd-code-reviewer)_
_Depth: deep_
