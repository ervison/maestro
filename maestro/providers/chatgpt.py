"""ChatGPT provider using OpenAI Responses API.

This module implements the ProviderPlugin Protocol for ChatGPT,
encapsulating all ChatGPT-specific HTTP, SSE, and wire-format logic.
"""

import json
import httpx
from typing import AsyncIterator

from maestro import auth
from maestro.providers.base import (
    Message,
    ProviderPlugin,
    Tool,
    ToolCall,
)

# Constants migrated from maestro/agent.py
RESPONSES_ENDPOINT = f"{auth.CODEX_API_BASE}/codex/responses"

USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

_REASONING_DEFAULTS: dict[str, str] = {
    "gpt-5-codex": "high",
    "gpt-5.1-codex-max": "high",
    "gpt-5.1-codex-mini": "medium",
    "gpt-5.4": "high",
    "gpt-5.4-mini": "high",
    "gpt-5.4-nano": "high",
    "gpt-5.4-pro": "medium",
    "gpt-5.2": "high",
    "gpt-5.1": "medium",
}

# Model constants migrated from maestro/auth.py
MODELS = [
    "gpt-5.4",
    "gpt-5.4-mini",
    "gpt-5.2",
    # Extended family (may require Pro tier)
    "gpt-5-codex",
    "gpt-5.1-codex-max",
    "gpt-5.1-codex-mini",
    "gpt-5.4-nano",
    "gpt-5.1",
]

# Aliases: what the user types -> what the API expects
MODEL_ALIASES: dict[str, str] = {
    "codex-mini-latest": "gpt-5.1-codex-mini",
    "gpt-5-codex-mini": "gpt-5.1-codex-mini",
    "gpt-5.1-codex": "gpt-5-codex",
    "gpt-5.2-codex": "gpt-5-codex",
    "gpt-5.3-codex": "gpt-5-codex",
    "gpt-5.3-codex-spark": "gpt-5-codex",
    "gpt-5": "gpt-5.4",
    "gpt-5-mini": "gpt-5.4-mini",
    "gpt-5-nano": "gpt-5.4-nano",
}

# Default model for ChatGPT Plus/Pro accounts via Codex endpoint
DEFAULT_MODEL = "gpt-5.4-mini"


def resolve_model(model_id: str) -> str:
    """Resolve model alias to API model name."""
    return MODEL_ALIASES.get(model_id, model_id)


def _reasoning_effort(model: str) -> str:
    """Get default reasoning effort for a model."""
    return _REASONING_DEFAULTS.get(model, "medium")


def _headers(tokens: auth.TokenSet) -> dict:
    """Build HTTP headers for ChatGPT API requests."""
    h = {
        "Authorization": f"Bearer {tokens.access}",
        "Content-Type": "application/json",
        "Accept": "text/event-stream",
        "User-Agent": USER_AGENT,
        "originator": "codex_cli_rs",
        "OpenAI-Beta": "responses=experimental",
    }
    if tokens.account_id:
        h["chatgpt-account-id"] = tokens.account_id
    return h


def _convert_messages_to_input(messages: list[Message]) -> list[dict]:
    """Convert neutral Messages to Responses API input format.

    Maps provider-neutral Message types to ChatGPT/OpenAI wire format.
    """
    input_items: list[dict] = []

    for msg in messages:
        if msg.role == "user":
            input_items.append({
                "type": "message",
                "role": "user",
                "content": [{"type": "input_text", "text": msg.content}],
            })
        elif msg.role == "assistant":
            input_items.append({
                "type": "message",
                "role": "assistant",
                "content": [{"type": "output_text", "text": msg.content}],
            })
        elif msg.role == "system":
            # System messages are handled as instructions, not input items
            pass
        elif msg.role == "tool":
            # Tool results are handled separately
            input_items.append({
                "type": "function_call_output",
                "call_id": msg.tool_call_id or "",
                "output": msg.content,
            })

    return input_items


def _convert_tools_to_schemas(tools: list[Tool]) -> list[dict]:
    """Convert neutral Tools to ChatGPT function schemas.

    Maps provider-neutral Tool definitions to OpenAI function calling format.
    """
    return [
        {
            "type": "function",
            "name": tool.name,
            "description": tool.description,
            "parameters": tool.parameters,
        }
        for tool in tools
    ]


def _extract_instructions(messages: list[Message]) -> str | None:
    """Extract system message content for instructions field."""
    for msg in messages:
        if msg.role == "system":
            return msg.content
    return None


def _parse_tool_call(item: dict) -> ToolCall:
    """Parse wire format tool call to neutral ToolCall.

    Args:
        item: Raw function_call item from ChatGPT API response.

    Returns:
        Provider-neutral ToolCall instance.
    """
    arguments = item.get("arguments", "{}")
    try:
        parsed_args = json.loads(arguments) if isinstance(arguments, str) else arguments
    except json.JSONDecodeError:
        parsed_args = {}

    return ToolCall(
        id=item.get("id", ""),
        name=item.get("name", ""),
        arguments=parsed_args,
    )


# Re-export TokenSet for backward compatibility
TokenSet = auth.TokenSet


class ChatGPTProvider:
    """ChatGPT provider using OpenAI Responses API.

    Implements the ProviderPlugin Protocol for ChatGPT Plus/Pro subscriptions.
    All ChatGPT-specific transport and wire-format logic is encapsulated here.
    """

    @property
    def id(self) -> str:
        """Unique provider identifier."""
        return "chatgpt"

    @property
    def name(self) -> str:
        """Human-readable provider name."""
        return "ChatGPT"

    def list_models(self) -> list[str]:
        """Return list of available model IDs for this provider."""
        return MODELS.copy()

    async def stream(
        self,
        messages: list[Message],
        model: str,
        tools: list[Tool] | None = None,
    ) -> AsyncIterator[str | Message]:
        """Stream completion from ChatGPT Responses API.

        Converts neutral Message/Tool types to ChatGPT wire format,
        sends request, parses SSE stream, yields neutral types back.

        Args:
            messages: Provider-neutral conversation history.
            model: Model ID or alias to use.
            tools: Optional list of provider-neutral tool definitions.

        Yields:
            str: Partial text chunks during streaming.
            Message: Complete assistant message when stream ends.

        Raises:
            RuntimeError: If not authenticated or API returns error.
        """
        # Get credentials - check immediately before any async operations
        creds = auth.get("chatgpt")
        if not creds:
            raise RuntimeError("Not authenticated. Run: maestro auth login chatgpt")

        # Build TokenSet for headers (backward compat)
        tokens = auth.TokenSet(**creds)
        tokens = auth.ensure_valid(tokens)

        # Resolve model alias
        api_model = resolve_model(model)

        # Convert neutral messages to Responses API format
        input_items = _convert_messages_to_input(messages)

        # Convert neutral tools to Responses API format
        tool_schemas = _convert_tools_to_schemas(tools) if tools else []

        # Extract system message for instructions
        instructions = _extract_instructions(messages)

        # Build payload
        payload = {
            "model": api_model,
            "instructions": instructions or "You are a helpful assistant.",
            "input": input_items,
            "tools": tool_schemas,
            "stream": True,
            "store": False,
            "reasoning": {
                "effort": _reasoning_effort(api_model),
                "summary": "auto",
            },
            "text": {"verbosity": "medium"},
            "include": ["reasoning.encrypted_content"],
        }

        # Stream request
        async with httpx.AsyncClient() as client:
            async with client.stream(
                "POST",
                RESPONSES_ENDPOINT,
                json=payload,
                headers=_headers(tokens),
                timeout=120,
            ) as response:
                if not response.is_success:
                    body = await response.aread()
                    raise RuntimeError(
                        f"API error {response.status_code}: {body[:800].decode()}"
                    )

                text_parts: list[str] = []
                tool_calls: list[ToolCall] = []

                async for line in response.aiter_lines():
                    if not line.startswith("data: "):
                        continue
                    raw = line[6:]
                    if raw == "[DONE]":
                        break

                    try:
                        event = json.loads(raw)
                    except json.JSONDecodeError:
                        continue

                    etype = event.get("type", "")

                    if etype == "response.output_text.delta":
                        delta = event.get("delta", "")
                        text_parts.append(delta)
                        yield delta  # Yield text chunk

                    elif etype == "response.output_item.done":
                        item = event.get("item", {})
                        if item.get("type") == "function_call":
                            tool_calls.append(_parse_tool_call(item))

                    elif etype == "response.done":
                        resp = event.get("response", {})
                        for out in resp.get("output", []):
                            if out.get("type") == "message" and not text_parts:
                                for part in out.get("content", []):
                                    if part.get("type") == "output_text":
                                        text_parts.append(part["text"])

        # Yield final Message
        content = "".join(text_parts)
        yield Message(
            role="assistant",
            content=content,
            tool_calls=tool_calls,
        )

    def auth_required(self) -> bool:
        """Return True if this provider requires authentication."""
        return True

    def login(self) -> None:
        """Perform interactive authentication.

        Delegates to existing auth.login() for ChatGPT OAuth.
        Blocks until complete or raises.
        """
        auth.login()

    def is_authenticated(self) -> bool:
        """Return True if valid credentials are currently available."""
        return auth.get("chatgpt") is not None
