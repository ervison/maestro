# Technology Stack

**Analysis Date:** 2025-04-18

## Languages

**Primary:**
- Python 3.12.7 (requires-python >=3.11 in `pyproject.toml`)

**Secondary:**
- None (pure Python project)

## Runtime

**Environment:**
- CPython 3.12.7
- Virtual environment at `.venv/`

**Package Manager:**
- pip (bundled with Python)
- pyproject.toml for project metadata and dependencies
- Lockfile: None (uses direct version constraints)

## Frameworks & Libraries

**Core:**
| Package | Version | Purpose |
|---------|---------|---------|
| langgraph | >=0.4 | Agent orchestration framework |
| langchain | >=0.3 | LLM abstractions and messages |
| langchain-openai | >=0.3 | OpenAI integration for LangChain |
| httpx | >=0.27 | Async HTTP client |

**Testing:**
| Package | Version | Purpose |
|---------|---------|---------|
| pytest | >=7.0 | Test framework |
| pytest-asyncio | >=0.21 | Async test support |

**Stdlib Extensions:**
| Module | Purpose |
|--------|---------|
| importlib.metadata | Entry point discovery (stdblib, Python 3.12) |
| dataclasses | Immutable data types |
| pathlib | Modern path handling |
| asyncio | Async/await for streaming |

## Key Dependencies

**Critical for Functionality:**
- **langgraph** - Provides `@entrypoint/@task` decorators and `StateGraph` API
- **httpx** - All HTTP/SSE communication with ChatGPT API
- **pydantic** (via langchain) - Structured output validation

**Infrastructure:**
- **langchain_core** - Message types (`HumanMessage`, `AIMessage`, `SystemMessage`)
- **anyio** (transitive) - Async I/O compatibility layer

## Configuration

**Environment:**
- `MAESTRO_CONFIG_FILE` - Override config file path
- `MAESTRO_AUTH_FILE` - Override auth file path
- `MAESTRO_MODEL` - Default model selection

**Build:**
- `pyproject.toml` - PEP 621 project metadata, dependencies, scripts

## Platform Requirements

**Development:**
- Python 3.11+ (3.12.7 recommended)
- pip for dependency management
- Virtual environment (`.venv/`)
- Network access for OAuth and API calls

**Production:**
- Same as development (Python CLI tool)
- User's ChatGPT Plus/Pro subscription
- Local filesystem access for file tools

## Version Constraints

```toml
[project]
requires-python = ">=3.11"
dependencies = [
    "langgraph>=0.4",
    "langchain>=0.3",
    "langchain-openai>=0.3",
    "httpx>=0.27",
]

[project.optional-dependencies]
dev = [
    "pytest>=7.0",
    "pytest-asyncio>=0.21",
]
```

## Installed Versions (from .venv/)

| Package | Actual Version |
|---------|----------------|
| langgraph | 1.1.6 |
| httpx | 0.28.1 |
| httpx-sse | 0.4.1 |
| pydantic | 2.11.7 |
| openai | 2.32.0 |
| anyio | 4.10.0 |

## Notes

- No additional build tools required (pure Python)
- No frontend/UI components
- No database dependencies (uses local JSON files)
- Entry point: `maestro = "maestro.cli:main"` in pyproject.toml

---

*Stack analysis: 2025-04-18*
