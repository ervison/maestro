"""Dashboard HTTP server."""

from __future__ import annotations

import json
import logging
import queue
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from maestro.dashboard.emitter import DashboardEmitter


_STATIC_DIR = Path(__file__).parent / "static"
logger = logging.getLogger(__name__)


def _make_handler(emitter: DashboardEmitter) -> type[BaseHTTPRequestHandler]:
    class DashboardHandler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
            pass

        def do_GET(self) -> None:
            if self.path in ("/", ""):
                self._serve_static()
                return

            if self.path == "/events":
                self._serve_sse()
                return

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
            # Do NOT set Access-Control-Allow-Origin: * — the UI is served by
            # this same process, so cross-origin access is not needed and
            # a wildcard would allow any page in the browser to read
            # planner output and worker logs from the local server.
            self.end_headers()

            client_queue: queue.Queue[dict[str, Any]] = queue.Queue()

            def handler(event: dict[str, Any]) -> None:
                client_queue.put(event)

            emitter.subscribe(handler)
            try:
                while True:
                    try:
                        event = client_queue.get(timeout=15)
                    except queue.Empty:
                        self.wfile.write(b": heartbeat\n\n")
                        self.wfile.flush()
                        continue

                    try:
                        data = json.dumps(event)
                    except (TypeError, ValueError) as exc:
                        logger.warning("DashboardEmitter: could not serialize event: %s", exc)
                        continue

                    self.wfile.write(f"data: {data}\n\n".encode("utf-8"))
                    self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError):
                pass
            finally:
                emitter.unsubscribe(handler)

    return DashboardHandler


def start_dashboard_server(emitter: DashboardEmitter, port: int = 4040) -> ThreadingHTTPServer:
    """Start the dashboard server in a daemon thread."""

    ThreadingHTTPServer.allow_reuse_address = True
    server = ThreadingHTTPServer(("127.0.0.1", port), _make_handler(emitter))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server
