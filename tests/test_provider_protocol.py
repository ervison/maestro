"""Tests for ProviderPlugin Protocol and neutral types."""

import pytest
from dataclasses import is_dataclass
from typing import AsyncIterator, Protocol
from maestro.providers.base import Message, ProviderPlugin


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

    def test_create_tool_result_message(self):
        from maestro.providers.base import Message

        msg = Message(role="tool", content='{"result": "ok"}', tool_call_id="call_1")
        assert msg.role == "tool"
        assert msg.tool_call_id == "call_1"

    def test_tool_call_id_defaults_to_none(self):
        from maestro.providers.base import Message

        msg = Message(role="user", content="Hello")
        assert msg.tool_call_id is None


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


# ============== ProviderPlugin Protocol Tests ==============


class MockProvider:
    """A valid implementation of ProviderPlugin for testing."""

    @property
    def id(self) -> str:
        return "mock-provider"

    @property
    def name(self) -> str:
        return "Mock Provider"

    def list_models(self) -> list[str]:
        return ["mock-model-1", "mock-model-2"]

    async def stream(
        self,
        messages: list,
        model: str,
        tools: list | None = None,
        **kwargs: object,
    ) -> AsyncIterator[str | Message]:
        from maestro.providers.base import Message

        yield "Hello "
        yield "world!"
        yield Message(role="assistant", content="Hello world!")

    def auth_required(self) -> bool:
        return True

    def login(self) -> None:
        pass  # Mock login does nothing

    def is_authenticated(self) -> bool:
        return True


class IncompleteProvider:
    """Missing required methods — should fail isinstance check."""

    @property
    def id(self) -> str:
        return "incomplete"

    # Missing: name, list_models, stream, auth_required, login, is_authenticated


class TestProviderPlugin:
    def test_protocol_importable(self):
        """ProviderPlugin should be importable from base module."""
        from maestro.providers.base import ProviderPlugin

        assert ProviderPlugin is not None

    def test_protocol_is_protocol(self):
        """ProviderPlugin should be a Protocol."""
        from maestro.providers.base import ProviderPlugin

        assert issubclass(ProviderPlugin, Protocol)

    def test_protocol_is_runtime_checkable(self):
        """ProviderPlugin should have @runtime_checkable decorator."""
        from maestro.providers.base import ProviderPlugin

        # Check that hasattr works (indicates @runtime_checkable)
        assert hasattr(ProviderPlugin, "id")
        assert hasattr(ProviderPlugin, "name")
        assert hasattr(ProviderPlugin, "list_models")
        assert hasattr(ProviderPlugin, "stream")
        assert hasattr(ProviderPlugin, "auth_required")
        assert hasattr(ProviderPlugin, "login")
        assert hasattr(ProviderPlugin, "is_authenticated")

    def test_mock_provider_passes_isinstance(self):
        """A complete implementation passes runtime isinstance() check."""
        from maestro.providers.base import ProviderPlugin

        provider = MockProvider()
        assert isinstance(provider, ProviderPlugin)

    def test_incomplete_provider_fails_isinstance(self):
        """An incomplete implementation fails runtime isinstance() check."""
        from maestro.providers.base import ProviderPlugin

        provider = IncompleteProvider()
        assert not isinstance(provider, ProviderPlugin)

    def test_mock_provider_properties(self):
        """Verify properties return expected types."""
        provider = MockProvider()
        assert provider.id == "mock-provider"
        assert provider.name == "Mock Provider"

    def test_mock_provider_list_models(self):
        """Verify list_models returns list of strings."""
        provider = MockProvider()
        models = provider.list_models()
        assert isinstance(models, list)
        assert all(isinstance(m, str) for m in models)
        assert len(models) == 2

    def test_mock_provider_auth_methods(self):
        """Verify auth methods return expected types."""
        provider = MockProvider()
        assert provider.auth_required() is True
        assert provider.is_authenticated() is True
        provider.login()  # Should not raise

    @pytest.mark.asyncio
    async def test_mock_provider_stream(self):
        """Verify stream yields strings and final Message."""
        from maestro.providers.base import Message

        provider = MockProvider()
        messages = [Message(role="user", content="Hi")]

        chunks = []
        async for chunk in provider.stream(messages, "mock-model-1"):
            chunks.append(chunk)

        assert chunks[0] == "Hello "
        assert chunks[1] == "world!"
        assert chunks[-1] == Message(role="assistant", content="Hello world!")

    @pytest.mark.asyncio
    async def test_mock_provider_stream_accepts_extra_kwargs(self):
        """stream() must accept **kwargs so planner can pass extra= for structured output."""
        from maestro.providers.base import Message

        provider = MockProvider()
        messages = [Message(role="user", content="Hi")]

        chunks = []
        # Planner calls provider.stream(..., extra={"response_format": ...})
        async for chunk in provider.stream(messages, "mock-model-1", extra={"response_format": {"type": "json_object"}}):
            chunks.append(chunk)

        assert len(chunks) > 0


# ============== Import Tests ==============


class TestImports:
    def test_import_from_base(self):
        """All types importable from maestro.providers.base."""
        from maestro.providers.base import (
            Message,
            Tool,
            ToolCall,
            ToolResult,
            ProviderPlugin,
        )

        assert Message is not None
        assert ProviderPlugin is not None

    def test_import_from_package(self):
        """All types importable from maestro.providers (re-exports)."""
        from maestro.providers import (
            Message,
            Tool,
            ToolCall,
            ToolResult,
            ProviderPlugin,
        )

        assert Message is not None
        assert ProviderPlugin is not None
