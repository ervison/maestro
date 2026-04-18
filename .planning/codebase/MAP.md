# Codebase Map

**Scan Date:** 2025-04-18

## Overview

Maestro is a CLI-driven AI agent that executes software engineering tasks using file system tools and shell commands. Built on LangGraph with a provider plugin system for LLM backends.

## Entry Points

### CLI Entry Point
- `maestro/cli.py:main()` - Main CLI entry point via `maestro` command
- Registered in `pyproject.toml` as `[project.scripts]` entry point

### Agent Execution Entry Point
- `maestro/agent.py:run()` - Main agent execution function
- `maestro/agent.py:_run_agentic_loop()` - Core agentic loop implementation

## Main Packages/Modules

### Core Package: `maestro/`

| File | Purpose | Key Classes/Functions |
|------|---------|----------------------|
| `maestro/__init__.py` | Package exports | Config, model resolution, provider registry functions |
| `maestro/cli.py` | Command-line interface | CLI commands: auth, login, logout, run, models, status |
| `maestro/agent.py` | Agent execution | `run()`, `_run_agentic_loop()`, `@entrypoint/@task` |
| `maestro/auth.py` | OAuth2 authentication | `TokenSet`, PKCE flow, device code flow |
| `maestro/config.py` | Configuration management | `Config`, `load()`, `save()` |
| `maestro/models.py` | Model resolution | `resolve_model()`, `parse_model_string()`, `get_available_models()` |
| `maestro/tools.py` | File system tools | `execute_tool()`, `TOOL_SCHEMAS`, path guards |

### Provider Package: `maestro/providers/`

| File | Purpose | Key Classes/Functions |
|------|---------|----------------------|
| `maestro/providers/__init__.py` | Provider exports | Re-exports base types and ChatGPTProvider |
| `maestro/providers/base.py` | Protocol definition | `ProviderPlugin` Protocol, `Message`, `Tool`, `ToolCall` |
| `maestro/providers/chatgpt.py` | ChatGPT provider | `ChatGPTProvider`, model fetching, SSE streaming |
| `maestro/providers/registry.py` | Provider discovery | `discover_providers()`, `get_provider()`, `get_default_provider()` |

## Tests Location

- **Test Directory:** `tests/`
- **Test Files:**
  - `test_agent_loop.py` - Core agent loop tests (legacy path)
  - `test_agent_loop_provider.py` - Provider-based agent loop tests
  - `test_auth_browser_oauth.py` - OAuth flow tests
  - `test_auth_store.py` - Auth storage tests
  - `test_chatgpt_provider.py` - ChatGPT provider tests
  - `test_cli_auth.py` - CLI authentication tests
  - `test_cli_models.py` - CLI models command tests
  - `test_config.py` - Configuration tests
  - `test_model_resolution.py` - Model resolution tests
  - `test_provider_protocol.py` - Provider Protocol tests
  - `test_provider_registry.py` - Provider registry tests
  - `test_tools.py` - Tool execution tests

## Dependencies

- **Dependency File:** `pyproject.toml`
- **Core Dependencies:**
  - `langgraph>=0.4`
  - `langchain>=0.3`
  - `langchain-openai>=0.3`
  - `httpx>=0.27`
  - `pydantic>=2.0` (implied by langchain)

## Provider Plugin System

- **Entry Point Group:** `maestro.providers` (defined in `pyproject.toml`)
- **Current Provider:** ChatGPT (`chatgpt` entry point)
- **Registry Location:** `maestro/providers/registry.py`
- **Discovery Method:** `importlib.metadata.entry_points()`
- **Protocol Definition:** `maestro/providers/base.py:ProviderPlugin`

## LangGraph Orchestration

- **LangGraph Version:** 1.1.6 (from `.venv/`)
- **APIs Used:**
  - `@entrypoint/@task` decorators (single-agent observability)
  - `StateGraph` API (for multi-agent orchestration, future)
- **Graph State:** Not currently persisted to external store
- **Current Pattern:** Single-agent loop with tool execution

## Configuration & State

- **Config File:** `~/.maestro/config.json` (via `maestro/config.py`)
- **Auth File:** `~/.maestro/auth.json` (via `maestro/auth.py`)
- **Cache Directory:** `~/.cache/maestro/` (models, available models)
- **Environment Variable:** `MAESTRO_CONFIG_FILE`, `MAESTRO_AUTH_FILE`

## Key External Integrations

- **OpenAI Auth:** `https://auth.openai.com/oauth/` (PKCE + device flow)
- **ChatGPT API:** `https://chatgpt.com/backend-api/codex/responses`
- **Models Catalog:** `https://models.dev/api.json`

## Security Considerations

- **Path Guard:** `maestro/tools.py:resolve_path()` - validates paths within workdir
- **File Permissions:** Auth/config files written with 0o600 permissions
- **Destructive Tools:** Confirmation required unless `--auto` flag set
- **OAuth Scope:** `openid profile email offline_access api.connectors.read api.connectors.invoke`
