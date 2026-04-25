"""Tests for the gaps server - parser and server round-trip."""
from __future__ import annotations

import asyncio
import json
import threading
import time
import urllib.error
import urllib.request
from unittest.mock import AsyncMock, patch


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
    from maestro.sdlc.schemas import GapItem

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

    async def fake_enrich(items, provider, model, context, *, max_concurrent=3, on_progress=None):
        del provider, model, context
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

    async def fake_enrich(items, provider, model, context, *, max_concurrent=3, on_progress=None):
        del items, provider, model, max_concurrent, on_progress
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
