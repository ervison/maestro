import threading
import time
import socket
import urllib.error
import urllib.request

from maestro.dashboard.emitter import DashboardEmitter
from maestro.dashboard.server import start_dashboard_server


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
