# Assumptions & Constraints

**Scan Date:** 2025-04-18

## Hard Constraints (Project Invariants)

### Backward Compatibility
- `maestro run` (no flags) must behave identically to current behavior
- All 26+ existing tests must continue to pass
- Legacy `maestro login/logout` commands deprecated but still functional

### Tech Stack Lock
- **Language:** Python 3.12.7 (confirmed via `pyproject.toml` requires-python >=3.11)
- **Package Manager:** pip + pyproject.toml
- **No Framework Changes:** Cannot change to different HTTP client, LangGraph version locked

### Security Requirements
- Path guard must apply inside every Worker (not just CLI level)
- Recursion safety: max depth guard mandatory; infinite recursion = hard failure
- Destructive tool confirmation required unless `--auto` flag

## Environmental Assumptions

### Development Environment
- Python 3.12+ installed and accessible
- `~/.maestro/` directory writable for auth/config storage
- Network access to `auth.openai.com` and `chatgpt.com`
- Modern browser available for OAuth (or `--device` flag for headless)

### Runtime Assumptions
- **Default Model:** `gpt-5.4-mini` (ChatGPT provider)
- **Workdir:** Defaults to current working directory if not specified
- **Token Refresh:** Automatic refresh when within 5 minutes of expiry
- **Max Iterations:** 20 tool-call iterations before agent loop terminates

## Architectural Assumptions

### Provider Plugin System
- Entry points defined in `pyproject.toml` under `[project.entry-points."maestro.providers"]`
- Third-party providers installable via `pip install` without touching maestro source
- Provider must implement `ProviderPlugin` Protocol from `maestro/providers/base.py`

### Authentication Model
- ChatGPT uses OAuth2 PKCE + Device Code flow (same as Codex CLI)
- Token storage is per-provider (keyed by provider ID in auth.json)
- Access tokens valid ~1 hour, refresh tokens long-lived

### Tool Execution Model
- All file paths resolved relative to workdir with path guard validation
- Tools return JSON-serializable dicts (success or error)
- Shell execution runs in workdir with configurable timeout (default 30s)

## Known Limitations

### Current (Phase 4 Status)
- Only ChatGPT provider fully wired for execution (per `cli.py` line 286-290)
- Non-ChatGPT providers are discoverable but not runnable
- Phase 5 required to wire `provider.stream()` for alternate providers

### LangGraph Pattern Constraints
- `@entrypoint/@task` decorators used for single-agent flow
- `StateGraph` + `Send` API required for multi-agent parallel execution (not yet implemented)
- Parallel writes require `Annotated[list, operator.add]` reducers

### Test Coverage Gaps
- Integration tests for third-party providers (external packages) need provider installation
- OAuth flows mocked in tests; no live auth testing in CI

## Version Assumptions

### Confirmed Versions (from `.venv/`)
| Package | Version | Confidence |
|---------|---------|------------|
| Python | 3.12.7 | High |
| langgraph | 1.1.6 | High |
| httpx | 0.28.1 | High |
| httpx-sse | 0.4.1 | High |
| pydantic | 2.11.7 | High |
| openai | 2.32.0 | High |

### GitHub Copilot (Planned)
- **CLIENT_ID:** `Ov23li8tweQw6odWQebz` (from design spec)
- **API Base:** `https://api.githubcopilot.com/chat/completions`
- **Status:** Planned in ROADMAP but not yet implemented
