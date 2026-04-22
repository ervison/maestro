"""Gaps questionnaire server — blocks pipeline until user answers all [GAP] items."""
from __future__ import annotations

import json
import re
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from maestro.sdlc.schemas import GapAnswer, GapItem

_STATIC_DIR = Path(__file__).parent / "static"

_DEFAULT_OPTIONS: list[str] = [
    "Yes",
    "No",
    "Not decided yet",
    "Other (specify in notes)",
]


def parse_gaps(gaps_markdown: str) -> list[GapItem]:
    """Extract ``[GAP]`` questions from generated gaps markdown."""
    items: list[GapItem] = []
    for line in gaps_markdown.splitlines():
        stripped = line.strip()
        if not stripped.startswith("[GAP]"):
            continue

        question = stripped[len("[GAP]") :].strip()
        if not question:
            continue

        items.append(
            GapItem(
                question=question,
                options=_infer_options(question),
                recommended_index=0,
            )
        )

    return items


def _infer_options(question: str) -> list[str]:
    """Heuristically derive answer options from question text."""
    q_lower = question.lower()

    paren_match = re.search(r"\(([^)]+)\)", question)
    if paren_match:
        inner = paren_match.group(1)
        parts = [
            part.strip().rstrip("?")
            for part in re.split(r"\s+or\s+", inner, flags=re.IGNORECASE)
        ]
        if len(parts) >= 2:
            return parts + ["Needs discussion", "Not applicable"]

    yes_no_keywords = (
        "is ",
        "are ",
        "will ",
        "should ",
        "does ",
        "do ",
        "has ",
        "have ",
        "can ",
        "must ",
    )
    if any(q_lower.startswith(keyword) for keyword in yes_no_keywords):
        return ["Yes", "No", "Needs discussion", "Not applicable"]

    if any(
        keyword in q_lower
        for keyword in ("how many", "how much", "count", "number", "volume", "scale")
    ):
        return ["< 1,000 / month", "1,000-100,000 / month", "> 100,000 / month", "Unknown / TBD"]

    if any(
        keyword in q_lower
        for keyword in ("audience", "user", "customer", "persona", "target")
    ):
        return ["B2C consumers", "B2B companies", "Internal teams", "Mixed / TBD"]

    return _DEFAULT_OPTIONS.copy()


class GapsServer:
    """HTTP server that presents gap questions and blocks until user answers."""

    def __init__(self, items: list[GapItem], port: int = 4041) -> None:
        self._items = items
        self._requested_port = port
        self._answers: list[GapAnswer] | None = None
        self._event = threading.Event()
        self._server: ThreadingHTTPServer | None = None

    @property
    def port(self) -> int:
        if self._server is None:
            raise RuntimeError("Server not started")
        return self._server.server_address[1]

    def start(self) -> None:
        """Start the HTTP server in a daemon thread."""
        ThreadingHTTPServer.allow_reuse_address = True
        self._server = ThreadingHTTPServer(
            ("127.0.0.1", self._requested_port),
            self._make_handler(),
        )
        thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        thread.start()

    def stop(self) -> None:
        if self._server:
            self._server.shutdown()
            self._server = None

    def get_answers(self, timeout: float | None = None) -> list[GapAnswer] | None:
        """Block until user submits answers, then return them."""
        self._event.wait(timeout=timeout)
        return self._answers

    def _make_handler(self) -> type[BaseHTTPRequestHandler]:
        server_ref = self

        class GapsHandler(BaseHTTPRequestHandler):
            def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
                del format, args

            def do_GET(self) -> None:
                if self.path in ("/", ""):
                    self._serve_html()
                elif self.path == "/gaps":
                    self._serve_gaps_json()
                else:
                    self.send_error(404)

            def do_POST(self) -> None:
                if self.path == "/answers":
                    self._receive_answers()
                else:
                    self.send_error(404)

            def _serve_html(self) -> None:
                html_path = _STATIC_DIR / "gaps.html"
                try:
                    content = html_path.read_bytes()
                except FileNotFoundError:
                    self.send_error(404, "gaps.html not found")
                    return

                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(content)))
                self.end_headers()
                self.wfile.write(content)

            def _serve_gaps_json(self) -> None:
                payload = [
                    {
                        "question": item.question,
                        "options": item.options,
                        "recommended_index": item.recommended_index,
                    }
                    for item in server_ref._items
                ]
                body = json.dumps(payload).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(body)

            def _receive_answers(self) -> None:
                length = int(self.headers.get("Content-Length", 0))
                raw = self.rfile.read(length)
                try:
                    data: list[dict[str, str]] = json.loads(raw)
                    answers = [
                        GapAnswer(
                            question=item["question"],
                            chosen_option=item["chosen_option"],
                        )
                        for item in data
                    ]
                except (json.JSONDecodeError, KeyError, TypeError):
                    self.send_error(400, "Invalid JSON")
                    return

                server_ref._answers = answers
                server_ref._event.set()

                body = b'{"status": "ok"}'
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        return GapsHandler


def serve_gaps(items: list[GapItem], port: int = 4041) -> GapsServer:
    """Start a GapsServer, return it for blocking answer retrieval."""
    server = GapsServer(items, port=port)
    server.start()
    return server
