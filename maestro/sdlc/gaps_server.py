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
from maestro.sdlc.schemas import DiscoveryProfile, GapAnswer, GapItem, ProfileOption, ProfileQuestion

_STATIC_DIR = Path(__file__).parent / "static"

_NEEDS_DISCUSSION = "Needs discussion"
_NOT_APPLICABLE = "Not applicable"
_JSON_CONTENT_TYPE = "application/json"

_OPEN_QUESTION_PREFIXES: tuple[str, ...] = (
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

_PORTUGUESE_TOKENS: tuple[str, ...] = (
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


# ── Profile-based gap filtering ────────────────────────────────────────────

_TECHNICAL_GAP_PATTERNS: tuple[str, ...] = (
    "database", "schema", "orm", "sql",
    "deploy", "docker", "kubernetes", "infrastructure",
    "cach", "redis", "memcached",
    "queue", "worker", "background job", "message broker",
    "logging", "monitoring", "observability", "tracing", "metric",
    "test", "testing", "mock", "stub", "coverage",
    "api version", "rate limit", "throttl",
    "framework", "library", "tech stack",
    "encrypt", "hash", "salt", "jwt",
    "index", "shard", "replication",
    "websocket", "sse", "polling", "server-sent",
    "migration", "migrate",
    "cdn", "load balanc",
    "sso", "oauth", "openid",
    "webhook",
    "backup", "disaster recovery",
    "helm", "terraform", "provision",
    "pipeline", "ci/cd",
)


_DEEP_TECH_PATTERNS: tuple[str, ...] = (
    "cach", "redis", "memcached",
    "kubernetes", "helm", "terraform", "provision",
    "message broker", "queue", "background job",
    "cdn", "load balanc",
    "websocket", "sse", "polling", "server-sent",
    "shard", "replication",
    "logging", "monitoring", "observability", "tracing",
    "backup", "disaster recovery",
)


def _is_technical_gap(question: str) -> bool:
    """Check if a gap question is about technical implementation details."""
    lower = question.lower()
    return any(pattern in lower for pattern in _TECHNICAL_GAP_PATTERNS)


def _is_deep_tech_gap(question: str) -> bool:
    """Check if a gap question is about deep infrastructure concerns."""
    lower = question.lower()
    return any(pattern in lower for pattern in _DEEP_TECH_PATTERNS)


def _filter_gaps_by_profile(
    items: list[GapItem],
    profile: DiscoveryProfile | None,
) -> tuple[list[GapItem], list[GapItem]]:
    """Split gaps into visible and auto-answered based on user profile.

    Returns:
        (visible_items, auto_answered_items)

    * ``non_technical`` — auto-answer all technical gaps.
    * ``software_familiar`` — auto-answer only deep infra gaps.
    * ``developer`` / ``architect`` — keep everything visible.
    * ``profile is None`` — keep everything visible (backward-compat).
    """
    if profile is None:
        return list(items), []

    level = profile.audience_level

    if level in ("developer", "architect"):
        return list(items), []

    if level == "non_technical":
        visible: list[GapItem] = []
        auto: list[GapItem] = []
        for item in items:
            if _is_technical_gap(item.question):
                auto.append(item)
            else:
                visible.append(item)
        return visible, auto

    if level == "software_familiar":
        visible = []
        auto = []
        for item in items:
            if _is_deep_tech_gap(item.question):
                auto.append(item)
            else:
                visible.append(item)
        return visible, auto

    return list(items), []


def _auto_answer_gaps(items: list[GapItem]) -> list[GapAnswer]:
    """Create answers for gaps that should be auto-answered.

    Uses ``recommended_options`` when available, falls back to
    ``Not applicable``.
    """
    answers: list[GapAnswer] = []
    for item in items:
        if item.recommended_options:
            selected = item.recommended_options[:]
        else:
            selected = [_NOT_APPLICABLE]
        answers.append(GapAnswer(question=item.question, selected_options=selected))
    return answers


def _extract_paren_alternatives(question: str) -> list[str]:
    """Extract alternatives from parenthesized text like '(manual, automatico)'."""
    paren_match = re.search(r"\(([^)]+)\)", question)
    if paren_match is None:
        return []
    inner = paren_match.group(1)
    parts = [
        part.strip().rstrip("?")
        for part in _split_choice_alternatives(inner)
        if part.strip()
    ]
    if len(parts) >= 2:
        return parts + [_NEEDS_DISCUSSION, _NOT_APPLICABLE]
    return []


def _split_choice_alternatives(text: str) -> list[str]:
    parts: list[str] = []
    for slash_part in text.split("/"):
        parts.extend(_split_on_choice_words(slash_part))
    return parts


def _split_on_choice_words(text: str) -> list[str]:
    lower = text.casefold()
    parts: list[str] = []
    start = 0
    index = 0

    while index < len(text):
        matched_word = _match_choice_word(lower, text, index)

        if matched_word is None:
            index += 1
            continue

        parts.append(text[start:index])
        index += len(matched_word)
        while index < len(text) and text[index].isspace():
            index += 1
        start = index

    parts.append(text[start:])
    return parts


def _match_choice_word(lower: str, text: str, index: int) -> str | None:
    for word in ("or", "ou"):
        next_index = index + len(word)
        if not lower.startswith(word, index):
            continue
        if index == 0 or not text[index - 1].isspace():
            continue
        if next_index >= len(text) or not text[next_index].isspace():
            continue
        return word
    return None


def _strip_gap_markers(question: str) -> str:
    cleaned = question.lstrip()
    while True:
        lowered = cleaned.casefold()
        if lowered.startswith("[gap]"):
            cleaned = cleaned[len("[gap]") :].lstrip()
            continue
        if lowered.startswith("[hypothesis]"):
            cleaned = cleaned[len("[hypothesis]") :].lstrip()
            continue
        return cleaned


def _trim_trailing_gap_offer(question: str) -> str:
    cut_at = len(question)
    lowered = question.casefold()
    for phrase in ("e preciso confirmar", "é preciso confirmar", "se quiser, posso"):
        search_from = 0
        while True:
            index = lowered.find(phrase, search_from)
            if index == -1:
                break
            if index > 0 and question[index - 1].isspace():
                cut_at = min(cut_at, index)
                break
            search_from = index + 1
    return question[:cut_at]


_YES_NO_KEYWORDS: tuple[str, ...] = (
    "is ", "are ", "will ", "should ", "does ",
    "do ", "has ", "have ", "can ", "must ",
)

_NUMERIC_KEYWORDS: tuple[str, ...] = (
    "how many", "how much", "count", "number", "volume", "scale",
)

_AUDIENCE_KEYWORDS: tuple[str, ...] = (
    "audience", "user", "customer", "persona", "target",
)


def _infer_options(question: str) -> list[str]:
    """Heuristically derive answer options from question text."""
    q_lower = question.lower()

    inline_alternatives = _extract_inline_alternatives(question)
    if inline_alternatives:
        return inline_alternatives + [_NEEDS_DISCUSSION, _NOT_APPLICABLE]

    paren_result = _extract_paren_alternatives(question)
    if paren_result:
        return paren_result

    if any(q_lower.startswith(kw) for kw in _YES_NO_KEYWORDS):
        return ["Yes", "No", _NEEDS_DISCUSSION, _NOT_APPLICABLE]

    if any(q_lower.startswith(kw) for kw in _OPEN_QUESTION_PREFIXES):
        if _looks_portuguese(question):
            return _DEFAULT_OPEN_OPTIONS_PT.copy()
        return _DEFAULT_OPEN_OPTIONS_EN.copy()

    if any(kw in q_lower for kw in _NUMERIC_KEYWORDS):
        return ["< 1,000 / month", "1,000-100,000 / month", "> 100,000 / month", "Unknown / TBD"]

    if any(kw in q_lower for kw in _AUDIENCE_KEYWORDS):
        return ["B2C consumers", "B2B companies", "Internal teams", "Mixed / TBD"]

    return _DEFAULT_OPTIONS.copy()


def _sanitize_gap_question(question: str) -> str:
    """Normalize a raw [GAP] line into a clean single question."""
    cleaned = _strip_gap_markers(question)
    cleaned = cleaned.replace("**", "").strip()
    cleaned = _trim_trailing_gap_offer(cleaned).strip(" .;:-")
    return cleaned


def _looks_portuguese(text: str) -> bool:
    """Best-effort language hint for default option localization."""
    probe = text.lower()
    return any(token in f" {probe} " for token in _PORTUGUESE_TOKENS)


_ENRICH_SYSTEM = """\
You are a requirements analyst performing a MANDATORY enrichment task. \
Your output is consumed directly by a UI — it MUST be machine-parseable. \
Your role is authoritative: produce exactly the schema requested, nothing more.

Return a JSON object (no markdown, raw JSON only) with EXACTLY these fields:
- selection_mode: "single" if exactly one answer applies, "multiple" if several can apply simultaneously
- options: array of 3-6 SHORT, CONCRETE, STANDALONE answer strings
- recommended_options: array of 0-2 items from options you consider most common/default
- allow_free_text: true if the question requires a custom answer not coverable by options
- free_text_placeholder: short placeholder for the textarea when allow_free_text=true, else ""
- display_question: short user-facing rewrite of the gap question, or "" to keep the original question text
- help_text: short clarification text for the UI, or "" when no extra guidance is needed

MANDATORY RULES — violations produce broken UI:
- Each option MUST be a self-contained phrase. A user reading only the option must understand what they are selecting.
- Do NOT fragment the question sentence into pseudo-options. That is a FAILURE.
- Do NOT invent domain-specific options that have no basis in the project context provided.
- Do NOT produce fewer than 3 options. A single option defeats the purpose of a selection UI.
- Keep the original question identity stable. Use display_question/help_text for presentation only.
- Respond with ONLY the JSON object. No explanation. No markdown fences. No preamble.

RATIONALIZATION GUARD — these rationalizations are FORBIDDEN:
- "The question is self-explanatory" → still produce concrete options
- "The user will know what to pick" → still produce concrete options
- "There are only two obvious answers" → add a third meaningful option
"""

_ENRICH_USER_TMPL = (
    "Project context:\n{context}\n\n"
    "Discovery profile:\n{profile}\n\n"
    "Gap question: {question}"
)


def _format_enrichment_profile(profile: DiscoveryProfile | None) -> str:
    if profile is None:
        return "none"
    return (
        f"audience_level: {profile.audience_level}\n"
        f"question_style: {profile.question_style}\n"
        f"discovery_preference: {profile.discovery_preference}\n"
        f"language_tone: {profile.language_tone}"
    )


async def enrich_gap_items(
    items: list[GapItem],
    provider: Any,
    model: str | None,
    context: str,
    *,
    profile: DiscoveryProfile | None = None,
    max_concurrent: int = 3,
    on_progress: Any = None,
) -> list[GapItem]:
    """Enrich gap items with LLM-generated options and UI metadata.

    Calls are made in parallel (up to *max_concurrent* at a time) to avoid
    making the user wait for a sequential chain of LLM round-trips.  The
    semaphore keeps request rate reasonable for hosted providers.

    Falls back to heuristic if provider is None or a call returns unparseable
    content.
    """
    import asyncio

    if provider is None:
        return [_heuristic_enrich(item) for item in items]

    sem = asyncio.Semaphore(max_concurrent)
    completed_count = 0

    async def _enrich_one(item: GapItem) -> GapItem:
        nonlocal completed_count
        async with sem:
            try:
                enriched = await _llm_enrich(item, provider, model, context, profile=profile)
            except Exception:
                enriched = _heuristic_enrich(item)
        completed_count += 1
        if on_progress is not None:
            on_progress(completed_count)
        return enriched

    return list(await asyncio.gather(*(_enrich_one(item) for item in items)))


def _validate_llm_enrichment(data: dict) -> tuple:
    """Validate and unpack LLM enrichment response. Raises ValueError on invalid data."""
    selection_mode = data.get("selection_mode")
    options = data.get("options")
    recommended_options = data.get("recommended_options", [])
    allow_free_text = data.get("allow_free_text", False)
    free_text_placeholder = data.get("free_text_placeholder", "")
    display_question = data.get("display_question", "")
    help_text = data.get("help_text", "")

    if selection_mode not in {"single", "multiple"}:
        raise ValueError("invalid selection_mode")
    if (
        not isinstance(options, list)
        or len(options) < 3
        or len(options) > 6
        or not all(isinstance(o, str) and o for o in options)
    ):
        raise ValueError("invalid options")
    if (
        not isinstance(recommended_options, list)
        or len(recommended_options) > 2
        or not all(isinstance(o, str) and o in options for o in recommended_options)
    ):
        raise ValueError("invalid recommended_options")
    if not isinstance(allow_free_text, bool):
        raise ValueError("invalid allow_free_text")
    if not isinstance(free_text_placeholder, str):
        raise ValueError("invalid free_text_placeholder")
    if not allow_free_text and free_text_placeholder:
        raise ValueError("invalid free_text_placeholder")
    if not isinstance(display_question, str):
        raise ValueError("invalid display_question")
    if not isinstance(help_text, str):
        raise ValueError("invalid help_text")

    return options, selection_mode, recommended_options, allow_free_text, \
        free_text_placeholder, display_question, help_text


async def _llm_enrich(
    item: GapItem,
    provider: Any,
    model: str | None,
    context: str,
    profile: DiscoveryProfile | None = None,
) -> GapItem:
    messages = [
        Message(role="system", content=_ENRICH_SYSTEM),
        Message(
            role="user",
            content=_ENRICH_USER_TMPL.format(
                context=context,
                profile=_format_enrichment_profile(profile),
                question=item.question,
            ),
        ),
    ]
    collected_parts: list[str] = []
    async for msg in provider.stream(messages, model=model):
        if isinstance(msg, str):
            collected_parts.append(msg)
        elif hasattr(msg, "content") and msg.content:
            collected_parts.append(msg.content)
    collected = "".join(collected_parts)
    data = _json.loads(collected.strip())
    options, selection_mode, recommended_options, allow_free_text, \
        free_text_placeholder, display_question, help_text = _validate_llm_enrichment(data)

    return GapItem(
        question=item.question,
        options=options,
        selection_mode=selection_mode,
        recommended_index=0,
        recommended_options=recommended_options,
        allow_free_text=allow_free_text,
        free_text_placeholder=free_text_placeholder,
        display_question=display_question,
        help_text=help_text,
    )


def _heuristic_enrich(item: GapItem) -> GapItem:
    """Apply heuristic option inference and wrap into a full GapItem."""
    options = _infer_options(item.question)
    q_lower = item.question.lower()
    allow_free = any(q_lower.startswith(p) for p in _OPEN_QUESTION_PREFIXES)
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

    chunks: list[str] = []
    for comma_part in source.split(","):
        for raw in _split_on_choice_words(comma_part):
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


def _is_portuguese_hint(language_hint: str) -> bool:
    probe = language_hint.strip().lower()
    if not probe:
        return False
    return probe.startswith("pt") or "portugu" in probe or _looks_portuguese(probe)


def _send_json_response(handler: BaseHTTPRequestHandler, payload: Any) -> None:
    body = json.dumps(payload).encode("utf-8")
    handler.send_response(200)
    handler.send_header("Content-Type", _JSON_CONTENT_TYPE)
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def _serve_static_html(handler: BaseHTTPRequestHandler, filename: str) -> None:
    html_path = _STATIC_DIR / filename
    try:
        content = html_path.read_bytes()
    except FileNotFoundError:
        handler.send_error(404, f"{filename} not found")
        return

    handler.send_response(200)
    handler.send_header("Content-Type", "text/html; charset=utf-8")
    handler.send_header("Content-Length", str(len(content)))
    handler.end_headers()
    handler.wfile.write(content)


def _read_request_body(handler: BaseHTTPRequestHandler) -> bytes:
    length = int(handler.headers.get("Content-Length", 0))
    return handler.rfile.read(length)


def _dispatch_profile_get(handler: BaseHTTPRequestHandler) -> None:
    if handler.path in ("/", ""):
        _serve_static_html(handler, "profile.html")
        return
    if handler.path == "/profile/questions":
        _send_json_response(
            handler,
            _build_profile_questions_payload(handler.server_ref._questions),
        )
        return
    handler.send_error(404)


def _dispatch_profile_post(handler: BaseHTTPRequestHandler) -> None:
    if handler.path != "/profile/answers":
        handler.send_error(404)
        return

    raw = _read_request_body(handler)
    try:
        profile = _parse_profile_submission(raw, handler.allowed_values)
    except (KeyError, TypeError, ValueError):
        handler.send_error(400, "Invalid JSON")
        return

    handler.server_ref._profile = profile
    handler.server_ref._event.set()
    _send_json_response(handler, {"status": "ok"})


def _dispatch_gaps_get(handler: BaseHTTPRequestHandler) -> None:
    if handler.path in ("/", ""):
        _serve_static_html(handler, "gaps.html")
        return
    if handler.path == "/gaps":
        _send_json_response(handler, _build_gaps_payload(handler.server_ref._items))
        return
    if handler.path == "/gaps/status":
        _send_json_response(handler, _build_gaps_status_payload(handler.server_ref))
        return
    handler.send_error(404)


def _dispatch_gaps_post(handler: BaseHTTPRequestHandler) -> None:
    if handler.path != "/answers":
        handler.send_error(404)
        return

    raw = _read_request_body(handler)
    try:
        answers = _parse_gap_answers(raw)
    except (KeyError, TypeError, ValueError):
        handler.send_error(400, "Invalid JSON")
        return

    handler.server_ref._answers = answers
    handler.server_ref._event.set()
    _send_json_response(handler, {"status": "ok"})


def _build_profile_questions_payload(
    questions: list[ProfileQuestion],
) -> list[dict[str, Any]]:
    return [
        {
            "key": question.key,
            "prompt": question.prompt,
            "options": [
                {"value": option.value, "label": option.label}
                for option in question.options
            ],
        }
        for question in questions
    ]


def _parse_profile_submission(
    raw: bytes,
    allowed_values: dict[str, set[str]],
) -> DiscoveryProfile:
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise ValueError("payload must be an object")
    for key, values in allowed_values.items():
        value = data[key]
        if not isinstance(value, str) or value not in values:
            raise ValueError(f"invalid {key}")
    return DiscoveryProfile(**data)


def _build_gaps_payload(items: list[GapItem]) -> list[dict[str, Any]]:
    return [
        {
            "question": item.question,
            "display_question": item.display_question,
            "help_text": item.help_text,
            "options": item.options,
            "selection_mode": item.selection_mode,
            "recommended_index": item.recommended_index,
            "recommended_options": item.recommended_options,
            "allow_free_text": item.allow_free_text,
            "free_text_placeholder": item.free_text_placeholder,
        }
        for item in items
    ]


def _build_gaps_status_payload(server: "GapsServer") -> dict[str, int | bool]:
    return {
        "ready": server._enrich_ready,
        "enriched": server._enriched_count,
        "total": len(server._items),
    }


def _selected_options_from_answer_payload(item: dict[str, Any]) -> list[str]:
    selected = item.get("selected_options")
    legacy = item.get("chosen_option")
    if isinstance(selected, list) and selected and all(
        isinstance(opt, str) and opt for opt in selected
    ):
        return selected
    if isinstance(legacy, str) and legacy:
        return [legacy]
    raise ValueError("answer requires selected_options: list[str]")


def _parse_gap_answers(raw: bytes) -> list[GapAnswer]:
    data: list[dict[str, Any]] = json.loads(raw)
    answers: list[GapAnswer] = []
    for item in data:
        answers.append(
            GapAnswer(
                question=item["question"],
                selected_options=_selected_options_from_answer_payload(item),
                free_text=item.get("free_text", ""),
            )
        )
    return answers


def build_discovery_profile_questions(language_hint: str) -> list[ProfileQuestion]:
    """Build the static discovery-profile questionnaire for the standalone UI."""
    if _is_portuguese_hint(language_hint):
        return [
            ProfileQuestion(
                key="audience_level",
                prompt="Quem vai consumir esses artefatos primeiro?",
                options=[
                    ProfileOption(value="non_technical", label="Pessoa nao tecnica"),
                    ProfileOption(
                        value="software_familiar",
                        label="Pessoa familiarizada com software",
                    ),
                    ProfileOption(value="developer", label="Desenvolvedor(a)"),
                    ProfileOption(value="architect", label="Arquiteto(a) / Tech Lead"),
                ],
            ),
            ProfileQuestion(
                key="question_style",
                prompt="Como devo formular perguntas quando faltar contexto?",
                options=[
                    ProfileOption(value="simple", label="Mais simples e diretas"),
                    ProfileOption(value="functional", label="Focadas em fluxo e negocio"),
                    ProfileOption(value="technical", label="Mais tecnicas e detalhadas"),
                ],
            ),
            ProfileQuestion(
                key="discovery_preference",
                prompt="Quando houver lacunas, como devo agir?",
                options=[
                    ProfileOption(value="ask_more", label="Perguntar mais antes de decidir"),
                    ProfileOption(value="suggest", label="Sugerir caminhos para acelerar"),
                    ProfileOption(
                        value="decide_when_needed",
                        label="Decidir quando o contexto permitir",
                    ),
                ],
            ),
            ProfileQuestion(
                key="language_tone",
                prompt="Qual tom de linguagem devo usar?",
                options=[
                    ProfileOption(value="simple", label="Simples"),
                    ProfileOption(value="balanced", label="Equilibrado"),
                    ProfileOption(value="technical", label="Tecnico"),
                ],
            ),
        ]

    return [
        ProfileQuestion(
            key="audience_level",
            prompt="Who will consume these artifacts first?",
            options=[
                ProfileOption(value="non_technical", label="Non-technical stakeholder"),
                ProfileOption(value="software_familiar", label="Software-familiar stakeholder"),
                ProfileOption(value="developer", label="Developer"),
                ProfileOption(value="architect", label="Architect / Tech Lead"),
            ],
        ),
        ProfileQuestion(
            key="question_style",
            prompt="How should I ask questions when context is missing?",
            options=[
                ProfileOption(value="simple", label="Simpler and more direct"),
                ProfileOption(value="functional", label="Focused on workflow and business"),
                ProfileOption(value="technical", label="More technical and detailed"),
            ],
        ),
        ProfileQuestion(
            key="discovery_preference",
            prompt="When gaps remain, how should I behave?",
            options=[
                ProfileOption(value="ask_more", label="Ask more before deciding"),
                ProfileOption(value="suggest", label="Suggest paths to accelerate"),
                ProfileOption(
                    value="decide_when_needed",
                    label="Decide when the context supports it",
                ),
            ],
        ),
        ProfileQuestion(
            key="language_tone",
            prompt="What language tone should I use?",
            options=[
                ProfileOption(value="simple", label="Simple"),
                ProfileOption(value="balanced", label="Balanced"),
                ProfileOption(value="technical", label="Technical"),
            ],
        ),
    ]


class ProfileServer:
    """HTTP server that collects a discovery profile before discovery continues."""

    def __init__(self, questions: list[ProfileQuestion], port: int = 4041) -> None:
        self._questions = questions
        self._requested_port = port
        self._profile: DiscoveryProfile | None = None
        self._event = threading.Event()
        self._server: ThreadingHTTPServer | None = None

    @property
    def port(self) -> int:
        if self._server is None:
            raise RuntimeError("Server not started")
        return self._server.server_address[1]

    def start(self) -> None:
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

    def get_profile(self, timeout: float | None = None) -> DiscoveryProfile | None:
        self._event.wait(timeout=timeout)
        return self._profile

    def _make_handler(self) -> type[BaseHTTPRequestHandler]:
        server_ref = self
        allowed_values = {
            question.key: {option.value for option in question.options}
            for question in self._questions
        }

        class ProfileHandler(BaseHTTPRequestHandler):
            def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
                del format, args

            def do_GET(self) -> None:
                _dispatch_profile_get(self)

            def do_POST(self) -> None:
                _dispatch_profile_post(self)

        ProfileHandler.server_ref = server_ref
        ProfileHandler.allowed_values = allowed_values
        return ProfileHandler


def resolve_discovery_profile(
    context_hint: str,
    port: int = 4041,
    open_browser: bool = True,
) -> DiscoveryProfile:
    """Serve a blocking discovery-profile form and return the user's profile."""
    questions = build_discovery_profile_questions(context_hint)
    server = ProfileServer(questions, port=port)
    server.start()
    try:
        if open_browser:
            webbrowser.open(f"http://localhost:{server.port}")
        profile = server.get_profile(timeout=None)
    finally:
        server.stop()

    if profile is None:
        raise RuntimeError("Profile not submitted")
    return profile


class GapsServer:
    """HTTP server that presents gap questions and blocks until user answers."""

    def __init__(self, items: list[GapItem], port: int = 4041) -> None:
        self._items = items
        self._enriched_count: int = 0
        self._enrich_ready: bool = False
        self._requested_port = port
        self._answers: list[GapAnswer] | None = None
        self._event = threading.Event()
        self._server: ThreadingHTTPServer | None = None

    @property
    def port(self) -> int:
        if self._server is None:
            raise RuntimeError("Server not started")
        return self._server.server_address[1]

    def update_items(self, items: list[GapItem]) -> None:
        """Replace items with enriched versions and mark ready."""
        self._items = items
        self._enriched_count = len(items)
        self._enrich_ready = True

    def update_enriched_count(self, count: int) -> None:
        """Update the count of enriched items (for progress reporting)."""
        self._enriched_count = count

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
                _dispatch_gaps_get(self)

            def do_POST(self) -> None:
                _dispatch_gaps_post(self)

        GapsHandler.server_ref = server_ref
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
    profile: DiscoveryProfile | None = None,
) -> list[GapAnswer]:
    """Parse gaps from markdown, serve questionnaire, block until answered.

    The server starts immediately with heuristic-enriched items so the browser
    can open without delay.  LLM enrichment runs in the background (up to 3
    concurrent calls) and the frontend polls ``/gaps/status`` to show a
    progress bar until the enriched questions are ready.
    """
    import asyncio

    items = parse_gaps(gaps_content)
    if not items:
        return []

    # Apply profile-based filtering: auto-answer technical gaps for
    # non-technical users so the questionnaire stays approachable.
    visible_items, auto_answered_items = _filter_gaps_by_profile(items, profile)
    auto_answers = _auto_answer_gaps(auto_answered_items)

    # Heuristic enrichment is instant — start serving right away so the
    # browser opens before any LLM call is made.
    heuristic_items = [_heuristic_enrich(item) for item in visible_items]
    server = serve_gaps(heuristic_items, port=port)
    url = f"http://localhost:{server.port}"
    if open_browser:
        webbrowser.open(url)

    # Run LLM enrichment in the background.  When done, push updated items
    # back into the server so the frontend can pick them up via polling.
    async def _background_enrich() -> None:
        enriched_items = await enrich_gap_items(
            visible_items,
            provider=provider,
            model=model,
            context=gaps_content,
            profile=profile,
            max_concurrent=3,
            on_progress=server.update_enriched_count,
        )
        server.update_items(enriched_items)

    enrich_task = asyncio.ensure_future(_background_enrich())

    # get_answers() calls threading.Event.wait() which blocks the OS thread.
    # Running it via run_in_executor frees the asyncio event loop so that
    # _background_enrich can make progress while we wait for the user.
    loop = asyncio.get_event_loop()
    try:
        answers = await loop.run_in_executor(None, lambda: server.get_answers(timeout=None))
    finally:
        enrich_task.cancel()
        server.stop()

    return (answers or []) + auto_answers
