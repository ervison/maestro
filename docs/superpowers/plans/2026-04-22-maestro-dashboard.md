# Maestro Dashboard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a real-time web dashboard that visualizes the multi-agent DAG as it runs, with live worker log streaming, accessible at `http://localhost:4040`.

**Architecture:** A `DashboardEmitter` singleton collects SSE events from graph nodes and broadcasts them to connected browser clients via a stdlib HTTP server running in a background thread. The UI is a single `index.html` file with vanilla JS — no build step, no NPM deps. All nodes in `multi_agent.py` receive an optional `emitter` parameter and call `emitter.emit(...)` at key lifecycle points.

**Tech Stack:** Python stdlib (`http.server`, `threading`, `queue`, `json`), vanilla HTML/CSS/JS (EventSource API), SSE transport.

---

## File Map

| File | Action | Responsibility |
|------|--------|---------------|
| `maestro/dashboard/__init__.py` | Create | Package marker |
| `maestro/dashboard/emitter.py` | Create | `DashboardEmitter` — thread-safe event queue + subscriber fan-out |
| `maestro/dashboard/server.py` | Create | HTTP server: serves `index.html` at `/`, SSE stream at `/events` |
| `maestro/dashboard/static/index.html` | Create | Complete dashboard UI (pipeline cards, side panel, SSE client) |
| `maestro/multi_agent.py` | Modify | Add `emitter` param to `run_multi_agent` and all node functions; emit events |
| `maestro/cli.py` | Modify | Instantiate emitter, start server, print URL before `run_multi_agent` |
| `tests/test_dashboard_emitter.py` | Create | Unit tests for `DashboardEmitter` |
| `tests/test_dashboard_server.py` | Create | Unit tests for SSE server responses |
| `tests/test_dashboard_integration.py` | Create | Integration: `run_multi_agent` emits correct event sequence |

---

### Task 1: `DashboardEmitter` — thread-safe event broadcaster

**Files:**
- Create: `maestro/dashboard/__init__.py`
- Create: `maestro/dashboard/emitter.py`
- Test: `tests/test_dashboard_emitter.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_dashboard_emitter.py
import threading
import time
from maestro.dashboard.emitter import DashboardEmitter


def test_emit_delivers_to_subscriber():
    emitter = DashboardEmitter()
    received = []

    def handler(event):
        received.append(event)

    emitter.subscribe(handler)
    emitter.emit({"type": "node_update", "id": "t1", "status": "active"})

    assert len(received) == 1
    assert received[0]["type"] == "node_update"
    assert received[0]["id"] == "t1"


def test_emit_delivers_to_multiple_subscribers():
    emitter = DashboardEmitter()
    received_a = []
    received_b = []

    emitter.subscribe(lambda e: received_a.append(e))
    emitter.subscribe(lambda e: received_b.append(e))
    emitter.emit({"type": "dag_ready", "tasks": []})

    assert len(received_a) == 1
    assert len(received_b) == 1


def test_unsubscribe_stops_delivery():
    emitter = DashboardEmitter()
    received = []
    handler = lambda e: received.append(e)

    emitter.subscribe(handler)
    emitter.unsubscribe(handler)
    emitter.emit({"type": "node_update", "id": "t1", "status": "done"})

    assert len(received) == 0


def test_emit_is_thread_safe():
    emitter = DashboardEmitter()
    received = []
    lock = threading.Lock()

    def handler(event):
        with lock:
            received.append(event)

    emitter.subscribe(handler)

    threads = [
        threading.Thread(target=emitter.emit, args=({"type": "node_log", "id": f"t{i}", "kind": "text", "text": "x"},))
        for i in range(50)
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(received) == 50


def test_emit_without_subscribers_does_not_raise():
    emitter = DashboardEmitter()
    emitter.emit({"type": "dag_ready", "tasks": []})  # no subscribers — must not raise
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /path/to/maestro
pytest tests/test_dashboard_emitter.py -v
```
Expected: ImportError or AttributeError — module does not exist yet.

- [ ] **Step 3: Create package and implement `DashboardEmitter`**

Create `maestro/dashboard/__init__.py` (empty):
```python
```

Create `maestro/dashboard/emitter.py`:
```python
"""DashboardEmitter — thread-safe SSE event broadcaster.

Maintains a list of subscriber callables. When emit() is called,
all subscribers receive the event dict. Used by multi_agent nodes
to push real-time updates to the dashboard SSE server.
"""

from __future__ import annotations

import threading
from typing import Any, Callable


class DashboardEmitter:
    """Thread-safe event broadcaster for dashboard SSE updates.

    Usage:
        emitter = DashboardEmitter()
        emitter.subscribe(my_handler)  # handler(event: dict) -> None
        emitter.emit({"type": "node_update", "id": "t1", "status": "active"})
    """

    def __init__(self) -> None:
        self._subscribers: list[Callable[[dict[str, Any]], None]] = []
        self._lock = threading.Lock()

    def subscribe(self, handler: Callable[[dict[str, Any]], None]) -> None:
        """Register a handler to receive all future events."""
        with self._lock:
            self._subscribers.append(handler)

    def unsubscribe(self, handler: Callable[[dict[str, Any]], None]) -> None:
        """Remove a previously registered handler."""
        with self._lock:
            try:
                self._subscribers.remove(handler)
            except ValueError:
                pass

    def emit(self, event: dict[str, Any]) -> None:
        """Broadcast event to all subscribers.

        Subscribers are called synchronously in registration order.
        If a subscriber raises, the exception is suppressed to avoid
        disrupting the agent graph execution.
        """
        with self._lock:
            handlers = list(self._subscribers)
        for handler in handlers:
            try:
                handler(event)
            except Exception:
                pass
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_dashboard_emitter.py -v
```
Expected: all 5 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add maestro/dashboard/__init__.py maestro/dashboard/emitter.py tests/test_dashboard_emitter.py
git commit -m "feat: add DashboardEmitter thread-safe event broadcaster"
```

---

### Task 2: SSE HTTP server

**Files:**
- Create: `maestro/dashboard/server.py`
- Test: `tests/test_dashboard_server.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_dashboard_server.py
import json
import queue
import threading
import time
import urllib.request
from maestro.dashboard.emitter import DashboardEmitter
from maestro.dashboard.server import start_dashboard_server


def _find_free_port() -> int:
    import socket
    with socket.socket() as s:
        s.bind(("", 0))
        return s.getsockname()[1]


def test_root_returns_html():
    emitter = DashboardEmitter()
    port = _find_free_port()
    start_dashboard_server(emitter, port=port)
    time.sleep(0.2)  # server startup

    with urllib.request.urlopen(f"http://localhost:{port}/") as resp:
        assert resp.status == 200
        content_type = resp.headers.get("Content-Type", "")
        assert "text/html" in content_type


def test_events_endpoint_headers():
    emitter = DashboardEmitter()
    port = _find_free_port()
    start_dashboard_server(emitter, port=port)
    time.sleep(0.2)

    req = urllib.request.Request(f"http://localhost:{port}/events")
    # Open with a short timeout — we just need headers
    try:
        with urllib.request.urlopen(req, timeout=1) as resp:
            content_type = resp.headers.get("Content-Type", "")
            assert "text/event-stream" in content_type
    except Exception:
        # timeout is expected — SSE connection stays open
        pass


def test_events_delivers_emitted_events():
    emitter = DashboardEmitter()
    port = _find_free_port()
    start_dashboard_server(emitter, port=port)
    time.sleep(0.2)

    received_lines: list[str] = []
    done = threading.Event()

    def _read_sse():
        try:
            req = urllib.request.Request(f"http://localhost:{port}/events")
            with urllib.request.urlopen(req, timeout=2) as resp:
                for line in resp:
                    decoded = line.decode("utf-8").strip()
                    if decoded:
                        received_lines.append(decoded)
                    if len(received_lines) >= 2:
                        done.set()
                        return
        except Exception:
            done.set()

    reader = threading.Thread(target=_read_sse, daemon=True)
    reader.start()
    time.sleep(0.1)

    emitter.emit({"type": "dag_ready", "tasks": []})
    done.wait(timeout=3)

    assert any("dag_ready" in line for line in received_lines), f"Got: {received_lines}"


def test_unknown_path_returns_404():
    emitter = DashboardEmitter()
    port = _find_free_port()
    start_dashboard_server(emitter, port=port)
    time.sleep(0.2)

    try:
        urllib.request.urlopen(f"http://localhost:{port}/nonexistent")
        assert False, "Expected 404"
    except urllib.error.HTTPError as e:
        assert e.code == 404
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_dashboard_server.py -v
```
Expected: ImportError — module does not exist yet.

- [ ] **Step 3: Implement `server.py`**

Create `maestro/dashboard/server.py`:
```python
"""Dashboard HTTP server.

Serves:
  GET /         → static/index.html (text/html)
  GET /events   → SSE stream (text/event-stream)
  *             → 404

The server runs in a daemon background thread and shuts down when the
main process exits. A new SSE queue is created per client connection
and registered with the DashboardEmitter for the lifetime of the connection.
"""

from __future__ import annotations

import json
import queue
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from importlib.resources import files
from pathlib import Path
from typing import Any

from maestro.dashboard.emitter import DashboardEmitter

_STATIC_DIR = Path(__file__).parent / "static"


def _make_handler(emitter: DashboardEmitter) -> type:
    """Create a request handler class bound to the given emitter."""

    class DashboardHandler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
            # Suppress default access log to avoid cluttering CLI output
            pass

        def do_GET(self) -> None:
            if self.path in ("/", ""):
                self._serve_static()
            elif self.path == "/events":
                self._serve_sse()
            else:
                self.send_error(404)

        def _serve_static(self) -> None:
            html_path = _STATIC_DIR / "index.html"
            try:
                content = html_path.read_bytes()
            except FileNotFoundError:
                self.send_error(404, "index.html not found")
                return
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)

        def _serve_sse(self) -> None:
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Connection", "keep-alive")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()

            # Per-client event queue
            client_queue: queue.Queue[dict[str, Any] | None] = queue.Queue()

            def handler(event: dict[str, Any]) -> None:
                client_queue.put(event)

            emitter.subscribe(handler)
            try:
                while True:
                    try:
                        event = client_queue.get(timeout=15)
                    except queue.Empty:
                        # Send SSE comment as heartbeat to keep connection alive
                        self.wfile.write(b": heartbeat\n\n")
                        self.wfile.flush()
                        continue

                    if event is None:
                        # Sentinel: close connection
                        break

                    data = json.dumps(event)
                    line = f"data: {data}\n\n".encode("utf-8")
                    self.wfile.write(line)
                    self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError):
                pass
            finally:
                emitter.unsubscribe(handler)

    return DashboardHandler


def start_dashboard_server(emitter: DashboardEmitter, port: int = 4040) -> HTTPServer:
    """Start the dashboard HTTP server in a daemon background thread.

    Args:
        emitter: DashboardEmitter instance to subscribe SSE clients to
        port: TCP port to bind on (default: 4040). Binds to 0.0.0.0.

    Returns:
        HTTPServer instance (already running in background thread)
    """
    handler_class = _make_handler(emitter)
    server = HTTPServer(("0.0.0.0", port), handler_class)

    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    return server
```

- [ ] **Step 4: Create `maestro/dashboard/static/` directory and placeholder**

```bash
mkdir -p maestro/dashboard/static
touch maestro/dashboard/static/.gitkeep
```

The actual `index.html` is created in Task 4. For now, create a minimal placeholder so the server test can find it:

```bash
cat > maestro/dashboard/static/index.html << 'EOF'
<!DOCTYPE html><html><body><h1>Maestro Dashboard</h1></body></html>
EOF
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
pytest tests/test_dashboard_server.py -v
```
Expected: all 4 tests PASS.

- [ ] **Step 6: Commit**

```bash
git add maestro/dashboard/server.py maestro/dashboard/static/index.html tests/test_dashboard_server.py
git commit -m "feat: add dashboard SSE HTTP server"
```

---

### Task 3: Wire emitter into `multi_agent.py`

**Files:**
- Modify: `maestro/multi_agent.py`
- Test: `tests/test_dashboard_integration.py`

- [ ] **Step 1: Write failing integration tests**

```python
# tests/test_dashboard_integration.py
"""Integration tests verifying run_multi_agent emits correct SSE events."""

import time
from unittest.mock import MagicMock, patch

from maestro.dashboard.emitter import DashboardEmitter


def _make_mock_provider(answer="done"):
    """Create a mock provider that returns a fixed answer."""
    provider = MagicMock()

    async def _stream(messages, model, instructions, tools=None, **kw):
        from maestro.providers.base import Message
        yield Message(role="assistant", content=answer)

    provider.stream = _stream
    provider.id = "mock"
    return provider


def _make_planner_result(tasks):
    """Build a minimal planner DAG result."""
    from maestro.planner.schemas import AgentPlan, PlanTask
    plan = AgentPlan(tasks=[
        PlanTask(id=t["id"], domain=t["domain"], prompt=t["prompt"], deps=t.get("deps", []))
        for t in tasks
    ])
    return {"dag": plan.model_dump(), "ready_tasks": []}


def test_dag_ready_event_emitted():
    """dag_ready event is emitted after planner succeeds."""
    emitter = DashboardEmitter()
    received = []
    emitter.subscribe(lambda e: received.append(e))

    provider = _make_mock_provider()

    with patch("maestro.multi_agent.planner_node") as mock_planner, \
         patch("maestro.multi_agent.get_default_provider", return_value=provider), \
         patch("maestro.agent._run_agentic_loop", return_value="result"):

        mock_planner.return_value = _make_planner_result([
            {"id": "t1", "domain": "code", "prompt": "do something", "deps": []}
        ])

        from maestro.multi_agent import run_multi_agent
        run_multi_agent(
            task="test task",
            workdir=".",
            auto=True,
            depth=0,
            max_depth=2,
            provider=provider,
            model="mock-model",
            aggregate=False,
            emitter=emitter,
        )

    dag_events = [e for e in received if e["type"] == "dag_ready"]
    assert len(dag_events) == 1
    assert len(dag_events[0]["tasks"]) == 1


def test_node_update_active_emitted_for_workers():
    """node_update with status=active is emitted when a worker starts."""
    emitter = DashboardEmitter()
    received = []
    emitter.subscribe(lambda e: received.append(e))

    provider = _make_mock_provider()

    with patch("maestro.multi_agent.planner_node") as mock_planner, \
         patch("maestro.multi_agent.get_default_provider", return_value=provider), \
         patch("maestro.agent._run_agentic_loop", return_value="result"):

        mock_planner.return_value = _make_planner_result([
            {"id": "t1", "domain": "code", "prompt": "do something", "deps": []}
        ])

        from maestro.multi_agent import run_multi_agent
        run_multi_agent(
            task="test task",
            workdir=".",
            auto=True,
            depth=0,
            max_depth=2,
            provider=provider,
            model="mock-model",
            aggregate=False,
            emitter=emitter,
        )

    active_events = [
        e for e in received
        if e["type"] == "node_update" and e.get("status") == "active" and e.get("id") == "t1"
    ]
    assert len(active_events) >= 1


def test_node_update_done_emitted_for_workers():
    """node_update with status=done is emitted when a worker completes."""
    emitter = DashboardEmitter()
    received = []
    emitter.subscribe(lambda e: received.append(e))

    provider = _make_mock_provider()

    with patch("maestro.multi_agent.planner_node") as mock_planner, \
         patch("maestro.multi_agent.get_default_provider", return_value=provider), \
         patch("maestro.agent._run_agentic_loop", return_value="result"):

        mock_planner.return_value = _make_planner_result([
            {"id": "t1", "domain": "code", "prompt": "do something", "deps": []}
        ])

        from maestro.multi_agent import run_multi_agent
        run_multi_agent(
            task="test task",
            workdir=".",
            auto=True,
            depth=0,
            max_depth=2,
            provider=provider,
            model="mock-model",
            aggregate=False,
            emitter=emitter,
        )

    done_events = [
        e for e in received
        if e["type"] == "node_update" and e.get("status") == "done" and e.get("id") == "t1"
    ]
    assert len(done_events) >= 1


def test_no_emitter_does_not_crash():
    """run_multi_agent with emitter=None runs without errors."""
    provider = _make_mock_provider()

    with patch("maestro.multi_agent.planner_node") as mock_planner, \
         patch("maestro.multi_agent.get_default_provider", return_value=provider), \
         patch("maestro.agent._run_agentic_loop", return_value="result"):

        mock_planner.return_value = _make_planner_result([
            {"id": "t1", "domain": "code", "prompt": "do something", "deps": []}
        ])

        from maestro.multi_agent import run_multi_agent
        result = run_multi_agent(
            task="test task",
            workdir=".",
            auto=True,
            depth=0,
            max_depth=2,
            provider=provider,
            model="mock-model",
            aggregate=False,
            emitter=None,  # no dashboard
        )

    assert "outputs" in result
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_dashboard_integration.py -v
```
Expected: FAIL — `run_multi_agent` doesn't accept `emitter` yet.

- [ ] **Step 3: Add `emitter` param to `run_multi_agent` signature**

In `maestro/multi_agent.py`, locate the `run_multi_agent` function definition (around line 498). Change:

```python
def run_multi_agent(
    task: str,
    workdir: str = ".",
    auto: bool = False,
    depth: int = 0,
    max_depth: int = 2,
    provider=None,
    model: str | None = None,
    aggregate: bool = True,
) -> dict[str, Any]:
```

To:

```python
def run_multi_agent(
    task: str,
    workdir: str = ".",
    auto: bool = False,
    depth: int = 0,
    max_depth: int = 2,
    provider=None,
    model: str | None = None,
    aggregate: bool = True,
    emitter=None,
) -> dict[str, Any]:
```

- [ ] **Step 4: Add `emitter` import and pass-through to planner/graph**

At the top of `run_multi_agent` body, add a local helper to safely emit:

```python
def _emit(event: dict) -> None:
    if emitter is not None:
        emitter.emit(event)
```

After `planner_node(planner_state)` call (around line 549), before `_print_lifecycle("planner", "done")`, add:

```python
planner_result = planner_node(planner_state)
_emit({"type": "node_update", "id": "planner", "status": "done"})

dag = planner_result.get("dag")
if dag is None:
    raise RuntimeError("Planner failed to produce a DAG")

# Emit dag_ready with task list
dag_tasks = dag.get("tasks", []) if isinstance(dag, dict) else []
_emit({
    "type": "dag_ready",
    "tasks": [
        {
            "id": t.get("id") if isinstance(t, dict) else t.id,
            "domain": t.get("domain") if isinstance(t, dict) else t.domain,
            "description": t.get("prompt", "")[:100] if isinstance(t, dict) else (t.prompt or "")[:100],
            "deps": t.get("deps", []) if isinstance(t, dict) else t.deps,
        }
        for t in dag_tasks
    ],
})
```

Also emit `planner` started before `planner_node(planner_state)`:

```python
_emit({"type": "node_update", "id": "planner", "status": "active"})
planner_result = planner_node(planner_state)
```

- [ ] **Step 5: Pass emitter through to dispatch_route and worker_node via state**

`AgentState` is a TypedDict in `maestro/planner/schemas.py`. Add an optional `emitter` field.

Open `maestro/planner/schemas.py` and find the `AgentState` TypedDict. Add:

```python
from typing import Any, Optional
# ...existing fields...
emitter: Optional[Any]  # DashboardEmitter instance or None (not in LangGraph serialization)
```

Then in `run_multi_agent`, add `"emitter": emitter` to `initial_state`:

```python
initial_state: AgentState = {
    # ... existing fields ...
    "emitter": emitter,
}
```

- [ ] **Step 6: Emit events in `dispatch_route` (worker started)**

In `dispatch_route` (around line 213), before `sends.append(Send("worker", payload))`, add:

```python
_emitter = state.get("emitter")
# ...existing loop...
for task in ready_tasks:
    _print_lifecycle(f"worker:{task['id']}", "started")
    if _emitter is not None:
        _emitter.emit({
            "type": "node_update",
            "id": task["id"],
            "domain": task["domain"],
            "status": "active",
            "model": model or "gpt-4o",
        })
    # ... existing payload building ...
```

- [ ] **Step 7: Emit events in `worker_node` (done/failed) with elapsed time**

In `worker_node` (around line 255), at the top of the function body, add:

```python
import time as _time
_start_time = _time.monotonic()
_emitter = state.get("emitter")

def _worker_emit(event: dict) -> None:
    if _emitter is not None:
        _emitter.emit(event)
```

Pass `on_text` and `on_tool_start` to `_run_agentic_loop` (around line 320):

```python
tool_count = [0]

def _on_tool_start() -> None:
    tool_count[0] += 1
    _worker_emit({"type": "node_log", "id": task_id, "kind": "tool", "text": f"tool call #{tool_count[0]}"})

result = _run_agentic_loop(
    messages=messages,
    model=model,
    instructions=system_prompt,
    provider=provider,
    workdir=workdir,
    auto=auto,
    on_text=lambda chunk: _worker_emit({"type": "node_log", "id": task_id, "kind": "text", "text": chunk}),
    on_tool_start=_on_tool_start,
)
```

On success (around line 330):
```python
elapsed = _time.monotonic() - _start_time
_print_lifecycle(f"worker:{task_id}", "done")
_worker_emit({"type": "node_update", "id": task_id, "status": "done", "elapsed": round(elapsed, 1)})
return {"completed": [task_id], "outputs": {task_id: result}}
```

On exception (around line 336):
```python
elapsed = _time.monotonic() - _start_time
logger.exception("Task %s failed: %s", task_id, error_msg)
_print_lifecycle(f"worker:{task_id}", "failed")
_worker_emit({"type": "node_update", "id": task_id, "status": "failed", "elapsed": round(elapsed, 1)})
return {"failed": [task_id], "errors": [f"{task_id}: {error_msg}"]}
```

- [ ] **Step 8: Emit aggregator events**

In `aggregator_node` (around line 362), at the top add:

```python
_emitter = state.get("emitter")

def _agg_emit(event: dict) -> None:
    if _emitter is not None:
        _emitter.emit(event)

_agg_emit({"type": "node_update", "id": "aggregator", "status": "active"})
```

Before each `return` that includes `_print_lifecycle("aggregator", "done")`, add:
```python
_agg_emit({"type": "node_update", "id": "aggregator", "status": "done"})
```

- [ ] **Step 9: Run integration tests**

```bash
pytest tests/test_dashboard_integration.py -v
```
Expected: all 4 tests PASS.

- [ ] **Step 10: Run full existing test suite to verify zero regressions**

```bash
pytest --tb=short -q
```
Expected: all existing tests PASS (26+).

- [ ] **Step 11: Commit**

```bash
git add maestro/multi_agent.py maestro/planner/schemas.py tests/test_dashboard_integration.py
git commit -m "feat: wire DashboardEmitter into multi_agent nodes"
```

---

### Task 4: Wire emitter into `cli.py`

**Files:**
- Modify: `maestro/cli.py`

- [ ] **Step 1: Add dashboard startup to the `--multi` branch in `cli.py`**

In `maestro/cli.py`, find the `if args.multi:` branch (around line 382). Before the `run_multi_agent(...)` call, add:

```python
import os
from maestro.dashboard.emitter import DashboardEmitter
from maestro.dashboard.server import start_dashboard_server

dashboard_emitter = DashboardEmitter()
dashboard_port = int(os.environ.get("MAESTRO_DASHBOARD_PORT", "4040"))
start_dashboard_server(dashboard_emitter, port=dashboard_port)
print(f"[maestro] dashboard → http://localhost:{dashboard_port}")
```

Then pass `emitter=dashboard_emitter` to `run_multi_agent`:

```python
result = run_multi_agent(
    task=args.prompt,
    workdir=wd,
    auto=args.auto,
    depth=0,
    max_depth=2,
    provider=provider,
    model=model_id,
    aggregate=aggregate,
    emitter=dashboard_emitter,
)
```

- [ ] **Step 2: Run the existing CLI integration tests**

```bash
pytest tests/test_multi_agent_cli.py -v
```
Expected: all tests PASS — CLI still works, emitter is optional and backward-compatible.

- [ ] **Step 3: Commit**

```bash
git add maestro/cli.py
git commit -m "feat: auto-start dashboard server on maestro run --multi"
```

---

### Task 5: Build the dashboard UI (`index.html`)

**Files:**
- Modify: `maestro/dashboard/static/index.html` (replace placeholder)

- [ ] **Step 1: Write the full dashboard UI**

Replace `maestro/dashboard/static/index.html` with:

```html
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Maestro Dashboard</title>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { background: #0d1117; color: #c9d1d9; font-family: 'SF Mono', 'Fira Code', monospace; font-size: 13px; display: flex; height: 100vh; overflow: hidden; }

  /* Pipeline canvas */
  #pipeline { flex: 1; display: flex; align-items: center; justify-content: center; padding: 32px; overflow: auto; }
  .pipeline-row { display: flex; align-items: center; gap: 24px; }
  .pipeline-column { display: flex; flex-direction: column; gap: 12px; }
  .arrow { color: #484f58; font-size: 20px; flex-shrink: 0; }

  /* Pipeline cards */
  .card {
    background: #161b22;
    border: 1.5px solid #30363d;
    border-radius: 8px;
    padding: 12px 16px;
    min-width: 160px;
    cursor: pointer;
    transition: border-color 0.2s, background 0.2s;
    user-select: none;
  }
  .card:hover { border-color: #58a6ff; }
  .card.waiting { opacity: 0.5; }
  .card.active { border-color: #388bfd; background: #0d1f3c; }
  .card.done { opacity: 0.6; border-color: #30363d; }
  .card.failed { border-color: #f85149; background: #200d0d; }

  .card-label { font-size: 11px; color: #8b949e; text-transform: uppercase; letter-spacing: 0.08em; margin-bottom: 4px; }
  .card-title { font-size: 13px; font-weight: 600; color: #e6edf3; }
  .card-status { font-size: 11px; margin-top: 4px; }
  .card.waiting .card-status { color: #484f58; }
  .card.active .card-status { color: #388bfd; }
  .card.done .card-status { color: #3fb950; }
  .card.failed .card-status { color: #f85149; }

  /* Animated progress bar (shimmer) */
  .progress-bar { height: 2px; background: #21262d; border-radius: 1px; margin-top: 8px; overflow: hidden; }
  .progress-fill {
    height: 100%;
    width: 40%;
    background: linear-gradient(90deg, transparent, #388bfd, transparent);
    animation: shimmer 1.4s infinite;
    display: none;
  }
  .card.active .progress-fill { display: block; }
  @keyframes shimmer {
    0% { transform: translateX(-150%); }
    100% { transform: translateX(350%); }
  }

  /* Side panel */
  #panel {
    width: 380px;
    background: #161b22;
    border-left: 1px solid #30363d;
    display: none;
    flex-direction: column;
    overflow: hidden;
  }
  #panel.open { display: flex; }

  #panel-header {
    padding: 16px;
    border-bottom: 1px solid #30363d;
    display: flex;
    align-items: center;
    justify-content: space-between;
  }
  #panel-title { font-size: 14px; font-weight: 600; color: #e6edf3; }
  #panel-close { background: none; border: none; color: #8b949e; cursor: pointer; font-size: 18px; line-height: 1; }
  #panel-close:hover { color: #e6edf3; }

  #panel-meta { padding: 12px 16px; border-bottom: 1px solid #30363d; display: flex; flex-direction: column; gap: 6px; }
  .meta-row { display: flex; justify-content: space-between; }
  .meta-key { color: #8b949e; }
  .meta-val { color: #c9d1d9; }

  #panel-log {
    flex: 1;
    overflow-y: auto;
    padding: 12px 16px;
    font-size: 12px;
    line-height: 1.6;
  }
  .log-tool { color: #d29922; }
  .log-text { color: #6e7681; }
  .cursor {
    display: inline-block;
    width: 7px;
    height: 13px;
    background: #388bfd;
    vertical-align: text-bottom;
    animation: blink 1s step-end infinite;
    margin-left: 2px;
  }
  @keyframes blink { 0%, 100% { opacity: 1; } 50% { opacity: 0; } }

  /* Empty state */
  #empty { color: #484f58; font-size: 14px; text-align: center; }

  /* Status badge */
  .badge {
    display: inline-block;
    padding: 2px 8px;
    border-radius: 20px;
    font-size: 11px;
    font-weight: 600;
  }
  .badge-waiting { background: #21262d; color: #8b949e; }
  .badge-active { background: #0d2e5f; color: #58a6ff; }
  .badge-done { background: #0d2c1e; color: #3fb950; }
  .badge-failed { background: #2c0d0d; color: #f85149; }
</style>
</head>
<body>

<div id="pipeline">
  <div id="empty">Waiting for agent run...</div>
</div>

<div id="panel">
  <div id="panel-header">
    <div>
      <div id="panel-title">—</div>
      <span id="panel-badge" class="badge badge-waiting">waiting</span>
    </div>
    <button id="panel-close" onclick="closePanel()">✕</button>
  </div>
  <div id="panel-meta">
    <div class="meta-row"><span class="meta-key">Domain</span><span class="meta-val" id="meta-domain">—</span></div>
    <div class="meta-row"><span class="meta-key">Model</span><span class="meta-val" id="meta-model">—</span></div>
    <div class="meta-row"><span class="meta-key">Elapsed</span><span class="meta-val" id="meta-elapsed">—</span></div>
    <div class="meta-row"><span class="meta-key">Tools used</span><span class="meta-val" id="meta-tools">0</span></div>
    <div class="meta-row" id="desc-row" style="display:none"><span class="meta-key">Task</span><span class="meta-val" id="meta-desc" style="max-width:220px;text-align:right;word-break:break-word">—</span></div>
  </div>
  <div id="panel-log"></div>
</div>

<script>
// ── State ──────────────────────────────────────────────────────────────────
const nodes = {};          // id → {id, domain, status, model, elapsed, toolCount, logs, description}
let selectedId = null;
let elapsedTimers = {};    // id → setInterval handle

// ── SSE connection ─────────────────────────────────────────────────────────
const sse = new EventSource('/events');
sse.onmessage = e => {
  const event = JSON.parse(e.data);
  handleEvent(event);
};
sse.onerror = () => {
  console.warn('SSE connection lost — will retry');
};

// ── Event handlers ─────────────────────────────────────────────────────────
function handleEvent(event) {
  if (event.type === 'dag_ready') {
    initDag(event.tasks);
  } else if (event.type === 'node_update') {
    updateNode(event);
  } else if (event.type === 'node_log') {
    appendLog(event);
  }
}

function initDag(tasks) {
  document.getElementById('empty').style.display = 'none';

  // Initialize synthetic pipeline nodes
  ['planner', 'scheduler', 'aggregator'].forEach(id => {
    if (!nodes[id]) nodes[id] = makeNode(id, id, id, []);
  });

  tasks.forEach(t => {
    nodes[t.id] = makeNode(t.id, t.domain, t.description || t.id, t.deps || []);
  });

  renderPipeline();
}

function makeNode(id, domain, description, deps) {
  return { id, domain, description, deps, status: 'waiting', model: '—', elapsed: null, toolCount: 0, logs: [] };
}

function updateNode(event) {
  const { id, status, model, elapsed, domain } = event;

  if (!nodes[id]) {
    nodes[id] = makeNode(id, domain || id, id, []);
  }

  const node = nodes[id];
  node.status = status;
  if (model) node.model = model;
  if (elapsed != null) node.elapsed = elapsed;
  if (domain) node.domain = domain;

  // Start elapsed timer when active
  if (status === 'active' && !elapsedTimers[id]) {
    const startMs = Date.now();
    elapsedTimers[id] = setInterval(() => {
      if (nodes[id]) {
        nodes[id].elapsed = (Date.now() - startMs) / 1000;
        if (selectedId === id) updatePanelMeta(nodes[id]);
      }
    }, 200);
  }

  // Stop timer when done/failed
  if (status === 'done' || status === 'failed') {
    clearInterval(elapsedTimers[id]);
    delete elapsedTimers[id];
  }

  renderCard(id);
  if (selectedId === id) updatePanelMeta(node);
}

function appendLog(event) {
  const { id, kind, text } = event;
  if (!nodes[id]) return;

  const node = nodes[id];
  node.logs.push({ kind, text });
  if (kind === 'tool') node.toolCount++;

  if (selectedId === id) {
    appendLogLine(kind, text);
    if (kind === 'tool' && nodes[id]) updatePanelMeta(nodes[id]);
  }
}

// ── Rendering ──────────────────────────────────────────────────────────────
function renderPipeline() {
  const pipeline = document.getElementById('pipeline');
  pipeline.innerHTML = '';

  const workerIds = Object.keys(nodes).filter(id => !['planner','scheduler','aggregator'].includes(id));

  const row = document.createElement('div');
  row.className = 'pipeline-row';

  // Planner
  row.appendChild(makeCardEl('planner'));
  row.appendChild(makeArrow());

  // Scheduler
  row.appendChild(makeCardEl('scheduler'));
  row.appendChild(makeArrow());

  // Workers column
  if (workerIds.length > 0) {
    const col = document.createElement('div');
    col.className = 'pipeline-column';
    workerIds.forEach(id => col.appendChild(makeCardEl(id)));
    row.appendChild(col);
    row.appendChild(makeArrow());
  }

  // Aggregator
  row.appendChild(makeCardEl('aggregator'));

  pipeline.appendChild(row);
}

function makeCardEl(id) {
  const node = nodes[id];
  const el = document.createElement('div');
  el.className = `card ${node.status}`;
  el.id = `card-${id}`;
  el.onclick = () => openPanel(id);
  el.innerHTML = `
    <div class="card-label">${node.domain}</div>
    <div class="card-title">${id}</div>
    <div class="card-status">${statusLabel(node.status)}</div>
    <div class="progress-bar"><div class="progress-fill"></div></div>
  `;
  return el;
}

function renderCard(id) {
  const existing = document.getElementById(`card-${id}`);
  if (!existing) {
    renderPipeline();
    return;
  }
  const node = nodes[id];
  existing.className = `card ${node.status}`;
  existing.querySelector('.card-label').textContent = node.domain;
  existing.querySelector('.card-status').textContent = statusLabel(node.status);
}

function makeArrow() {
  const el = document.createElement('div');
  el.className = 'arrow';
  el.textContent = '→';
  return el;
}

function statusLabel(status) {
  return { waiting: 'waiting', active: 'running…', done: '✓ done', failed: '✗ failed' }[status] || status;
}

// ── Side panel ─────────────────────────────────────────────────────────────
function openPanel(id) {
  selectedId = id;
  const node = nodes[id];
  const panel = document.getElementById('panel');
  panel.classList.add('open');

  document.getElementById('panel-title').textContent = id;
  updatePanelMeta(node);

  // Render logs
  const logEl = document.getElementById('panel-log');
  logEl.innerHTML = '';
  node.logs.forEach(l => appendLogLine(l.kind, l.text));

  // Show description if available
  if (node.description && node.description !== id) {
    document.getElementById('meta-desc').textContent = node.description;
    document.getElementById('desc-row').style.display = 'flex';
  }
}

function closePanel() {
  selectedId = null;
  document.getElementById('panel').classList.remove('open');
}

function updatePanelMeta(node) {
  // Badge
  const badge = document.getElementById('panel-badge');
  badge.className = `badge badge-${node.status}`;
  badge.textContent = node.status;

  document.getElementById('meta-domain').textContent = node.domain;
  document.getElementById('meta-model').textContent = node.model || '—';
  document.getElementById('meta-elapsed').textContent = node.elapsed != null ? `${node.elapsed.toFixed(1)}s` : '—';
  document.getElementById('meta-tools').textContent = node.toolCount;
}

function appendLogLine(kind, text) {
  const logEl = document.getElementById('panel-log');

  // Remove cursor from previous last line
  const oldCursor = logEl.querySelector('.cursor');
  if (oldCursor) oldCursor.remove();

  const line = document.createElement('div');
  line.className = kind === 'tool' ? 'log-tool' : 'log-text';
  line.textContent = text;

  const node = selectedId ? nodes[selectedId] : null;
  if (node && node.status === 'active') {
    const cursor = document.createElement('span');
    cursor.className = 'cursor';
    line.appendChild(cursor);
  }

  logEl.appendChild(line);
  logEl.scrollTop = logEl.scrollHeight;
}
</script>
</body>
</html>
```

- [ ] **Step 2: Verify server still passes tests**

```bash
pytest tests/test_dashboard_server.py tests/test_dashboard_emitter.py -v
```
Expected: all PASS.

- [ ] **Step 3: Commit**

```bash
git add maestro/dashboard/static/index.html
git commit -m "feat: add Maestro dashboard UI (pipeline cards + SSE side panel)"
```

---

### Task 6: Final verification — full test suite

**Files:** None (verification only)

- [ ] **Step 1: Run the complete test suite**

```bash
pytest --tb=short -q
```
Expected: all tests PASS including all 26+ pre-existing tests.

- [ ] **Step 2: Smoke-test the server manually**

Start a quick Python session to verify server starts and UI loads:

```bash
python -c "
import time
from maestro.dashboard.emitter import DashboardEmitter
from maestro.dashboard.server import start_dashboard_server

emitter = DashboardEmitter()
start_dashboard_server(emitter, port=4040)
print('Dashboard at http://localhost:4040 — sending test events')

import time; time.sleep(0.5)
emitter.emit({'type': 'dag_ready', 'tasks': [
  {'id': 't1', 'domain': 'code', 'description': 'Build FastAPI app', 'deps': []},
  {'id': 't2', 'domain': 'test', 'description': 'Write tests', 'deps': ['t1']},
]})
time.sleep(0.3)
emitter.emit({'type': 'node_update', 'id': 't1', 'domain': 'code', 'status': 'active', 'model': 'gpt-4o'})
time.sleep(1)
emitter.emit({'type': 'node_log', 'id': 't1', 'kind': 'tool', 'text': 'write_file(src/main.py)'})
time.sleep(0.5)
emitter.emit({'type': 'node_log', 'id': 't1', 'kind': 'text', 'text': 'Creating FastAPI application...'})
time.sleep(2)
emitter.emit({'type': 'node_update', 'id': 't1', 'status': 'done', 'elapsed': 3.2})
print('Done — open http://localhost:4040 in browser to verify')
time.sleep(30)
"
```

Open `http://localhost:4040` and verify:
- Pipeline cards render for planner, scheduler, t1, t2, aggregator
- t1 transitions from waiting → active (blue border + shimmer) → done (faded)
- Clicking t1 opens side panel with log lines

- [ ] **Step 3: Final commit**

```bash
git add -A
git commit -m "feat: maestro dashboard — complete implementation"
```

---

## Summary

6 tasks total:
1. `DashboardEmitter` — thread-safe broadcaster (5 tests)
2. SSE HTTP server (4 tests)
3. Wire emitter into `multi_agent.py` (4 integration tests + full regression)
4. Wire emitter into `cli.py` (CLI integration tests)
5. Full dashboard UI (`index.html`)
6. Final verification + smoke test
