"""Gaps questionnaire server — blocks pipeline until user answers all [GAP] items."""
from __future__ import annotations

import json
import json as _json
import re
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from maestro.providers.base import Message
from maestro.sdlc.schemas import GapAnswer, GapItem

_STATIC_DIR = Path(__file__).parent / "static"

_DEFAULT_OPTIONS: list[str] = [
    "Yes",
    "No",
    "Not decided yet",
    "Other (specify in notes)",
]

_DEFAULT_OPEN_OPTIONS_EN: list[str] = [
    "Provide specific answer",
    "Needs discussion",
    "Depends on context",
    "Not applicable",
]

_DEFAULT_OPEN_OPTIONS_PT: list[str] = [
    "Definir resposta especifica",
    "Precisa de discussao",
    "Depende do contexto",
    "Nao se aplica",
]


def parse_gaps(gaps_markdown: str) -> list[GapItem]:
    """Extract ``[GAP]`` questions from generated gaps markdown."""
    items: list[GapItem] = []
    seen_questions: set[str] = set()
    for line in gaps_markdown.splitlines():
        stripped = line.strip()
        stripped = re.sub(r"^(?:[-*+]\s+|\d+\.\s+)", "", stripped)
        if not stripped.startswith("[GAP]"):
            continue

        question = _sanitize_gap_question(stripped[len("[GAP]") :].strip())
        if not question:
            continue

        question_key = question.casefold()
        if question_key in seen_questions:
            continue
        seen_questions.add(question_key)

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

    inline_alternatives = _extract_inline_alternatives(question)
    if inline_alternatives:
        return inline_alternatives + ["Needs discussion", "Not applicable"]

    paren_match = re.search(r"\(([^)]+)\)", question)
    if paren_match:
        inner = paren_match.group(1)
        parts = [
            part.strip().rstrip("?")
            for part in re.split(r"\s+(?:or|ou)\s+|/", inner, flags=re.IGNORECASE)
            if part.strip()
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

    open_question_keywords = (
        "what ",
        "which ",
        "how ",
        "when ",
        "where ",
        "why ",
        "who ",
        "quem ",
        "qual ",
        "quais ",
        "como ",
        "quanto ",
        "quantos ",
        "quantas ",
        "quando ",
        "onde ",
        "por que ",
        "o que ",
    )
    if any(q_lower.startswith(keyword) for keyword in open_question_keywords):
        if _looks_portuguese(question):
            return _DEFAULT_OPEN_OPTIONS_PT.copy()
        return _DEFAULT_OPEN_OPTIONS_EN.copy()

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


def _sanitize_gap_question(question: str) -> str:
    """Normalize a raw [GAP] line into a clean single question."""
    cleaned = re.sub(r"^(?:\[(?:GAP|HYPOTHESIS)\]\s*)+", "", question, flags=re.IGNORECASE)
    cleaned = cleaned.replace("**", "").strip()
    cleaned = re.split(
        r"\s+(?:e preciso confirmar|é preciso confirmar|se quiser, posso)\b",
        cleaned,
        maxsplit=1,
        flags=re.IGNORECASE,
    )[0].strip(" .;:-")
    return cleaned


def _looks_portuguese(text: str) -> bool:
    """Best-effort language hint for default option localization."""
    probe = text.lower()
    tokens = (
        " qual ",
        " quais ",
        " como ",
        " quem ",
        " quanto ",
        " quantos ",
        " quantas ",
        " quando ",
        " onde ",
        " por que ",
        " o que ",
    )
    return any(token in f" {probe} " for token in tokens)


_ENRICH_SYSTEM = """\
You are a requirements analyst. Given a gap question from an SDLC discovery session, \
return a JSON object (no markdown, raw JSON only) with exactly these fields:
- selection_mode: "single" if the question has one correct answer, "multiple" if several can apply simultaneously
- options: array of 3-6 short, concrete, mutually-understandable answer strings (NOT sentence fragments of the question itself)
- recommended_options: array with 0-2 options you consider most common/default (must be items from options)
- allow_free_text: true if the question is open-ended enough to need a custom answer
- free_text_placeholder: short placeholder string for the textarea when allow_free_text is true, else ""

Rules:
- Each option must be a standalone phrase a user can select without reading the question again
- Do NOT split the question sentence into fragments as options
- Use the project context to make options domain-relevant
- Respond with ONLY the JSON object, no explanation, no markdown fences
"""

_ENRICH_USER_TMPL = "Project context: {context}\n\nGap question: {question}"


async def enrich_gap_items(
    items: list[GapItem],
    provider: Any,
    model: str | None,
    context: str,
) -> list[GapItem]:
    """Enrich gap items with LLM-generated options and UI metadata.

    Falls back to heuristic if provider is None or returns unparseable content.
    """
    enriched: list[GapItem] = []
    for item in items:
        if provider is None:
            enriched.append(_heuristic_enrich(item))
            continue
        try:
            enriched.append(await _llm_enrich(item, provider, model, context))
        except Exception:
            enriched.append(_heuristic_enrich(item))
    return enriched


async def _llm_enrich(
    item: GapItem,
    provider: Any,
    model: str | None,
    context: str,
) -> GapItem:
    messages = [
        Message(role="system", content=_ENRICH_SYSTEM),
        Message(
            role="user",
            content=_ENRICH_USER_TMPL.format(context=context, question=item.question),
        ),
    ]
    collected_parts: list[str] = []
    async for msg in provider.stream(messages, model=model):
        if isinstance(msg, str):
            collected_parts.append(msg)
        elif hasattr(msg, "content") and msg.content:
            collected_parts = [msg.content]
    collected = "".join(collected_parts)

    data = _json.loads(collected.strip())
    return GapItem(
        question=item.question,
        options=[str(o) for o in data.get("options", [])],
        selection_mode=data.get("selection_mode", "single"),
        recommended_index=0,
        recommended_options=[str(o) for o in data.get("recommended_options", [])],
        allow_free_text=bool(data.get("allow_free_text", False)),
        free_text_placeholder=str(data.get("free_text_placeholder", "")),
    )


def _heuristic_enrich(item: GapItem) -> GapItem:
    """Apply heuristic option inference and wrap into a full GapItem."""
    options = _infer_options(item.question)
    q_lower = item.question.lower()
    open_prefixes = (
        "what ", "which ", "how ", "when ", "where ", "why ", "who ",
        "quem ", "qual ", "quais ", "como ", "quanto ", "quantos ",
        "quantas ", "quando ", "onde ", "por que ", "o que ",
    )
    allow_free = any(q_lower.startswith(p) for p in open_prefixes)
    multi_keywords = (
        "quais ", "which ", "select all", "pode ser mais", "podem ser",
        "list ", "listar", "technologies", "tecnologias", "protocols",
        "protocolos", "features", "funcionalidades",
    )
    is_multi = any(kw in q_lower for kw in multi_keywords)
    return GapItem(
        question=item.question,
        options=options,
        selection_mode="multiple" if is_multi else "single",
        recommended_index=0,
        recommended_options=[],
        allow_free_text=allow_free,
        free_text_placeholder="Especifique..." if _looks_portuguese(item.question) else "Specify...",
    )


def _extract_inline_alternatives(question: str) -> list[str]:
    """Extract inline alternatives from text like 'manual, automatica ou ambas?'"""
    source = question.strip().rstrip("?")
    if ":" in source:
        source = source.split(":", 1)[1].strip()

    if not re.search(r"\s(?:or|ou)\s", source, flags=re.IGNORECASE):
        return []

    chunks: list[str] = []
    for comma_part in source.split(","):
        for raw in re.split(r"\s+(?:or|ou)\s+", comma_part, flags=re.IGNORECASE):
            candidate = raw.strip(" .;:-")
            if candidate:
                chunks.append(candidate)

    deduped: list[str] = []
    for chunk in chunks:
        if chunk not in deduped:
            deduped.append(chunk)

    if 2 <= len(deduped) <= 6:
        return deduped
    return []


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
            self._server.server_close()
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
                        "selection_mode": item.selection_mode,
                        "recommended_index": item.recommended_index,
                        "recommended_options": item.recommended_options,
                        "allow_free_text": item.allow_free_text,
                        "free_text_placeholder": item.free_text_placeholder,
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
                    data: list[dict] = json.loads(raw)
                    answers = [
                        GapAnswer(
                            question=item["question"],
                            selected_options=(
                                item.get("selected_options")
                                or [item.get("chosen_option", "unknown")]
                            ),
                            free_text=item.get("free_text", ""),
                        )
                        for item in data
                    ]
                except (json.JSONDecodeError, KeyError, TypeError, ValueError):
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


async def resolve_gaps(
    gaps_content: str,
    provider: Any = None,
    model: str | None = None,
    port: int = 4041,
    open_browser: bool = True,
) -> list[GapAnswer]:
    """Parse gaps from markdown, enrich with LLM, serve questionnaire, block until answered."""
    items = parse_gaps(gaps_content)
    if not items:
        return []

    items = await enrich_gap_items(items, provider=provider, model=model, context=gaps_content[:500])

    server = serve_gaps(items, port=port)
    url = f"http://localhost:{server.port}"
    if open_browser:
        webbrowser.open(url)

    try:
        answers = server.get_answers(timeout=None)
    finally:
        server.stop()

    return answers or []
