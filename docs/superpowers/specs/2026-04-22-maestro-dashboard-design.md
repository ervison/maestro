# Maestro Dashboard — Design Spec

**Date:** 2026-04-22
**Status:** Approved

---

## Overview

Add a real-time web dashboard to `maestro run --multi` that visualizes the agent DAG as it executes. The dashboard auto-starts on a local HTTP server, prints a single URL to the terminal, and streams live updates via SSE. Zero new dependencies. Zero build tooling. Docker-friendly.

---

## Goals

- Show the full DAG graph (Planner → Scheduler → Workers → Aggregator) updating in real time
- Stream per-worker tool calls and LLM text output to a side panel on click
- Work inside Docker: bind `0.0.0.0`, port configurable via env var
- Zero NPM, zero build step, zero new pip dependencies

---

## Non-Goals

- No persistent state or replay — dashboard is ephemeral per run
- No authentication
- No mobile layout
- No multi-run history

---

## Architecture

### Components

| File | Responsibility |
|------|---------------|
| `maestro/dashboard/server.py` | HTTP server (stdlib `http.server` + asyncio). Serves `index.html` at `/` and SSE stream at `/events` |
| `maestro/dashboard/emitter.py` | `DashboardEmitter` class — thread-safe event queue. Called by graph nodes via `emitter.emit(event_dict)` |
| `maestro/dashboard/static/index.html` | Full dashboard UI — vanilla HTML/CSS/JS, single file, no external deps |
| `maestro/multi_agent.py` | Modified to accept optional `emitter` param; nodes call `emitter.emit(...)` when present |
| `maestro/cli.py` | Instantiates emitter, starts server in background thread, prints URL, passes emitter to `run_multi_agent` |

### Transport: Server-Sent Events (SSE)

SSE is unidirectional (server → browser), Docker/proxy friendly, supported natively by all browsers, and requires zero client-side dependencies. The `/events` endpoint holds a connection open and pushes `data: {...}\n\n` frames.

### Server Lifecycle

1. CLI starts the HTTP server in a daemon background thread before calling `run_multi_agent`
2. Prints: `[maestro] dashboard → http://localhost:4040`
3. `run_multi_agent` runs with emitter injected
4. Nodes call `emitter.emit(...)` at key lifecycle points
5. Server shuts down with the main process (daemon thread)

---

## SSE Event Protocol

All events are JSON objects with a `type` field.

### `dag_ready`
Emitted by `planner_node` after the DAG is validated. Initializes all nodes in the UI.

```json
{
  "type": "dag_ready",
  "tasks": [
    {"id": "t1", "domain": "code", "description": "Create FastAPI app", "deps": []},
    {"id": "t2", "domain": "test", "description": "Write pytest tests", "deps": ["t1"]}
  ]
}
```

### `node_update`
Emitted when a node changes state.

```json
{
  "type": "node_update",
  "id": "t1",
  "domain": "code",
  "status": "active",
  "model": "gpt-4o",
  "elapsed": 3.2
}
```

`status` values: `"waiting"` | `"active"` | `"done"` | `"failed"`

Special node IDs for pipeline stages: `"planner"`, `"scheduler"`, `"aggregator"`

### `node_log`
Emitted for each tool call or LLM text chunk within a worker.

```json
{"type": "node_log", "id": "t1", "kind": "tool", "text": "write_file(src/main.py)"}
{"type": "node_log", "id": "t1", "kind": "text", "text": "Criando estrutura FastAPI..."}
```

---

## UI Design

### Layout

Horizontal pipeline, left → right:

```
┌──────────┐    ┌───────────┐    ┌────────────┐    ┌─────────────┐
│  Planner │───▶│ Scheduler │───▶│  Worker t1 │    │ Aggregator  │
└──────────┘    └───────────┘    │  Worker t2 │───▶└─────────────┘
                                  │  Worker t3 │
                                  └────────────┘
```

Workers are stacked vertically in a column between Scheduler and Aggregator.

### Node States (Pipeline Cards)

| State | Visual |
|-------|--------|
| `waiting` | Dark background, dim text, no border |
| `active` | Blue border, animated progress bar (shimmer), pulsing label |
| `done` | Light gray, faded text, checkmark |
| `failed` | Red border, error icon |

### Side Panel (on node click)

Opens on the right side. Contains:

- **Header:** node name + status badge (color-coded)
- **Metadata:**
  - Domain
  - Task description
  - Elapsed time (live, counting up)
  - Tools used count
  - Model being used
- **Log stream:** real-time append-only log
  - Tool calls: amber text
  - LLM text output: dim white text
  - Blinking cursor at bottom while `active`

### Special nodes

- `planner` and `aggregator` show status only (no log stream — they don't expose streaming output)
- `scheduler` is always shown between planner and workers columns; transitions `active → done` as batches complete

---

## Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `MAESTRO_DASHBOARD_PORT` | `4040` | HTTP server port |
| Bind address | `0.0.0.0` | Always binds to all interfaces for Docker compatibility |

---

## Integration Points

### `maestro/multi_agent.py`

- `run_multi_agent(...)` gains optional `emitter: DashboardEmitter | None = None` parameter
- `planner_node`: emit `node_update(id="planner", status="active")` at start, `dag_ready` after validation, `node_update(id="planner", status="done")` when done
- `scheduler_node`: emit `node_update(id="scheduler", status="active")` on each call
- `dispatch_route`: emit `node_update(id=task_id, status="active", model=..., domain=...)` per dispatched task
- `worker_node`: pass `on_text` and `on_tool_start` callbacks to `_run_agentic_loop` that emit `node_log` events; emit `node_update(status="done"|"failed", elapsed=...)` on completion
- `aggregator_node`: emit `node_update(id="aggregator", status="active")` at start, `node_update(id="aggregator", status="done")` when done

### `maestro/cli.py`

```python
if args.multi:
    from maestro.dashboard.emitter import DashboardEmitter
    from maestro.dashboard.server import start_dashboard_server

    emitter = DashboardEmitter()
    port = int(os.environ.get("MAESTRO_DASHBOARD_PORT", "4040"))
    start_dashboard_server(emitter, port=port)
    print(f"[maestro] dashboard → http://localhost:{port}")

    result = run_multi_agent(..., emitter=emitter)
```

---

## Backward Compatibility

- `emitter` is always `None` when dashboard is not active (no `--multi` → no emitter)
- All `emitter.emit(...)` calls are guarded: `if emitter: emitter.emit(...)`
- All existing tests for `multi_agent.py` pass `emitter=None` or omit it (default)
- No changes to the single-agent path

---

## Testing Strategy

- Unit test `DashboardEmitter`: emit events, subscribe, verify delivery, thread safety
- Unit test SSE server: mock emitter, verify `/events` returns correct `text/event-stream` headers and `data:` framing
- Integration test: `run_multi_agent` with a mock emitter, assert `dag_ready` and `node_update` events are emitted in the correct order
- Existing tests: run full suite to verify zero regressions

---

## File Structure

```
maestro/
  dashboard/
    __init__.py
    emitter.py       # DashboardEmitter — thread-safe event queue + subscriber list
    server.py        # HTTP server, /events SSE endpoint, static file serving
    static/
      index.html     # Complete dashboard UI (vanilla HTML/CSS/JS)
tests/
  test_dashboard_emitter.py   # Unit tests for DashboardEmitter
  test_dashboard_server.py    # Unit tests for SSE server
  test_dashboard_integration.py  # Integration: run_multi_agent emits correct events
```
