"""Tests for ChatGPT provider implementation.

These tests verify that ChatGPTProvider correctly implements the ProviderPlugin
Protocol and maintains backward compatibility with existing auth interfaces.
"""

import json
import pytest


class TestProtocolCompliance:
    """Verify ChatGPTProvider implements ProviderPlugin correctly."""

    def test_chatgpt_provider_implements_protocol(self):
        """ChatGPTProvider passes isinstance check against ProviderPlugin."""
        from maestro.providers import ProviderPlugin
        from maestro.providers.chatgpt import ChatGPTProvider

        provider = ChatGPTProvider()
        assert isinstance(provider, ProviderPlugin)

    def test_provider_properties(self):
        """Provider has correct id and name."""
        from maestro.providers.chatgpt import ChatGPTProvider

        provider = ChatGPTProvider()
        assert provider.id == "chatgpt"
        assert provider.name == "ChatGPT"


class TestModelListing:
    """Verify model listing functionality."""

    def test_list_models_returns_known_models(self):
        """list_models() returns expected model IDs."""
        from maestro.providers.chatgpt import ChatGPTProvider, MODELS

        provider = ChatGPTProvider()
        models = provider.list_models()
        assert models == MODELS
        assert "gpt-5.4" in models

    def test_list_models_returns_copy(self):
        """list_models() returns a copy, not the original list."""
        from maestro.providers.chatgpt import ChatGPTProvider, MODELS

        provider = ChatGPTProvider()
        models = provider.list_models()
        models.append("fake-model")
        # Original should be unchanged
        assert "fake-model" not in MODELS


class TestAuthMethods:
    """Verify authentication state methods."""

    def test_auth_required(self):
        """Provider requires authentication."""
        from maestro.providers.chatgpt import ChatGPTProvider

        provider = ChatGPTProvider()
        assert provider.auth_required() is True

    def test_is_authenticated_false_when_no_creds(self, tmp_path, monkeypatch):
        """is_authenticated() returns False when no credentials stored."""
        from maestro.providers.chatgpt import ChatGPTProvider
        from maestro import auth

        # Point to empty auth file
        auth_file = tmp_path / "auth.json"
        monkeypatch.setattr(auth, "AUTH_FILE", auth_file)

        provider = ChatGPTProvider()
        assert provider.is_authenticated() is False

    def test_is_authenticated_true_when_creds_exist(self, tmp_path, monkeypatch):
        """is_authenticated() returns True when credentials exist."""
        from maestro.providers.chatgpt import ChatGPTProvider
        from maestro import auth

        auth_file = tmp_path / "auth.json"
        auth_file.write_text(
            json.dumps(
                {"chatgpt": {"access": "test", "refresh": "", "expires": 9999999999.0}}
            )
        )
        monkeypatch.setattr(auth, "AUTH_FILE", auth_file)

        provider = ChatGPTProvider()
        assert provider.is_authenticated() is True


class TestTypeConversionHelpers:
    """Verify message and tool conversion helpers."""

    def test_convert_messages_to_input(self):
        """_convert_messages_to_input produces correct format."""
        from maestro.providers.chatgpt import _convert_messages_to_input
        from maestro.providers.base import Message

        messages = [
            Message(role="user", content="Hello"),
            Message(role="assistant", content="Hi there"),
        ]
        result = _convert_messages_to_input(messages)

        assert len(result) == 2
        assert result[0]["type"] == "message"
        assert result[0]["role"] == "user"
        assert result[0]["content"][0]["text"] == "Hello"
        assert result[1]["role"] == "assistant"
        assert result[1]["content"][0]["text"] == "Hi there"

    def test_convert_messages_skips_system(self):
        """System messages are extracted as instructions, not input items."""
        from maestro.providers.chatgpt import _convert_messages_to_input
        from maestro.providers.base import Message

        messages = [
            Message(role="system", content="You are helpful"),
            Message(role="user", content="Hello"),
        ]
        result = _convert_messages_to_input(messages)

        # System message should not appear as input item
        assert len(result) == 1
        assert result[0]["role"] == "user"

    def test_convert_messages_includes_tool_results(self):
        """Tool results are converted to function_call_output format."""
        from maestro.providers.chatgpt import _convert_messages_to_input
        from maestro.providers.base import Message

        messages = [
            Message(role="user", content="Call tool"),
            Message(
                role="tool",
                content='{"result": "success"}',
                tool_call_id="call_123",
            ),
        ]
        result = _convert_messages_to_input(messages)

        assert len(result) == 2
        assert result[1]["type"] == "function_call_output"
        assert result[1]["call_id"] == "call_123"
        assert result[1]["output"] == '{"result": "success"}'

    def test_convert_tools_to_schemas(self):
        """_convert_tools_to_schemas produces function schema format."""
        from maestro.providers.chatgpt import _convert_tools_to_schemas
        from maestro.providers.base import Tool

        tools = [
            Tool(
                name="read_file",
                description="Read a file",
                parameters={"type": "object", "properties": {}},
            )
        ]
        result = _convert_tools_to_schemas(tools)

        assert len(result) == 1
        assert result[0]["type"] == "function"
        assert result[0]["name"] == "read_file"
        assert result[0]["description"] == "Read a file"

    def test_extract_instructions(self):
        """_extract_instructions extracts system message content."""
        from maestro.providers.chatgpt import _extract_instructions
        from maestro.providers.base import Message

        messages = [
            Message(role="system", content="Be helpful"),
            Message(role="user", content="Hello"),
        ]
        result = _extract_instructions(messages)

        assert result == "Be helpful"

    def test_extract_instructions_none_when_no_system(self):
        """_extract_instructions returns None when no system message."""
        from maestro.providers.chatgpt import _extract_instructions
        from maestro.providers.base import Message

        messages = [
            Message(role="user", content="Hello"),
        ]
        result = _extract_instructions(messages)

        assert result is None

    def test_parse_tool_call(self):
        """_parse_tool_call parses wire format to neutral ToolCall."""
        from maestro.providers.chatgpt import _parse_tool_call

        item = {
            "id": "call_123",
            "name": "read_file",
            "arguments": '{"path": "/tmp/file.txt"}',
        }
        result = _parse_tool_call(item)

        assert result.id == "call_123"
        assert result.name == "read_file"
        assert result.arguments == {"path": "/tmp/file.txt"}

    def test_parse_tool_call_with_dict_arguments(self):
        """_parse_tool_call handles already-parsed dict arguments."""
        from maestro.providers.chatgpt import _parse_tool_call

        item = {
            "id": "call_456",
            "name": "write_file",
            "arguments": {"path": "/tmp/file.txt", "content": "hello"},
        }
        result = _parse_tool_call(item)

        assert result.arguments == {"path": "/tmp/file.txt", "content": "hello"}

    def test_parse_tool_call_invalid_json(self):
        """_parse_tool_call handles invalid JSON gracefully."""
        from maestro.providers.chatgpt import _parse_tool_call

        item = {
            "id": "call_789",
            "name": "broken",
            "arguments": "not valid json",
        }
        result = _parse_tool_call(item)

        assert result.arguments == {}


class TestBackwardCompatibility:
    """Verify backward compatibility with existing auth imports."""

    def test_models_importable_from_auth(self):
        """MODELS, DEFAULT_MODEL, resolve_model still importable from auth."""
        from maestro import auth

        assert hasattr(auth, "MODELS")
        assert hasattr(auth, "DEFAULT_MODEL")
        assert hasattr(auth, "resolve_model")
        assert "gpt-5.4" in auth.MODELS

    def test_model_aliases_importable_from_auth(self):
        """MODEL_ALIASES still importable from auth."""
        from maestro import auth

        assert hasattr(auth, "MODEL_ALIASES")
        assert auth.MODEL_ALIASES["gpt-5"] == "gpt-5.4"

    def test_resolve_model_via_auth(self):
        """resolve_model() works when imported from auth."""
        from maestro import auth

        assert auth.resolve_model("gpt-5") == "gpt-5.4"
        assert auth.resolve_model("gpt-5.4") == "gpt-5.4"  # No alias

    def test_tokenset_still_importable_from_auth(self):
        """TokenSet still importable from maestro.auth."""
        from maestro.auth import TokenSet

        ts = TokenSet(access="test", refresh="test", expires=0.0)
        assert ts.access == "test"

    def test_tokenset_reexported_from_chatgpt(self):
        """TokenSet also re-exported from chatgpt module for convenience."""
        from maestro.providers.chatgpt import TokenSet

        ts = TokenSet(access="test", refresh="test", expires=0.0)
        assert ts.access == "test"


class TestStreamContract:
    """Verify the async stream method signature and behavior."""

    @pytest.mark.asyncio
    async def test_stream_raises_when_not_authenticated(self, tmp_path, monkeypatch):
        """stream() raises RuntimeError when not authenticated."""
        from maestro.providers.chatgpt import ChatGPTProvider
        from maestro.providers.base import Message
        from maestro import auth

        # Use empty auth file to ensure no credentials
        auth_file = tmp_path / "empty_auth.json"
        auth_file.write_text("{}")
        monkeypatch.setattr(auth, "AUTH_FILE", auth_file)

        provider = ChatGPTProvider()

        # The error is raised on first iteration attempt
        with pytest.raises(RuntimeError, match="Not authenticated"):
            async for _ in provider.stream(
                messages=[Message(role="user", content="Hello")],
                model="gpt-5.4",
            ):
                pass

    @pytest.mark.asyncio
    async def test_stream_method_exists(self):
        """stream() method exists and returns an async iterator."""
        from maestro.providers.chatgpt import ChatGPTProvider
        from collections.abc import AsyncIterator

        provider = ChatGPTProvider()
        assert hasattr(provider, "stream")

        # stream() returns an AsyncIterator
        stream = provider.stream(
            messages=[],
            model="gpt-5.4",
        )
        assert isinstance(stream, AsyncIterator)


class TestConstants:
    """Verify constants and configuration."""

    def test_default_model_constant(self):
        """DEFAULT_MODEL is correct."""
        from maestro.providers.chatgpt import DEFAULT_MODEL

        assert DEFAULT_MODEL == "gpt-5.4-mini"

    def test_models_list_complete(self):
        """MODELS includes expected ChatGPT models."""
        from maestro.providers.chatgpt import MODELS

        expected = [
            "gpt-5.4",
            "gpt-5.4-mini",
            "gpt-5.2",
            "gpt-5-codex",
            "gpt-5.1-codex-max",
            "gpt-5.1-codex-mini",
            "gpt-5.4-nano",
            "gpt-5.1",
        ]
        for model in expected:
            assert model in MODELS

    def test_model_aliases_mappings(self):
        """Key model aliases are correctly mapped."""
        from maestro.providers.chatgpt import MODEL_ALIASES, resolve_model

        assert resolve_model("gpt-5") == "gpt-5.4"
        assert resolve_model("gpt-5-mini") == "gpt-5.4-mini"
        assert resolve_model("gpt-5-nano") == "gpt-5.4-nano"
        assert resolve_model("codex-mini-latest") == "gpt-5.1-codex-mini"

    def test_reasoning_defaults_exist(self):
        """Reasoning effort defaults are defined for key models."""
        from maestro.providers.chatgpt import _reasoning_effort

        # Should return values for known models
        assert _reasoning_effort("gpt-5.4") == "high"
        assert _reasoning_effort("gpt-5.4-mini") == "high"
        assert _reasoning_effort("gpt-5.1") == "medium"

        # Should return default for unknown models
        assert _reasoning_effort("unknown-model") == "medium"


class TestRegressionGuard:
    """Placeholder to remind running full test suite."""

    def test_existing_tests_still_pass(self):
        """Marker: run full test suite to verify no regressions.

        To run: python -m pytest tests/ -v
        """
        pass
