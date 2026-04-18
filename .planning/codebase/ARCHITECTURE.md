# Architecture

**Analysis Date:** 2025-04-18

## Pattern Overview

**Overall:** Layered architecture with plugin-based provider system

**Key Characteristics:**
1. **Single-Agent Loop** (current) - LangGraph `@entrypoint/@task` for observability
2. **Provider Plugin System** - Entry point-based discovery with Protocol interface
3. **Tool-Based Interaction** - File system and shell tools exposed to LLM
4. **Path Guard Security** - All file operations constrained to workdir

## Layers

### CLI Layer
- **Purpose:** Command-line interface, argument parsing, command dispatch
- **Location:** `maestro/cli.py`
- **Contains:** argparse setup, command handlers, user interaction
- **Depends on:** Auth, Config, Models, Agent
- **Used by:** User (direct invocation)

### Agent Layer
- **Purpose:** Core agentic loop execution, LLM streaming, tool orchestration
- **Location:** `maestro/agent.py`
- **Contains:** `run()`, `_run_agentic_loop()`, `@entrypoint/@task` decorators
- **Depends on:** Auth, Providers, Tools
- **Used by:** CLI layer

### Provider Layer
- **Purpose:** LLM provider abstraction and discovery
- **Location:** `maestro/providers/`
- **Contains:** Protocol, registry, ChatGPT implementation
- **Depends on:** Auth (for credentials), httpx (for transport)
- **Used by:** Agent layer

### Tools Layer
- **Purpose:** File system and shell tool implementations
- **Location:** `maestro/tools.py`
- **Contains:** 8 tools (read, write, create, delete, move, list, search, shell)
- **Depends on:** None (stdlib only)
- **Used by:** Agent layer

### Auth Layer
- **Purpose:** OAuth2 authentication and token management
- **Location:** `maestro/auth.py`
- **Contains:** `TokenSet`, PKCE flow, device flow, token refresh
- **Depends on:** None (httpx for HTTP, stdlib for crypto)
- **Used by:** CLI layer, Provider layer

### Config Layer
- **Purpose:** User configuration persistence
- **Location:** `maestro/config.py`
- **Contains:** `Config` dataclass, dot-notation access
- **Depends on:** None (stdlib only)
- **Used by:** CLI layer, Models layer

### Models Layer
- **Purpose:** Model string parsing and resolution
- **Location:** `maestro/models.py`
- **Contains:** `parse_model_string()`, `resolve_model()`, `get_available_models()`
- **Depends on:** Config, Provider registry
- **Used by:** CLI layer

## Data Flow

### Single-Agent Execution Flow

1. **CLI receives command:** `maestro run "prompt"`
2. **CLI resolves model:** Priority chain (flag → env → config → default)
3. **CLI calls agent:** `run(model, prompt, workdir)`
4. **Agent creates provider:** `get_default_provider()` via registry
5. **Agent runs loop:** `_run_agentic_loop()` with streaming
6. **Provider streams:** `provider.stream()` yields text chunks + final Message
7. **Agent executes tools:** If `tool_calls` in message, execute and append results
8. **Loop continues:** Until no tool calls or max iterations reached
9. **Result returned:** Final text response to CLI, printed to stdout

### Provider Discovery Flow

1. **Registry queried:** `discover_providers()` called
2. **Entry points scanned:** `importlib.metadata.entry_points(group="maestro.providers")`
3. **Classes loaded:** Each entry point loaded, instantiated
4. **Validation:** `_is_valid_provider()` checks Protocol compliance
5. **Cached:** `lru_cache(maxsize=1)` stores results
6. **Lookup:** `get_provider(id)` returns fresh instance

### Authentication Flow

1. **User runs:** `maestro auth login chatgpt`
2. **Method selected:** Browser (default) or Device (`--device`)
3. **Browser flow:**
   - PKCE verifier/challenge generated
   - Browser opened to authorize URL
   - Local server waits for callback
   - Code exchanged for tokens
4. **Device flow:**
   - Device code requested
   - User code displayed
   - Poll token endpoint until authorized
5. **Tokens stored:** `~/.maestro/auth.json` with 0o600 permissions

## Key Abstractions

### ProviderPlugin Protocol
- **Purpose:** Define interface for LLM providers
- **Location:** `maestro/providers/base.py`
- **Methods:** `id`, `name`, `list_models()`, `stream()`, `auth_required()`, `login()`, `is_authenticated()`
- **Pattern:** `@runtime_checkable` for `isinstance()` checks

### Message Type
- **Purpose:** Provider-neutral conversation message
- **Location:** `maestro/providers/base.py`
- **Fields:** `role` (user/assistant/system/tool), `content`, `tool_calls`, `tool_call_id`
- **Pattern:** Immutable dataclass

### Tool Type
- **Purpose:** Provider-neutral tool definition
- **Location:** `maestro/providers/base.py`
- **Fields:** `name`, `description`, `parameters` (JSON Schema)
- **Pattern:** Matches OpenAI function calling schema

## Entry Points

### CLI Entry
- **Location:** `maestro/cli.py:main()`
- **Triggers:** `maestro` command (console script)
- **Responsibilities:** Parse args, dispatch commands, handle errors

### Agent Entry
- **Location:** `maestro/agent.py:run()`
- **Triggers:** `maestro run` command via CLI
- **Responsibilities:** Setup LangGraph flow, invoke agent

### Provider Entry
- **Location:** Provider classes via entry points
- **Triggers:** `discover_providers()` in registry
- **Responsibilities:** Implement `ProviderPlugin` Protocol

## Error Handling

**Strategy:** Layer-specific error handling with actionable messages

**Patterns:**
1. **Path errors:** `PathOutsideWorkdirError` raised, caught, returned as tool error
2. **Auth errors:** RuntimeError with "Run: maestro auth login" guidance
3. **API errors:** RuntimeError with status code and body snippet
4. **Config errors:** RuntimeError with file path and repair guidance

## Cross-Cutting Concerns

### Logging
- **Approach:** Standard Python logging
- **Level:** Debug for internal operations, info for user-facing
- **Location:** Module-level loggers (`__name__`)

### Validation
- **Approach:** Pydantic (via LangChain) + manual validation
- **Model validation:** `model_validate()` in `models.py`
- **Provider validation:** Runtime Protocol checks in `registry.py`

### Authentication
- **Approach:** Per-provider OAuth2 with token refresh
- **Storage:** JSON file with filesystem permissions
- **Refresh:** Automatic when within 5 minutes of expiry

---

*Architecture analysis: 2025-04-18*
