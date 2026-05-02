from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import Mock, patch

import httpx
import pytest

from maestro import auth
from maestro.providers.base import Message, Tool, ToolCall
from maestro.providers.chatgpt import (
    FALLBACK_MODELS,
    ChatGPTProvider,
    _append_text_delta,
    _build_stream_payload,
    _cache_path,
    _collect_done_message_text,
    _collect_function_call,
    _convert_messages_to_input,
    _convert_tools_to_schemas,
    _dispatch_chatgpt_event,
    _extract_instructions,
    _extract_output_text,
    _headers,
    _iter_sse_data_lines,
    _message_to_input_items,
    _parse_tool_call,
    _read_cache,
    _reasoning_effort,
    _stream_chatgpt_response,
    _write_cache,
    fetch_models,
    probe_available_models,
    resolve_model,
)
from maestro.providers.copilot import (
    COPILOT_API_BASE,
    POLLING_SAFETY_MARGIN,
    CopilotProvider,
    _build_final_message,
    _collect_list_models,
    _convert_messages_to_wire,
    _convert_tools_to_wire,
    _extract_model_ids,
    _handle_poll_response,
    _parse_sse_event,
    _process_copilot_sse,
)


class FakeChatGPTStreamResponse:
    def __init__(self, *, lines: list[str] | None = None, is_success: bool = True, status_code: int = 200, body: bytes = b"") -> None:
        self._lines = lines or []
        self.is_success = is_success
        self.status_code = status_code
        self._body = body

    async def __aenter__(self) -> FakeChatGPTStreamResponse:
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None

    async def aiter_lines(self):
        for line in self._lines:
            yield line

    async def aread(self) -> bytes:
        return self._body


class FakeChatGPTAsyncClient:
    def __init__(self, response: FakeChatGPTStreamResponse | None = None, error: Exception | None = None) -> None:
        self.response = response
        self.error = error
        self.calls: list[dict] = []

    async def __aenter__(self) -> FakeChatGPTAsyncClient:
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None

    def stream(self, method: str, url: str, **kwargs):
        self.calls.append({"method": method, "url": url, **kwargs})
        if self.error is not None:
            raise self.error
        assert self.response is not None
        return self.response


class FakeSSE:
    def __init__(self, data: str) -> None:
        self.data = data


class FakeAsyncClientContext:
    async def __aenter__(self) -> FakeAsyncClientContext:
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None


class FakeCopilotEventSource:
    def __init__(self, events: list[FakeSSE], response: SimpleNamespace | None = None) -> None:
        self._events = events
        self.response = response or SimpleNamespace(is_success=True, status_code=200)

    async def __aenter__(self) -> FakeCopilotEventSource:
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None

    async def aiter_sse(self):
        for event in self._events:
            yield event


class FakeCopilotResponse:
    def __init__(self, *, is_success: bool = True, status_code: int = 200, body: bytes = b"", json_data=None) -> None:
        self.is_success = is_success
        self.status_code = status_code
        self._body = body
        self._json_data = json_data

    def raise_for_status(self) -> None:
        if not self.is_success:
            raise httpx.HTTPStatusError("bad response", request=Mock(), response=Mock(status_code=self.status_code))

    def json(self):
        return self._json_data

    async def aread(self) -> bytes:
        return self._body


def _sample_messages() -> list[Message]:
    return [
        Message(role="system", content="Follow the schema."),
        Message(role="user", content="Hello"),
        Message(
            role="assistant",
            content="Calling tool",
            tool_calls=[ToolCall(id="call-1", name="lookup", arguments={"q": "abc"})],
        ),
        Message(role="tool", content='{"ok": true}', tool_call_id="call-1"),
    ]


def _sample_tool() -> Tool:
    return Tool(
        name="lookup",
        description="Look up data",
        parameters={"type": "object", "properties": {"q": {"type": "string"}}},
    )


def test_chatgpt_resolve_model_handles_aliases() -> None:
    assert resolve_model("gpt-5") == "gpt-5.4"
    assert resolve_model("codex-mini-latest") == "gpt-5.1-codex-mini"
    assert resolve_model("custom-model") == "custom-model"


def test_chatgpt_fetch_models_uses_cache_and_fallbacks(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    import maestro.providers.chatgpt as chatgpt

    monkeypatch.setattr(chatgpt, "_CACHE_DIR", tmp_path)
    _write_cache(["cached-model"])
    assert _read_cache() == ["cached-model"]
    assert fetch_models() == ["cached-model"]

    _cache_path().write_text("not-json")
    assert _read_cache() is None

    stale = json.dumps({"ts": 0, "models": ["stale"]})
    _cache_path().write_text(stale)
    assert _read_cache() is None

    with patch("maestro.providers.chatgpt.httpx.get", side_effect=RuntimeError("boom")):
        assert fetch_models(force=True) == FALLBACK_MODELS


def test_chatgpt_cache_helpers_ignore_os_errors(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    import maestro.providers.chatgpt as chatgpt

    monkeypatch.setattr(chatgpt, "_CACHE_DIR", tmp_path)

    with patch("pathlib.Path.read_text", side_effect=OSError("boom")):
        assert _read_cache() is None

    with patch("pathlib.Path.write_text", side_effect=OSError("boom")):
        _write_cache(["x"])


def test_chatgpt_fetch_models_filters_http_catalog_and_handles_empty_result(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    import maestro.providers.chatgpt as chatgpt

    monkeypatch.setattr(chatgpt, "_CACHE_DIR", tmp_path)
    response = Mock()
    response.raise_for_status.return_value = None
    response.json.return_value = {
        "openai": {
            "models": {
                "gpt-5.4": {},
                "gpt-5.1-codex-mini": {},
                "text-embedding-3-small": {},
            }
        }
    }

    with patch("maestro.providers.chatgpt.httpx.get", return_value=response):
        assert fetch_models(force=True) == ["gpt-5.1-codex-mini", "gpt-5.4"]

    response.json.return_value = {"openai": {"models": {"text-embedding-3-small": {}}}}
    with patch("maestro.providers.chatgpt.httpx.get", return_value=response):
        assert fetch_models(force=True) == FALLBACK_MODELS


def test_chatgpt_probe_available_models_uses_cache_and_ignores_runtime_errors(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    import sys
    import types
    import maestro.providers.chatgpt as chatgpt

    monkeypatch.setattr(chatgpt, "_CACHE_DIR", tmp_path)
    available_cache = chatgpt._available_cache_path()
    available_cache.write_text(json.dumps({"ts": 9999999999, "models": ["cached"]}))
    tokens = auth.TokenSet(access="a", refresh="r", expires=9999999999.0)
    assert probe_available_models(tokens, ttl=86400) == ["cached"]

    available_cache.unlink()
    monkeypatch.setitem(
        sys.modules,
        "langchain_core.messages",
        types.SimpleNamespace(HumanMessage=lambda content: {"content": content}),
    )
    monkeypatch.setitem(
        sys.modules,
        "maestro.agent",
        types.SimpleNamespace(
            _call_responses_api=lambda model, msgs, creds: (
                None if model == "gpt-5.4" else (_ for _ in ()).throw(RuntimeError("no"))
            )
        ),
    )

    with patch("maestro.providers.chatgpt.fetch_models", return_value=["gpt-5.4", "bad"]):
        assert probe_available_models(tokens, force=True) == ["gpt-5.4"]


def test_chatgpt_probe_available_models_handles_invalid_cache_and_write_errors(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    import sys
    import types
    import maestro.providers.chatgpt as chatgpt

    monkeypatch.setattr(chatgpt, "_CACHE_DIR", tmp_path)
    chatgpt._available_cache_path().write_text("{")
    monkeypatch.setitem(
        sys.modules,
        "langchain_core.messages",
        types.SimpleNamespace(HumanMessage=lambda content: {"content": content}),
    )
    monkeypatch.setitem(
        sys.modules,
        "maestro.agent",
        types.SimpleNamespace(_call_responses_api=lambda model, msgs, creds: None),
    )
    tokens = auth.TokenSet(access="a", refresh="r", expires=9999999999.0)

    with (
        patch("maestro.providers.chatgpt.fetch_models", return_value=["gpt-5.4"]),
        patch("pathlib.Path.write_text", side_effect=OSError("nope")),
    ):
        assert probe_available_models(tokens, force=False) == ["gpt-5.4"]


def test_chatgpt_message_and_tool_helpers_cover_edge_cases() -> None:
    assistant = Message(
        role="assistant",
        content="hi",
        tool_calls=[ToolCall(id="c1", name="lookup", arguments={"q": "x"})],
    )

    assert _convert_messages_to_input(_sample_messages())[0]["role"] == "user"
    assert _message_to_input_items(assistant)[0]["type"] == "function_call"
    assert _message_to_input_items(Message(role="unknown", content="?")) == []
    assert _convert_tools_to_schemas([_sample_tool()])[0]["type"] == "function"
    assert _extract_instructions([Message(role="user", content="hi")]) is None


def test_chatgpt_parsing_and_dispatch_helpers_cover_remaining_branches() -> None:
    text_parts: list[str] = []
    tool_calls: list[ToolCall] = []

    assert _reasoning_effort("unknown-model") == "medium"
    assert _headers(auth.TokenSet(access="a", refresh="r", expires=1.0))["Authorization"] == "Bearer a"
    assert "chatgpt-account-id" in _headers(
        auth.TokenSet(access="a", refresh="r", expires=1.0, account_id="acct")
    )
    assert _parse_tool_call({"id": "1", "name": "lookup", "arguments": "{"}).arguments == {}
    assert _append_text_delta({"delta": "x"}, text_parts) == "x"
    _collect_function_call({"item": {"type": "message"}}, tool_calls)
    assert tool_calls == []
    assert _extract_output_text({"type": "reasoning"}) is None
    assert _extract_output_text({"type": "message", "content": [{"type": "other"}]}) is None
    assert _collect_done_message_text({"response": {"output": []}}, ["already there"]) is None
    assert _collect_done_message_text(
        {"response": {"output": [{"type": "message", "content": [{"type": "other"}]}]}},
        [],
    ) is None
    assert _dispatch_chatgpt_event({"type": "ignored"}, [], []) is None


@pytest.mark.asyncio
async def test_chatgpt_iter_sse_data_lines_yields_trailing_data_without_blank() -> None:
    response = FakeChatGPTStreamResponse(lines=["data: partial"])

    result = [line async for line in _iter_sse_data_lines(response)]

    assert result == ["partial"]


def test_chatgpt_build_stream_payload_includes_reasoning_and_response_format() -> None:
    payload = _build_stream_payload(
        "gpt-5.4",
        [{"type": "message", "role": "user", "content": [{"type": "input_text", "text": "hi"}]}],
        [{"type": "function", "name": "lookup", "description": "Look up data", "parameters": {}}],
        None,
        {"response_format": {"type": "json_schema"}},
    )

    assert payload["model"] == "gpt-5.4"
    assert payload["instructions"] == "You are a helpful assistant."
    assert payload["stream"] is True
    assert payload["store"] is False
    assert payload["reasoning"] == {"effort": "high", "summary": "auto"}
    assert payload["response_format"] == {"type": "json_schema"}


@pytest.mark.asyncio
async def test_chatgpt_iter_sse_data_lines_collects_multiline_events() -> None:
    response = FakeChatGPTStreamResponse(
        lines=[": keepalive", "data: first", "data: second", "", "data: [DONE]", ""]
    )

    result = [line async for line in _iter_sse_data_lines(response)]

    assert result == ["first\nsecond", "[DONE]"]


def test_chatgpt_dispatch_event_handles_text_delta_and_function_call() -> None:
    text_parts: list[str] = []
    tool_calls: list[ToolCall] = []

    delta = _dispatch_chatgpt_event(
        {"type": "response.output_text.delta", "delta": "Hello"},
        text_parts,
        tool_calls,
    )
    ignored = _dispatch_chatgpt_event(
        {
            "type": "response.output_item.done",
            "item": {
                "type": "function_call",
                "call_id": "call-1",
                "name": "lookup",
                "arguments": '{"q": "hello"}',
            },
        },
        text_parts,
        tool_calls,
    )

    assert delta == "Hello"
    assert ignored is None
    assert text_parts == ["Hello"]
    assert tool_calls == [ToolCall(id="call-1", name="lookup", arguments={"q": "hello"})]


def test_chatgpt_dispatch_event_uses_response_done_when_no_deltas_exist() -> None:
    text_parts: list[str] = []

    result = _dispatch_chatgpt_event(
        {
            "type": "response.done",
            "response": {
                "output": [
                    {"type": "reasoning", "content": []},
                    {
                        "type": "message",
                        "content": [
                            {"type": "output_text", "text": "final answer"},
                        ],
                    },
                ]
            },
        },
        text_parts,
        [],
    )

    assert result == "final answer"
    assert text_parts == ["final answer"]


@pytest.mark.asyncio
async def test_chatgpt_stream_response_dispatches_json_text_function_call_and_done() -> None:
    response = FakeChatGPTStreamResponse(
        lines=[
            "data: not-json",
            "",
            f"data: {json.dumps({'type': 'response.output_text.delta', 'delta': 'Hel'})}",
            "",
            f"data: {json.dumps({'type': 'response.output_text.delta', 'delta': 'lo'})}",
            "",
            "data: " + json.dumps(
                {
                    "type": "response.output_item.done",
                    "item": {
                        "type": "function_call",
                        "call_id": "call-1",
                        "name": "lookup",
                        "arguments": '{"q": "hello"}',
                    },
                }
            ),
            "",
            "data: " + json.dumps(
                {
                    "type": "response.done",
                    "response": {
                        "output": [
                            {
                                "type": "message",
                                "content": [{"type": "output_text", "text": "ignored final"}],
                            }
                        ]
                    },
                }
            ),
            "",
            "data: [DONE]",
            "",
        ]
    )
    client = FakeChatGPTAsyncClient(response=response)
    tokens = auth.TokenSet(access="access", refresh="refresh", expires=9999999999.0)
    text_parts: list[str] = []
    tool_calls: list[ToolCall] = []

    with patch("maestro.providers.chatgpt.httpx.AsyncClient", return_value=client):
        chunks = [
            chunk
            async for chunk in _stream_chatgpt_response({"model": "gpt-5.4"}, tokens, text_parts, tool_calls)
        ]

    assert chunks == ["Hel", "lo"]
    assert text_parts == ["Hel", "lo"]
    assert tool_calls == [ToolCall(id="call-1", name="lookup", arguments={"q": "hello"})]
    assert client.calls[0]["headers"]["Authorization"] == "Bearer access"


@pytest.mark.asyncio
async def test_chatgpt_stream_response_ignores_invalid_json_and_emits_done_text() -> None:
    response = FakeChatGPTStreamResponse(
        lines=[
            "data: {'broken': }",
            "",
            "data: "
            + json.dumps(
                {
                    "type": "response.done",
                    "response": {
                        "output": [
                            {
                                "type": "message",
                                "content": [{"type": "output_text", "text": "final only"}],
                            }
                        ]
                    },
                }
            ),
        ]
    )
    client = FakeChatGPTAsyncClient(response=response)
    tokens = auth.TokenSet(access="access", refresh="refresh", expires=9999999999.0)

    with patch("maestro.providers.chatgpt.httpx.AsyncClient", return_value=client):
        chunks = [chunk async for chunk in _stream_chatgpt_response({"model": "gpt-5.4"}, tokens, [], [])]

    assert chunks == ["final only"]


@pytest.mark.asyncio
async def test_chatgpt_stream_response_raises_runtime_error_on_http_failure() -> None:
    response = FakeChatGPTStreamResponse(is_success=False, status_code=500, body=b"server exploded")
    client = FakeChatGPTAsyncClient(response=response)
    tokens = auth.TokenSet(access="access", refresh="refresh", expires=9999999999.0)

    with patch("maestro.providers.chatgpt.httpx.AsyncClient", return_value=client):
        with pytest.raises(RuntimeError, match="API error 500: server exploded"):
            _ = [
                chunk
                async for chunk in _stream_chatgpt_response({"model": "gpt-5.4"}, tokens, [], [])
            ]


@pytest.mark.asyncio
async def test_chatgpt_stream_response_propagates_timeout_and_connection_errors() -> None:
    timeout_client = FakeChatGPTAsyncClient(error=httpx.TimeoutException("timed out"))
    connect_client = FakeChatGPTAsyncClient(error=httpx.ConnectError("offline"))
    tokens = auth.TokenSet(access="access", refresh="refresh", expires=9999999999.0)

    with patch("maestro.providers.chatgpt.httpx.AsyncClient", return_value=timeout_client):
        with pytest.raises(httpx.TimeoutException):
            _ = [chunk async for chunk in _stream_chatgpt_response({"model": "gpt-5.4"}, tokens, [], [])]

    with patch("maestro.providers.chatgpt.httpx.AsyncClient", return_value=connect_client):
        with pytest.raises(httpx.ConnectError):
            _ = [chunk async for chunk in _stream_chatgpt_response({"model": "gpt-5.4"}, tokens, [], [])]


@pytest.mark.asyncio
async def test_chatgpt_provider_stream_yields_chunks_then_final_message() -> None:
    provider = ChatGPTProvider()
    final_tool_call = ToolCall(id="call-1", name="lookup", arguments={"q": "abc"})

    async def fake_stream_response(payload, tokens, text_parts, tool_calls):
        assert payload["model"] == "gpt-5.4"
        assert payload["instructions"] == "Follow the schema."
        assert payload["tools"][0]["name"] == "lookup"
        assert tokens.access == "fresh"
        text_parts.extend(["Hi", " there"])
        tool_calls.append(final_tool_call)
        yield "Hi"
        yield " there"

    with (
        patch("maestro.providers.chatgpt.auth.get", return_value={"access": "old", "refresh": "r", "expires": 1.0}),
        patch(
            "maestro.providers.chatgpt.auth.ensure_valid",
            return_value=auth.TokenSet(access="fresh", refresh="r", expires=9999999999.0),
        ),
        patch("maestro.providers.chatgpt._stream_chatgpt_response", side_effect=fake_stream_response),
    ):
        outputs = [
            item
            async for item in provider.stream(_sample_messages(), "gpt-5", tools=[_sample_tool()])
        ]

    assert outputs[:-1] == ["Hi", " there"]
    assert outputs[-1] == Message(role="assistant", content="Hi there", tool_calls=[final_tool_call])


@pytest.mark.asyncio
async def test_chatgpt_provider_stream_requires_authentication() -> None:
    provider = ChatGPTProvider()

    with patch("maestro.providers.chatgpt.auth.get", return_value=None):
        with pytest.raises(RuntimeError, match="Not authenticated"):
            _ = [item async for item in provider.stream([Message(role="user", content="hi")], "gpt-5.4")]


def test_chatgpt_provider_metadata_and_auth_helpers() -> None:
    provider = ChatGPTProvider()

    with (
        patch("maestro.providers.chatgpt.fetch_models", return_value=["gpt-5.4"]),
        patch("maestro.providers.chatgpt.auth.login") as mock_login,
        patch("maestro.providers.chatgpt.auth.get", return_value={"access": "x"}),
    ):
        assert provider.id == "chatgpt"
        assert provider.name == "ChatGPT"
        assert provider.list_models() == ["gpt-5.4"]
        assert provider.auth_required() is True
        provider.login("device")
        assert provider.is_authenticated() is True

    mock_login.assert_called_once_with("device")

    with patch("maestro.providers.chatgpt.auth.get", return_value=None):
        assert provider.is_authenticated() is False


def test_copilot_list_models_reads_api_response() -> None:
    provider = CopilotProvider()
    response = FakeCopilotResponse(json_data={"data": [{"id": "gpt-4.1"}, {"name": "o3-mini"}]})

    with (
        patch("maestro.providers.copilot.auth.get", return_value={"access_token": "token"}),
        patch("maestro.providers.copilot.httpx.get", return_value=response) as mock_get,
    ):
        models = provider.list_models()

    assert models == ["gpt-4.1", "o3-mini"]
    assert mock_get.call_args.args[0] == f"{COPILOT_API_BASE}/models"


def test_copilot_list_models_raises_for_missing_auth_and_bad_response() -> None:
    provider = CopilotProvider()

    with patch("maestro.providers.copilot.auth.get", return_value=None):
        with pytest.raises(RuntimeError, match="Not authenticated"):
            provider.list_models()

    with (
        patch("maestro.providers.copilot.auth.get", return_value={"access_token": "token"}),
        patch("maestro.providers.copilot.httpx.get", side_effect=httpx.ConnectError("offline")),
    ):
        with pytest.raises(RuntimeError, match="Failed to fetch models"):
            provider.list_models()


def test_copilot_list_models_rejects_unparseable_response() -> None:
    provider = CopilotProvider()
    response = FakeCopilotResponse(json_data={"models": []})

    with (
        patch("maestro.providers.copilot.auth.get", return_value={"access_token": "token"}),
        patch("maestro.providers.copilot.httpx.get", return_value=response),
    ):
        with pytest.raises(RuntimeError, match="Could not parse model list"):
            provider.list_models()


@pytest.mark.asyncio
async def test_process_copilot_sse_yields_text_and_accumulates_tool_calls() -> None:
    event_source = FakeCopilotEventSource(
        [
            FakeSSE("not-json"),
            FakeSSE(json.dumps({"choices": [{"delta": {"content": "Hel"}, "finish_reason": None}]})),
            FakeSSE(
                json.dumps(
                    {
                        "choices": [
                            {
                                "delta": {
                                    "tool_calls": [
                                        {
                                            "index": 0,
                                            "id": "call-1",
                                            "function": {"name": "lookup", "arguments": '{"q": '},
                                        }
                                    ]
                                },
                                "finish_reason": None,
                            }
                        ]
                    }
                )
            ),
            FakeSSE(
                json.dumps(
                    {
                        "choices": [
                            {
                                "delta": {
                                    "tool_calls": [
                                        {"index": 0, "function": {"arguments": '"abc"}'}}
                                    ]
                                },
                                "finish_reason": "tool_calls",
                            }
                        ]
                    }
                )
            ),
        ]
    )
    text_parts: list[str] = []
    tool_calls_buffer: dict[str, dict] = {}

    chunks = [chunk async for chunk in _process_copilot_sse(event_source, text_parts, tool_calls_buffer)]

    assert chunks == ["Hel"]
    assert text_parts == ["Hel"]
    assert tool_calls_buffer == {
        "0": {"id": "call-1", "name": "lookup", "arguments": '{"q": "abc"}'}
    }


@pytest.mark.asyncio
async def test_process_copilot_sse_handles_done_empty_choices_and_stop() -> None:
    event_source = FakeCopilotEventSource(
        [
            FakeSSE(json.dumps({"choices": []})),
            FakeSSE(json.dumps({"choices": [{"delta": {}, "finish_reason": "stop"}]})),
            FakeSSE("[DONE]"),
        ]
    )

    chunks = [chunk async for chunk in _process_copilot_sse(event_source, [], {})]

    assert chunks == []


@pytest.mark.asyncio
async def test_copilot_provider_stream_yields_final_message() -> None:
    provider = CopilotProvider()
    event_source = FakeCopilotEventSource(
        [
            FakeSSE(json.dumps({"choices": [{"delta": {"content": "Hello"}, "finish_reason": None}]})),
            FakeSSE("[DONE]"),
        ]
    )
    fake_client = FakeAsyncClientContext()

    with (
        patch("maestro.providers.copilot.auth.get", return_value={"access_token": "token"}),
        patch("maestro.providers.copilot.httpx.AsyncClient", return_value=fake_client),
        patch("maestro.providers.copilot.aconnect_sse", return_value=event_source) as mock_sse,
    ):
        outputs = [
            item
            async for item in provider.stream([Message(role="user", content="hi")], "gpt-4.1", tools=[_sample_tool()])
        ]

    assert outputs == ["Hello", Message(role="assistant", content="Hello", tool_calls=[])]
    assert mock_sse.call_args.kwargs["json"]["tools"][0]["function"]["name"] == "lookup"


@pytest.mark.asyncio
async def test_copilot_provider_stream_raises_on_api_error() -> None:
    provider = CopilotProvider()
    response = SimpleNamespace(is_success=False, status_code=401, aread=Mock(return_value=None))

    async def fake_aread() -> bytes:
        return b"denied"

    response.aread = fake_aread
    event_source = FakeCopilotEventSource([], response=response)
    fake_client = FakeAsyncClientContext()

    with (
        patch("maestro.providers.copilot.auth.get", return_value={"access_token": "token"}),
        patch("maestro.providers.copilot.httpx.AsyncClient", return_value=fake_client),
        patch("maestro.providers.copilot.aconnect_sse", return_value=event_source),
    ):
        with pytest.raises(RuntimeError, match="API error 401: denied"):
            _ = [item async for item in provider.stream([Message(role="user", content="hi")], "gpt-4.1")]


def test_copilot_provider_helpers_and_wire_conversion_cover_remaining_branches() -> None:
    provider = CopilotProvider()
    assistant = Message(
        role="assistant",
        content="done",
        tool_calls=[ToolCall(id="call-1", name="lookup", arguments={"q": "x"})],
    )
    tool_msg = Message(role="tool", content="{}", tool_call_id="call-1")
    system = Message(role="system", content="rules")

    assert provider.id == "github-copilot"
    assert provider.name == "GitHub Copilot"
    assert provider.auth_required() is True

    with patch("maestro.providers.copilot.auth.get", return_value=None):
        assert provider.is_authenticated() is False
        with pytest.raises(RuntimeError, match="Not authenticated"):
            provider._require_token()

    with patch("maestro.providers.copilot.auth.get", return_value={"access_token": "token"}):
        assert provider._require_token() == "token"
        assert provider.is_authenticated() is True

    with patch("maestro.providers.copilot.auth.get", return_value={"access_token": ""}):
        with pytest.raises(RuntimeError, match="Invalid credentials"):
            provider._require_token()

    assert provider._build_payload([system], "gpt-4.1", None, extra={}) == {
        "model": "gpt-4.1",
        "messages": [{"role": "system", "content": "rules"}],
        "stream": True,
    }
    assert provider._build_payload(
        [system],
        "gpt-4.1",
        [_sample_tool()],
        extra={"response_format": {"type": "json_schema"}},
    )["response_format"] == {"type": "json_schema"}
    assert _convert_messages_to_wire([Message(role="user", content="hi"), assistant, system, tool_msg])[1]["tool_calls"][0]["function"]["name"] == "lookup"
    assert _convert_tools_to_wire([_sample_tool()])[0]["function"]["name"] == "lookup"
    assert _convert_messages_to_wire([tool_msg]) == [{"role": "tool", "tool_call_id": "call-1", "content": "{}"}]


def test_copilot_model_and_sse_helpers_cover_edge_cases() -> None:
    models: list[str] = []
    _collect_list_models(["gpt-4.1", {"id": "o3"}, {"model": "o4"}, {"name": "o1"}, 7], models)

    assert models == ["gpt-4.1", "o3", "o4", "o1"]
    assert _extract_model_ids([]) == []
    assert _extract_model_ids({"available_models": {"gpt-4.1": {}, "o3": {}}}) == ["gpt-4.1", "o3"]
    assert _parse_sse_event("not-json") is None


def test_copilot_login_rejects_invalid_device_response_and_times_out() -> None:
    provider = CopilotProvider()
    invalid_device = FakeCopilotResponse(json_data={"device_code": "", "user_code": ""})
    timed_device = FakeCopilotResponse(
        json_data={"device_code": "device", "user_code": "code", "interval": 1, "expires_in": 10}
    )
    pending = FakeCopilotResponse(json_data={"error": "authorization_pending"})

    with patch("maestro.providers.copilot.httpx.post", return_value=invalid_device):
        with pytest.raises(RuntimeError, match="Invalid device code response"):
            provider.login()

    with (
        patch("maestro.providers.copilot.httpx.post", side_effect=[timed_device, pending]),
        patch("maestro.providers.copilot.time.sleep"),
        patch("maestro.providers.copilot.time.time", side_effect=[0, 20]),
    ):
        with pytest.raises(RuntimeError, match="timed out"):
            provider.login()


def test_copilot_handle_poll_response_branches() -> None:
    assert _handle_poll_response({"error": "authorization_pending"}, 5) == (None, 5)
    assert _handle_poll_response({"error": "slow_down"}, 5) == (None, 10)
    assert _handle_poll_response({"access_token": "token"}, 5) == ("token", 5)

    with pytest.raises(RuntimeError, match="Device code expired"):
        _handle_poll_response({"error": "expired_token"}, 5)

    with pytest.raises(RuntimeError, match="Access denied"):
        _handle_poll_response({"error": "access_denied"}, 5)

    with pytest.raises(RuntimeError, match="OAuth error: boom"):
        _handle_poll_response({"error": "boom"}, 5)


def test_copilot_login_polls_until_token_and_saves_credentials() -> None:
    provider = CopilotProvider()
    device_response = FakeCopilotResponse(
        json_data={
            "device_code": "device-code",
            "user_code": "USER-CODE",
            "interval": 2,
            "expires_in": 30,
        }
    )
    pending_response = FakeCopilotResponse(json_data={"error": "authorization_pending"})
    token_response = FakeCopilotResponse(json_data={"access_token": "copilot-token"})

    with (
        patch("maestro.providers.copilot.httpx.post", side_effect=[device_response, pending_response, token_response]),
        patch("maestro.providers.copilot.time.sleep") as mock_sleep,
        patch("maestro.providers.copilot.time.time", side_effect=[0, 1, 10, 11]),
        patch("maestro.providers.copilot.auth.set") as mock_set,
    ):
        provider.login()

    assert mock_sleep.call_args_list[0].args[0] == 2 + POLLING_SAFETY_MARGIN
    assert mock_set.call_args.args == ("github-copilot", {"access_token": "copilot-token"})


def test_copilot_build_final_message_handles_invalid_tool_json() -> None:
    message = _build_final_message(["done"], {"0": {"id": "call-1", "name": "lookup", "arguments": "{"}})

    assert message == Message(
        role="assistant",
        content="done",
        tool_calls=[ToolCall(id="call-1", name="lookup", arguments={})],
    )
