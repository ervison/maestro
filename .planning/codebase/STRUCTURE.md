# Codebase Structure

**Analysis Date:** 2025-04-18

## Directory Layout

```
maestro/
├── maestro/               # Main package
│   ├── __init__.py        # Package exports
│   ├── cli.py             # CLI entry point and commands
│   ├── agent.py           # Agent execution and LangGraph integration
│   ├── auth.py            # OAuth2 authentication (ChatGPT)
│   ├── config.py          # Configuration management
│   ├── models.py          # Model resolution and parsing
│   ├── tools.py           # File system and shell tools
│   └── providers/         # Provider plugin package
│       ├── __init__.py    # Provider exports
│       ├── base.py        # ProviderPlugin Protocol and types
│       ├── chatgpt.py     # ChatGPT provider implementation
│       └── registry.py    # Provider discovery and registry
├── tests/                 # Test suite
│   ├── __init__.py        # Test package marker
│   ├── test_agent_loop.py           # Core agent loop tests
│   ├── test_agent_loop_provider.py  # Provider-based loop tests
│   ├── test_auth_browser_oauth.py   # OAuth flow tests
│   ├── test_auth_store.py           # Auth storage tests
│   ├── test_chatgpt_provider.py     # ChatGPT provider tests
│   ├── test_cli_auth.py             # CLI auth command tests
│   ├── test_cli_models.py           # CLI models command tests
│   ├── test_config.py               # Config tests
│   ├── test_model_resolution.py     # Model resolution tests
│   ├── test_provider_protocol.py    # Provider Protocol tests
│   ├── test_provider_registry.py    # Provider registry tests
│   └── test_tools.py                # Tool execution tests
├── .planning/             # Project planning (GSD)
│   ├── PROJECT.md         # Project definition
│   ├── ROADMAP.md         # Implementation roadmap
│   ├── REQUIREMENTS.md    # Requirements specification
│   ├── STATE.md           # Current state tracking
│   └── codebase/          # This scan output
├── pyproject.toml         # Project metadata and dependencies
├── .gitignore             # Git ignore patterns
├── AGENTS.md              # Agent configuration docs
└── SECURITY.md            # Security policy
```

## Directory Purposes

**`maestro/`** - Main package
- Purpose: Core application code
- Contains: 12 Python modules
- Key files: `cli.py`, `agent.py`, `auth.py`, `tools.py`

**`maestro/providers/`** - Provider plugin package
- Purpose: LLM provider abstraction
- Contains: 4 Python modules
- Key files: `base.py` (Protocol), `chatgpt.py` (implementation), `registry.py` (discovery)

**`tests/`** - Test suite
- Purpose: Unit and integration tests
- Contains: 12 test files
- Pattern: One test file per source module

**`.planning/`** - Project planning
- Purpose: GSD workflow artifacts
- Contains: Project docs, roadmap, requirements, state tracking
- Key files: `PROJECT.md`, `ROADMAP.md`, `REQUIREMENTS.md`

## Key File Locations

### Entry Points
- `maestro/cli.py:main()` - CLI command `maestro`
- `maestro/agent.py:run()` - Agent execution entry
- Registered in `pyproject.toml`:
  ```toml
  [project.scripts]
  maestro = "maestro.cli:main"
  ```

### Configuration
- `pyproject.toml` - Project metadata, dependencies, entry points
- `maestro/config.py` - Runtime configuration loading
- `maestro/auth.py` - Auth storage paths

### Core Logic
- `maestro/agent.py` - Agent loop (439 lines)
- `maestro/providers/chatgpt.py` - ChatGPT provider (466 lines)
- `maestro/providers/registry.py` - Provider discovery (286 lines)
- `maestro/auth.py` - OAuth implementation (399 lines)

### Testing
- `tests/test_provider_protocol.py` - Protocol validation tests
- `tests/test_provider_registry.py` - Registry tests (428 lines)
- `tests/test_chatgpt_provider.py` - Provider implementation tests

## Naming Conventions

### Files
- **Source:** `snake_case.py` (e.g., `chatgpt.py`, `registry.py`)
- **Tests:** `test_*.py` (e.g., `test_tools.py`, `test_config.py`)
- **No type suffixes:** Use `chatgpt.py` not `chatgpt_provider.py`

### Directories
- **Packages:** `snake_case` (e.g., `maestro/providers/`)
- **Top-level:** Flat names (e.g., `tests/`, `docs/`)

### Functions
- **Public:** `snake_case()` (e.g., `run()`, `resolve_model()`)
- **Private:** `_leading_underscore()` (e.g., `_save()`, `_read_store()`)
- **Test functions:** `test_description()` (e.g., `test_create_user_message()`)

### Classes
- **Public:** `PascalCase` (e.g., `ChatGPTProvider`, `TokenSet`)
- **Protocols:** `PascalCase` with `Protocol` suffix implied
- **Tests:** `TestPascalCase` (e.g., `TestMessage`)

### Constants
- **Module-level:** `UPPER_CASE` (e.g., `CLIENT_ID`, `DEFAULT_MODEL`)
- **Private:** `_LEADING_UNDERSCORE` (e.g., `_CACHE_TTL`)

## Where to Add New Code

### New Feature (e.g., new CLI command)
- Primary code: `maestro/cli.py` (add subparser and handler)
- Tests: `tests/test_cli_*.py` (create new or add to existing)

### New Provider (e.g., GitHub Copilot)
- Implementation: `maestro/providers/copilot.py`
- Entry point: `pyproject.toml` under `[project.entry-points."maestro.providers"]`
- Tests: `tests/test_copilot_provider.py`

### New Tool
- Implementation: `maestro/tools.py` (add to `_TOOL_FNS` dict)
- Schema: `TOOL_SCHEMAS` list in same file
- Tests: `tests/test_tools.py`

### New Configuration Option
- Config dataclass: `maestro/config.py` `Config` class
- CLI flag: `maestro/cli.py` (add to relevant subparser)
- Tests: `tests/test_config.py`

### Multi-Agent Orchestration
- New file: `maestro/orchestrator.py` (for StateGraph + Send API)
- Integration: `maestro/agent.py` (refactor or extend)
- Tests: `tests/test_orchestrator.py`

## Special Directories

### `.venv/`
- Purpose: Virtual environment (not committed)
- Generated: Yes (by `python -m venv` or similar)
- Committed: No (in `.gitignore`)

### `.planning/`
- Purpose: GSD workflow artifacts
- Generated: Partially (some manual, some by GSD commands)
- Committed: Yes (tracked in git)

### `.pytest_cache/`
- Purpose: pytest cache directory
- Generated: Yes (by pytest)
- Committed: No (in `.gitignore`)

### `.mypy_cache/`
- Purpose: mypy type checking cache
- Generated: Yes (by mypy)
- Committed: No (in `.gitignore`)

---

*Structure analysis: 2025-04-18*
