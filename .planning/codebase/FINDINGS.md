# Scan Findings

**Scan Date:** 2025-04-18
**Focus:** tech+arch

## Critical Blockers

### 1. Non-ChatGPT Providers Not Executable
- **Location:** `maestro/cli.py` lines 286-290
- **Issue:** Runtime check rejects non-ChatGPT providers even when discoverable
- **Impact:** Cannot use alternate providers (GitHub Copilot, etc.)
- **Code:**
  ```python
  if provider.id != "chatgpt":
      raise RuntimeError(
          f"Provider '{provider.id}' is discoverable but not runnable yet; "
          "Phase 5 must wire provider.stream()"
      )
  ```
- **Resolution:** Phase 5 implementation required

## High Priority Gaps

### 2. Missing Multi-Agent Orchestration
- **Current:** Single-agent loop with `@entrypoint/@task`
- **Missing:** LangGraph `StateGraph` + `Send` API for parallel Workers
- **Impact:** Cannot execute multi-domain tasks in parallel
- **Requirement:** Per PROJECT.md, planner must decompose tasks into dependency DAG

### 3. TODO/FIXME Comments Found
- **None detected** in source files (clean codebase)

## Technical Debt

### 4. Legacy Path in Agent Loop
- **Location:** `maestro/agent.py` lines 256-259
- **Issue:** Dual-path code (provider-based and tokens-based)
- **Purpose:** Backward compatibility with existing tests
- **Recommendation:** Deprecate tokens-based path once tests migrated

### 5. Hard-coded ChatGPT Constants in Auth
- **Location:** `maestro/auth.py` line 22-36
- **Issue:** ChatGPT-specific OAuth URLs and CLIENT_ID hard-coded
- **Impact:** Other providers must implement their own auth flows
- **Note:** This is by design - auth is provider-specific

### 6. Model Resolution Complexity
- **Location:** `maestro/models.py` lines 61-131
- **Issue:** 5-level priority chain with fallbacks
- **Complexity:** High - may confuse users
- **Chain:** CLI flag → env var → agent config → global config → provider default

## Security Findings

### 7. Path Traversal Prevention
- **Location:** `maestro/tools.py` lines 25-37
- **Status:** Implemented correctly
- **Method:** `resolve_path()` validates with `relative_to()` check
- **Exception:** `PathOutsideWorkdirError` raised for escaping paths

### 8. File Permissions
- **Location:** `maestro/auth.py` lines 66-69, `maestro/config.py` lines 149-154
- **Status:** Correct (0o600)
- **Pattern:** `os.open()` with mode + `chmod()` backup

## Code Quality

### 9. Test Coverage
- **Total Test Files:** 12
- **Test Count:** ~100+ test cases
- **Coverage Areas:**
  - ✅ Provider Protocol (structural validation)
  - ✅ Provider Registry (discovery, instantiation)
  - ✅ Model Resolution (parsing, priority chain)
  - ✅ Auth (OAuth flows, storage, refresh)
  - ✅ CLI (commands, error handling)
  - ✅ Agent Loop (single-agent, tool execution)
  - ✅ Tools (all 8 tool functions)
  - ✅ Config (load/save, dot notation)

### 10. Type Safety
- **Pattern:** Heavy use of `from __future__ import annotations`
- **Protocol:** `@runtime_checkable` ProviderPlugin Protocol
- **Dataclasses:** Message, Tool, ToolCall, ToolResult, Config, TokenSet
- **Runtime Checks:** `_is_valid_provider()` validates signatures

## Suggested Next Steps

### Immediate (Priority 1)
1. **Implement Phase 5:** Wire non-ChatGPT providers via `provider.stream()`
2. **Add GitHub Copilot Provider:** OAuth device flow + completions endpoint
3. **Test Multi-Provider Flow:** Ensure registry handles multiple providers

### Short-term (Priority 2)
4. **Implement Multi-Agent:** LangGraph `StateGraph` with `Send` API
5. **Add DAG Planning:** Pydantic models for task decomposition
6. **Add Topological Sort:** `graphlib.TopologicalSorter` for dependency resolution

### Medium-term (Priority 3)
7. **Documentation:** Add docstrings to test files
8. **Integration Tests:** Live provider testing (mocked or sandbox)
9. **Performance:** Benchmark agent loop with large contexts

## Unknowns

### A. GitHub Copilot OAuth
- **CLIENT_ID:** Documented in design spec (`Ov23li8tweQw6odWQebz`)
- **Status:** Not verified against actual GitHub OAuth App registration
- **Risk:** May need different client ID for production

### B. Entry Point Loading
- **Question:** How do external packages declare `maestro.providers` entry points?
- **Assumption:** Same as internal - `pyproject.toml [project.entry-points."maestro.providers"]`
- **Verification:** Need test with external package installation

### C. LangGraph StateGraph Compatibility
- **Question:** Does Send API work with @entrypoint/@task decorators?
- **Answer:** No - per design docs, `StateGraph` is separate API
- **Risk:** Need to refactor single-agent path or maintain dual implementations
