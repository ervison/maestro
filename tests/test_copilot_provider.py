"""Tests for GitHub Copilot provider implementation.

These tests verify that CopilotProvider correctly implements the ProviderPlugin
Protocol and handles OAuth device code flow correctly.
"""

import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch, call
import httpx


class TestProtocolCompliance:
    """Verify CopilotProvider implements ProviderPlugin correctly."""

    def test_copilot_provider_implements_protocol(self):
        """CopilotProvider passes isinstance check against ProviderPlugin."""
        from maestro.providers import ProviderPlugin
        from maestro.providers.copilot import CopilotProvider

        provider = CopilotProvider()
        assert isinstance(provider, ProviderPlugin)

    def test_provider_properties(self):
        """Provider has correct id and name."""
        from maestro.providers.copilot import CopilotProvider

        provider = CopilotProvider()
        assert provider.id == "github-copilot"
        assert provider.name == "GitHub Copilot"


class TestAuthMethods:
    """Verify authentication state methods."""

    def test_auth_required(self):
        """Provider requires authentication."""
        from maestro.providers.copilot import CopilotProvider

        provider = CopilotProvider()
        assert provider.auth_required() is True

    def test_is_authenticated_false_when_no_creds(self, tmp_path, monkeypatch):
        """is_authenticated() returns False when no credentials stored."""
        from maestro.providers.copilot import CopilotProvider
        from maestro import auth

        # Point to empty auth file
        auth_file = tmp_path / "auth.json"
        auth_file.write_text("{}")
        monkeypatch.setattr(auth, "AUTH_FILE", auth_file)

        provider = CopilotProvider()
        assert provider.is_authenticated() is False

    def test_is_authenticated_true_when_token_exists(self, tmp_path, monkeypatch):
        """is_authenticated() returns True when token exists."""
        from maestro.providers.copilot import CopilotProvider
        from maestro import auth

        auth_file = tmp_path / "auth.json"
        auth_file.write_text(
            json.dumps({"github-copilot": {"access_token": "ghu_test123"}})
        )
        monkeypatch.setattr(auth, "AUTH_FILE", auth_file)

        provider = CopilotProvider()
        assert provider.is_authenticated() is True


class TestLogin:
    """Verify OAuth device code flow."""

    def test_login_prints_device_code(self, tmp_path, monkeypatch, capsys):
        """login() prints user_code and device URL."""
        from maestro.providers.copilot import CopilotProvider
        from maestro import auth

        auth_file = tmp_path / "auth.json"
        auth_file.write_text("{}")
        monkeypatch.setattr(auth, "AUTH_FILE", auth_file)

        provider = CopilotProvider()

        # Mock device code response
        device_response = MagicMock()
        device_response.json.return_value = {
            "device_code": "test_device_code",
            "user_code": "ABCD-1234",
            "interval": 5,
            "expires_in": 900,
        }
        device_response.raise_for_status = MagicMock()

        # Mock token response (success)
        token_response = MagicMock()
        token_response.json.return_value = {
            "access_token": "ghu_test_token",
        }
        token_response.raise_for_status = MagicMock()

        call_count = [0]
        def mock_post(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                return device_response
            return token_response

        with patch("httpx.post", side_effect=mock_post):
            with patch("time.sleep"):  # Skip sleeps
                # Provide multiple time values for the while loop check
                with patch("time.time", side_effect=[0, 1, 1000]):
                    provider.login()

        captured = capsys.readouterr()
        assert "github.com/login/device" in captured.out
        assert "ABCD-1234" in captured.out

    def test_login_stores_token_on_success(self, tmp_path, monkeypatch):
        """login() stores access_token on successful auth."""
        from maestro.providers.copilot import CopilotProvider
        from maestro import auth

        auth_file = tmp_path / "auth.json"
        auth_file.write_text("{}")
        monkeypatch.setattr(auth, "AUTH_FILE", auth_file)

        provider = CopilotProvider()

        # Mock device code response
        device_response = MagicMock()
        device_response.json.return_value = {
            "device_code": "test_device_code",
            "user_code": "ABCD-1234",
            "interval": 5,
            "expires_in": 900,
        }
        device_response.raise_for_status = MagicMock()

        # Mock token response (success)
        token_response = MagicMock()
        token_response.json.return_value = {
            "access_token": "ghu_test_token_123",
        }
        token_response.raise_for_status = MagicMock()

        call_count = [0]
        def mock_post(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                return device_response
            return token_response

        with patch("httpx.post", side_effect=mock_post):
            with patch("time.sleep"):
                # Provide multiple time values for the while loop check
                with patch("time.time", side_effect=[0, 1, 1000]):
                    provider.login()

        # Verify token stored
        stored = auth.get("github-copilot")
        assert stored is not None
        assert stored["access_token"] == "ghu_test_token_123"

    def test_login_polls_with_interval(self, tmp_path, monkeypatch):
        """login() polls at interval + POLLING_SAFETY_MARGIN."""
        from maestro.providers.copilot import CopilotProvider
        from maestro import auth

        auth_file = tmp_path / "auth.json"
        auth_file.write_text("{}")
        monkeypatch.setattr(auth, "AUTH_FILE", auth_file)

        provider = CopilotProvider()

        # Mock device code response
        device_response = MagicMock()
        device_response.json.return_value = {
            "device_code": "test_device_code",
            "user_code": "ABCD-1234",
            "interval": 5,
            "expires_in": 900,
        }
        device_response.raise_for_status = MagicMock()

        # First poll: authorization_pending, Second: success
        pending_response = MagicMock()
        pending_response.json.return_value = {"error": "authorization_pending"}
        pending_response.raise_for_status = MagicMock()

        success_response = MagicMock()
        success_response.json.return_value = {"access_token": "ghu_token"}
        success_response.raise_for_status = MagicMock()

        call_count = [0]
        def mock_post(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                return device_response
            elif call_count[0] == 2:
                return pending_response
            return success_response

        with patch("httpx.post", side_effect=mock_post):
            with patch("time.sleep") as mock_sleep:
                # Provide multiple time values for the while loop check (one per iteration)
                with patch("time.time", side_effect=[0, 1, 2, 1000]):
                    provider.login()

        # Should sleep interval + POLLING_SAFETY_MARGIN (5 + 5 = 10)
        mock_sleep.assert_called_with(10)

    def test_login_handles_slow_down(self, tmp_path, monkeypatch):
        """login() handles slow_down by incrementing interval by 5 seconds (AUTH-07)."""
        from maestro.providers.copilot import CopilotProvider
        from maestro import auth

        auth_file = tmp_path / "auth.json"
        auth_file.write_text("{}")
        monkeypatch.setattr(auth, "AUTH_FILE", auth_file)

        provider = CopilotProvider()

        # Mock device code response
        device_response = MagicMock()
        device_response.json.return_value = {
            "device_code": "test_device_code",
            "user_code": "ABCD-1234",
            "interval": 5,
            "expires_in": 900,
        }
        device_response.raise_for_status = MagicMock()

        # First poll: slow_down (increases interval from 5 to 10)
        slow_response = MagicMock()
        slow_response.json.return_value = {"error": "slow_down"}
        slow_response.raise_for_status = MagicMock()

        # Second poll: success
        success_response = MagicMock()
        success_response.json.return_value = {"access_token": "ghu_token"}
        success_response.raise_for_status = MagicMock()

        call_count = [0]
        def mock_post(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                return device_response
            elif call_count[0] == 2:
                return slow_response
            return success_response

        with patch("httpx.post", side_effect=mock_post):
            with patch("time.sleep") as mock_sleep:
                # Provide multiple time values for the while loop check (one per iteration)
                with patch("time.time", side_effect=[0, 1, 2, 3, 1000]):
                    provider.login()

        # Check sleep calls: first at 5+5=10, second at 10+5=15 (after slow_down)
        assert mock_sleep.call_count == 2
        assert mock_sleep.call_args_list[0] == call(10)  # Initial: 5 + 5
        assert mock_sleep.call_args_list[1] == call(15)  # After slow_down: 10 + 5

    def test_login_handles_authorization_pending(self, tmp_path, monkeypatch):
        """login() continues polling on authorization_pending."""
        from maestro.providers.copilot import CopilotProvider
        from maestro import auth

        auth_file = tmp_path / "auth.json"
        auth_file.write_text("{}")
        monkeypatch.setattr(auth, "AUTH_FILE", auth_file)

        provider = CopilotProvider()

        # Mock device code response
        device_response = MagicMock()
        device_response.json.return_value = {
            "device_code": "test_device_code",
            "user_code": "ABCD-1234",
            "interval": 5,
            "expires_in": 900,
        }
        device_response.raise_for_status = MagicMock()

        # Two pending, then success
        pending_response = MagicMock()
        pending_response.json.return_value = {"error": "authorization_pending"}
        pending_response.raise_for_status = MagicMock()

        success_response = MagicMock()
        success_response.json.return_value = {"access_token": "ghu_token"}
        success_response.raise_for_status = MagicMock()

        call_count = [0]
        def mock_post(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                return device_response
            elif call_count[0] in (2, 3):
                return pending_response
            return success_response

        with patch("httpx.post", side_effect=mock_post):
            with patch("time.sleep"):
                # Provide multiple time values for the while loop check (one per iteration)
                with patch("time.time", side_effect=[0, 1, 2, 3, 4, 1000]):
                    provider.login()

        # Should complete without error
        assert auth.get("github-copilot") is not None

    def test_login_handles_expired_token(self, tmp_path, monkeypatch):
        """login() raises RuntimeError on expired_token."""
        from maestro.providers.copilot import CopilotProvider
        from maestro import auth

        auth_file = tmp_path / "auth.json"
        auth_file.write_text("{}")
        monkeypatch.setattr(auth, "AUTH_FILE", auth_file)

        provider = CopilotProvider()

        # Mock device code response
        device_response = MagicMock()
        device_response.json.return_value = {
            "device_code": "test_device_code",
            "user_code": "ABCD-1234",
            "interval": 5,
            "expires_in": 900,
        }
        device_response.raise_for_status = MagicMock()

        # Expired response
        expired_response = MagicMock()
        expired_response.json.return_value = {"error": "expired_token"}
        expired_response.raise_for_status = MagicMock()

        call_count = [0]
        def mock_post(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                return device_response
            return expired_response

        with patch("httpx.post", side_effect=mock_post):
            with patch("time.sleep"):
                # Provide multiple time values for the while loop check
                with patch("time.time", side_effect=[0, 1]):
                    with pytest.raises(RuntimeError, match="expired"):
                        provider.login()

    def test_login_handles_access_denied(self, tmp_path, monkeypatch):
        """login() raises RuntimeError on access_denied."""
        from maestro.providers.copilot import CopilotProvider
        from maestro import auth

        auth_file = tmp_path / "auth.json"
        auth_file.write_text("{}")
        monkeypatch.setattr(auth, "AUTH_FILE", auth_file)

        provider = CopilotProvider()

        # Mock device code response
        device_response = MagicMock()
        device_response.json.return_value = {
            "device_code": "test_device_code",
            "user_code": "ABCD-1234",
            "interval": 5,
            "expires_in": 900,
        }
        device_response.raise_for_status = MagicMock()

        # Denied response
        denied_response = MagicMock()
        denied_response.json.return_value = {"error": "access_denied"}
        denied_response.raise_for_status = MagicMock()

        call_count = [0]
        def mock_post(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                return device_response
            return denied_response

        with patch("httpx.post", side_effect=mock_post):
            with patch("time.sleep"):
                # Provide multiple time values for the while loop check
                with patch("time.time", side_effect=[0, 1]):
                    with pytest.raises(RuntimeError, match="denied"):
                        provider.login()


class TestModelListing:
    """Verify model listing functionality."""

    def test_list_models_returns_known_models(self):
        """list_models() returns expected model IDs."""
        from maestro.providers.copilot import CopilotProvider, COPILOT_MODELS

        provider = CopilotProvider()
        models = provider.list_models()

        expected = ["gpt-4o", "gpt-4o-mini", "gpt-4-turbo", "gpt-3.5-turbo"]
        assert models == expected

    def test_list_models_returns_copy(self):
        """list_models() returns a copy, not the original list."""
        from maestro.providers.copilot import CopilotProvider, COPILOT_MODELS

        provider = CopilotProvider()
        models = provider.list_models()
        models.append("fake-model")

        # Original should be unchanged
        assert "fake-model" not in COPILOT_MODELS


class TestWireFormatConversion:
    """Verify message and tool conversion to OpenAI wire format."""

    def test_convert_user_message_to_wire(self):
        """_convert_messages_to_wire produces correct user message format."""
        from maestro.providers.copilot import _convert_messages_to_wire
        from maestro.providers.base import Message

        messages = [Message(role="user", content="Hello")]
        result = _convert_messages_to_wire(messages)

        assert len(result) == 1
        assert result[0] == {"role": "user", "content": "Hello"}

    def test_convert_system_message_to_wire(self):
        """_convert_messages_to_wire produces correct system message format."""
        from maestro.providers.copilot import _convert_messages_to_wire
        from maestro.providers.base import Message

        messages = [Message(role="system", content="You are helpful")]
        result = _convert_messages_to_wire(messages)

        assert len(result) == 1
        assert result[0] == {"role": "system", "content": "You are helpful"}

    def test_convert_assistant_message_to_wire(self):
        """_convert_messages_to_wire produces correct assistant message format."""
        from maestro.providers.copilot import _convert_messages_to_wire
        from maestro.providers.base import Message

        messages = [Message(role="assistant", content="Hi there")]
        result = _convert_messages_to_wire(messages)

        assert len(result) == 1
        assert result[0] == {"role": "assistant", "content": "Hi there"}

    def test_convert_assistant_message_with_tool_calls_to_wire(self):
        """Assistant message with tool_calls includes them in wire format."""
        from maestro.providers.copilot import _convert_messages_to_wire
        from maestro.providers.base import Message, ToolCall

        messages = [
            Message(
                role="assistant",
                content="I'll help",
                tool_calls=[
                    ToolCall(id="call_123", name="read_file", arguments={"path": "/tmp/file"})
                ]
            )
        ]
        result = _convert_messages_to_wire(messages)

        assert len(result) == 1
        assert result[0]["role"] == "assistant"
        assert result[0]["content"] == "I'll help"
        assert "tool_calls" in result[0]
        assert len(result[0]["tool_calls"]) == 1
        assert result[0]["tool_calls"][0]["id"] == "call_123"
        assert result[0]["tool_calls"][0]["type"] == "function"
        assert result[0]["tool_calls"][0]["function"]["name"] == "read_file"

    def test_convert_tool_result_to_wire(self):
        """_convert_messages_to_wire produces correct tool result format."""
        from maestro.providers.copilot import _convert_messages_to_wire
        from maestro.providers.base import Message

        messages = [
            Message(
                role="tool",
                content='{"result": "success"}',
                tool_call_id="call_123",
            )
        ]
        result = _convert_messages_to_wire(messages)

        assert len(result) == 1
        assert result[0]["role"] == "tool"
        assert result[0]["tool_call_id"] == "call_123"
        assert result[0]["content"] == '{"result": "success"}'

    def test_convert_tools_to_wire(self):
        """_convert_tools_to_wire produces function schema format."""
        from maestro.providers.copilot import _convert_tools_to_wire
        from maestro.providers.base import Tool

        tools = [
            Tool(
                name="read_file",
                description="Read a file",
                parameters={"type": "object", "properties": {}},
            )
        ]
        result = _convert_tools_to_wire(tools)

        assert len(result) == 1
        assert result[0]["type"] == "function"
        assert result[0]["function"]["name"] == "read_file"
        assert result[0]["function"]["description"] == "Read a file"
        assert result[0]["function"]["parameters"] == {"type": "object", "properties": {}}


class TestStream:
    """Verify the async stream method."""

    @pytest.mark.asyncio
    async def test_stream_raises_when_not_authenticated(self, tmp_path, monkeypatch):
        """stream() raises RuntimeError when not authenticated."""
        from maestro.providers.copilot import CopilotProvider
        from maestro.providers.base import Message
        from maestro import auth

        # Use empty auth file to ensure no credentials
        auth_file = tmp_path / "empty_auth.json"
        auth_file.write_text("{}")
        monkeypatch.setattr(auth, "AUTH_FILE", auth_file)

        provider = CopilotProvider()

        with pytest.raises(RuntimeError, match="Not authenticated"):
            async for _ in provider.stream(
                messages=[Message(role="user", content="Hello")],
                model="gpt-4o",
            ):
                pass

    @pytest.mark.asyncio
    async def test_stream_sends_correct_headers(self, tmp_path, monkeypatch):
        """stream() sends x-initiator and Openai-Intent headers (COPILOT-03)."""
        from maestro.providers.copilot import CopilotProvider
        from maestro.providers.base import Message
        from maestro import auth

        auth_file = tmp_path / "auth.json"
        auth_file.write_text(
            json.dumps({"github-copilot": {"access_token": "ghu_test_token"}})
        )
        monkeypatch.setattr(auth, "AUTH_FILE", auth_file)

        provider = CopilotProvider()

        captured_headers = {}

        async def mock_aiter_sse():
            return
            yield  # Make this a generator

        mock_event_source = AsyncMock()
        mock_event_source.aiter_sse = mock_aiter_sse

        # Mock aconnect_sse to capture headers - return a sync context manager
        def mock_aconnect_sse(client, method, url, **kwargs):
            nonlocal captured_headers
            captured_headers = kwargs.get("headers", {})
            # Return sync context manager (aconnect_sse is sync function returning async context)
            class MockContext:
                async def __aenter__(self):
                    return mock_event_source
                async def __aexit__(self, *args):
                    pass
            return MockContext()

        with patch("maestro.providers.copilot.aconnect_sse", mock_aconnect_sse):
            async for _ in provider.stream(
                messages=[Message(role="user", content="Hello")],
                model="gpt-4o",
            ):
                pass

        assert captured_headers.get("x-initiator") == "user"
        assert captured_headers.get("Openai-Intent") == "conversation-edits"
        assert captured_headers.get("Authorization") == "Bearer ghu_test_token"

    @pytest.mark.asyncio
    async def test_stream_yields_text_deltas(self, tmp_path, monkeypatch):
        """stream() yields text content from SSE deltas."""
        from maestro.providers.copilot import CopilotProvider
        from maestro.providers.base import Message
        from maestro import auth

        auth_file = tmp_path / "auth.json"
        auth_file.write_text(
            json.dumps({"github-copilot": {"access_token": "ghu_test"}})
        )
        monkeypatch.setattr(auth, "AUTH_FILE", auth_file)

        provider = CopilotProvider()

        # Mock SSE events
        mock_sse1 = MagicMock()
        mock_sse1.data = json.dumps({
            "choices": [{"delta": {"content": "Hello"}}]
        })
        mock_sse2 = MagicMock()
        mock_sse2.data = json.dumps({
            "choices": [{"delta": {"content": " world"}}]
        })
        mock_sse_done = MagicMock()
        mock_sse_done.data = "[DONE]"

        async def mock_aiter_sse():
            for sse in [mock_sse1, mock_sse2, mock_sse_done]:
                yield sse

        mock_event_source = AsyncMock()
        mock_event_source.aiter_sse = mock_aiter_sse

        # Mock aconnect_sse - sync function returning async context manager
        def mock_aconnect_sse(client, method, url, **kwargs):
            class MockContext:
                async def __aenter__(self):
                    return mock_event_source
                async def __aexit__(self, *args):
                    pass
            return MockContext()

        chunks = []
        with patch("maestro.providers.copilot.aconnect_sse", mock_aconnect_sse):
            async for chunk in provider.stream(
                messages=[Message(role="user", content="Hi")],
                model="gpt-4o",
            ):
                chunks.append(chunk)

        # Should yield text chunks and final Message
        assert len(chunks) == 3  # 2 text + 1 final Message
        assert chunks[0] == "Hello"
        assert chunks[1] == " world"
        assert isinstance(chunks[2], Message)
        assert chunks[2].role == "assistant"
        assert chunks[2].content == "Hello world"

    @pytest.mark.asyncio
    async def test_stream_yields_final_message(self, tmp_path, monkeypatch):
        """stream() yields final Message with complete content."""
        from maestro.providers.copilot import CopilotProvider
        from maestro.providers.base import Message
        from maestro import auth

        auth_file = tmp_path / "auth.json"
        auth_file.write_text(
            json.dumps({"github-copilot": {"access_token": "ghu_test"}})
        )
        monkeypatch.setattr(auth, "AUTH_FILE", auth_file)

        provider = CopilotProvider()

        mock_sse = MagicMock()
        mock_sse.data = json.dumps({
            "choices": [{"delta": {"content": "Response"}}]
        })
        mock_sse_done = MagicMock()
        mock_sse_done.data = "[DONE]"

        async def mock_aiter_sse():
            for sse in [mock_sse, mock_sse_done]:
                yield sse

        mock_event_source = AsyncMock()
        mock_event_source.aiter_sse = mock_aiter_sse

        # Mock aconnect_sse - sync function returning async context manager
        def mock_aconnect_sse(client, method, url, **kwargs):
            class MockContext:
                async def __aenter__(self):
                    return mock_event_source
                async def __aexit__(self, *args):
                    pass
            return MockContext()

        final_message = None
        with patch("maestro.providers.copilot.aconnect_sse", mock_aconnect_sse):
            async for chunk in provider.stream(
                messages=[Message(role="user", content="Hi")],
                model="gpt-4o",
            ):
                if isinstance(chunk, Message):
                    final_message = chunk

        assert final_message is not None
        assert final_message.role == "assistant"
        assert final_message.content == "Response"
        assert final_message.tool_calls == []

    @pytest.mark.asyncio
    async def test_stream_parses_tool_calls(self, tmp_path, monkeypatch):
        """stream() parses tool_calls from SSE deltas."""
        from maestro.providers.copilot import CopilotProvider
        from maestro.providers.base import Message
        from maestro import auth

        auth_file = tmp_path / "auth.json"
        auth_file.write_text(
            json.dumps({"github-copilot": {"access_token": "ghu_test"}})
        )
        monkeypatch.setattr(auth, "AUTH_FILE", auth_file)

        provider = CopilotProvider()

        # Tool call delta events
        mock_sse1 = MagicMock()
        mock_sse1.data = json.dumps({
            "choices": [{
                "delta": {
                    "tool_calls": [{
                        "index": 0,
                        "id": "call_123",
                        "function": {"name": "read_file", "arguments": ""}
                    }]
                }
            }]
        })
        mock_sse2 = MagicMock()
        mock_sse2.data = json.dumps({
            "choices": [{
                "delta": {
                    "tool_calls": [{
                        "index": 0,
                        "function": {"arguments": '{"path": '}
                    }]
                }
            }]
        })
        mock_sse3 = MagicMock()
        mock_sse3.data = json.dumps({
            "choices": [{
                "delta": {
                    "tool_calls": [{
                        "index": 0,
                        "function": {"arguments": '"/tmp/file.txt"}'}
                    }]
                },
                "finish_reason": "tool_calls"
            }]
        })

        async def mock_aiter_sse():
            for sse in [mock_sse1, mock_sse2, mock_sse3]:
                yield sse

        mock_event_source = AsyncMock()
        mock_event_source.aiter_sse = mock_aiter_sse

        # Mock aconnect_sse - sync function returning async context manager
        def mock_aconnect_sse(client, method, url, **kwargs):
            class MockContext:
                async def __aenter__(self):
                    return mock_event_source
                async def __aexit__(self, *args):
                    pass
            return MockContext()

        final_message = None
        with patch("maestro.providers.copilot.aconnect_sse", mock_aconnect_sse):
            async for chunk in provider.stream(
                messages=[Message(role="user", content="Read file")],
                model="gpt-4o",
            ):
                if isinstance(chunk, Message):
                    final_message = chunk

        assert final_message is not None
        assert len(final_message.tool_calls) == 1
        assert final_message.tool_calls[0].id == "call_123"
        assert final_message.tool_calls[0].name == "read_file"
        assert final_message.tool_calls[0].arguments == {"path": "/tmp/file.txt"}


@pytest.mark.integration
class TestIntegration:
    """Integration tests requiring real API credentials."""

    @pytest.mark.asyncio
    async def test_stream_integration(self):
        """Real API call with Copilot (skipped if no credentials)."""
        from maestro.providers.copilot import CopilotProvider
        from maestro.providers.base import Message
        from maestro import auth

        # Skip if no credentials
        creds = auth.get("github-copilot")
        if not creds or not creds.get("access_token"):
            pytest.skip("No GitHub Copilot credentials available")

        provider = CopilotProvider()

        chunks = []
        async for chunk in provider.stream(
            messages=[Message(role="user", content="Say 'hello' and nothing else")],
            model="gpt-4o-mini",
        ):
            chunks.append(chunk)

        # Should yield at least text chunks and final message
        assert len(chunks) >= 2
        assert isinstance(chunks[-1], Message)
        assert "hello" in chunks[-1].content.lower()


class TestRegressionGuard:
    """Placeholder to remind running full test suite."""

    def test_existing_tests_still_pass(self):
        """Marker: run full test suite to verify no regressions.

        To run: python -m pytest tests/ -v
        """
        pass
