# Multi-Agent DAG with Dynamic Planning and Recursive Workers

## Overview

Extend the maestro CLI to support multi-agent task execution using a dynamically inferred DAG (Directed Acyclic Graph). Instead of a single agent handling a task end-to-end, a small Planner model decomposes the task into a dependency graph, a Scheduler dispatches parallel workers via LangGraph's Send API, and each Worker can recursively spawn sub-tasks if needed.

This enables real parallelism for complex tasks (e.g., "build a REST API and write tests") where independent subtasks can run simultaneously, and specialized agents handle their domain without cross-contamination.

---

## Problem

The current maestro agent is single-threaded: one LLM call at a time, no parallelism, no task decomposition. For large or multi-domain tasks:

- Sequential execution is slow
- The agent juggles too many concerns (coding + testing + docs + deployment)
- There is no natural boundary for specialization
- No ability to express "do A and B at the same time, then C after both finish"

---

## Solution

A three-component pipeline:

### 1. Planner

A small, fast model (e.g., gpt-4o-mini) that receives the original user task and produces a DAG as structured JSON:

```json
{
  "tasks": [
    {
      "id": "t1",
      "domain": "backend",
      "prompt": "Create FastAPI CRUD for /users",
      "deps": []
    },
    {
      "id": "t2",
      "domain": "testing",
      "prompt": "Write pytest tests for /users CRUD",
      "deps": ["t1"]
    },
    {
      "id": "t3",
      "domain": "docs",
      "prompt": "Write OpenAPI description for /users",
      "deps": ["t1"]
    }
  ]
}
```

The Planner does NOT execute anything. It only produces the plan. The model is instructed to keep tasks atomic, avoid over-decomposition, and assign a domain to each task.

### 2. Scheduler

A pure Python node in LangGraph that:

1. Receives the DAG from the Planner
2. Computes a topological sort
3. Determines which tasks are ready (no unmet deps)
4. Uses LangGraph's `Send` API to dispatch each ready task to a `worker` node in parallel
5. After all workers finish, re-evaluates for newly unblocked tasks
6. Repeats until all tasks are done

This produces real parallelism — multiple workers run concurrently within the same LangGraph graph execution.

### 3. Worker

Each Worker is a full agentic loop (reusing maestro's existing `_run_agentic_loop`) with:

- Its own `system_prompt` tailored to its assigned domain
- Access to the same file system tools (`read_file`, `write_file`, `execute_shell`, etc.)
- A shared working directory so workers can read each other's outputs
- Optional recursion: a worker that detects its subtask is too complex can call a sub-Planner and produce its own inner DAG, spawning child workers

---

## Architecture

```
User Task
    │
    ▼
┌─────────┐
│ Planner │  (gpt-4o-mini, structured output)
└────┬────┘
     │ DAG JSON
     ▼
┌───────────┐
│ Scheduler │  (Python, topological sort + Send API)
└─────┬─────┘
      │ parallel Send
   ┌──┴──┬──────┐
   ▼     ▼      ▼
[W:t1] [W:t2] [W:t3]   ← Workers (agentic loops, specialized prompts)
   │     │      │
   └──┬──┴──────┘
      │ outputs merged into shared state
      ▼
┌────────────┐
│ Aggregator │  (optional: final summary or validation pass)
└────────────┘
```

---

## State Design

LangGraph state uses reducers for safe parallel writes:

```python
from typing import Annotated
from operator import add

class AgentState(TypedDict):
    task: str                              # original user task
    dag: dict                              # planner output
    completed: Annotated[list, add]        # task IDs completed
    outputs: Annotated[dict, merge_dicts]  # task_id → output text
    errors: Annotated[list, add]           # any worker errors
```

---

## Domain System

Workers are assigned a domain (e.g., `backend`, `testing`, `docs`, `devops`, `data`). Each domain maps to a specialized system prompt. The mapping is defined in a config file (`maestro/domains.py`), making it easy to add new domains.

Example domains:

- `backend` — writes server code, APIs, business logic
- `testing` — writes tests, asserts behavior, runs test suites
- `docs` — writes documentation, README, docstrings
- `devops` — writes Dockerfiles, CI configs, shell scripts
- `data` — writes migrations, seeds, data processing scripts
- `general` — fallback for unclassified tasks

---

## Recursive Workers

A worker can optionally call the Planner on its own subtask and receive a child DAG. This enables depth-first recursion for complex subtasks without pre-planning the full depth upfront.

Recursion guard: max depth configurable (default: 2). Workers at max depth cannot recurse further.

---

## CLI Interface

```bash
# Single-agent (existing behavior, unchanged)
maestro run "build a FastAPI CRUD"

# Multi-agent DAG mode
maestro run --multi "build a FastAPI CRUD with tests and docs" --workdir ./project

# Auto mode (non-interactive) with multi-agent
maestro run --multi --auto "build a FastAPI CRUD" --workdir ./project
```

The `--multi` flag activates the DAG pipeline. Without it, maestro behaves exactly as today.

---

## Reuse of Existing Code

| Existing component                                   | Reused as                               |
| ---------------------------------------------------- | --------------------------------------- |
| `maestro/tools.py` — `execute_tool`, `TOOL_SCHEMAS`  | Worker tool execution                   |
| `maestro/agent.py` — `_run_agentic_loop`             | Each worker's agentic loop              |
| `maestro/auth.py` — `resolve_model`, `DEFAULT_MODEL` | Model selection for planner and workers |
| `maestro/cli.py` — `--auto`, `--workdir`             | Passed through to multi-agent pipeline  |

No existing behavior is broken. The multi-agent pipeline is additive.

---

## Success Criteria

1. `maestro run --multi "task"` decomposes the task into a DAG via Planner
2. Independent tasks execute in parallel (verified by timestamps/logs)
3. Dependent tasks wait for their dependencies before starting
4. Each worker uses its domain system prompt
5. Final output aggregates all worker results
6. A worker can recurse up to max depth without infinite loops
7. All existing single-agent tests continue to pass
8. New tests cover: planner output parsing, scheduler topological sort, worker dispatch, recursive depth guard

---

## Out of Scope (v1)

- Dynamic worker pool sizing / resource limits
- Cross-worker communication (workers only read shared files, not each other's in-memory state)
- Human-in-the-loop approval of the DAG before execution
- Streaming partial results to the CLI during execution
- Persistent DAG state across CLI sessions

---

## Open Questions

1. Should the Planner be a separate model call or a node in the LangGraph graph?
2. Should domain prompts be user-overridable via config file?
3. What is the right default max recursion depth: 1 or 2?
4. Should the Aggregator node always run, or only when explicitly requested?
