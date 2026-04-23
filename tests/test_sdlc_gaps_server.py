"""Tests for the gaps server - parser and server round-trip."""
from __future__ import annotations

import asyncio
import json
import threading
import time
import urllib.error
import urllib.request


GAP_MARKDOWN = """\
# Gaps

[GAP] What is the target audience? (B2C or B2B?)
[GAP] What is the expected monthly active user count?
[GAP] Is SSO required?
"""


def test_parse_gaps_returns_gap_items():
    from maestro.sdlc.gaps_server import parse_gaps

    items = parse_gaps(GAP_MARKDOWN)
    assert len(items) == 3
    assert items[0].question == "What is the target audience? (B2C or B2B?)"
    assert len(items[0].options) >= 2
    assert items[0].recommended_index == 0


def test_parse_gaps_empty_content():
    from maestro.sdlc.gaps_server import parse_gaps

    items = parse_gaps("# Gaps\n\nNo gaps found.\n")
    assert items == []


def test_parse_gaps_no_gap_tag():
    from maestro.sdlc.gaps_server import parse_gaps

    items = parse_gaps("# Gaps\n\nSome text without GAP markers.\n")
    assert items == []


def test_parse_gaps_accepts_markdown_list_prefixes():
    from maestro.sdlc.gaps_server import parse_gaps

    content = """\
# Gaps

- [GAP] Is SSO required?
* [GAP] Which regions must we support?
1. [GAP] What is the expected monthly active user count?
"""

    items = parse_gaps(content)
    assert [item.question for item in items] == [
        "Is SSO required?",
        "Which regions must we support?",
        "What is the expected monthly active user count?",
    ]


def test_parse_gaps_open_portuguese_question_avoids_yes_no_defaults():
    from maestro.sdlc.gaps_server import parse_gaps

    content = "[GAP] Qual e exatamente o fluxo a ser testado?\n"
    items = parse_gaps(content)

    assert len(items) == 1
    assert items[0].options == [
        "Definir resposta especifica",
        "Precisa de discussao",
        "Depende do contexto",
        "Nao se aplica",
    ]


def test_parse_gaps_binary_question_keeps_yes_no_options():
    from maestro.sdlc.gaps_server import parse_gaps

    content = "[GAP] Is SSO required?\n"
    items = parse_gaps(content)

    assert len(items) == 1
    assert items[0].options == [
        "Yes",
        "No",
        "Needs discussion",
        "Not applicable",
    ]


def test_parse_gaps_portuguese_who_question_uses_open_options():
    from maestro.sdlc.gaps_server import parse_gaps

    content = "[GAP] Quem pode pausar um gap?\n"
    items = parse_gaps(content)

    assert len(items) == 1
    assert items[0].options == [
        "Definir resposta especifica",
        "Precisa de discussao",
        "Depende do contexto",
        "Nao se aplica",
    ]


def test_parse_gaps_extracts_inline_alternatives_without_parentheses():
    from maestro.sdlc.gaps_server import parse_gaps

    content = "[GAP] A pausa e manual, automatica ou ambas?\n"
    items = parse_gaps(content)

    assert len(items) == 1
    assert items[0].options == [
        "A pausa e manual",
        "automatica",
        "ambas",
        "Needs discussion",
        "Not applicable",
    ]


def test_parse_gaps_sanitizes_nested_markers_and_deduplicates_questions():
    from maestro.sdlc.gaps_server import parse_gaps

    content = """\
[GAP] [HYPOTHESIS] O que significa gap neste contexto? E preciso confirmar com o usuario.
[GAP] O que significa gap neste contexto?
[GAP] Se quiser, posso transformar esses gaps em checklist.
"""

    items = parse_gaps(content)

    assert [item.question for item in items] == [
        "O que significa gap neste contexto?",
        "Se quiser, posso transformar esses gaps em checklist",
    ]


def test_parse_gaps_ignores_trailing_llm_offer_text_appended_to_gap():
    from maestro.sdlc.gaps_server import parse_gaps

    content = (
        "[GAP] Qual e o objetivo da pausa? "
        "Se quiser, posso transformar esses gaps em criterios de aceite.\n"
    )

    items = parse_gaps(content)

    assert len(items) == 1
    assert items[0].question == "Qual e o objetivo da pausa?"


def test_gaps_server_serves_answers_endpoint():
    """GapsServer serves GET /gaps and accepts POST /answers."""
    from maestro.sdlc.gaps_server import GapsServer, parse_gaps

    items = parse_gaps("[GAP] Is SSO required?\n[GAP] What is the scale?\n")
    assert len(items) == 2

    server = GapsServer(items, port=0)
    server.start()
    port = server.port
    try:
        resp = urllib.request.urlopen(f"http://localhost:{port}/gaps", timeout=3)
        data = json.loads(resp.read())
        assert len(data) == 2
        assert data[0]["question"] == "Is SSO required?"
        assert "options" in data[0]
        assert "selection_mode" in data[0]
        assert "recommended_index" in data[0]

        answers = [
            {
                "question": "Is SSO required?",
                "selected_options": ["Yes"],
                "free_text": "",
            },
            {
                "question": "What is the scale?",
                "selected_options": ["Unknown / TBD"],
                "free_text": "",
            },
        ]
        req = urllib.request.Request(
            f"http://localhost:{port}/answers",
            data=json.dumps(answers).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        urllib.request.urlopen(req, timeout=3)

        time.sleep(0.1)
        result = server.get_answers(timeout=1.0)
        assert len(result) == 2
        assert result[0].selected_options == ["Yes"]
    finally:
        server.stop()


def test_gaps_server_get_answers_blocks_until_submission():
    """get_answers() blocks and only returns after POST /answers."""
    from maestro.sdlc.gaps_server import GapsServer, parse_gaps

    items = parse_gaps("[GAP] Any gaps?\n")
    server = GapsServer(items, port=0)
    server.start()
    port = server.port

    answers_received: list = []

    def submit_later():
        time.sleep(0.1)
        answers = [{"question": "Any gaps?", "selected_options": ["Yes"], "free_text": ""}]
        req = urllib.request.Request(
            f"http://localhost:{port}/answers",
            data=json.dumps(answers).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        urllib.request.urlopen(req, timeout=3)

    t = threading.Thread(target=submit_later)
    t.start()
    result = server.get_answers(timeout=2.0)
    t.join()
    server.stop()

    assert result is not None
    assert len(result) == 1
    assert result[0].question == "Any gaps?"


def test_enrich_gap_items_no_provider_uses_fallback():
    from maestro.sdlc.gaps_server import enrich_gap_items
    from maestro.sdlc.schemas import GapItem

    items = [GapItem(question="Is SSO required?", options=[])]

    result = asyncio.run(enrich_gap_items(items, provider=None, model=None, context=""))

    assert len(result) == 1
    assert len(result[0].options) >= 2
    assert result[0].selection_mode in ("single", "multiple")


def test_enrich_gap_items_provider_returns_valid_json():
    from maestro.sdlc.gaps_server import enrich_gap_items
    from maestro.sdlc.schemas import GapItem

    class FakeProvider:
        async def stream(self, messages, model=None, **kw):
            del messages, model, kw
            payload = '{"selection_mode":"multiple","options":["REST","GraphQL","gRPC"],"recommended_options":["REST"],"allow_free_text":false,"free_text_placeholder":""}'
            yield type("Msg", (), {"content": payload, "tool_calls": None})()

    items = [GapItem(question="Which API protocols are needed?", options=[])]

    result = asyncio.run(
        enrich_gap_items(items, provider=FakeProvider(), model="x", context="API project")
    )

    assert result[0].selection_mode == "multiple"
    assert "REST" in result[0].options


def test_enrich_gap_items_provider_bad_json_uses_fallback():
    from maestro.sdlc.gaps_server import enrich_gap_items
    from maestro.sdlc.schemas import GapItem

    class BadProvider:
        async def stream(self, messages, model=None, **kw):
            del messages, model, kw
            yield type("Msg", (), {"content": "not json at all", "tool_calls": None})()

    items = [GapItem(question="Is mobile app required?", options=[])]

    result = asyncio.run(enrich_gap_items(items, provider=BadProvider(), model="x", context=""))

    assert len(result[0].options) >= 2


def test_gaps_json_endpoint_includes_new_fields():
    import json as _j

    from maestro.sdlc.gaps_server import GapsServer
    from maestro.sdlc.schemas import GapItem

    items = [
        GapItem(
            question="Which protocols are needed?",
            options=["REST", "GraphQL"],
            selection_mode="multiple",
            allow_free_text=False,
            recommended_options=["REST"],
        )
    ]
    server = GapsServer(items, port=0)
    server.start()
    try:
        resp = urllib.request.urlopen(f"http://127.0.0.1:{server.port}/gaps")
        data = _j.loads(resp.read())
        assert data[0]["selection_mode"] == "multiple"
        assert data[0]["allow_free_text"] is False
        assert data[0]["recommended_options"] == ["REST"]
    finally:
        server.stop()


def test_answers_endpoint_parses_selected_options():
    import json as _j

    from maestro.sdlc.gaps_server import GapsServer
    from maestro.sdlc.schemas import GapItem

    items = [
        GapItem(
            question="Which protocols?",
            options=["REST", "GraphQL"],
            selection_mode="multiple",
        )
    ]
    server = GapsServer(items, port=0)
    server.start()
    try:
        payload = _j.dumps(
            [
                {
                    "question": "Which protocols?",
                    "selected_options": ["REST", "GraphQL"],
                    "free_text": "",
                }
            ]
        ).encode()
        req = urllib.request.Request(
            f"http://127.0.0.1:{server.port}/answers",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        resp = urllib.request.urlopen(req)
        assert resp.status == 200
        answers = server.get_answers(timeout=1.0)
        assert answers is not None
        assert answers[0].selected_options == ["REST", "GraphQL"]
        assert answers[0].free_text == ""
    finally:
        server.stop()
