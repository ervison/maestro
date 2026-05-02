"""Tests for the gaps server - parser and server round-trip."""
from __future__ import annotations

import asyncio
import io
import json
import threading
import time
import urllib.error
import urllib.request
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from test_sdlc_harness import *  # noqa: F401,F403


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


def test_parse_gaps_splits_choice_words_only_at_word_boundaries():
    from maestro.sdlc.gaps_server import parse_gaps

    content = "[GAP] Choose monitor ou keyboard ou mouse?\n"
    items = parse_gaps(content)

    assert len(items) == 1
    assert items[0].options == [
        "Choose monitor",
        "keyboard",
        "mouse",
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


def test_build_discovery_profile_questions_portuguese():
    from maestro.sdlc.gaps_server import build_discovery_profile_questions

    questions = build_discovery_profile_questions("pt-BR")

    assert [(question.key, question.prompt) for question in questions] == [
        ("audience_level", "Quem vai consumir esses artefatos primeiro?"),
        ("question_style", "Como devo formular perguntas quando faltar contexto?"),
        ("discovery_preference", "Quando houver lacunas, como devo agir?"),
        ("language_tone", "Qual tom de linguagem devo usar?"),
    ]
    assert [(option.value, option.label) for option in questions[0].options] == [
        ("non_technical", "Pessoa nao tecnica"),
        ("software_familiar", "Pessoa familiarizada com software"),
        ("developer", "Desenvolvedor(a)"),
        ("architect", "Arquiteto(a) / Tech Lead"),
    ]
    assert [(option.value, option.label) for option in questions[1].options] == [
        ("simple", "Mais simples e diretas"),
        ("functional", "Focadas em fluxo e negocio"),
        ("technical", "Mais tecnicas e detalhadas"),
    ]
    assert [(option.value, option.label) for option in questions[2].options] == [
        ("ask_more", "Perguntar mais antes de decidir"),
        ("suggest", "Sugerir caminhos para acelerar"),
        ("decide_when_needed", "Decidir quando o contexto permitir"),
    ]
    assert [(option.value, option.label) for option in questions[3].options] == [
        ("simple", "Simples"),
        ("balanced", "Equilibrado"),
        ("technical", "Tecnico"),
    ]


def test_profile_server_round_trip():
    from maestro.sdlc.gaps_server import ProfileServer, build_discovery_profile_questions
    from maestro.sdlc.schemas import DiscoveryProfile

    server = ProfileServer(build_discovery_profile_questions("pt-BR"), port=0)
    server.start()
    port = server.port
    try:
        resp = urllib.request.urlopen(f"http://localhost:{port}/profile/questions", timeout=3)
        data = json.loads(resp.read())
        assert [item["key"] for item in data] == [
            "audience_level",
            "question_style",
            "discovery_preference",
            "language_tone",
        ]
        assert data[0]["options"][0] == {
            "value": "non_technical",
            "label": "Pessoa nao tecnica",
        }

        html = urllib.request.urlopen(f"http://localhost:{port}/", timeout=3).read().decode("utf-8")
        assert "Discovery Profile" in html

        payload = {
            "audience_level": "developer",
            "question_style": "technical",
            "discovery_preference": "decide_when_needed",
            "language_tone": "balanced",
        }
        req = urllib.request.Request(
            f"http://localhost:{port}/profile/answers",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        urllib.request.urlopen(req, timeout=3)

        assert server.get_profile(timeout=1.0) == DiscoveryProfile(**payload)
    finally:
        server.stop()


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


def test_enrich_gap_items_parseable_invalid_json_uses_fallback():
    from maestro.sdlc.gaps_server import enrich_gap_items
    from maestro.sdlc.schemas import GapItem

    class InvalidShapeProvider:
        async def stream(self, messages, model=None, **kw):
            del messages, model, kw
            payload = '{"selection_mode":"banana","options":"yes","recommended_options":"no","allow_free_text":"maybe","free_text_placeholder":123}'
            yield type("Msg", (), {"content": payload, "tool_calls": None})()

    items = [GapItem(question="Is mobile app required?", options=[])]

    result = asyncio.run(
        enrich_gap_items(items, provider=InvalidShapeProvider(), model="x", context="")
    )

    assert result[0].options == ["Yes", "No", "Needs discussion", "Not applicable"]
    assert result[0].selection_mode == "single"
    assert result[0].recommended_options == []
    assert result[0].allow_free_text is False
    assert result[0].free_text_placeholder == "Specify..."


def test_enrich_gap_items_parseable_too_few_options_uses_fallback():
    from maestro.sdlc.gaps_server import enrich_gap_items
    from maestro.sdlc.schemas import GapItem

    class TooFewOptionsProvider:
        async def stream(self, messages, model=None, **kw):
            del messages, model, kw
            payload = '{"selection_mode":"single","options":["Yes","No"],"recommended_options":["Yes"],"allow_free_text":false,"free_text_placeholder":""}'
            yield type("Msg", (), {"content": payload, "tool_calls": None})()

    items = [GapItem(question="Is mobile app required?", options=[])]

    result = asyncio.run(
        enrich_gap_items(items, provider=TooFewOptionsProvider(), model="x", context="")
    )

    assert result[0].options == ["Yes", "No", "Needs discussion", "Not applicable"]
    assert result[0].selection_mode == "single"
    assert result[0].recommended_options == []


def test_enrich_gap_items_parseable_too_many_options_uses_fallback():
    from maestro.sdlc.gaps_server import enrich_gap_items
    from maestro.sdlc.schemas import GapItem

    class TooManyOptionsProvider:
        async def stream(self, messages, model=None, **kw):
            del messages, model, kw
            payload = '{"selection_mode":"single","options":["One","Two","Three","Four","Five","Six","Seven"],"recommended_options":["One"],"allow_free_text":false,"free_text_placeholder":""}'
            yield type("Msg", (), {"content": payload, "tool_calls": None})()

    items = [GapItem(question="Is mobile app required?", options=[])]

    result = asyncio.run(
        enrich_gap_items(items, provider=TooManyOptionsProvider(), model="x", context="")
    )

    assert result[0].options == ["Yes", "No", "Needs discussion", "Not applicable"]
    assert result[0].selection_mode == "single"
    assert result[0].recommended_options == []


def test_enrich_gap_items_parseable_too_many_recommended_options_uses_fallback():
    from maestro.sdlc.gaps_server import enrich_gap_items
    from maestro.sdlc.schemas import GapItem

    class TooManyRecommendedOptionsProvider:
        async def stream(self, messages, model=None, **kw):
            del messages, model, kw
            payload = '{"selection_mode":"multiple","options":["REST","GraphQL","gRPC"],"recommended_options":["REST","GraphQL","gRPC"],"allow_free_text":false,"free_text_placeholder":""}'
            yield type("Msg", (), {"content": payload, "tool_calls": None})()

    items = [GapItem(question="Which API protocols are needed?", options=[])]

    result = asyncio.run(
        enrich_gap_items(
            items,
            provider=TooManyRecommendedOptionsProvider(),
            model="x",
            context="API project",
        )
    )

    assert result[0].options == [
        "Provide specific answer",
        "Needs discussion",
        "Depends on context",
        "Not applicable",
    ]
    assert result[0].selection_mode == "multiple"
    assert result[0].recommended_options == []


def test_enrich_gap_items_parseable_placeholder_without_free_text_uses_fallback():
    from maestro.sdlc.gaps_server import enrich_gap_items
    from maestro.sdlc.schemas import GapItem

    class PlaceholderWithoutFreeTextProvider:
        async def stream(self, messages, model=None, **kw):
            del messages, model, kw
            payload = '{"selection_mode":"single","options":["Yes","No","Needs discussion"],"recommended_options":["Yes"],"allow_free_text":false,"free_text_placeholder":"Please explain"}'
            yield type("Msg", (), {"content": payload, "tool_calls": None})()

    items = [GapItem(question="Is mobile app required?", options=[])]

    result = asyncio.run(
        enrich_gap_items(
            items,
            provider=PlaceholderWithoutFreeTextProvider(),
            model="x",
            context="",
        )
    )

    assert result[0].options == ["Yes", "No", "Needs discussion", "Not applicable"]
    assert result[0].selection_mode == "single"
    assert result[0].recommended_options == []
    assert result[0].allow_free_text is False
    assert result[0].free_text_placeholder == "Specify..."


def test_llm_enrich_accumulates_string_and_message_chunks():
    from maestro.sdlc.gaps_server import _llm_enrich
    from maestro.sdlc.schemas import DiscoveryProfile, GapItem

    class ChunkedProvider:
        async def stream(self, messages, model=None, **kw):
            del messages, model, kw
            yield '{"selection_mode":"multiple",'
            yield type(
                "Msg",
                (),
                {"content": '"options":["REST","GraphQL","gRPC"],', "tool_calls": None},
            )()
            yield '"recommended_options":["REST"],"allow_free_text":false,"free_text_placeholder":""}'

    result = asyncio.run(
        _llm_enrich(
            GapItem(question="Which API protocols are needed?", options=[]),
            provider=ChunkedProvider(),
            model="x",
            context="API project",
        )
    )

    assert result.selection_mode == "multiple"
    assert result.options == ["REST", "GraphQL", "gRPC"]
    assert result.recommended_options == ["REST"]


def test_llm_enrich_accepts_display_question_and_help_text_fields():
    from maestro.sdlc.gaps_server import _llm_enrich
    from maestro.sdlc.schemas import DiscoveryProfile, GapItem

    profile = DiscoveryProfile(
        audience_level="developer",
        question_style="technical",
        discovery_preference="suggest",
        language_tone="balanced",
    )

    class ProfileAwareProvider:
        async def stream(self, messages, model=None, **kw):
            del model, kw
            assert len(messages) == 2
            assert "audience_level: developer" in messages[1].content
            assert "question_style: technical" in messages[1].content
            yield (
                '{"selection_mode":"multiple","options":["REST","GraphQL","gRPC"],'
                '"recommended_options":["REST"],"allow_free_text":true,'
                '"free_text_placeholder":"Add constraints","display_question":"Which API protocols should the platform support?",'
                '"help_text":"Select every protocol the first release must expose."}'
            )

    result = asyncio.run(
        _llm_enrich(
            GapItem(question="Which API protocols are needed?", options=[]),
            provider=ProfileAwareProvider(),
            model="x",
            context="API project",
            profile=profile,
        )
    )

    assert result.question == "Which API protocols are needed?"
    assert result.display_question == "Which API protocols should the platform support?"
    assert result.help_text == "Select every protocol the first release must expose."


def test_enrich_gap_items_reports_progress_per_completed_item():
    from maestro.sdlc.gaps_server import enrich_gap_items
    from maestro.sdlc.schemas import GapItem

    class SlowProvider:
        async def stream(self, messages, model=None, **kw):
            del model, kw
            question = messages[-1].content.split("Gap question: ", 1)[1]
            delays = {
                "First question?": 0.03,
                "Second question?": 0.01,
                "Third question?": 0.02,
            }
            await asyncio.sleep(delays[question])
            yield (
                '{"selection_mode":"single","options":["Yes","No","Needs discussion"],'
                '"recommended_options":["Yes"],"allow_free_text":false,"free_text_placeholder":""}'
            )

    progress_updates: list[int] = []
    items = [
        GapItem(question="First question?", options=[]),
        GapItem(question="Second question?", options=[]),
        GapItem(question="Third question?", options=[]),
    ]

    result = asyncio.run(
        enrich_gap_items(
            items,
            provider=SlowProvider(),
            model="x",
            context="",
            max_concurrent=3,
            on_progress=progress_updates.append,
        )
    )

    assert progress_updates == [1, 2, 3]
    assert [item.question for item in result] == [
        "First question?",
        "Second question?",
        "Third question?",
    ]


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


def test_gaps_json_endpoint_includes_display_question_and_help_text():
    import json as _j

    from maestro.sdlc.gaps_server import GapsServer
    from maestro.sdlc.schemas import GapItem

    items = [
        GapItem(
            question="Which protocols are needed?",
            display_question="Which API protocols should the first release support?",
            help_text="Select every protocol the external clients must consume.",
            options=["REST", "GraphQL", "gRPC"],
        )
    ]
    server = GapsServer(items, port=0)
    server.start()
    try:
        resp = urllib.request.urlopen(f"http://127.0.0.1:{server.port}/gaps")
        data = _j.loads(resp.read())
        assert data[0]["question"] == "Which protocols are needed?"
        assert data[0]["display_question"] == "Which API protocols should the first release support?"
        assert data[0]["help_text"] == "Select every protocol the external clients must consume."
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


def test_resolve_gaps_reuses_shared_enrichment_pipeline_with_progress_updates():
    from maestro.sdlc.gaps_server import resolve_gaps
    from maestro.sdlc.schemas import GapAnswer, GapItem

    heuristic_event = threading.Event()
    served_items: list[GapItem] = []
    final_items: list[GapItem] = []
    progress_updates: list[int] = []
    answers = [GapAnswer(question="First question?", selected_options=["Yes"], free_text="")]

    class FakeServer:
        port = 4312

        def update_enriched_count(self, count: int) -> None:
            progress_updates.append(count)

        def update_items(self, items: list[GapItem]) -> None:
            final_items[:] = items
            heuristic_event.set()

        def get_answers(self, timeout=None):
            del timeout
            heuristic_event.wait(1.0)
            return answers

        def stop(self) -> None:
            pass

    async def fake_enrich(
        items,
        provider,
        model,
        context,
        *,
        profile=None,
        max_concurrent=3,
        on_progress=None,
    ):
        del provider, model, context, profile
        assert max_concurrent == 3
        assert on_progress is not None
        on_progress(1)
        on_progress(2)
        return [
            GapItem(question=item.question, options=["Enriched"], selection_mode="single")
            for item in items
        ]

    def fake_serve(items, port=4041):
        del port
        served_items[:] = items
        return FakeServer()

    with patch("maestro.sdlc.gaps_server.serve_gaps", side_effect=fake_serve):
        with patch("maestro.sdlc.gaps_server.enrich_gap_items", new=AsyncMock(side_effect=fake_enrich)) as mock_enrich:
            result = asyncio.run(
                resolve_gaps(
                    "[GAP] First question?\n[GAP] Second question?\n",
                    provider=object(),
                    model="test-model",
                    open_browser=False,
                )
            )

    assert [item.question for item in served_items] == ["First question?", "Second question?"]
    assert progress_updates == [1, 2]
    assert [item.options for item in final_items] == [["Enriched"], ["Enriched"]]
    assert result == answers
    mock_enrich.assert_awaited_once()


def test_resolve_gaps_passes_full_context_to_enrichment_pipeline():
    from maestro.sdlc.gaps_server import resolve_gaps
    from maestro.sdlc.schemas import GapAnswer, GapItem

    answers_ready = threading.Event()
    expected_context = "[GAP] First question?\n" + ("project context line\n" * 80)
    answers = [GapAnswer(question="First question?", selected_options=["Yes"], free_text="")]

    class FakeServer:
        port = 4313

        def update_enriched_count(self, count: int) -> None:
            del count

        def update_items(self, items: list[GapItem]) -> None:
            del items
            answers_ready.set()

        def get_answers(self, timeout=None):
            del timeout
            answers_ready.wait(1.0)
            return answers

        def stop(self) -> None:
            pass

    async def fake_enrich(
        items,
        provider,
        model,
        context,
        *,
        profile=None,
        max_concurrent=3,
        on_progress=None,
    ):
        del items, provider, model, profile, max_concurrent, on_progress
        assert context == expected_context
        return [GapItem(question="First question?", options=["Enriched"], selection_mode="single")]

    with patch("maestro.sdlc.gaps_server.serve_gaps", return_value=FakeServer()):
        with patch("maestro.sdlc.gaps_server.enrich_gap_items", new=AsyncMock(side_effect=fake_enrich)):
            result = asyncio.run(
                resolve_gaps(
                    expected_context,
                    provider=object(),
                    model="test-model",
                    open_browser=False,
                )
            )

    assert result == answers


def test_resolve_gaps_passes_profile_to_enrichment_pipeline():
    from maestro.sdlc.gaps_server import resolve_gaps
    from maestro.sdlc.schemas import DiscoveryProfile, GapAnswer, GapItem

    answers_ready = threading.Event()
    answers = [GapAnswer(question="First question?", selected_options=["Yes"], free_text="")]
    profile = DiscoveryProfile(
        audience_level="developer",
        question_style="technical",
        discovery_preference="suggest",
        language_tone="balanced",
    )

    class FakeServer:
        port = 4315

        def update_enriched_count(self, count: int) -> None:
            del count

        def update_items(self, items: list[GapItem]) -> None:
            del items
            answers_ready.set()

        def get_answers(self, timeout=None):
            del timeout
            answers_ready.wait(1.0)
            return answers

        def stop(self) -> None:
            pass

    async def fake_enrich(
        items,
        provider,
        model,
        context,
        *,
        profile=None,
        max_concurrent=3,
        on_progress=None,
    ):
        del items, provider, model, context, max_concurrent, on_progress
        assert profile == profile_obj
        return [GapItem(question="First question?", options=["Enriched"], selection_mode="single")]

    profile_obj = profile

    with patch("maestro.sdlc.gaps_server.serve_gaps", return_value=FakeServer()):
        with patch("maestro.sdlc.gaps_server.enrich_gap_items", new=AsyncMock(side_effect=fake_enrich)):
            result = asyncio.run(
                resolve_gaps(
                    "[GAP] First question?\n",
                    provider=object(),
                    model="test-model",
                    open_browser=False,
                    profile=profile,
                )
            )

    assert result == answers


def test_resolve_gaps_parseable_invalid_json_uses_fallback_items():
    from maestro.sdlc.gaps_server import resolve_gaps
    from maestro.sdlc.schemas import GapAnswer, GapItem

    answers_ready = threading.Event()
    served_items: list[GapItem] = []
    final_items: list[GapItem] = []
    answers = [GapAnswer(question="Is mobile app required?", selected_options=["Fallback final"], free_text="")]

    class InvalidShapeProvider:
        async def stream(self, messages, model=None, **kw):
            del messages, model, kw
            yield type(
                "Msg",
                (),
                {
                    "content": (
                        '{"selection_mode":"banana","options":"yes","recommended_options":"no",'
                        '"allow_free_text":"maybe","free_text_placeholder":123}'
                    ),
                    "tool_calls": None,
                },
            )()

    class FakeServer:
        port = 4314

        def update_enriched_count(self, count: int) -> None:
            del count

        def update_items(self, items: list[GapItem]) -> None:
            final_items[:] = items
            answers_ready.set()

        def get_answers(self, timeout=None):
            del timeout
            answers_ready.wait(1.0)
            return answers

        def stop(self) -> None:
            pass

    def fake_heuristic(item: GapItem) -> GapItem:
        option = "Fallback initial" if not served_items else "Fallback final"
        return GapItem(question=item.question, options=[option], selection_mode="single")

    def fake_serve(items, port=4041):
        del port
        served_items[:] = items
        return FakeServer()

    with patch("maestro.sdlc.gaps_server.serve_gaps", side_effect=fake_serve):
        with patch("maestro.sdlc.gaps_server._heuristic_enrich", side_effect=fake_heuristic):
            result = asyncio.run(
                resolve_gaps(
                    "[GAP] Is mobile app required?\n",
                    provider=InvalidShapeProvider(),
                    model="test-model",
                    open_browser=False,
                )
            )

    assert [item.options for item in served_items] == [["Fallback initial"]]
    assert [item.options for item in final_items] == [["Fallback final"]]
    assert result == answers


def test_gap_helper_functions_cover_remaining_edge_cases() -> None:
    from maestro.sdlc.gaps_server import (
        _extract_inline_alternatives,
        _extract_paren_alternatives,
        _infer_options,
        _is_portuguese_hint,
        _match_choice_word,
        _sanitize_gap_question,
        _selected_options_from_answer_payload,
        _split_choice_alternatives,
        _validate_llm_enrichment,
        parse_gaps,
    )

    assert parse_gaps("[GAP] ;:-\n") == []
    assert _extract_paren_alternatives("No inline hints here") == []
    assert _extract_paren_alternatives("Only one (manual)") == []
    assert _extract_paren_alternatives("Modo (manual ou automatico)?") == [
        "manual",
        "automatico",
        "Needs discussion",
        "Not applicable",
    ]
    assert _split_choice_alternatives("manual/automatico ou ambos") == [
        "manual",
        "automatico ",
        "ambos",
    ]
    assert _match_choice_word("wordor word", "wordor word", 4) is None
    assert _match_choice_word("a or!", "a or!", 2) is None
    assert _sanitize_gap_question("[GAP] [HYPOTHESIS] Qual? Se quiser, posso ajudar.") == "Qual?"
    assert _extract_inline_alternatives("Modes: manual, automatico, ambos?") == [
        "manual",
        "automatico",
        "ambos",
    ]
    assert _extract_inline_alternatives("Only one option") == []
    assert _is_portuguese_hint("") is False
    assert _is_portuguese_hint("portuguese") is True
    assert _infer_options("Expected monthly active user count scale") == [
        "< 1,000 / month",
        "1,000-100,000 / month",
        "> 100,000 / month",
        "Unknown / TBD",
    ]
    assert _infer_options("Target audience for initial release") == [
        "B2C consumers",
        "B2B companies",
        "Internal teams",
        "Mixed / TBD",
    ]
    assert _selected_options_from_answer_payload({"chosen_option": "REST"}) == ["REST"]
    with pytest.raises(ValueError):
        _selected_options_from_answer_payload({"selected_options": []})

    with pytest.raises(ValueError, match="invalid allow_free_text"):
        _validate_llm_enrichment(
            {
                "selection_mode": "single",
                "options": ["Yes", "No", "Maybe"],
                "allow_free_text": "yes",
            }
        )
    with pytest.raises(ValueError, match="invalid free_text_placeholder"):
        _validate_llm_enrichment(
            {
                "selection_mode": "single",
                "options": ["Yes", "No", "Maybe"],
                "allow_free_text": True,
                "free_text_placeholder": 1,
            }
        )
    with pytest.raises(ValueError, match="invalid display_question"):
        _validate_llm_enrichment(
            {
                "selection_mode": "single",
                "options": ["Yes", "No", "Maybe"],
                "display_question": 1,
            }
        )
    with pytest.raises(ValueError, match="invalid help_text"):
        _validate_llm_enrichment(
            {
                "selection_mode": "single",
                "options": ["Yes", "No", "Maybe"],
                "help_text": 1,
            }
        )
    assert _selected_options_from_answer_payload(
        {"selected_options": [""], "chosen_option": "REST"}
    ) == ["REST"]


def test_infer_options_paren_and_validation_type_errors() -> None:
    from maestro.sdlc import gaps_server

    with patch.object(gaps_server, "_extract_inline_alternatives", return_value=[]), patch.object(
        gaps_server,
        "_extract_paren_alternatives",
        return_value=["manual", "automatico", "Needs discussion", "Not applicable"],
    ):
        assert gaps_server._infer_options("Any question") == [
            "manual",
            "automatico",
            "Needs discussion",
            "Not applicable",
        ]

    with patch.object(gaps_server, "_extract_inline_alternatives", return_value=[]), patch.object(
        gaps_server, "_extract_paren_alternatives", return_value=[]
    ):
        with pytest.raises(ValueError, match="invalid allow_free_text"):
            gaps_server._validate_llm_enrichment(
                {
                    "selection_mode": "single",
                    "options": ["Yes", "No", "Maybe"],
                    "allow_free_text": "yes",
                }
            )
        with pytest.raises(ValueError, match="invalid free_text_placeholder"):
            gaps_server._validate_llm_enrichment(
                {
                    "selection_mode": "single",
                    "options": ["Yes", "No", "Maybe"],
                    "allow_free_text": True,
                    "free_text_placeholder": 1,
                }
            )
        with pytest.raises(ValueError, match="invalid display_question"):
            gaps_server._validate_llm_enrichment(
                {
                    "selection_mode": "single",
                    "options": ["Yes", "No", "Maybe"],
                    "display_question": 1,
                }
            )
        with pytest.raises(ValueError, match="invalid help_text"):
            gaps_server._validate_llm_enrichment(
                {
                    "selection_mode": "single",
                    "options": ["Yes", "No", "Maybe"],
                    "help_text": 1,
                }
            )


def test_profile_and_gap_dispatch_helpers_cover_error_paths() -> None:
    from maestro.sdlc.gaps_server import (
        _build_gaps_status_payload,
        _dispatch_gaps_get,
        _dispatch_gaps_post,
        _dispatch_profile_get,
        _dispatch_profile_post,
        _parse_gap_answers,
        _parse_profile_submission,
        _read_request_body,
        _send_json_response,
        _serve_static_html,
        build_discovery_profile_questions,
    )
    from maestro.sdlc.schemas import GapItem

    class FakeHandler:
        def __init__(self, path="/", body=b"", headers=None):
            self.path = path
            self.headers = headers or {}
            self.rfile = io.BytesIO(body)
            self.wfile = io.BytesIO()
            self.responses = []
            self.server_ref = SimpleNamespace(
                _questions=build_discovery_profile_questions("en"),
                _items=[GapItem(question="Is SSO required?", options=["Yes", "No"])],
                _enrich_ready=False,
                _enriched_count=0,
                _event=threading.Event(),
                _profile=None,
                _answers=None,
            )
            self.allowed_values = {
                question.key: {option.value for option in question.options}
                for question in self.server_ref._questions
            }

        def send_response(self, status):
            self.responses.append(("status", status))

        def send_header(self, name, value):
            self.responses.append((name, value))

        def end_headers(self):
            self.responses.append(("end", None))

        def send_error(self, status, message=None):
            self.responses.append(("error", status, message))

    json_handler = FakeHandler()
    _send_json_response(json_handler, {"ok": True})
    assert ("Content-Type", "application/json") in json_handler.responses
    assert json.loads(json_handler.wfile.getvalue()) == {"ok": True}

    html_handler = FakeHandler()
    _serve_static_html(html_handler, "profile.html")
    assert ("status", 200) in html_handler.responses

    missing_html_handler = FakeHandler()
    _serve_static_html(missing_html_handler, "missing-file.html")
    assert ("error", 404, "missing-file.html not found") in missing_html_handler.responses

    body_handler = FakeHandler(body=b"abc", headers={"Content-Length": "3"})
    assert _read_request_body(body_handler) == b"abc"

    questions_handler = FakeHandler(path="/profile/questions")
    _dispatch_profile_get(questions_handler)
    assert json.loads(questions_handler.wfile.getvalue())[0]["key"] == "audience_level"

    root_handler = FakeHandler(path="/")
    _dispatch_profile_get(root_handler)
    assert ("status", 200) in root_handler.responses

    missing_profile_handler = FakeHandler(path="/missing")
    _dispatch_profile_get(missing_profile_handler)
    assert ("error", 404, None) in missing_profile_handler.responses

    invalid_profile_path = FakeHandler(path="/other")
    _dispatch_profile_post(invalid_profile_path)
    assert ("error", 404, None) in invalid_profile_path.responses

    invalid_profile_json = FakeHandler(
        path="/profile/answers",
        body=b"{}",
        headers={"Content-Length": "2"},
    )
    _dispatch_profile_post(invalid_profile_json)
    assert ("error", 400, "Invalid JSON") in invalid_profile_json.responses

    gaps_root_handler = FakeHandler(path="/")
    _dispatch_gaps_get(gaps_root_handler)
    assert ("status", 200) in gaps_root_handler.responses

    gaps_handler = FakeHandler(path="/gaps")
    _dispatch_gaps_get(gaps_handler)
    assert json.loads(gaps_handler.wfile.getvalue())[0]["question"] == "Is SSO required?"

    status_handler = FakeHandler(path="/gaps/status")
    _dispatch_gaps_get(status_handler)
    assert json.loads(status_handler.wfile.getvalue()) == {
        "ready": False,
        "enriched": 0,
        "total": 1,
    }

    missing_gaps_handler = FakeHandler(path="/nope")
    _dispatch_gaps_get(missing_gaps_handler)
    assert ("error", 404, None) in missing_gaps_handler.responses

    invalid_gap_path = FakeHandler(path="/other")
    _dispatch_gaps_post(invalid_gap_path)
    assert ("error", 404, None) in invalid_gap_path.responses

    invalid_gap_json = FakeHandler(
        path="/answers",
        body=b"[{}]",
        headers={"Content-Length": "4"},
    )
    _dispatch_gaps_post(invalid_gap_json)
    assert ("error", 400, "Invalid JSON") in invalid_gap_json.responses

    answers_payload = json.dumps(
        [{"question": "Q1", "selected_options": ["Yes"], "free_text": ""}]
    ).encode()
    valid_gap_json = FakeHandler(
        path="/answers",
        body=answers_payload,
        headers={"Content-Length": str(len(answers_payload))},
    )
    _dispatch_gaps_post(valid_gap_json)
    assert valid_gap_json.server_ref._answers[0].selected_options == ["Yes"]

    with pytest.raises(ValueError, match="payload must be an object"):
        _parse_profile_submission(b"[]", valid_gap_json.allowed_values)
    with pytest.raises(ValueError, match="invalid audience_level"):
        _parse_profile_submission(
            json.dumps(
                {
                    "audience_level": "bad",
                    "question_style": "simple",
                    "discovery_preference": "ask_more",
                    "language_tone": "simple",
                }
            ).encode(),
            valid_gap_json.allowed_values,
        )
    with pytest.raises(ValueError):
        _parse_gap_answers(json.dumps([{"question": "Q1", "chosen_option": ""}]).encode())

    status = _build_gaps_status_payload(valid_gap_json.server_ref)
    assert status == {"ready": False, "enriched": 0, "total": 1}


def test_profile_server_gaps_server_and_resolvers_cover_remaining_lines() -> None:
    from maestro.sdlc.gaps_server import (
        GapsServer,
        ProfileServer,
        resolve_discovery_profile,
        resolve_gaps,
        serve_gaps,
    )
    from maestro.sdlc.schemas import DiscoveryProfile, GapItem

    profile_server = ProfileServer([], port=0)
    with pytest.raises(RuntimeError, match="Server not started"):
        _ = profile_server.port

    gaps_server = GapsServer([GapItem(question="Q1", options=["Yes", "No"])], port=0)
    with pytest.raises(RuntimeError, match="Server not started"):
        _ = gaps_server.port
    gaps_server.update_enriched_count(2)
    gaps_server.update_items([GapItem(question="Q1", options=["A", "B"])])
    assert gaps_server._enriched_count == 1
    assert gaps_server._enrich_ready is True
    served = serve_gaps([GapItem(question="Q1", options=["Yes", "No"])], port=0)
    served.stop()

    submitted_profile = DiscoveryProfile(
        audience_level="developer",
        question_style="technical",
        discovery_preference="suggest",
        language_tone="balanced",
    )

    class FakeProfileServer:
        def __init__(self, questions, port):
            del questions, port
            self.port = 4321

        def start(self):
            return None

        def get_profile(self, timeout=None):
            del timeout
            return submitted_profile

        def stop(self):
            return None

    with (
        patch("maestro.sdlc.gaps_server.ProfileServer", FakeProfileServer),
        patch("maestro.sdlc.gaps_server.webbrowser.open") as mock_open,
    ):
        assert resolve_discovery_profile("pt-BR", open_browser=True) == submitted_profile
    mock_open.assert_called_once_with("http://localhost:4321")

    class FakeEmptyProfileServer(FakeProfileServer):
        def get_profile(self, timeout=None):
            del timeout
            return None

    with patch("maestro.sdlc.gaps_server.ProfileServer", FakeEmptyProfileServer):
        with pytest.raises(RuntimeError, match="Profile not submitted"):
            resolve_discovery_profile("en", open_browser=False)

    assert asyncio.run(resolve_gaps("No gaps here", open_browser=False)) == []

    stopped = threading.Event()

    class FakeAnswerServer:
        port = 4444

        def update_enriched_count(self, count: int) -> None:
            del count

        def update_items(self, items):
            del items

        def get_answers(self, timeout=None):
            del timeout
            return None

        def stop(self) -> None:
            stopped.set()

    async def fake_enrich(*args, **kwargs):
        await asyncio.sleep(0)
        return [GapItem(question="Q1", options=["Yes", "No"], selection_mode="single")]

    with (
        patch("maestro.sdlc.gaps_server.serve_gaps", return_value=FakeAnswerServer()),
        patch("maestro.sdlc.gaps_server.enrich_gap_items", new=AsyncMock(side_effect=fake_enrich)),
        patch("maestro.sdlc.gaps_server.webbrowser.open") as mock_open,
    ):
        assert asyncio.run(resolve_gaps("[GAP] Q1\n", open_browser=True)) == []
    mock_open.assert_called_once_with("http://localhost:4444")
    assert stopped.is_set()


def test_harness_setup_spec_dir_raises_runtime_error(tmp_path):
    from maestro.sdlc.harness import DiscoveryHarness
    from maestro.sdlc.schemas import SDLCRequest

    harness = DiscoveryHarness(workdir=str(tmp_path))

    with patch("pathlib.Path.mkdir", side_effect=PermissionError(13, "Permission denied")):
        with pytest.raises(RuntimeError, match="Failed to create spec directory"):
            harness._setup_spec_dir(SDLCRequest("Build X", workdir=str(tmp_path)))


@pytest.mark.asyncio
async def test_harness_run_gate_auto_passes_without_provider() -> None:
    from maestro.sdlc.harness import DiscoveryHarness

    gate = await DiscoveryHarness()._run_gate(3, [], [])

    assert gate.passed is True
    assert gate.sprint_id == 3


def test_harness_resolve_gaps_retries_without_profile_keyword(tmp_path):
    from maestro.sdlc.harness import DiscoveryHarness
    from maestro.sdlc.schemas import ArtifactType, GapAnswer, SDLCArtifact, SDLCRequest

    harness = DiscoveryHarness(provider=object(), model="test", open_browser=False)
    request = SDLCRequest("Build X", workdir=str(tmp_path))
    artifact = SDLCArtifact(ArtifactType.GAPS, "03-gaps.md", "[GAP] Is SSO required?")

    async def fake_resolve_gaps(*args, **kwargs):
        del args
        if "profile" in kwargs:
            raise TypeError("unexpected keyword argument 'profile'")
        return [GapAnswer(question="Is SSO required?", selected_options=["Yes"])]

    with patch("maestro.sdlc.harness.resolve_discovery_profile", return_value=SimpleNamespace()):
        with patch("maestro.sdlc.harness.resolve_gaps", new=AsyncMock(side_effect=fake_resolve_gaps)) as mock_resolve:
            updated = asyncio.run(harness._resolve_gaps(request, artifact))

    assert "## Gap Answers" in updated.prompt
    assert mock_resolve.await_count == 2


def test_harness_resolve_gaps_reraises_unrelated_type_error(tmp_path):
    from maestro.sdlc.harness import DiscoveryHarness
    from maestro.sdlc.schemas import ArtifactType, SDLCArtifact, SDLCRequest

    harness = DiscoveryHarness(provider=object(), model="test", open_browser=False)
    request = SDLCRequest("Build X", workdir=str(tmp_path))
    artifact = SDLCArtifact(ArtifactType.GAPS, "03-gaps.md", "[GAP] Is SSO required?")

    with patch("maestro.sdlc.harness.resolve_discovery_profile", return_value=SimpleNamespace()):
        with patch(
            "maestro.sdlc.harness.resolve_gaps",
            new=AsyncMock(side_effect=TypeError("different type error")),
        ):
            with pytest.raises(TypeError, match="different type error"):
                asyncio.run(harness._resolve_gaps(request, artifact))


def test_harness_scan_codebase_lists_python_files(tmp_path):
    from maestro.sdlc.harness import DiscoveryHarness

    (tmp_path / "b.py").write_text("print('b')", encoding="utf-8")
    (tmp_path / "a.py").write_text("print('a')", encoding="utf-8")
    (tmp_path / "notes.txt").write_text("ignore", encoding="utf-8")

    scan = DiscoveryHarness()._scan_codebase(str(tmp_path))

    assert scan == "a.py\nb.py"


# ── Profile-based gap filtering ──────────────────────────────────────


def test_is_technical_gap_detects_implementation_questions() -> None:
    from maestro.sdlc.gaps_server import _is_technical_gap

    assert _is_technical_gap("Which database should we use?")
    assert _is_technical_gap("Should we deploy with Docker?")
    assert _is_technical_gap("What caching strategy to use?")
    assert _is_technical_gap("Do we need a message queue?")
    assert _is_technical_gap("What testing framework?")
    assert _is_technical_gap("Should we use Kubernetes?")


def test_is_technical_gap_does_not_flag_business_questions() -> None:
    from maestro.sdlc.gaps_server import _is_technical_gap

    assert not _is_technical_gap("What is the target audience?")
    assert not _is_technical_gap("Which features are most important?")
    assert not _is_technical_gap("Should users receive email notifications?")
    assert not _is_technical_gap("What roles should exist?")
    assert not _is_technical_gap("How should the checkout flow work?")


def test_filter_gaps_by_profile_non_technical_removes_technical_gaps() -> None:
    from maestro.sdlc.gaps_server import _filter_gaps_by_profile
    from maestro.sdlc.schemas import DiscoveryProfile, GapItem

    profile = DiscoveryProfile(
        audience_level="non_technical",
        question_style="simple",
        discovery_preference="decide_when_needed",
        language_tone="simple",
    )

    items = [
        GapItem(question="What is the target audience?", options=["B2C", "B2B"]),
        GapItem(question="Which database should we use?", options=["Postgres", "MySQL"]),
        GapItem(question="Should users receive email notifications?", options=["Yes", "No"]),
        GapItem(question="What caching strategy to use?", options=["Redis", "None"]),
    ]

    visible, auto_answered = _filter_gaps_by_profile(items, profile)

    assert len(visible) == 2
    assert visible[0].question == "What is the target audience?"
    assert visible[1].question == "Should users receive email notifications?"
    assert len(auto_answered) == 2
    assert auto_answered[0].question == "Which database should we use?"
    assert auto_answered[1].question == "What caching strategy to use?"


def test_filter_gaps_by_profile_architect_keeps_all_gaps() -> None:
    from maestro.sdlc.gaps_server import _filter_gaps_by_profile
    from maestro.sdlc.schemas import DiscoveryProfile, GapItem

    profile = DiscoveryProfile(
        audience_level="architect",
        question_style="technical",
        discovery_preference="ask_more",
        language_tone="technical",
    )

    items = [
        GapItem(question="What is the target audience?", options=["B2C", "B2B"]),
        GapItem(question="Which database should we use?", options=["Postgres", "MySQL"]),
        GapItem(question="Should we use Kubernetes?", options=["Yes", "No"]),
    ]

    visible, auto_answered = _filter_gaps_by_profile(items, profile)

    assert len(visible) == 3
    assert auto_answered == []


def test_filter_gaps_by_profile_software_familiar_filters_deep_tech_only() -> None:
    from maestro.sdlc.gaps_server import _filter_gaps_by_profile
    from maestro.sdlc.schemas import DiscoveryProfile, GapItem

    profile = DiscoveryProfile(
        audience_level="software_familiar",
        question_style="functional",
        discovery_preference="suggest",
        language_tone="balanced",
    )

    items = [
        GapItem(question="What is the target audience?", options=["B2C", "B2B"]),
        GapItem(question="Which database should we use?", options=["Postgres", "MySQL"]),
        GapItem(question="What caching strategy to use?", options=["Redis", "None"]),
    ]

    visible, auto_answered = _filter_gaps_by_profile(items, profile)

    # software_familiar: keep db choice (fundamental tech), skip caching (deep infra)
    assert len(visible) == 2
    assert visible[0].question == "What is the target audience?"
    assert visible[1].question == "Which database should we use?"
    assert len(auto_answered) == 1
    assert auto_answered[0].question == "What caching strategy to use?"


def test_filter_gaps_returns_empty_when_no_items() -> None:
    from maestro.sdlc.gaps_server import _filter_gaps_by_profile
    from maestro.sdlc.schemas import DiscoveryProfile

    profile = DiscoveryProfile(
        audience_level="non_technical",
        question_style="simple",
        discovery_preference="decide_when_needed",
        language_tone="simple",
    )

    visible, auto_answered = _filter_gaps_by_profile([], profile)
    assert visible == []
    assert auto_answered == []


def test_filter_gaps_profile_none_keeps_all() -> None:
    from maestro.sdlc.gaps_server import _filter_gaps_by_profile
    from maestro.sdlc.schemas import GapItem

    items = [
        GapItem(question="Which database should we use?", options=["Postgres", "MySQL"]),
        GapItem(question="What is the target audience?", options=["B2C", "B2B"]),
    ]

    visible, auto_answered = _filter_gaps_by_profile(items, None)
    assert len(visible) == 2
    assert auto_answered == []


def test_auto_answer_gaps_uses_recommended_options() -> None:
    from maestro.sdlc.gaps_server import _auto_answer_gaps
    from maestro.sdlc.schemas import GapItem

    auto_gaps = [
        GapItem(
            question="Which database should we use?",
            options=["Postgres", "MySQL", "MongoDB"],
            recommended_options=["Postgres"],
            recommended_index=0,
        ),
        GapItem(
            question="What caching strategy to use?",
            options=["Redis", "Memcached", "None"],
            recommended_options=[],
            recommended_index=0,
        ),
    ]

    answers = _auto_answer_gaps(auto_gaps)

    assert len(answers) == 2
    assert answers[0].question == "Which database should we use?"
    assert answers[0].selected_options == ["Postgres"]
    assert answers[1].question == "What caching strategy to use?"
    assert answers[1].selected_options == ["Not applicable"]


def test_auto_answer_gaps_empty_list() -> None:
    from maestro.sdlc.gaps_server import _auto_answer_gaps

    assert _auto_answer_gaps([]) == []


def test_filter_gaps_developer_keeps_all_but_auto_answers_deep_infra() -> None:
    from maestro.sdlc.gaps_server import _filter_gaps_by_profile
    from maestro.sdlc.schemas import DiscoveryProfile, GapItem

    profile = DiscoveryProfile(
        audience_level="developer",
        question_style="technical",
        discovery_preference="ask_more",
        language_tone="balanced",
    )

    items = [
        GapItem(question="What is the target audience?", options=["B2C", "B2B"]),
        GapItem(question="Which database should we use?", options=["Postgres", "MySQL"]),
        GapItem(question="Should we use Kubernetes?", options=["Yes", "No"]),
    ]

    visible, auto_answered = _filter_gaps_by_profile(items, profile)

    # developer keeps all, no auto-answer (ask_more)
    assert len(visible) == 3
    assert auto_answered == []


def test_resolve_gaps_filters_with_profile_non_technical() -> None:
    """Integration: resolve_gaps filters technical gaps when profile is non_technical."""
    from unittest.mock import AsyncMock, MagicMock, patch

    from maestro.sdlc.gaps_server import GapAnswer, resolve_gaps
    from maestro.sdlc.schemas import DiscoveryProfile

    profile = DiscoveryProfile(
        audience_level="non_technical",
        question_style="simple",
        discovery_preference="decide_when_needed",
        language_tone="simple",
    )

    gaps_md = (
        "[GAP] What is the target audience?\n"
        "[GAP] Which database should we use?\n"
    )

    fake_server = MagicMock()
    fake_server.port = 12345
    fake_server.get_answers = lambda timeout=None: [
        GapAnswer(question="What is the target audience?", selected_options=["B2C"]),
    ]

    async def _run_resolve():
        with (
            patch("maestro.sdlc.gaps_server.serve_gaps", return_value=fake_server),
            patch("maestro.sdlc.gaps_server.webbrowser.open"),
            patch("maestro.sdlc.gaps_server._heuristic_enrich", side_effect=lambda item: item),
            patch("maestro.sdlc.gaps_server.enrich_gap_items", new=AsyncMock(return_value=[])),
        ):
            return await resolve_gaps(gaps_md, profile=profile, open_browser=False)

    answers = asyncio.run(_run_resolve())

    assert len(answers) == 2
    questions = {a.question for a in answers}
    assert "What is the target audience?" in questions
    assert "Which database should we use?" in questions

    user_answer = next(a for a in answers if a.question == "What is the target audience?")
    assert user_answer.selected_options == ["B2C"]

    auto_answer = next(a for a in answers if a.question == "Which database should we use?")
    assert auto_answer.selected_options == ["Not applicable"]


def test_resolve_gaps_no_profile_keeps_all() -> None:
    """Integration: resolve_gaps without profile shows all gaps (backward-compat)."""
    from unittest.mock import AsyncMock, MagicMock, patch

    from maestro.sdlc.gaps_server import GapAnswer, resolve_gaps

    gaps_md = "[GAP] Which database should we use?\n[GAP] What is the audience?\n"

    fake_server = MagicMock()
    fake_server.port = 12345
    fake_server.get_answers = lambda timeout=None: [
        GapAnswer(question="Which database should we use?", selected_options=["Postgres"]),
        GapAnswer(question="What is the audience?", selected_options=["B2C"]),
    ]

    async def _run_resolve():
        with (
            patch("maestro.sdlc.gaps_server.serve_gaps", return_value=fake_server),
            patch("maestro.sdlc.gaps_server.webbrowser.open"),
            patch("maestro.sdlc.gaps_server._heuristic_enrich", side_effect=lambda item: item),
            patch("maestro.sdlc.gaps_server.enrich_gap_items", new=AsyncMock(return_value=[])),
        ):
            return await resolve_gaps(gaps_md, open_browser=False)

    answers = asyncio.run(_run_resolve())

    assert len(answers) == 2
    assert {a.question for a in answers} == {
        "Which database should we use?",
        "What is the audience?",
    }


def test_resolve_gaps_architect_gets_all_gaps() -> None:
    """Integration: resolve_gaps with architect profile keeps all gaps."""
    from unittest.mock import AsyncMock, MagicMock, patch

    from maestro.sdlc.gaps_server import GapAnswer, resolve_gaps
    from maestro.sdlc.schemas import DiscoveryProfile

    profile = DiscoveryProfile(
        audience_level="architect",
        question_style="technical",
        discovery_preference="ask_more",
        language_tone="technical",
    )

    gaps_md = "[GAP] Should we use Kubernetes?\n[GAP] What is the audience?\n"

    fake_server = MagicMock()
    fake_server.port = 12345
    fake_server.get_answers = lambda timeout=None: [
        GapAnswer(question="Should we use Kubernetes?", selected_options=["Yes"]),
        GapAnswer(question="What is the audience?", selected_options=["B2C"]),
    ]

    async def _run_resolve():
        with (
            patch("maestro.sdlc.gaps_server.serve_gaps", return_value=fake_server),
            patch("maestro.sdlc.gaps_server.webbrowser.open"),
            patch("maestro.sdlc.gaps_server._heuristic_enrich", side_effect=lambda item: item),
            patch("maestro.sdlc.gaps_server.enrich_gap_items", new=AsyncMock(return_value=[])),
        ):
            return await resolve_gaps(gaps_md, profile=profile, open_browser=False)

    answers = asyncio.run(_run_resolve())

    assert len(answers) == 2
    assert {a.question for a in answers} == {
        "Should we use Kubernetes?",
        "What is the audience?",
    }
