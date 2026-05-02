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

_ = ProviderPlugin

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

_CODEX_MINI = "gpt-5.1-codex-mini"
_GPT54 = "gpt-5.4"
_GPT54_MINI = "gpt-5.4-mini"
_GPT54_NANO = "gpt-5.4-nano"

# Fallback model list (used when models.dev is unreachable)
FALLBACK_MODELS = [
    _GPT54,
    _GPT54_MINI,
    "gpt-5.2",
    "gpt-5-codex",
    "gpt-5.1-codex-max",
    _CODEX_MINI,
    _GPT54_NANO,
    "gpt-5.1",
]

# Dynamic model list — fetched from models.dev on first access
MODELS = fetch_models()

# Aliases: what the user types -> what the API expects
MODEL_ALIASES: dict[str, str] = {
    "codex-mini-latest": _CODEX_MINI,
    "gpt-5-codex-mini": _CODEX_MINI,
    "gpt-5.1-codex": "gpt-5-codex",
    "gpt-5.2-codex": "gpt-5-codex",
    "gpt-5.3-codex": "gpt-5-codex",
    "gpt-5.3-codex-spark": "gpt-5-codex",
    "gpt-5": _GPT54,
    "gpt-5-mini": _GPT54_MINI,
    "gpt-5-nano": _GPT54_NANO,
}

# Default model for ChatGPT Plus/Pro accounts via Codex endpoint
DEFAULT_MODEL = _GPT54_MINI


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
        input_items.extend(_message_to_input_items(msg))

    return input_items


def _assistant_input_items(msg: Message) -> list[dict]:
    items = [
        {
            "type": "function_call",
            "call_id": tc.id,
            "name": tc.name,
            "arguments": json.dumps(tc.arguments),
        }
        for tc in msg.tool_calls
    ]
    items.append(
        {
            "type": "message",
            "role": "assistant",
            "content": [{"type": "output_text", "text": msg.content}],
        }
    )
    return items


def _message_to_input_items(msg: Message) -> list[dict]:
    if msg.role == "user":
        return [
            {
                "type": "message",
                "role": "user",
                "content": [{"type": "input_text", "text": msg.content}],
            }
        ]
    if msg.role == "assistant":
        return _assistant_input_items(msg)
    if msg.role == "tool":
        return [
            {
                "type": "function_call_output",
                "call_id": msg.tool_call_id or "",
                "output": msg.content,
            }
        ]
    return []


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


async def _iter_sse_data_lines(response: httpx.Response) -> AsyncIterator[str]:
    """Yield SSE data payloads without requiring a specific content-type header."""
    data_lines: list[str] = []

    async for line in response.aiter_lines():
        if line == "" and data_lines:
            yield "\n".join(data_lines)
            data_lines = []
        if line == "":
            continue
        if line.startswith(":"):
            continue
        if line.startswith("data:"):
            data_lines.append(line[5:].lstrip())

    if data_lines:
        yield "\n".join(data_lines)


# Re-export TokenSet for backward compatibility
TokenSet = auth.TokenSet


def _dispatch_chatgpt_event(
    event: dict,
    text_parts: list[str],
    tool_calls: list[ToolCall],
) -> str | None:
    """Dispatch a parsed ChatGPT SSE event. Returns text delta or None."""
    etype = event.get("type", "")
    if etype == "response.output_text.delta":
        return _append_text_delta(event, text_parts)
    if etype == "response.output_item.done":
        _collect_function_call(event, tool_calls)
        return None
    if etype == "response.done":
        return _collect_done_message_text(event, text_parts)
    return None


def _append_text_delta(event: dict, text_parts: list[str]) -> str:
    delta = event.get("delta", "")
    text_parts.append(delta)
    return delta


def _collect_function_call(event: dict, tool_calls: list[ToolCall]) -> None:
    item = event.get("item", {})
    if item.get("type") == "function_call":
        tool_calls.append(_parse_tool_call(item))


def _collect_done_message_text(event: dict, text_parts: list[str]) -> str | None:
    if text_parts:
        return None

    resp = event.get("response", {})
    for out in resp.get("output", []):
        text = _extract_output_text(out)
        if text is not None:
            text_parts.append(text)
            return text
    return None


def _extract_output_text(output_item: dict) -> str | None:
    if output_item.get("type") != "message":
        return None

    for part in output_item.get("content", []):
        if part.get("type") == "output_text":
            return part["text"]
    return None


def _build_stream_payload(
    api_model: str,
    input_items: list[dict],
    tool_schemas: list[dict],
    instructions: str | None,
    extra: object,
) -> dict:
    payload: dict = {
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
    if isinstance(extra, dict) and "response_format" in extra:
        payload["response_format"] = extra["response_format"]
    return payload


async def _stream_chatgpt_response(
    payload: dict,
    tokens: auth.TokenSet,
    text_parts: list[str],
    tool_calls: list[ToolCall],
) -> AsyncIterator[str]:
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
                    f"API error {response.status_code}: {body[:800].decode(errors='replace')}"
                )

            async for data in _iter_sse_data_lines(response):
                if data == "[DONE]":
                    break

                try:
                    event = json.loads(data)
                except json.JSONDecodeError:
                    continue

                text_chunk = _dispatch_chatgpt_event(event, text_parts, tool_calls)
                if text_chunk is not None:
                    yield text_chunk


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
        **kwargs: object,
    ) -> AsyncIterator[str | Message]:
        """Stream completion from ChatGPT Responses API."""
        creds = auth.get("chatgpt")
        if not creds:
            raise RuntimeError("Not authenticated. Run: maestro auth login chatgpt")

        tokens = auth.TokenSet(**creds)
        tokens = auth.ensure_valid(tokens)
        api_model = resolve_model(model)
        input_items = _convert_messages_to_input(messages)
        tool_schemas = _convert_tools_to_schemas(tools) if tools else []
        instructions = _extract_instructions(messages)
        payload = _build_stream_payload(
            api_model,
            input_items,
            tool_schemas,
            instructions,
            kwargs.get("extra"),
        )

        text_parts: list[str] = []
        tool_calls: list[ToolCall] = []

        async for text_chunk in _stream_chatgpt_response(
            payload,
            tokens,
            text_parts,
            tool_calls,
        ):
            yield text_chunk

        yield Message(
            role="assistant",
            content="".join(text_parts),
            tool_calls=tool_calls,
        )

    def auth_required(self) -> bool:
        """Return True if this provider requires authentication."""
        return True

    def login(self, method: str = "browser") -> None:
        """Perform interactive authentication.

        Delegates to existing auth.login() for ChatGPT OAuth.
        Blocks until complete or raises.

        Args:
            method: Authentication method — "browser" (default) or "device".
        """
        auth.login(method)

    def is_authenticated(self) -> bool:
        """Return True if valid credentials are currently available."""
        return auth.get("chatgpt") is not None
