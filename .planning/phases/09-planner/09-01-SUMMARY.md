---
phase: 09-planner
plan: 1
subsystem: planner
tags: [langgraph, pydantic, structured-output, dag, retry-logic]

# Dependency graph
requires:
  - phase: 08-dag-state-types-domains
    provides: AgentState, AgentPlan, PlanTask schemas and validate_dag function
  - phase: 05-agent-loop-refactor
    provides: provider.stream() interface for LLM calls
  - phase: 04-provider-registry
    provides: get_provider(), get_default_provider() for provider resolution
provides:
  - planner_node() function for LangGraph integration
  - LLM-driven DAG generation with structured output validation
  - Retry logic with error feedback for invalid responses
  - Configurable planner model with provider/model resolution
  - PLANNER_SYSTEM_PROMPT with domain definitions
affects:
  - scheduler (next phase - will consume dag output)
  - workers (will execute tasks from generated plans)
  - cli (may add --multi flag to use planner)

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Pydantic model_json_schema() for LLM structured output"
    - "API-level response_format with prompt-only fallback"
    - "Retry loop with error feedback in conversation history"
    - "Async generator collection with sync bridge"
    - "Markdown fence stripping for robust JSON parsing"

key-files:
  created:
    - maestro/planner/node.py - Planner node implementation
    - tests/test_planner_node.py - Unit tests with mocked provider
  modified:
    - maestro/planner/__init__.py - Added planner_node and PLANNER_SYSTEM_PROMPT exports

key-decisions:
  - "Use AgentPlan.model_json_schema() to embed schema in system prompt"
  - "Try API-level response_format first, fall back to prompt-only"
  - "Retry up to 3 times with error feedback in conversation"
  - "Support provider/model format in config (e.g., 'chatgpt/gpt-4o')"
  - "Strip markdown fences from LLM responses for robust parsing"

patterns-established:
  - "Provider stream collection with sync/async bridge using asyncio.get_running_loop()"
  - "Structured output validation with Pydantic model_validate_json()"
  - "Retry logic with conversation history mutation for LLM feedback"

requirements-completed: []

# Metrics
duration: 15min
completed: 2026-04-18
---

# Phase 9: Planner Node Summary

**LLM-driven DAG generation with structured output validation, retry logic, and configurable model resolution for LangGraph multi-agent orchestration**

## Performance

- **Duration:** 15 min
- **Started:** 2026-04-18T18:15:00Z
- **Completed:** 2026-04-18T18:30:00Z
- **Tasks:** 3
- **Files modified:** 3

## Accomplishments

- Implemented `planner_node()` function that takes user task and generates validated AgentPlan
- Added API-level JSON schema enforcement with graceful fallback to prompt-only
- Built retry logic with up to 3 attempts and error feedback in conversation history
- Implemented configurable model resolution from `config.agent.planner.model`
- Added support for provider/model format (e.g., 'chatgpt/gpt-4o')
- Exported `PLANNER_SYSTEM_PROMPT` with 7 domain definitions for task decomposition

## Task Commits

Each task was committed atomically:

1. **Task 1: Create planner node implementation** - `a5404f4` (feat)
   - Created `maestro/planner/node.py` with complete planner logic
   - Implemented `_call_provider_with_schema()` with API-level and prompt-only modes
   - Added markdown fence stripping for robust JSON parsing

2. **Task 2: Update planner package exports** - `a5404f4` (feat)
   - Added `planner_node` and `PLANNER_SYSTEM_PROMPT` to `__init__.py`

3. **Task 3: Create planner node tests** - `a5404f4` (feat)
   - Created `tests/test_planner_node.py` with 9 comprehensive tests
   - Tests cover valid DAG, schema rejection, cycle rejection, config resolution, retry success

**Plan metadata:** `bad0a6b` (docs: update STATE.md)

## Files Created/Modified

- `maestro/planner/node.py` - Planner node with structured output validation and retry logic
- `maestro/planner/__init__.py` - Added planner_node and PLANNER_SYSTEM_PROMPT exports
- `tests/test_planner_node.py` - 9 unit tests with mocked provider

## Decisions Made

- Used `AgentPlan.model_json_schema()` to dynamically embed schema in system prompt
- Implemented dual-mode provider calling: API-level response_format first, then prompt-only fallback
- Retry loop mutates conversation history with error feedback for LLM correction
- Config parser supports both "provider/model" and plain "model" formats
- Used `asyncio.get_running_loop()` for Python 3.12+ compatibility (avoids deprecation warning)

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed config import name**
- **Found during:** Task 3 (Running tests)
- **Issue:** `from maestro.config import load_config` failed - actual function is `load()`
- **Fix:** Changed to `from maestro.config import load as load_config`
- **Files modified:** `maestro/planner/node.py`
- **Committed in:** `a5404f4`

**2. [Rule 1 - Bug] Fixed asyncio deprecation warning**
- **Found during:** Task 3 (Running tests)
- **Issue:** `asyncio.get_event_loop()` triggers DeprecationWarning in Python 3.12 when no loop exists
- **Fix:** Changed to `asyncio.get_running_loop()` with proper exception handling
- **Files modified:** `maestro/planner/node.py`
- **Committed in:** `a5404f4`

---

**Total deviations:** 2 auto-fixed (2 bugs)
**Impact on plan:** Minor import/API fixes, no scope creep

## Issues Encountered

None - all tests passed successfully

## Next Phase Readiness

- Planner node complete and ready for LangGraph integration
- Scheduler phase can now consume `dag` output from planner_node
- Workers can execute tasks from validated AgentPlan

---
*Phase: 09-planner*
*Completed: 2026-04-18*
