"""GitHub Copilot provider using OpenAI Chat Completions API.

This module implements the ProviderPlugin Protocol for GitHub Copilot,
encapsulating all Copilot-specific OAuth, HTTP, SSE, and wire-format logic.
"""

import json
import logging
import time
from typing import AsyncIterator

import httpx
from httpx_sse import aconnect_sse

from maestro import auth
from maestro.providers.base import (
    Message,
    ProviderPlugin,
    Tool,
    ToolCall,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# OAuth Device Code Flow Constants
# ---------------------------------------------------------------------------
CLIENT_ID = "Ov23li8tweQw6odWQebz"
DEVICE_CODE_URL = "https://github.com/login/device/code"
ACCESS_TOKEN_URL = "https://github.com/login/oauth/access_token"
COPILOT_API_BASE = "https://api.githubcopilot.com"
SCOPE = "read:user"
POLLING_SAFETY_MARGIN = 5  # seconds extra beyond interval

class CopilotProvider:
    """GitHub Copilot provider using OpenAI Chat Completions API.

    Implements the ProviderPlugin Protocol for GitHub Copilot subscriptions.
    All Copilot-specific transport and wire-format logic is encapsulated here.
    """

    @property
    def id(self) -> str:
        """Unique provider identifier."""
        return "github-copilot"

    @property
    def name(self) -> str:
        """Human-readable provider name."""
        return "GitHub Copilot"

    def list_models(self) -> list[str]:
        """Return list of available model IDs from the Copilot API.

        Requires authentication. Fetches models dynamically so the list
        reflects ALL models available on the user's Copilot subscription
        (including non-GPT models like Gemini, Anthropic, etc.).

        Raises:
            RuntimeError: If not authenticated or API request fails.
        """
        creds = auth.get("github-copilot")
        if not creds or not creds.get("access_token"):
            raise RuntimeError(
                "Not authenticated. Run: maestro auth login github-copilot"
            )

        token = creds["access_token"]
        try:
            resp = httpx.get(
                f"{COPILOT_API_BASE}/models",
                headers={"Authorization": f"Bearer {token}"},
                timeout=10,
            )
            resp.raise_for_status()
            data = resp.json()
        except Exception as exc:
            raise RuntimeError(
                f"Failed to fetch models from Copilot API: {exc}"
            ) from exc

        # Parse response — normalise common shapes:
        # - { "models": ["id1", "id2"] }
        # - { "models": [{"id": "id1"}, ...] }
        # - { "data": [{"id": "id1"}, ...] }  (OpenAI-style)
        models: list[str] = []

        if isinstance(data, dict):
            for key in ("models", "data", "available_models", "model_ids"):
                if key not in data:
                    continue
                val = data[key]
                if isinstance(val, list):
                    for item in val:
                        if isinstance(item, str):
                            models.append(item)
                        elif isinstance(item, dict):
                            mid = item.get("id") or item.get("model") or item.get("name")
                            if isinstance(mid, str):
                                models.append(mid)
                    if models:
                        break
                elif isinstance(val, dict):
                    models = [k for k in val if isinstance(k, str)]
                    if models:
                        break

        if not models:
            raise RuntimeError(
                f"Could not parse model list from Copilot API response: {str(data)[:200]}"
            )

        return models

    async def stream(
        self,
        messages: list[Message],
        model: str,
        tools: list[Tool] | None = None,
        **kwargs: object,
    ) -> AsyncIterator[str | Message]:
        """Stream completion from GitHub Copilot Chat Completions API.

        Converts neutral Message/Tool types to OpenAI chat completions wire format,
        sends request, parses SSE stream, yields neutral types back.

        Args:
            messages: Provider-neutral conversation history.
            model: Model ID to use.
            tools: Optional list of provider-neutral tool definitions.

        Yields:
            str: Partial text chunks during streaming.
            Message: Complete assistant message when stream ends.

        Raises:
            RuntimeError: If not authenticated or API returns error.
        """
        token = self._require_token()
        extra = kwargs.get("extra")
        payload = self._build_payload(messages, model, tools, extra=extra if isinstance(extra, dict) else None)

        text_parts: list[str] = []
        tool_calls_buffer: dict[str, dict] = {}

        async with httpx.AsyncClient() as client:
            async with aconnect_sse(
                client,
                "POST",
                f"{COPILOT_API_BASE}/chat/completions",
                json=payload,
                headers={
                    "Authorization": f"Bearer {token}",
                    "x-initiator": "user",
                    "Openai-Intent": "conversation-edits",
                    "Content-Type": "application/json",
                },
                timeout=120,
            ) as event_source:
                response = event_source.response
                if not response.is_success:
                    body = await response.aread()
                    raise RuntimeError(
                        f"API error {response.status_code}: {body[:800].decode()}"
                    )

                async for sse in event_source.aiter_sse():
                    if sse.data == "[DONE]":
                        break

                    event = _parse_sse_event(sse.data)
                    if event is None:
                        continue

                    choices = event.get("choices", [])
                    if not choices:
                        continue

                    delta = choices[0].get("delta", {})

                    content = delta.get("content")
                    if content:
                        text_parts.append(content)
                        yield content

                    _accumulate_tool_call_deltas(delta.get("tool_calls", []), tool_calls_buffer)

                    finish_reason = choices[0].get("finish_reason")
                    if finish_reason in ("tool_calls", "stop", "length"):
                        break

        yield _build_final_message(text_parts, tool_calls_buffer)

    def _require_token(self) -> str:
        """Return the Copilot access token or raise RuntimeError if missing."""
        creds = auth.get("github-copilot")
        if not creds:
            raise RuntimeError(
                "Not authenticated. Run: maestro auth login github-copilot"
            )
        token = creds.get("access_token", "")
        if not token:
            raise RuntimeError(
                "Invalid credentials. Run: maestro auth login github-copilot"
            )
        return token

    def _build_payload(
        self,
        messages: list[Message],
        model: str,
        tools: list[Tool] | None,
        extra: dict | None = None,
    ) -> dict:
        """Build the JSON payload for the Copilot chat completions request."""
        payload: dict = {
            "model": model,
            "messages": _convert_messages_to_wire(messages),
            "stream": True,
        }
        converted_tools = _convert_tools_to_wire(tools) if tools else []
        if converted_tools:
            payload["tools"] = converted_tools
        # Merge supported extra kwargs (e.g. response_format for structured output)
        if extra and "response_format" in extra:
            payload["response_format"] = extra["response_format"]
        return payload

    def auth_required(self) -> bool:
        """Return True if this provider requires authentication."""
        return True

    def login(self) -> None:
        """Perform interactive authentication via GitHub Device Code flow.

        Blocks until complete or raises.
        """
        # Step 1: Request device code
        resp = httpx.post(
            DEVICE_CODE_URL,
            data={
                "client_id": CLIENT_ID,
                "scope": SCOPE,
            },
            headers={"Accept": "application/json"},
        )
        resp.raise_for_status()
        data = resp.json()

        device_code = data.get("device_code", "")
        user_code = data.get("user_code", "")
        interval = int(data.get("interval", 5))
        expires_in = int(data.get("expires_in", 900))  # Default 15 min

        if not device_code or not user_code:
            raise RuntimeError("Invalid device code response from GitHub")

        # Step 2: Show user instructions
        print(f"\n  Go to: https://github.com/login/device")
        print(f"  Enter code: {user_code}\n")

        # Step 3: Poll for token
        deadline = time.time() + expires_in
        current_interval = interval

        while time.time() < deadline:
            time.sleep(current_interval + POLLING_SAFETY_MARGIN)

            token_resp = httpx.post(
                ACCESS_TOKEN_URL,
                data={
                    "client_id": CLIENT_ID,
                    "device_code": device_code,
                    "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
                },
                headers={"Accept": "application/json"},
            )
            token_resp.raise_for_status()
            token_data = token_resp.json()

            error = token_data.get("error")

            if error == "authorization_pending":
                # Still waiting for user to authorize
                logger.debug("Authorization pending, continuing to poll...")
                continue

            elif error == "slow_down":
                # GitHub wants us to poll slower (AUTH-07)
                current_interval += 5
                logger.debug(f"Slow down received, increasing interval to {current_interval}s")
                continue

            elif error == "expired_token":
                raise RuntimeError("Device code expired. Please try again.")

            elif error == "access_denied":
                raise RuntimeError("Access denied. Authorization was declined.")

            elif error:
                raise RuntimeError(f"OAuth error: {error}")

            # Check for access_token
            access_token = token_data.get("access_token")
            if access_token:
                # Success! Store the token (ghu_... format, long-lived)
                auth.set("github-copilot", {"access_token": access_token})
                logger.debug("Successfully authenticated with GitHub Copilot")
                return

        # Timeout
        raise RuntimeError("Device code login timed out after 15 minutes")

    def is_authenticated(self) -> bool:
        """Return True if valid credentials are currently available."""
        creds = auth.get("github-copilot")
        return bool(creds and creds.get("access_token"))


# ---------------------------------------------------------------------------
# Wire format helpers (OpenAI Chat Completions API)
# ---------------------------------------------------------------------------


def _parse_sse_event(data: str) -> dict | None:
    """Parse a single SSE data string into a dict, or None on failure."""
    try:
        return json.loads(data)
    except json.JSONDecodeError:
        return None


def _accumulate_tool_call_deltas(
    delta_tool_calls: list[dict],
    tool_calls_buffer: dict[str, dict],
) -> None:
    """Merge streaming tool-call delta fragments into the buffer."""
    for tc_delta in delta_tool_calls:
        tc_index = str(tc_delta.get("index", 0))
        if tc_index not in tool_calls_buffer:
            tool_calls_buffer[tc_index] = {"id": "", "name": "", "arguments": ""}
        tc_buf = tool_calls_buffer[tc_index]
        if "id" in tc_delta:
            tc_buf["id"] = tc_delta["id"]
        if tc_delta.get("function", {}).get("name"):
            tc_buf["name"] = tc_delta["function"]["name"]
        if tc_delta.get("function", {}).get("arguments"):
            tc_buf["arguments"] += tc_delta["function"]["arguments"]


def _build_final_message(
    text_parts: list[str],
    tool_calls_buffer: dict[str, dict],
) -> Message:
    """Construct the final assistant Message from accumulated stream data."""
    tool_calls = []
    for tc_buf in tool_calls_buffer.values():
        if tc_buf["id"] and tc_buf["name"]:
            try:
                args = json.loads(tc_buf["arguments"]) if tc_buf["arguments"] else {}
            except json.JSONDecodeError:
                args = {}
            tool_calls.append(
                ToolCall(id=tc_buf["id"], name=tc_buf["name"], arguments=args)
            )
    return Message(
        role="assistant",
        content="".join(text_parts),
        tool_calls=tool_calls,
    )


def _convert_messages_to_wire(messages: list[Message]) -> list[dict]:
    """Convert neutral Messages to OpenAI chat completions format.

    Maps provider-neutral Message types to OpenAI chat completions wire format.
    """
    result: list[dict] = []

    for msg in messages:
        if msg.role == "user":
            result.append({
                "role": "user",
                "content": msg.content,
            })
        elif msg.role == "assistant":
            wire_msg: dict = {
                "role": "assistant",
                "content": msg.content,
            }
            # Include tool_calls if present
            if msg.tool_calls:
                wire_msg["tool_calls"] = [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.name,
                            "arguments": json.dumps(tc.arguments),
                        },
                    }
                    for tc in msg.tool_calls
                ]
            result.append(wire_msg)
        elif msg.role == "system":
            result.append({
                "role": "system",
                "content": msg.content,
            })
        elif msg.role == "tool":
            result.append({
                "role": "tool",
                "tool_call_id": msg.tool_call_id or "",
                "content": msg.content,
            })

    return result


def _convert_tools_to_wire(tools: list[Tool]) -> list[dict]:
    """Convert neutral Tools to OpenAI function format.

    Maps provider-neutral Tool definitions to OpenAI function calling format.
    """
    return [
        {
            "type": "function",
            "function": {
                "name": tool.name,
                "description": tool.description,
                "parameters": tool.parameters,
            },
        }
        for tool in tools
    ]

