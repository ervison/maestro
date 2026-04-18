import json
import pytest
from pathlib import Path
from langchain_core.messages import HumanMessage
from maestro.agent import _run_agentic_loop
from maestro.providers.base import Message, ToolCall


def make_mock_provider(stream_results: list[list]):
    """Create mock provider returning stream_results on successive calls.

    Args:
        stream_results: List of result lists. Each inner list contains
                       str chunks and a final Message for one stream call.

    Returns:
        Mock provider class instance with id, is_authenticated, and stream.
    """
    call_idx = 0

    class MockProvider:
        id = "mock"

        def is_authenticated(self):
            return True

        async def stream(self, messages, model, tools=None):
            nonlocal call_idx
            results = stream_results[call_idx]
            call_idx += 1
            for item in results:
                yield item

    return MockProvider()


def test_agentic_loop_direct_answer(tmp_path):
    """Model answers directly without any tool calls."""
    final_msg = Message(role="assistant", content="Hello world", tool_calls=[])
    provider = make_mock_provider([[final_msg]])

    result = _run_agentic_loop(
        messages=[HumanMessage(content="say hi")],
        model="gpt-5.4-mini",
        instructions="You are helpful.",
        provider=provider,
        workdir=tmp_path,
        auto=True,
    )
    assert result == "Hello world"


def test_agentic_loop_one_tool_call(tmp_path):
    """Model calls write_file once then answers."""
    (tmp_path / "dummy").mkdir(exist_ok=True)

    tool_call = ToolCall(
        id="call_1", name="write_file", arguments={"path": "out.txt", "content": "done"}
    )
    first_msg = Message(role="assistant", content="", tool_calls=[tool_call])
    final_msg = Message(role="assistant", content="File written.", tool_calls=[])
    provider = make_mock_provider([[first_msg], [final_msg]])

    result = _run_agentic_loop(
        messages=[HumanMessage(content="write a file")],
        model="gpt-5.4-mini",
        instructions="You are helpful.",
        provider=provider,
        workdir=tmp_path,
        auto=True,
    )
    assert result == "File written."
    assert (tmp_path / "out.txt").read_text() == "done"
