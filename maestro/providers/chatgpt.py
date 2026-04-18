"""ChatGPT provider using OpenAI Responses API.

This module implements the ProviderPlugin Protocol for ChatGPT,
encapsulating all ChatGPT-specific HTTP, SSE, and wire-format logic.
"""

import json
import logging
import time
from pathlib import Path
from typing import AsyncIterator

import httpx

from maestro import auth
from maestro.providers.base import (
    Message,
    ProviderPlugin,
    Tool,
    ToolCall,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Dynamic model catalog from models.dev
# ---------------------------------------------------------------------------
MODELS_DEV_URL = "https://models.dev/api.json"
_CACHE_TTL = 3600  # 1 hour
_CACHE_DIR = Path.home() / ".cache" / "maestro"


def _cache_path() -> Path:
    _CACHE_DIR.mkdir(parents=True, exist_ok=True)
    return _CACHE_DIR / "models-dev.json"


def _read_cache() -> list[str] | None:
    """Read cached models list if still fresh."""
    path = _cache_path()
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text())
        if time.time() - data.get("ts", 0) < _CACHE_TTL:
            return data.get("models", [])
    except (json.JSONDecodeError, OSError):
        pass
    return None


def _write_cache(models: list[str]) -> None:
    try:
        _cache_path().write_text(json.dumps({"ts": time.time(), "models": models}))
    except OSError:
        pass


def _is_codex_model(model_id: str) -> bool:
    """Filter for models usable via the ChatGPT Codex endpoint."""
    return "gpt-5" in model_id or "codex" in model_id


def fetch_models(*, force: bool = False) -> list[str]:
    """Fetch OpenAI model list from models.dev catalog.

    Returns filtered list of codex-compatible models.
    Falls back to FALLBACK_MODELS on any error.
    """
    if not force:
        cached = _read_cache()
        if cached:
            return cached

    try:
        resp = httpx.get(MODELS_DEV_URL, timeout=10, follow_redirects=True)
        resp.raise_for_status()
        catalog = resp.json()
        openai_entry = catalog.get("openai", {})
        all_models = list(openai_entry.get("models", {}).keys())
        filtered = sorted([m for m in all_models if _is_codex_model(m)])
        if filtered:
            _write_cache(filtered)
            return filtered
    except Exception as exc:
        logger.debug("Failed to fetch models from models.dev: %s", exc)

    return FALLBACK_MODELS.copy()


def _available_cache_path() -> Path:
    _CACHE_DIR.mkdir(parents=True, exist_ok=True)
    return _CACHE_DIR / "models-available.json"


def probe_available_models(
    tokens: "auth.TokenSet",
    *,
    force: bool = False,
    ttl: int = 86400,
) -> list[str]:
    """Probe which models are available for the authenticated account.

    Results are cached for ``ttl`` seconds (default 24 h).
    Use ``force=True`` or ``maestro models --check`` to re-probe.
    """
    path = _available_cache_path()

    if not force and path.exists():
        try:
            data = json.loads(path.read_text())
            if time.time() - data.get("ts", 0) < ttl:
                return data.get("models", [])
        except (json.JSONDecodeError, OSError):
            pass

    # Late import to avoid circular dependency
    from maestro.agent import _call_responses_api
    from langchain_core.messages import HumanMessage

    all_models = fetch_models()
    msgs = [HumanMessage(content="hi")]
    available: list[str] = []

    for m in all_models:
        try:
            _call_responses_api(m, msgs, tokens)
            available.append(m)
        except RuntimeError:
            pass

    if available:
        try:
            path.write_text(json.dumps({"ts": time.time(), "models": available}))
        except OSError:
            pass

    return available


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

# Fallback model list (used when models.dev is unreachable)
FALLBACK_MODELS = [
    "gpt-5.4",
    "gpt-5.4-mini",
    "gpt-5.2",
    "gpt-5-codex",
    "gpt-5.1-codex-max",
    "gpt-5.1-codex-mini",
    "gpt-5.4-nano",
    "gpt-5.1",
]

# Dynamic model list — fetched from models.dev on first access
MODELS = fetch_models()

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
    Preserves tool-call context by emitting function_call items before
    their corresponding function_call_output items.
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
            # First emit any tool_calls as function_call items
            for tc in msg.tool_calls:
                input_items.append({
                    "type": "function_call",
                    "call_id": tc.id,   # call_id links to function_call_output
                    "name": tc.name,
                    "arguments": json.dumps(tc.arguments),
                })
            # Then emit the assistant message content
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
        id=item.get("call_id") or item.get("id", ""),
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
        """Return list of available model IDs (fetched dynamically)."""
        return fetch_models()

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
