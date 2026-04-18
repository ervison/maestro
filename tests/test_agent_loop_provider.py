"""Provider-based agent loop regression tests.

These tests verify the provider-based architecture with mock providers,
complementing the original tests that use httpx mocking.
"""

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


def test_provider_direct_answer(tmp_path):
    """Model answers directly without any tool calls (provider path)."""
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


def test_provider_one_tool_call(tmp_path):
    """Model calls write_file once then answers (provider path)."""
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


def test_provider_streaming_deltas_not_duplicated(tmp_path):
    """Provider yields text deltas + final Message; loop returns text exactly once.

    Regression test for WR-01: streamed assistant text was being returned twice
    because the loop concatenated both streaming deltas AND the final Message.content.
    """
    # Provider yields text deltas followed by final Message
    final_msg = Message(role="assistant", content="Hello world", tool_calls=[])
    provider = make_mock_provider([["Hello ", "world", final_msg]])

    result = _run_agentic_loop(
        messages=[HumanMessage(content="say hi")],
        model="gpt-5.4-mini",
        instructions="You are helpful.",
        provider=provider,
        workdir=tmp_path,
        auto=True,
    )

    # Should return text exactly once, not duplicated
    assert result == "Hello world"
    assert result != "Hello worldHello world"  # Ensure no duplication


def test_provider_preserves_tool_call_context(tmp_path):
    """Tool-call follow-up requests include both assistant tool_calls and tool output.

    Regression test for WR-02: the loop must preserve the assistant message that
    requested the tools, and the provider must receive both the function_call
    context and the function_call_output in the second iteration.
    """
    (tmp_path / "dummy").mkdir(exist_ok=True)

    tool_call = ToolCall(
        id="call_abc123",
        name="write_file",
        arguments={"path": "test.txt", "content": "test content"},
    )

    # First iteration: assistant requests tool call
    first_msg = Message(
        role="assistant",
        content="I'll create that file for you.",
        tool_calls=[tool_call],
    )

    # Second iteration: assistant provides final answer
    final_msg = Message(role="assistant", content="Done!", tool_calls=[])

    # Capture messages sent to provider in second iteration
    captured_messages = []

    class CapturingMockProvider:
        id = "mock"
        call_idx = 0

        def is_authenticated(self):
            return True

        async def stream(self, messages, model, tools=None):
            nonlocal captured_messages
            if self.call_idx == 1:  # Second iteration
                captured_messages = messages
            self.call_idx += 1

            if self.call_idx == 1:
                yield first_msg
            else:
                yield final_msg

    provider = CapturingMockProvider()

    result = _run_agentic_loop(
        messages=[HumanMessage(content="create a file")],
        model="gpt-5.4-mini",
        instructions="You are helpful.",
        provider=provider,
        workdir=tmp_path,
        auto=True,
    )

    assert result == "Done!"
    assert (tmp_path / "test.txt").read_text() == "test content"

    # Verify second iteration received assistant message with tool_calls
    assistant_msgs = [m for m in captured_messages if m.role == "assistant"]
    assert len(assistant_msgs) >= 1, "Second iteration should include assistant context"

    # Find the assistant message that has the tool call
    assistant_with_tool = None
    for m in assistant_msgs:
        if m.tool_calls:
            assistant_with_tool = m
            break

    assert assistant_with_tool is not None, (
        "Second iteration should include assistant message with tool_calls"
    )
    assert len(assistant_with_tool.tool_calls) == 1
    assert assistant_with_tool.tool_calls[0].id == "call_abc123"
    assert assistant_with_tool.tool_calls[0].name == "write_file"

    # Verify second iteration also received tool result
    tool_msgs = [m for m in captured_messages if m.role == "tool"]
    assert len(tool_msgs) >= 1, "Second iteration should include tool result"
    assert tool_msgs[0].tool_call_id == "call_abc123"


def test_provider_uses_final_message_when_no_deltas(tmp_path):
    """When provider only yields final Message (no deltas), use Message.content."""
    final_msg = Message(role="assistant", content="Direct from message", tool_calls=[])
    provider = make_mock_provider([[final_msg]])

    result = _run_agentic_loop(
        messages=[HumanMessage(content="test")],
        model="gpt-5.4-mini",
        instructions="You are helpful.",
        provider=provider,
        workdir=tmp_path,
        auto=True,
    )

    assert result == "Direct from message"
