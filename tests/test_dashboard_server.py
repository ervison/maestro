import threading
import time
import socket
import queue
import urllib.error
import urllib.request
from io import BytesIO
from unittest.mock import patch

from maestro.dashboard.emitter import DashboardEmitter
from maestro.dashboard.server import _make_handler, _sse_handler_factory, start_dashboard_server


def _find_free_port() -> int:
    import socket

    with socket.socket() as s:
        s.bind(("", 0))
        return s.getsockname()[1]


def test_root_returns_html() -> None:
    emitter = DashboardEmitter()
    port = _find_free_port()
    start_dashboard_server(emitter, port=port)
    time.sleep(0.2)

    with urllib.request.urlopen(f"http://localhost:{port}/") as resp:
        assert resp.status == 200
        content_type = resp.headers.get("Content-Type", "")
        assert "text/html" in content_type


def test_events_endpoint_headers() -> None:
    emitter = DashboardEmitter()
    port = _find_free_port()
    start_dashboard_server(emitter, port=port)
    time.sleep(0.3)

    s = socket.create_connection(("localhost", port), timeout=2)
    s.sendall(b"GET /events HTTP/1.1\r\nHost: localhost\r\nConnection: close\r\n\r\n")
    response = b""
    s.settimeout(2)
    try:
        while True:
            chunk = s.recv(4096)
            if not chunk:
                break
            response += chunk
            if b"\r\n\r\n" in response:
                break
    except socket.timeout:
        pass
    finally:
        s.close()

    decoded = response.decode("utf-8", errors="replace")
    assert "text/event-stream" in decoded, f"Expected text/event-stream in headers, got: {decoded[:500]}"


def test_events_delivers_emitted_events() -> None:
    emitter = DashboardEmitter()
    port = _find_free_port()
    start_dashboard_server(emitter, port=port)
    time.sleep(0.2)

    received_lines: list[str] = []
    done = threading.Event()

    def _read_sse() -> None:
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


def test_events_skip_unserializable_payloads() -> None:
    emitter = DashboardEmitter()
    port = _find_free_port()
    start_dashboard_server(emitter, port=port)
    time.sleep(0.2)

    received_lines: list[str] = []
    done = threading.Event()

    def _read_sse() -> None:
        try:
            req = urllib.request.Request(f"http://localhost:{port}/events")
            with urllib.request.urlopen(req, timeout=3) as resp:
                for line in resp:
                    decoded = line.decode("utf-8").strip()
                    if decoded:
                        received_lines.append(decoded)
                    if any("dag_ready" in entry for entry in received_lines):
                        done.set()
                        return
        except Exception:
            done.set()

    reader = threading.Thread(target=_read_sse, daemon=True)
    reader.start()
    time.sleep(0.1)

    emitter.emit({"type": "bad", "payload": object()})
    emitter.emit({"type": "dag_ready", "tasks": []})
    done.wait(timeout=3)

    assert any("dag_ready" in line for line in received_lines), f"Got: {received_lines}"


def test_unknown_path_returns_404() -> None:
    emitter = DashboardEmitter()
    port = _find_free_port()
    start_dashboard_server(emitter, port=port)
    time.sleep(0.2)

    try:
        urllib.request.urlopen(f"http://localhost:{port}/nonexistent")
        assert False, "Expected 404"
    except urllib.error.HTTPError as e:
        assert e.code == 404


def test_root_returns_404_when_static_index_is_missing(tmp_path) -> None:
    emitter = DashboardEmitter()
    port = _find_free_port()

    with patch("maestro.dashboard.server._STATIC_DIR", tmp_path):
        server = start_dashboard_server(emitter, port=port)
        time.sleep(0.2)
        try:
            with urllib.request.urlopen(f"http://localhost:{port}/"):
                assert False, "Expected 404"
        except urllib.error.HTTPError as e:
            assert e.code == 404
        finally:
            server.shutdown()
            server.server_close()


def test_sse_handler_drops_oldest_event_when_queue_is_full() -> None:
    client_queue = queue.Queue(maxsize=1)
    client_queue.put_nowait({"type": "old"})

    _sse_handler_factory(client_queue)({"type": "new"})

    assert client_queue.get_nowait() == {"type": "new"}


def test_sse_handler_ignores_repeated_queue_full_failures() -> None:
    class FakeQueue:
        def put_nowait(self, event):
            del event
            raise queue.Full

        def get_nowait(self):
            raise queue.Empty

    _sse_handler_factory(FakeQueue())({"type": "new"})


def test_dashboard_handler_routes_events_path_to_sse() -> None:
    emitter = DashboardEmitter()
    handler_class = _make_handler(emitter)
    handler = handler_class.__new__(handler_class)
    handler.path = "/events"

    called = []
    handler._serve_sse = lambda: called.append(True)

    handler.do_GET()

    assert called == [True]


def test_sse_serves_heartbeat_and_unsubscribes_on_broken_pipe() -> None:
    emitter = DashboardEmitter()
    handler_class = _make_handler(emitter)
    handler = handler_class.__new__(handler_class)
    handler.wfile = BytesIO()
    sent_headers = []
    subscriptions = []

    handler.send_response = lambda code: sent_headers.append(("status", code))
    handler.send_header = lambda name, value: sent_headers.append((name, value))
    handler.end_headers = lambda: sent_headers.append(("end", None))

    def subscribe(callback):
        subscriptions.append(callback)

    def unsubscribe(callback):
        subscriptions.remove(callback)

    emitter.subscribe = subscribe
    emitter.unsubscribe = unsubscribe

    class FakeQueue:
        def __init__(self) -> None:
            self.calls = 0

        def get(self, timeout):
            self.calls += 1
            if self.calls == 1:
                raise queue.Empty
            return {"type": "dag_ready", "tasks": []}

    class BrokenPipeBuffer:
        def __init__(self) -> None:
            self.writes = []

        def write(self, data):
            self.writes.append(data)
            if data.startswith(b"data: "):
                raise BrokenPipeError

        def flush(self):
            return None

    handler.wfile = BrokenPipeBuffer()

    with patch("maestro.dashboard.server.queue.Queue", return_value=FakeQueue()):
        handler._serve_sse()

    assert ("Content-Type", "text/event-stream") in sent_headers
    assert handler.wfile.writes[0] == b": heartbeat\n\n"
    assert subscriptions == []
