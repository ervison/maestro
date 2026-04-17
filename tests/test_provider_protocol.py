"""Tests for neutral types - RED phase (tests should fail initially)."""

import pytest
from dataclasses import is_dataclass


def test_message_importable():
    """Message type should be importable from base module."""
    from maestro.providers.base import Message
    assert Message is not None


def test_tool_importable():
    """Tool type should be importable from base module."""
    from maestro.providers.base import Tool
    assert Tool is not None


def test_tool_call_importable():
    """ToolCall type should be importable from base module."""
    from maestro.providers.base import ToolCall
    assert ToolCall is not None


def test_tool_result_importable():
    """ToolResult type should be importable from base module."""
    from maestro.providers.base import ToolResult
    assert ToolResult is not None


class TestMessage:
    def test_create_user_message(self):
        from maestro.providers.base import Message
        msg = Message(role="user", content="Hello")
        assert msg.role == "user"
        assert msg.content == "Hello"
        assert msg.tool_calls == []

    def test_create_assistant_message_with_tool_calls(self):
        from maestro.providers.base import Message, ToolCall
        tc = ToolCall(id="call_1", name="read_file", arguments={"path": "test.txt"})
        msg = Message(role="assistant", content="", tool_calls=[tc])
        assert msg.role == "assistant"
        assert len(msg.tool_calls) == 1
        assert msg.tool_calls[0].name == "read_file"

    def test_create_system_message(self):
        from maestro.providers.base import Message
        msg = Message(role="system", content="You are helpful.")
        assert msg.role == "system"

    def test_message_is_dataclass(self):
        from maestro.providers.base import Message
        assert is_dataclass(Message)

    def test_message_equality(self):
        from maestro.providers.base import Message
        msg1 = Message(role="user", content="hi")
        msg2 = Message(role="user", content="hi")
        assert msg1 == msg2


class TestTool:
    def test_create_tool(self):
        from maestro.providers.base import Tool
        tool = Tool(
            name="read_file",
            description="Read a file",
            parameters={
                "type": "object",
                "properties": {"path": {"type": "string"}},
                "required": ["path"],
            },
        )
        assert tool.name == "read_file"
        assert "path" in tool.parameters["properties"]

    def test_tool_is_dataclass(self):
        from maestro.providers.base import Tool
        assert is_dataclass(Tool)

    def test_tool_equality(self):
        from maestro.providers.base import Tool
        t1 = Tool(name="test", description="desc", parameters={})
        t2 = Tool(name="test", description="desc", parameters={})
        assert t1 == t2


class TestToolCall:
    def test_create_tool_call(self):
        from maestro.providers.base import ToolCall
        tc = ToolCall(id="call_123", name="execute_shell", arguments={"command": "ls"})
        assert tc.id == "call_123"
        assert tc.name == "execute_shell"
        assert tc.arguments["command"] == "ls"

    def test_tool_call_is_dataclass(self):
        from maestro.providers.base import ToolCall
        assert is_dataclass(ToolCall)


class TestToolResult:
    def test_create_tool_result(self):
        from maestro.providers.base import ToolResult
        tr = ToolResult(call_id="call_123", output='{"files": ["a.py"]}')
        assert tr.call_id == "call_123"
        assert "files" in tr.output

    def test_tool_result_is_dataclass(self):
        from maestro.providers.base import ToolResult
        assert is_dataclass(ToolResult)
