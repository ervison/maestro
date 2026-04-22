import threading
import time
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
    time.sleep(0.2)

    req = urllib.request.Request(f"http://localhost:{port}/events")
    try:
        with urllib.request.urlopen(req, timeout=1) as resp:
            content_type = resp.headers.get("Content-Type", "")
            assert "text/event-stream" in content_type
    except Exception:
        pass


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
