import json
from pathlib import Path
from unittest.mock import Mock, patch

import pytest
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from maestro import agent
from maestro.agent import _dispatch_sse_text, _run_agentic_loop
from maestro.providers.base import Message, Tool, ToolCall
from maestro.providers.chatgpt import _dispatch_chatgpt_event


def test_dispatch_chatgpt_event_uses_response_done_text_without_deltas() -> None:
    text_parts: list[str] = []
    tool_calls: list[ToolCall] = []

    event = {
        "type": "response.done",
        "response": {
            "output": [
                {
                    "type": "message",
                    "content": [{"type": "output_text", "text": "final text"}],
                }
            ]
        },
    }

    assert _dispatch_chatgpt_event(event, text_parts, tool_calls) == "final text"
    assert text_parts == ["final text"]
    assert tool_calls == []


def test_dispatch_chatgpt_event_collects_function_call_output_item() -> None:
    text_parts: list[str] = []
    tool_calls: list[ToolCall] = []

    event = {
        "type": "response.output_item.done",
        "item": {
            "type": "function_call",
            "call_id": "call-1",
            "name": "read_file",
            "arguments": '{"path": "notes.md"}',
        },
    }

    assert _dispatch_chatgpt_event(event, text_parts, tool_calls) is None
    assert tool_calls == [
        ToolCall(id="call-1", name="read_file", arguments={"path": "notes.md"})
    ]


def test_dispatch_sse_text_uses_first_output_text_from_response_done() -> None:
    text_parts: list[str] = []

    _dispatch_sse_text(
        {
            "type": "response.done",
            "response": {
                "output": [
                    {"type": "reasoning", "content": []},
                    {
                        "type": "message",
                        "content": [
                            {"type": "other", "text": "ignore me"},
                            {"type": "output_text", "text": "final text"},
                        ],
                    },
                ]
            },
        },
        text_parts,
    )

    assert text_parts == ["final text"]


def test_run_agentic_loop_executes_tool_then_returns_followup_response(tmp_path) -> None:
    class FakeProvider:
        def __init__(self) -> None:
            self.calls = 0

        async def stream(self, messages, model, tools=None, **kwargs):
            del messages, model, tools, kwargs
            self.calls += 1
            if self.calls == 1:
                yield Message(
                    role="assistant",
                    content="Checking workspace",
                    tool_calls=[
                        ToolCall(
                            id="call-1",
                            name="read_file",
                            arguments={"path": "notes.md"},
                        )
                    ],
                )
                return

            yield Message(role="assistant", content="All set", tool_calls=[])

    provider = FakeProvider()

    with patch(
        "maestro.agent.execute_tool",
        return_value=({"status": "ok"}, False),
    ) as mock_execute_tool:
        result = _run_agentic_loop(
            messages=[HumanMessage(content="Check the notes")],
            model="gpt-5.4-mini",
            instructions="You are helpful.",
            provider=provider,
            workdir=Path(tmp_path),
        )

    assert result == "All set"
    assert provider.calls == 2
    assert mock_execute_tool.call_args == (
        ("read_file", {"path": "notes.md"}, Path(tmp_path)),
        {"auto": False},
    )


def test_convert_messages_to_input_and_role_formatters() -> None:
    tool_call = ToolCall(id="call-1", name="read_file", arguments={"path": "notes.md"})
    messages = [
        Message(role="system", content="system prompt"),
        Message(role="user", content="hello"),
        Message(role="assistant", content="thinking", tool_calls=[tool_call]),
        Message(role="assistant", content="done"),
        Message(role="tool", content='{"ok": true}', tool_call_id="call-1"),
        Message(role="other", content="ignored"),  # type: ignore[arg-type]
    ]

    input_items, instructions = agent._convert_messages_to_input(messages)

    assert instructions == "system prompt"
    assert input_items == [
        {
            "type": "message",
            "role": "user",
            "content": [{"type": "input_text", "text": "hello"}],
        },
        {
            "type": "function_call",
            "call_id": "call-1",
            "name": "read_file",
            "arguments": '{"path": "notes.md"}',
        },
        {
            "type": "message",
            "role": "assistant",
            "content": [{"type": "output_text", "text": "done"}],
        },
        {
            "type": "function_call_output",
            "call_id": "call-1",
            "output": '{"ok": true}',
        },
    ]


def test_convert_tools_and_neutral_messages() -> None:
    tools = agent._convert_tools_to_chatgpt(
        [Tool(name="read_file", description="Read a file", parameters={"type": "object"})]
    )
    neutral = agent._convert_messages_to_neutral(
        [HumanMessage(content="hello"), AIMessage(content="hi"), SystemMessage(content="ignored")],
        instructions="system prompt",
    )

    assert tools == [
        {
            "type": "function",
            "name": "read_file",
            "description": "Read a file",
            "parameters": {"type": "object"},
        }
    ]
    assert neutral == [
        Message(role="system", content="system prompt"),
        Message(role="user", content="hello"),
        Message(role="assistant", content="hi"),
    ]


def test_parse_sse_events_and_assemble_response() -> None:
    class FakeResponse:
        def iter_lines(self):
            yield "ignore"
            yield 'data: {"type":"response.output_text.delta","delta":"Hello"}'
            yield "data: not-json"
            yield (
                'data: {"type":"response.output_item.done","item":'
                '{"type":"function_call","call_id":"call-1","name":"read_file",'
                '"arguments":"{\\"path\\": \\"notes.md\\"}"}}'
            )
            yield "data: [DONE]"
            yield 'data: {"type":"response.output_text.delta","delta":"late"}'

    text_parts, tool_calls = agent._parse_sse_events(FakeResponse())
    result = agent._assemble_response(text_parts, tool_calls)

    assert text_parts == ["Hello"]
    assert tool_calls == [ToolCall(id="call-1", name="read_file", arguments={"path": "notes.md"})]
    assert result == [
        "Hello",
        Message(role="assistant", content="Hello", tool_calls=tool_calls),
    ]


def test_run_httpx_stream_sync_success_and_api_error() -> None:
    success_response = Mock()
    success_response.is_success = True
    success_response.iter_lines.return_value = iter(
        [
            'data: {"type":"response.output_text.delta","delta":"Hello"}',
            "data: [DONE]",
        ]
    )

    error_response = Mock()
    error_response.is_success = False
    error_response.status_code = 500
    error_response.read.return_value = b"boom"

    success_cm = Mock()
    success_cm.__enter__ = Mock(return_value=success_response)
    success_cm.__exit__ = Mock(return_value=None)
    error_cm = Mock()
    error_cm.__enter__ = Mock(return_value=error_response)
    error_cm.__exit__ = Mock(return_value=None)

    messages = [Message(role="user", content="hello")]
    tools = [Tool(name="read_file", description="Read", parameters={})]

    with patch("maestro.agent.httpx.stream", return_value=success_cm) as mock_stream:
        result = agent._run_httpx_stream_sync(messages, "gpt-5", tools, Mock())

    assert result == ["Hello", Message(role="assistant", content="Hello", tool_calls=[])]
    payload = mock_stream.call_args.kwargs["json"]
    assert payload["tool_choice"] == "auto"
    assert payload["tools"][0]["name"] == "read_file"

    with patch("maestro.agent.httpx.stream", return_value=error_cm):
        with pytest.raises(RuntimeError, match="API error 500: boom"):
            agent._run_httpx_stream_sync(messages, "gpt-5", [], Mock())


def test_run_provider_stream_sync_invokes_on_text() -> None:
    class FakeProvider:
        async def stream(self, messages, model, tools=None):
            assert messages == [Message(role="user", content="hello")]
            assert model == "gpt-5"
            assert tools == []
            yield "Hel"
            yield "lo"
            yield Message(role="assistant", content="Hello")

    on_text = Mock()

    result = agent._run_provider_stream_sync(
        FakeProvider(),
        [Message(role="user", content="hello")],
        "gpt-5",
        [],
        on_text=on_text,
    )

    assert result == ["Hel", "lo", Message(role="assistant", content="Hello")]
    assert on_text.call_args_list == [(("Hel",),), (("lo",),)]


@pytest.mark.parametrize(
    ("stream_results", "expected"),
    [
        (["a", "b", Message(role="assistant", content="ignored", tool_calls=[])], ("ab", [])),
        ([Message(role="assistant", content="done", tool_calls=[ToolCall(id="1", name="x", arguments={})])], ("done", [ToolCall(id="1", name="x", arguments={})])),
    ],
)
def test_collect_stream_chunks_success_cases(stream_results, expected) -> None:
    assert agent._collect_stream_chunks(stream_results) == expected


def test_collect_stream_chunks_raises_without_output() -> None:
    with pytest.raises(RuntimeError, match="No output received"):
        agent._collect_stream_chunks([])


def test_check_tool_loop_detects_repeated_signature() -> None:
    signatures: list[str] = []
    tool_calls = [ToolCall(id="1", name="read_file", arguments={"path": "a"})]

    agent._check_tool_loop(signatures, tool_calls, 3)
    agent._check_tool_loop(signatures, tool_calls, 3)

    with pytest.raises(RuntimeError, match="same tool call repeated 3 times"):
        agent._check_tool_loop(signatures, tool_calls, 3)


def test_check_tool_loop_trims_history_window() -> None:
    signatures: list[str] = []
    agent._check_tool_loop(signatures, [ToolCall(id="1", name="a", arguments={})], 2)
    agent._check_tool_loop(signatures, [ToolCall(id="2", name="b", arguments={})], 2)
    agent._check_tool_loop(signatures, [ToolCall(id="3", name="c", arguments={})], 2)

    assert len(signatures) == 2


def test_execute_tools_and_append_auto_escalates_once() -> None:
    tool_calls = [
        ToolCall(id="1", name="delete_file", arguments={"path": "a"}),
        ToolCall(id="2", name="read_file", arguments={"path": "b"}),
    ]
    neutral_messages: list[Message] = []
    on_tool_start = Mock()

    with patch(
        "maestro.agent.execute_tool",
        side_effect=[({"deleted": True}, True), ({"content": "ok"}, False)],
    ) as mock_execute:
        auto, none_value = agent._execute_tools_and_append(
            tool_calls,
            neutral_messages,
            "doing work",
            Path("."),
            False,
            on_tool_start,
        )

    assert auto is True
    assert none_value is None
    assert on_tool_start.call_count == 1
    assert mock_execute.call_args_list[1].kwargs == {"auto": True}
    assert neutral_messages[0].tool_calls == tool_calls
    assert json.loads(neutral_messages[1].content) == {"deleted": True}
    assert json.loads(neutral_messages[2].content) == {"content": "ok"}


def test_collect_stream_results_uses_correct_path_and_validates_provider() -> None:
    with patch("maestro.agent._run_httpx_stream_sync", return_value=["legacy"]) as legacy:
        assert agent._collect_stream_results(True, None, [], "gpt-5", [], Mock(), None) == ["legacy"]
        legacy.assert_called_once()

    with pytest.raises(RuntimeError, match="Either provider or tokens"):
        agent._collect_stream_results(False, None, [], "gpt-5", [], None, None)

    with patch("maestro.agent._run_provider_stream_sync", return_value=["provider"]) as provider_stream:
        provider = Mock()
        assert agent._collect_stream_results(False, provider, [], "gpt-5", [], None, None) == ["provider"]
        provider_stream.assert_called_once()


def test_run_agentic_iteration_and_advance_tool_iteration_delegate() -> None:
    with patch("maestro.agent._collect_stream_results", return_value=["he", "llo", Message(role="assistant", content="Hello", tool_calls=[])]) as collect:
        assert agent._run_agentic_iteration(False, Mock(), [], "gpt-5", [], None, None) == ("hello", [])
        collect.assert_called_once()

    with patch("maestro.agent._check_tool_loop") as check_loop, patch(
        "maestro.agent._execute_tools_and_append", return_value=(True, None)
    ) as execute:
        tool_calls = [ToolCall(id="1", name="read_file", arguments={})]
        assert agent._advance_tool_iteration([], tool_calls, [], "text", Path("."), False, None, 3) == (True, None)
        check_loop.assert_called_once()
        execute.assert_called_once()


def test_run_agentic_loop_raises_after_max_iterations() -> None:
    with patch(
        "maestro.agent._run_agentic_iteration",
        return_value=("working", [ToolCall(id="1", name="read_file", arguments={})]),
    ), patch("maestro.agent._advance_tool_iteration", return_value=(False, None)):
        with pytest.raises(RuntimeError, match="exceeded max_iterations=2"):
            agent._run_agentic_loop(
                messages=[HumanMessage(content="hello")],
                model="gpt-5",
                instructions="system",
                provider=Mock(),
                max_iterations=2,
            )


def test_dispatch_and_build_single_shot_helpers() -> None:
    text_parts = ["existing"]
    agent._dispatch_sse_text(
        {
            "type": "response.done",
            "response": {
                "output": [
                    {"type": "message", "content": [{"type": "output_text", "text": "ignored"}]}
                ]
            },
        },
        text_parts,
    )
    agent._dispatch_sse_text({"type": "response.output_text.delta", "delta": "!"}, text_parts)

    input_items, instructions = agent._build_single_shot_input(
        [SystemMessage(content="system"), HumanMessage(content="hi"), AIMessage(content="hello")]
    )

    assert text_parts == ["existing", "!"]
    assert instructions == "system"
    assert input_items == [
        {
            "type": "message",
            "role": "user",
            "content": [{"type": "input_text", "text": "hi"}],
        },
        {
            "type": "message",
            "role": "assistant",
            "content": [{"type": "output_text", "text": "hello"}],
        },
    ]
    assert agent._base_message_to_input_item(SystemMessage(content="skip")) is None
    assert agent._message_output_text({"type": "message", "content": [{"type": "other"}]}) is None


def test_read_streamed_text_response_and_call_responses_api() -> None:
    class FakeResponse:
        def __init__(self, lines, success=True, status_code=200, body=b"") -> None:
            self._lines = lines
            self.is_success = success
            self.status_code = status_code
            self._body = body

        def iter_lines(self):
            return iter(self._lines)

        def read(self):
            return self._body

    response = FakeResponse(
        [
            "ignored",
            "data: not-json",
            'data: {"type":"response.output_text.delta","delta":"Hello"}',
            "data: [DONE]",
        ]
    )
    assert agent._read_streamed_text_response(response) == "Hello"

    with pytest.raises(RuntimeError, match="No output_text"):
        agent._read_streamed_text_response(FakeResponse(["data: {\"type\":\"other\"}"]))

    success_cm = Mock()
    success_cm.__enter__ = Mock(return_value=response)
    success_cm.__exit__ = Mock(return_value=None)
    error_cm = Mock()
    error_cm.__enter__ = Mock(return_value=FakeResponse([], success=False, status_code=400, body=b"bad"))
    error_cm.__exit__ = Mock(return_value=None)

    with patch("maestro.agent.httpx.stream", return_value=success_cm) as mock_stream:
        result = agent._call_responses_api("gpt-5", [SystemMessage(content="system"), HumanMessage(content="hi")], Mock())
        assert result == "Hello"
        payload = mock_stream.call_args.kwargs["json"]
        assert payload["instructions"] == "system"
        assert payload["reasoning"]["summary"] == "auto"

    with patch("maestro.agent.httpx.stream", return_value=error_cm):
        with pytest.raises(RuntimeError, match="API error 400: bad"):
            agent._call_responses_api("gpt-5", [HumanMessage(content="hi")], Mock())


def test_run_uses_default_provider_and_returns_last_message(tmp_path) -> None:
    provider = Mock()

    with patch("maestro.agent.get_default_provider", return_value=provider), patch(
        "maestro.agent._run_agentic_loop", return_value="final output"
    ) as run_loop:
        result = agent.run(
            model_name="gpt-5",
            prompt="do work",
            system=None,
            workdir=Path(tmp_path),
            auto=True,
            provider=None,
            stream_callback=Mock(),
            on_tool_start=Mock(),
        )

    assert result == "final output"
    assert run_loop.call_args.kwargs["provider"] is provider
    assert run_loop.call_args.kwargs["auto"] is True
