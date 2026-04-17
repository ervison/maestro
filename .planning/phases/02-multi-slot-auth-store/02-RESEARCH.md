# Phase 2: Multi-Slot Auth Store - Research

**Researched:** 2026-04-17
**Domain:** Auth credential storage refactor (single-provider → multi-provider)
**Confidence:** HIGH

## Summary

Phase 2 refactors `maestro/auth.py` from a ChatGPT-specific single-credential store into a per-provider key-value store backed by `~/.maestro/auth.json`. The current implementation writes a flat JSON object `{access, refresh, expires, account_id, email}` to `AUTH_FILE` on every login. The target format nests credentials under provider IDs: `{"chatgpt": {access, refresh, ...}, "github-copilot": {token: "ghu_..."}}`.

This is a **purely internal refactor** — no new external dependencies needed. The public API surface changes from direct `TokenSet` access to `auth.get(provider_id)` / `auth.set(provider_id, data)`. Three consumers exist today: `cli.py` (login/logout/status), `agent.py` (load tokens for API calls), and `test_agent_loop.py` (imports `TokenSet`). All three must continue working during and after the transition.

**Primary recommendation:** Restructure `auth.json` to a dict-of-dicts keyed by provider ID. Add `get()`, `set()`, `remove()`, `all_providers()` functions. Keep existing `TokenSet`, `load()`, `_save()`, `login()`, `logout()` functions as backward-compat shims that delegate to the new API. Add deprecation warnings on old paths. This minimizes blast radius — `agent.py` doesn't change at all in this phase.

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| AUTH-01 | Auth credentials are stored per-provider in `~/.maestro/auth.json` (mode `0o600`) | New `auth.json` format: `{"chatgpt": {...}, "github-copilot": {...}}`. Existing `AUTH_FILE` and `chmod(0o600)` pattern preserved, extended to nested structure. |
| AUTH-02 | `auth.get(provider_id)`, `auth.set(provider_id, data)`, `auth.remove(provider_id)`, `auth.all_providers()` are the public API | Four new functions in `auth.py`. `get/set` are the core. `all_providers()` returns `list(data.keys())`. `remove()` deletes a key and rewrites. |
| AUTH-08 | Existing `maestro auth login` (ChatGPT OAuth flow) shows deprecation warning and routes to `maestro auth login chatgpt` | CLI subcommand restructure: `auth` becomes a subcommand group with `login`, `logout`, `status` children. Old `maestro login` → deprecation warning + redirect. |
</phase_requirements>

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Credential storage format | Auth Store (Tier 1) | — | File I/O and data format is auth's sole responsibility |
| CLI auth subcommands | CLI Surface (Tier 0) | — | Argument parsing and user interaction |
| Token validation/refresh | Auth Store (Tier 1) | — | JWT decode and OAuth exchange stay in auth module |
| Backward-compat re-exports | Auth Store (Tier 1) | — | Shims in auth.py prevent import breakage |

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| Python stdlib `json` | 3.12 | Read/write auth.json | Already used; no change needed |
| Python stdlib `os` | 3.12 | File permissions (`chmod 0o600`) | Already used in `_save()` |
| Python stdlib `pathlib.Path` | 3.12 | File path handling | Already used for `AUTH_FILE` |
| Python stdlib `warnings` | 3.12 | Deprecation warnings on old API paths | New usage; stdlib, zero deps |
| `httpx` | 0.28.1 | OAuth HTTP calls | Already installed, used by `login_browser()` and `login_device()` |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| Python stdlib `argparse` | 3.12 | CLI subcommand restructure | AUTH-08 requires new `auth` subcommand group |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Flat JSON file | SQLite / keyring / encrypted vault | Overkill for 2-3 provider credentials. JSON is human-readable, debuggable, and already works. Migration to keyring is v2 deferred idea. |
| Deprecation warnings | Hard break | Hard break violates backward compatibility constraint ("all 26 tests pass"). Deprecation warnings let Phase 3+ migrate gradually. |

**Installation:** No new packages required.

**Version verification:** All packages already installed and verified in project.

## Architecture Patterns

### System Architecture Diagram

```
                          CLI (cli.py)
                              │
              ┌───────────────┼───────────────┐
              │               │               │
        maestro login    maestro logout   maestro auth login <provider>
              │               │               │
              │  (deprecated) │  (deprecated)  │  (new)
              │      ┌────────┴────────┐      │
              ▼      ▼                 ▼      ▼
         ┌─────────────────────────────────────────┐
         │          auth.py (refactored)            │
         │                                           │
         │  NEW PUBLIC API:                          │
         │  ┌─────────┐  ┌─────────┐  ┌──────────┐ │
         │  │get(pid) │  │set(pid, │  │remove(pid)│ │
         │  │→ dict   │  │ data)   │  │           │ │
         │  └─────────┘  └─────────┘  └──────────┘ │
         │  ┌──────────────────────────────────────┐ │
         │  │all_providers() → list[str]            │ │
         │  └──────────────────────────────────────┘ │
         │                                           │
         │  BACKWARD-COMPAT (delegating to new API): │
         │  load() → auth.get("chatgpt") → TokenSet  │
         │  _save(ts) → auth.set("chatgpt", ts_dict) │
         │  login() → login_chatgpt() + set()        │
         │  logout() → remove("chatgpt")             │
         │  TokenSet (unchanged dataclass)            │
         └───────────────────┬───────────────────────┘
                             │
                             ▼
                    ~/.maestro/auth.json
                    {
                      "chatgpt": {
                        "access": "...",
                        "refresh": "...",
                        "expires": 12345.0,
                        "account_id": "...",
                        "email": "..."
                      },
                      "github-copilot": {
                        "token": "ghu_...",
                        "obtained_at": 12345.0
                      }
                    }
```

### Recommended Project Structure

```
maestro/
├── auth.py            # REFACTORED: multi-slot store + backward compat shims
├── cli.py             # MODIFIED: add `auth` subcommand group, deprecation on old commands
├── agent.py           # UNCHANGED in this phase (still uses auth.load(), auth.TokenSet)
├── providers/
│   ├── __init__.py    # UNCHANGED
│   └── base.py        # UNCHANGED
└── tools.py           # UNCHANGED

tests/
├── test_auth_store.py  # NEW: test multi-slot API
├── test_agent_loop.py  # UNCHANGED (backward compat verified)
├── test_tools.py       # UNCHANGED
└── test_provider_protocol.py  # UNCHANGED
```

### Pattern 1: Nest-and-Delegate Refactor

**What:** Restructure the storage format while keeping old function signatures working by delegating to the new API.

**When to use:** When refactoring a module's internal storage format while preserving its public API for backward compatibility.

**Example:**

```python
# auth.py — new core API

AUTH_FILE = Path(
    os.environ.get("MAESTRO_AUTH_FILE", Path.home() / ".maestro" / "auth.json")
)

def _read_store() -> dict:
    """Read the full auth store. Returns {} if file doesn't exist."""
    if not AUTH_FILE.exists():
        return {}
    return json.loads(AUTH_FILE.read_text())

def _write_store(data: dict) -> None:
    """Write the full auth store with correct permissions."""
    AUTH_FILE.parent.mkdir(parents=True, exist_ok=True)
    AUTH_FILE.write_text(json.dumps(data, indent=2))
    AUTH_FILE.chmod(0o600)

def get(provider_id: str) -> dict | None:
    """Get credentials for a specific provider."""
    store = _read_store()
    return store.get(provider_id)

def set(provider_id: str, data: dict) -> None:
    """Store credentials for a specific provider."""
    store = _read_store()
    store[provider_id] = data
    _write_store(store)

def remove(provider_id: str) -> None:
    """Remove credentials for a specific provider."""
    store = _read_store()
    if provider_id in store:
        del store[provider_id]
        _write_store(store)

def all_providers() -> list[str]:
    """List all provider IDs with stored credentials."""
    store = _read_store()
    return list(store.keys())
```

### Pattern 2: Backward-Compat Shim with Deprecation Warning

**What:** Old functions continue to work but warn users they're deprecated.

```python
# auth.py — backward compatibility (remove after Phase 6)

import warnings

# TokenSet dataclass stays exactly as-is
@dataclass
class TokenSet:
    access: str
    refresh: str
    expires: float
    account_id: str = ""
    email: str = ""

def _save(tokens: TokenSet):
    """Deprecated: Use auth.set("chatgpt", data) instead."""
    auth.set("chatgpt", {
        "access": tokens.access,
        "refresh": tokens.refresh,
        "expires": tokens.expires,
        "account_id": tokens.account_id,
        "email": tokens.email,
    })

def load() -> TokenSet | None:
    """Deprecated: Use auth.get("chatgpt") instead."""
    data = auth.get("chatgpt")
    if data is None:
        return None
    return TokenSet(**data)
```

### Pattern 3: CLI Subcommand Grouping

**What:** Restructure `maestro login`/`maestro logout` into `maestro auth login`/`maestro auth logout` with backward-compat aliases.

```python
# cli.py — new structure

def main():
    parser = argparse.ArgumentParser(prog="maestro", ...)
    sub = parser.add_subparsers(dest="command")

    # New: auth subcommand group
    auth_p = sub.add_parser("auth", help="Authentication management")
    auth_sub = auth_p.add_subparsers(dest="auth_command")

    auth_login = auth_sub.add_parser("login", help="Authenticate with a provider")
    auth_login.add_argument("provider", nargs="?", default=None,
                            help="Provider to authenticate with (e.g., chatgpt)")
    auth_login.add_argument("--device", action="store_true")

    auth_logout = auth_sub.add_parser("logout", help="Remove stored credentials")
    auth_logout.add_argument("provider", help="Provider to log out from")

    auth_status = auth_sub.add_parser("status", help="Show auth status")

    # Backward compat: old top-level commands
    login_p = sub.add_parser("login", help="Authenticate with ChatGPT (deprecated)")
    login_p.add_argument("--device", action="store_true")
    sub.add_parser("logout", help="Remove stored credentials (deprecated)")
    sub.add_parser("status", help="Show auth status (deprecated)")

    # ...

    if args.command == "login":
        warnings.warn(
            "'maestro login' is deprecated. Use 'maestro auth login chatgpt'.",
            DeprecationWarning,
            stacklevel=2,
        )
        # delegate to same logic as 'maestro auth login chatgpt'
```

### Anti-Patterns to Avoid

- **Breaking `TokenSet` import path:** Tests import `from maestro.auth import TokenSet`. Moving `TokenSet` to another module in this phase would break all tests. Keep `TokenSet` in `auth.py` throughout Phase 2. Phase 3 (ChatGPT provider migration) will handle the move with a re-export shim.
- **Changing `auth.load()` return type:** `agent.py` calls `auth.load()` and expects `TokenSet | None`. Changing this to return a dict would break the agent loop. Keep `load()` returning `TokenSet` — it's a shim that reads from the new store.
- **Auto-migrating existing `auth.json`:** The current `auth.json` is a flat dict `{access, refresh, expires, account_id, email}`. The new format nests it under `"chatgpt"`. The `_read_store()` function must detect the old format and handle it gracefully (or migration is a one-time task).
- **Adding provider-specific logic to the auth store:** The store is a dumb key-value persistence layer. Provider-specific OAuth flows (ChatGPT PKCE, Copilot device code) stay in their respective providers, not in `auth.py`.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| File permission enforcement | Custom permission-checking wrapper | `os.chmod(0o600)` on every write | Already done in `_save()`; extend to `_write_store()` |
| JSON format migration | Versioned schema with migration scripts | Detect old format at read time and wrap | Old format has `access` key at top level; new format has `chatgpt` at top level. Simple `isinstance(v, dict) and "access" in v` check. |
| Atomic file writes | Two-phase write with temp file + rename | Simple `write_text()` + `chmod()` | For 2-3 provider credentials (<1KB), crash safety from two-phase write is unnecessary. If it matters later, add it. |

**Key insight:** This phase is about storage format and API surface, not about new capabilities. Keep it small and boring.

## Runtime State Inventory

| Category | Items Found | Action Required |
|----------|-------------|------------------|
| Stored data | `~/.maestro/auth.json` exists with flat format `{access, refresh, expires, account_id, email}` | **Data migration:** Auto-detect old format on first `_read_store()` call, wrap under `"chatgpt"` key, rewrite file. One-time, transparent. |
| Live service config | None | — |
| OS-registered state | None | — |
| Secrets/env vars | `MAESTRO_AUTH_FILE` env var (configurable auth file path) | Code edit: ensure `_read_store()` and `_write_store()` use same `AUTH_FILE` constant (already the case) |
| Build artifacts | None | — |

**Nothing found in category:** Live service config, OS-registered state, Build artifacts — verified by codebase scan.

## Common Pitfalls

### Pitfall 1: Old `auth.json` Format Causes Crash on First Read After Upgrade

**What goes wrong:** User upgrades maestro, the existing `auth.json` is flat `{access, refresh, ...}`. `_read_store()` returns this dict. Code that expects `store.keys()` to return `["chatgpt"]` instead gets `["access", "refresh", "expires", ...]`. `all_providers()` returns `["access", "refresh", "expires"]` — nonsense.

**Why it happens:** Format change without migration detection.

**How to avoid:** Add format detection in `_read_store()`:

```python
def _read_store() -> dict:
    if not AUTH_FILE.exists():
        return {}
    data = json.loads(AUTH_FILE.read_text())
    # Detect old flat format (has 'access' key at top level)
    if isinstance(data, dict) and "access" in data and "chatgpt" not in data:
        # Migrate: wrap under "chatgpt" key
        migrated = {"chatgpt": data}
        _write_store(migrated)
        return migrated
    return data
```

**Warning signs:** `all_providers()` returns `["access", "refresh"]` instead of `["chatgpt"]`.

### Pitfall 2: `_save()` and `_write_store()` Race on the Same File

**What goes wrong:** During the transition period, both old `_save(tokens)` (from Phase 1 code) and new `_write_store(data)` write to the same `AUTH_FILE`. If `_save()` is called after `_write_store()`, it overwrites the multi-provider file with a flat single-provider file, destroying other providers' credentials.

**Why it happens:** Both code paths exist simultaneously during the transition.

**How to avoid:** Refactor `_save()` to delegate to `set()` instead of writing directly:

```python
def _save(tokens: TokenSet):
    """Backward compat: delegates to auth.set()."""
    auth.set("chatgpt", {
        "access": tokens.access,
        "refresh": tokens.refresh,
        "expires": tokens.expires,
        "account_id": tokens.account_id,
        "email": tokens.email,
    })
```

**Warning signs:** After logging in with ChatGPT, `auth.get("github-copilot")` returns `None` when it shouldn't.

### Pitfall 3: `argparse` Nested Subcommands Don't Parse Correctly

**What goes wrong:** Adding `auth` as a subcommand of `maestro` with `login`/`logout`/`status` as sub-subcommands. The `dest="auth_command"` is not accessible when `args.command == "auth"` — the inner parser's dest is separate.

**Why it happens:** `argparse` requires careful handling of nested subparsers. The outer parser sets `args.command = "auth"` but the inner parser sets a different attribute.

**How to avoid:** Use a single dest convention. Check `args.command` first, then check `args.auth_command` inside the `"auth"` branch. Test thoroughly with `maestro auth login chatgpt`, `maestro auth status`, `maestro auth logout chatgpt`.

```python
if args.command == "auth":
    if args.auth_command == "login":
        # handle auth login
    elif args.auth_command == "logout":
        # handle auth logout
    elif args.auth_command == "status":
        # handle auth status
```

**Warning signs:** `maestro auth login chatgpt` prints help instead of running login.

### Pitfall 4: Deprecation Warning Appears in Tests, Causing Test Noise

**What goes wrong:** Tests that call `auth.load()` or `auth._save()` trigger `DeprecationWarning`. pytest may show these as warnings in the output, or fail if `-W error::DeprecationWarning` is set.

**Why it happens:** Backward-compat shims emit warnings.

**How to avoid:** Use `warnings.warn(..., DeprecationWarning, stacklevel=2)` but don't emit warnings in the shim functions during this phase — only emit from the CLI layer when old top-level commands are used. The internal Python API (`load()`, `_save()`) should be annotated with docstring deprecation but NOT emit runtime warnings, to keep tests clean. The CLI layer (`maestro login`) is where the user-facing deprecation warning belongs.

**Warning signs:** Test output full of `DeprecationWarning` lines.

## Code Examples

### Core Multi-Slot API (auth.py additions)

```python
# Source: Derived from existing auth.py patterns + ROADMAP.md AUTH-02

def _read_store() -> dict:
    """Read the full auth store from disk."""
    if not AUTH_FILE.exists():
        return {}
    data = json.loads(AUTH_FILE.read_text())
    # Auto-migrate old flat format
    if isinstance(data, dict) and "access" in data and "chatgpt" not in data:
        migrated = {"chatgpt": data}
        _write_store(migrated)
        return migrated
    return data

def _write_store(store: dict) -> None:
    """Write the full auth store to disk with secure permissions."""
    AUTH_FILE.parent.mkdir(parents=True, exist_ok=True)
    AUTH_FILE.write_text(json.dumps(store, indent=2))
    AUTH_FILE.chmod(0o600)

def get(provider_id: str) -> dict | None:
    """Get credentials for a specific provider.

    Returns None if no credentials stored for this provider.
    """
    store = _read_store()
    return store.get(provider_id)

def set(provider_id: str, data: dict) -> None:
    """Store credentials for a specific provider.

    Creates the auth file if it doesn't exist.
    Overwrites existing credentials for the provider.
    """
    store = _read_store()
    store[provider_id] = data
    _write_store(store)

def remove(provider_id: str) -> bool:
    """Remove stored credentials for a provider.

    Returns True if credentials were removed, False if provider had no stored credentials.
    """
    store = _read_store()
    if provider_id in store:
        del store[provider_id]
        _write_store(store)
        return True
    return False

def all_providers() -> list[str]:
    """List all provider IDs with stored credentials."""
    store = _read_store()
    return list(store.keys())
```

### Backward-Compat Shim (auth.py modifications)

```python
# Existing _save() becomes a thin wrapper
def _save(tokens: TokenSet):
    """Store ChatGPT tokens. Deprecated: use auth.set('chatgpt', data)."""
    set("chatgpt", {
        "access": tokens.access,
        "refresh": tokens.refresh,
        "expires": tokens.expires,
        "account_id": tokens.account_id,
        "email": tokens.email,
    })

# Existing load() becomes a thin wrapper
def load() -> TokenSet | None:
    """Load ChatGPT tokens. Deprecated: use auth.get('chatgpt')."""
    data = get("chatgpt")
    if data is None:
        return None
    return TokenSet(**data)

# Existing logout() becomes a thin wrapper
def logout():
    """Remove ChatGPT credentials. Deprecated: use auth.remove('chatgpt')."""
    if remove("chatgpt"):
        print("Logged out.")
    else:
        print("Not logged in.")
```

### CLI Restructure (cli.py modifications)

```python
# New auth subcommand group
auth_p = sub.add_parser("auth", help="Authentication management")
auth_sub = auth_p.add_subparsers(dest="auth_command")

auth_login_p = auth_sub.add_parser("login", help="Authenticate with a provider")
auth_login_p.add_argument("provider", nargs="?", default=None)
auth_login_p.add_argument("--device", action="store_true")

auth_sub.add_parser("logout", help="Remove stored credentials")
# Note: logout needs a provider arg — add in Phase 6 when multiple providers exist
# For now, defaults to "chatgpt"

auth_sub.add_parser("status", help="Show auth status for all providers")

# In dispatch logic:
if args.command == "auth":
    if args.auth_command == "login":
        provider = args.provider or "chatgpt"  # default
        if provider == "chatgpt":
            method = "device" if args.device else "browser"
            ts = login(method)
            print(f"Logged in as: {ts.email or ts.account_id}")
        else:
            print(f"Unknown provider: {provider}")
    elif args.auth_command == "status":
        providers = auth.all_providers()
        if not providers:
            print("Not logged in to any provider.")
        for pid in providers:
            print(f"  {pid}: authenticated")
    elif args.auth_command == "logout":
        # For now, logout removes chatgpt (only provider)
        auth.remove("chatgpt")
        print("Logged out.")

# Old commands with deprecation warning:
elif args.command == "login":
    import warnings
    warnings.warn(
        "'maestro login' is deprecated. Use 'maestro auth login chatgpt'.",
        DeprecationWarning,
        stacklevel=2,
    )
    method = "device" if args.device else "browser"
    ts = auth.login(method)
    print(f"Logged in as: {ts.email or ts.account_id}")
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Flat `auth.json` | Per-provider nested `auth.json` | This phase | Enables multiple simultaneous provider credentials |
| `maestro login` top-level | `maestro auth login <provider>` | This phase | CLI becomes extensible for multiple providers |
| Direct `_save()` / `load()` | `set()` / `get()` with provider ID | This phase | Generic key-value store replaces ChatGPT-specific persistence |

**Deprecated/outdated:**
- `_save(tokens: TokenSet)` as the primary write path: delegates to `set("chatgpt", ...)` in this phase
- `load()` as the primary read path: delegates to `get("chatgpt")` in this phase
- `maestro login` as the top-level command deprecated in favor of `maestro auth login chatgpt`; top-level `maestro logout` and `maestro status` remain unchanged in Phase 2

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | Each provider's credential data is a flat dict (not deeply nested). Different providers store different fields. | Standard Stack | Low — even if nesting is needed, dict-of-dicts supports it |
| A2 | `TokenSet` stays in `auth.py` through Phase 2. Phase 3 moves it to `providers/chatgpt.py` with a re-export shim. | Architecture Patterns | Low — keeping it in auth.py is the safe default |
| A3 | Auto-migration of old `auth.json` format is safe (one-time, transparent, no user interaction needed). | Common Pitfalls | Low — migration is deterministic and lossless |
| A4 | The `remove()` function for `auth logout` in this phase only needs to handle "chatgpt" (the only existing provider). | Architecture Patterns | Low — the function is generic; CLI just passes "chatgpt" |

**If this table is empty:** All claims in this research were verified or cited — no user confirmation needed.

## Open Questions (RESOLVED)

1. **Should `_read_store()` auto-migrate or require explicit migration?**
   - What we know: The old format is `{access, refresh, ...}` and new format is `{"chatgpt": {access, refresh, ...}}`.
   - What's unclear: Whether auto-migration could cause issues if the file is partially written (crash during write).
   - Recommendation: Auto-migrate on read — it's the simplest user experience and the risk is minimal (file is <1KB, write is atomic at the OS level for small writes).
   - RESOLVED: Auto-migrate on read in Phase 2.

2. **Should `maestro auth login` (no provider arg) default to "chatgpt" or error?**
   - What we know: AUTH-08 requires the legacy login path to warn and route users to `maestro auth login chatgpt`. The new canonical command is provider-aware.
   - What's unclear: Whether `maestro auth login` (without a provider) should work and default to chatgpt.
   - Recommendation: Default to "chatgpt" when no provider is specified — matches existing behavior and provides a smooth transition.
   - RESOLVED: `maestro auth login` defaults to `chatgpt` with no extra provider-selection prompt.

3. **Should `maestro auth status` show token expiry details or just "authenticated/not authenticated"?**
   - What we know: AUTH-06 says "show all providers and their auth state." Phase 6 implements AUTH-06 fully.
   - What's unclear: Whether this phase should show per-provider expiry details.
   - Recommendation: Minimal implementation in Phase 2: list providers + "authenticated" or "not authenticated". Full details (expiry, email) deferred to Phase 6.
   - RESOLVED: Deferred entirely for Phase 2 because top-level `status` remains unchanged in this phase; richer provider-aware status work belongs to later phases.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python 3.12 | Runtime | ✓ | 3.12.7 | — |
| pytest | Test suite | ✓ | via dev deps | — |
| pytest-asyncio | Test suite | ✓ | via dev deps | — |
| httpx | OAuth flows | ✓ | 0.28.1 | — |
| `~/.maestro/` directory | Auth storage | ✓ | exists | Auto-created on first write |

**Missing dependencies with no fallback:** None

**Missing dependencies with fallback:** N/A

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest (via dev deps) |
| Config file | `pyproject.toml` → `[tool.pytest.ini_options]` |
| Quick run command | `python -m pytest tests/test_auth_store.py -v` |
| Full suite command | `python -m pytest tests/ -v` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| AUTH-01 | `auth.set("chatgpt", data)` and `auth.get("chatgpt")` round-trip | unit | `python -m pytest tests/test_auth_store.py::test_set_get_roundtrip -v` | ❌ Wave 0 |
| AUTH-01 | `~/.maestro/auth.json` created with `0o600` on first write | unit | `python -m pytest tests/test_auth_store.py::test_file_permissions -v` | ❌ Wave 0 |
| AUTH-01 | Old flat `auth.json` auto-migrates to nested format | unit | `python -m pytest tests/test_auth_store.py::test_auto_migration -v` | ❌ Wave 0 |
| AUTH-02 | `auth.all_providers()` returns list of provider IDs | unit | `python -m pytest tests/test_auth_store.py::test_all_providers -v` | ❌ Wave 0 |
| AUTH-02 | `auth.remove("chatgpt")` removes credentials | unit | `python -m pytest tests/test_auth_store.py::test_remove -v` | ❌ Wave 0 |
| AUTH-08 | `maestro login` shows deprecation warning | unit (CLI) | `python -m pytest tests/test_auth_store.py::test_login_deprecation -v` | ❌ Wave 0 |
| AUTH-08 | `maestro auth login chatgpt` works as new command | integration | `python -m pytest tests/test_auth_store.py::test_auth_login_chatgpt -v` | ❌ Wave 0 |
| Back-compat | `auth.load()` still returns `TokenSet` | unit | `python -m pytest tests/test_auth_store.py::test_load_backward_compat -v` | ❌ Wave 0 |
| Back-compat | `auth._save()` still writes readable by `load()` | unit | `python -m pytest tests/test_auth_store.py::test_save_backward_compat -v` | ❌ Wave 0 |
| No regression | All 55 existing tests pass | regression | `python -m pytest tests/ -v` | ✅ existing |

### Sampling Rate

- **Per task commit:** `python -m pytest tests/test_auth_store.py -v`
- **Per wave merge:** `python -m pytest tests/ -v`
- **Phase gate:** Full suite green before `/gsd-verify-work`

### Wave 0 Gaps

- [ ] `tests/test_auth_store.py` — covers AUTH-01, AUTH-02, AUTH-08, backward compat
- [ ] Framework config: already exists in `pyproject.toml`

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | yes | OAuth PKCE + Device Code flows (existing) |
| V3 Session Management | no | — |
| V4 Access Control | no | — |
| V5 Input Validation | yes | Provider ID validation (alphanumeric + hyphens) |
| V6 Cryptography | no | — (tokens stored as-is; encryption is deferred to v2) |

### Known Threat Patterns for Auth Store

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Credential file read by other users | Information Disclosure | `chmod(0o600)` on every write |
| Path traversal in provider ID | Tampering | Validate provider_id format: `^[a-z0-9-]+$` |
| Old-format auth.json read after downgrade | Information Disclosure | Format detection handles both old and new formats |
| Race condition on concurrent writes | Tampering | Single-process CLI; concurrent writes not expected in v1 |

## Sources

### Primary (HIGH confidence)

- `maestro/auth.py` — current implementation, all 318 lines analyzed line-by-line
- `maestro/cli.py` — current CLI structure, all 136 lines analyzed
- `maestro/agent.py` — auth consumer, `auth.load()` and `auth.TokenSet` usage confirmed
- `tests/test_agent_loop.py` — `from maestro.auth import TokenSet` confirmed at line 6
- `.planning/ROADMAP.md` — Phase 2 success criteria and requirements mapping
- `.planning/REQUIREMENTS.md` — AUTH-01, AUTH-02, AUTH-08 detailed specifications
- `.planning/research/ARCHITECTURE.md` — component boundaries, data flow, auth.py responsibility
- `.planning/research/PITFALLS.md` — Pitfall 9 (TokenSet import break), Pitfall 15 (file permissions)

### Secondary (MEDIUM confidence)

- `.planning/DEPENDENCY_ANALYSIS.md` — confirms Phase 2 depends only on Phase 1
- `.planning/phases/01-provider-plugin-protocol/01-VERIFICATION.md` — Phase 1 is verified complete, Phase 2 unblocked

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — all libraries already in project, no new deps
- Architecture: HIGH — minimal change to existing patterns, fully analyzed all consumers
- Pitfalls: HIGH — all pitfalls derived from direct code analysis, not theoretical

**Research date:** 2026-04-17
**Valid until:** 30 days (stable domain, no fast-moving dependencies)
