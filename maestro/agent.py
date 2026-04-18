"""
LangGraph agent that uses LLM providers via the provider plugin system.
"""

import json
import asyncio
import httpx
from pathlib import Path
from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage, AIMessage
from langgraph.func import entrypoint, task

from maestro import auth
from maestro.tools import execute_tool, TOOL_SCHEMAS
from maestro.providers.base import Message, Tool, ToolCall
from maestro.providers.registry import get_default_provider

# Keep ChatGPT imports for _call_responses_api (used by models --check)
# and for backward-compatible _run_agentic_loop legacy path
from maestro.providers.chatgpt import (
    RESPONSES_ENDPOINT,
    _reasoning_effort,
    _headers,
    resolve_model,
)


def _run_httpx_stream_sync(
    messages: list[Message],
    model: str,
    tools: list[Tool],
    tokens: auth.TokenSet,
) -> list:
    """Synchronous wrapper for legacy httpx.stream() SSE loop.

    Backward-compatibility shim for original tests that mock httpx.stream.
    Converts neutral types back to ChatGPT wire format and parses SSE.
    """
    api_model = resolve_model(model)

    # Convert neutral messages to ChatGPT input format
    input_items = []
    instructions = ""
    for msg in messages:
        if msg.role == "system":
            instructions = msg.content
        elif msg.role == "user":
            input_items.append(
                {
                    "type": "message",
                    "role": "user",
                    "content": [{"type": "input_text", "text": msg.content}],
                }
            )
        elif msg.role == "assistant":
            # Handle assistant messages with tool calls
            if msg.tool_calls:
                # This is a tool-call response - convert to function_call items
                for tc in msg.tool_calls:
                    input_items.append(
                        {
                            "type": "function_call",
                            "call_id": tc.id,
                            "name": tc.name,
                            "arguments": json.dumps(tc.arguments),
                        }
                    )
            else:
                input_items.append(
                    {
                        "type": "message",
                        "role": "assistant",
                        "content": [{"type": "output_text", "text": msg.content}],
                    }
                )
        elif msg.role == "tool":
            # Tool output becomes function_call_output
            input_items.append(
                {
                    "type": "function_call_output",
                    "call_id": msg.tool_call_id,
                    "output": msg.content,
                }
            )

    # Convert neutral tools to ChatGPT tool format
    chatgpt_tools = []
    for tool in tools:
        chatgpt_tools.append(
            {
                "type": "function",
                "name": tool.name,
                "description": tool.description,
                "parameters": tool.parameters,
            }
        )

    import sys as _sys
    payload: dict = {
        "model": api_model,
        "instructions": instructions or "You are a helpful assistant.",
        "input": input_items,
        "stream": True,
        "store": False,
    }

    if chatgpt_tools:
        payload["tools"] = chatgpt_tools
        payload["tool_choice"] = "auto"

    text_parts: list[str] = []
    tool_calls: list[ToolCall] = []

    with httpx.stream(
        "POST",
        RESPONSES_ENDPOINT,
        json=payload,
        headers=_headers(tokens),
        timeout=120,
    ) as r:
        if not r.is_success:
            body = r.read().decode()
            raise RuntimeError(f"API error {r.status_code}: {body[:800]}")

        for line in r.iter_lines():
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
                text_parts.append(event.get("delta", ""))
            elif etype == "response.output_item.done":
                item = event.get("item", {})
                if item.get("type") == "function_call":
                    # Responses API uses 'call_id' for function_call_output references;
                    # 'id' is the output-item ID. Use call_id when present.
                    tool_call_id = item.get("call_id") or item.get("id", "")
                    tool_calls.append(
                        ToolCall(
                            id=tool_call_id,
                            name=item.get("name", ""),
                            arguments=json.loads(item.get("arguments", "{}")),
                        )
                    )

    # Build final result: text deltas as separate chunks, then final Message
    result: list = []
    if text_parts:
        # Return deltas as individual string chunks for streaming
        result.extend(text_parts)
    # Always return final message with tool calls (may be empty)
    final_content = "".join(text_parts)
    result.append(
        Message(role="assistant", content=final_content, tool_calls=tool_calls)
    )
    return result


def _convert_tool_schemas(schemas: list[dict]) -> list[Tool]:
    """Convert raw tool schema dicts to neutral Tool types."""
    return [
        Tool(
            name=s["name"],
            description=s.get("description", ""),
            parameters=s.get("parameters", {}),
        )
        for s in schemas
    ]


def _convert_messages_to_neutral(
    messages: list[BaseMessage], instructions: str | None = None
) -> list[Message]:
    """Convert LangChain messages to neutral Message types."""
    result: list[Message] = []

    # Add system message as first message if provided
    if instructions:
        result.append(Message(role="system", content=instructions))

    for msg in messages:
        if isinstance(msg, HumanMessage):
            result.append(Message(role="user", content=msg.content))
        elif isinstance(msg, AIMessage):
            result.append(Message(role="assistant", content=msg.content))
        # SystemMessage is handled above via instructions parameter

    return result


def _run_provider_stream_sync(
    provider,
    messages: list[Message],
    model: str,
    tools: list[Tool] | None = None,
    on_text=None,
):
    """Synchronous wrapper for async provider.stream().

    Since _run_agentic_loop is synchronous but provider.stream() is async,
    we use asyncio.run() to bridge the gap.

    on_text: optional callable(str) invoked immediately for each text chunk,
             enabling real-time terminal output even though the outer loop is sync.
    """
    async def _inner():
        result = []
        async for chunk in provider.stream(messages, model, tools):
            if isinstance(chunk, str) and on_text is not None:
                on_text(chunk)
            result.append(chunk)
        return result

    return asyncio.run(_inner())


def _run_agentic_loop(
    messages: list[BaseMessage],
    model: str,
    instructions: str,
    provider=None,
    workdir: Path | None = None,
    auto: bool = False,
    max_iterations: int = 20,
    *,
    tokens: auth.TokenSet | None = None,
    on_text=None,
    on_tool_start=None,
) -> str:
    """Run the agentic loop using provider.stream() for HTTP delegation.

    Args:
        messages: LangChain messages (HumanMessage, AIMessage, etc.)
        model: Model identifier to use
        instructions: System prompt/instructions
        provider: ProviderPlugin instance for streaming (runtime path)
        workdir: Working directory for tool execution
        auto: Whether to auto-execute destructive tools without confirmation
        max_iterations: Maximum tool-call iterations before giving up
        tokens: TokenSet for legacy httpx-based streaming (backward compatibility)
        on_text: Optional callable(str) invoked with each text chunk as it arrives.
                 Use for real-time streaming output to the terminal.
        on_tool_start: Optional callable() invoked before executing tool calls.
                       Use to stop a spinner before tool confirmation prompts.

    Returns:
        Final text response from the model

    Raises:
        RuntimeError: If provider is unauthenticated or API returns error

    Note:
        Either `provider` OR `tokens` must be provided. The provider-based path
        is used at runtime; the tokens-based path is preserved for backward
        compatibility with existing tests that mock httpx.stream().
    """
    # Determine which path to use: provider-based (new) or tokens-based (legacy)
    use_legacy_path = tokens is not None

    # Ensure workdir is set
    wd = workdir or Path.cwd()

    # Convert messages to neutral types
    neutral_messages = _convert_messages_to_neutral(messages, instructions)

    # Convert tool schemas to neutral Tool types
    tools = _convert_tool_schemas(TOOL_SCHEMAS)

    # Track recent tool calls to detect infinite loops (same tool+args repeated)
    recent_tool_signatures: list[str] = []
    MAX_REPEATED_CALLS = 3

    for iteration in range(max_iterations):
        # Stream from provider (sync wrapper for async generator)
        if use_legacy_path:
            stream_results = _run_httpx_stream_sync(
                neutral_messages, model, tools, tokens
            )
        else:
            if provider is None:
                raise RuntimeError(
                    "Either provider or tokens must be provided to _run_agentic_loop"
                )
            stream_results = _run_provider_stream_sync(
                provider, neutral_messages, model, tools, on_text=on_text
            )

        text_parts: list[str] = []
        tool_calls: list[ToolCall] = []
        final_message: Message | None = None

        for chunk in stream_results:
            if isinstance(chunk, str):
                text_parts.append(chunk)
                # on_text already called inside _run_provider_stream_sync for real-time output
            elif isinstance(chunk, Message):
                # Final message with complete response
                final_message = chunk
                tool_calls = chunk.tool_calls

        # Determine final text: use streamed deltas if any, else use final message content
        if text_parts:
            final_text = "".join(text_parts)
        elif final_message:
            final_text = final_message.content
        else:
            raise RuntimeError("No output received from agent loop")

        # No tool calls → final answer
        if not tool_calls:
            return final_text

        # Detect infinite loop: same tool call signature repeated consecutively
        call_sig = json.dumps(
            [{"name": tc.name, "args": tc.arguments} for tc in tool_calls],
            sort_keys=True,
        )
        recent_tool_signatures.append(call_sig)
        if len(recent_tool_signatures) > MAX_REPEATED_CALLS:
            recent_tool_signatures.pop(0)
        if (
            len(recent_tool_signatures) == MAX_REPEATED_CALLS
            and len(set(recent_tool_signatures)) == 1
        ):
            raise RuntimeError(
                f"Agent loop detected: same tool call repeated {MAX_REPEATED_CALLS} times — {call_sig[:200]}"
            )

        # Preserve the assistant message that requested the tools
        neutral_messages.append(
            Message(
                role="assistant",
                content=final_text,
                tool_calls=tool_calls,
            )
        )

        # Execute each tool and append results as tool messages
        for tc in tool_calls:
            if on_tool_start is not None:
                on_tool_start()
                on_tool_start = None  # only fire once per iteration
            result, auto_escalated = execute_tool(tc.name, tc.arguments, wd, auto=auto)
            if auto_escalated:
                auto = True
                print("  [maestro] Auto-approving all remaining tool calls.")
            neutral_messages.append(
                Message(
                    role="tool",
                    content=json.dumps(result),
                    tool_call_id=tc.id,
                )
            )

    raise RuntimeError(f"Agent loop exceeded max_iterations={max_iterations}")


def _call_responses_api(
    model: str,
    messages: list[BaseMessage],
    tokens: auth.TokenSet,
) -> str:
    """Single-shot call to the Responses API (no tool loop). Used by models --check."""
    api_model = resolve_model(model)

    input_items = []
    instructions = ""
    for msg in messages:
        if isinstance(msg, SystemMessage):
            instructions = msg.content
        elif isinstance(msg, HumanMessage):
            input_items.append(
                {
                    "type": "message",
                    "role": "user",
                    "content": [{"type": "input_text", "text": msg.content}],
                }
            )
        elif isinstance(msg, AIMessage):
            input_items.append(
                {
                    "type": "message",
                    "role": "assistant",
                    "content": [{"type": "output_text", "text": msg.content}],
                }
            )

    payload = {
        "model": api_model,
        "instructions": instructions or "You are a helpful assistant.",
        "input": input_items,
        "stream": True,
        "store": False,
        "reasoning": {
            "effort": _reasoning_effort(api_model),
            "summary": "auto",
        },
        "text": {"verbosity": "medium"},
        "include": ["reasoning.encrypted_content"],
    }

    with httpx.stream(
        "POST",
        RESPONSES_ENDPOINT,
        json=payload,
        headers=_headers(tokens),
        timeout=120,
    ) as r:
        if not r.is_success:
            body = r.read().decode()
            raise RuntimeError(f"API error {r.status_code}: {body[:800]}")

        text_parts: list[str] = []
        for line in r.iter_lines():
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
                text_parts.append(event.get("delta", ""))
            elif etype == "response.done":
                resp = event.get("response", {})
                for item in resp.get("output", []):
                    if item.get("type") == "message":
                        for part in item.get("content", []):
                            if part.get("type") == "output_text" and not text_parts:
                                text_parts.append(part["text"])

    if text_parts:
        return "".join(text_parts)
    raise RuntimeError("No output_text received from streaming response")


def run(
    model_name: str,
    prompt: str,
    system: str | None = None,
    workdir: Path | None = None,
    auto: bool = False,
    provider=None,
    stream_callback=None,
    on_tool_start=None,
) -> str:
    """Run the agentic loop with the given model and prompt.

    Uses the given provider, or falls back to get_default_provider() to
    discover and use the first authenticated provider.

    Args:
        stream_callback: Optional callable(str) invoked with each text chunk
                         as it arrives from the model. Pass a printing function
                         for real-time terminal output.
    """
    # Use provided provider or fall back to default
    if provider is None:
        provider = get_default_provider()

    wd = workdir or Path.cwd()
    instructions = (
        system or "You are a helpful assistant with access to file system tools."
    )

    @task
    def call_agent(msgs: list[BaseMessage]) -> AIMessage:
        text = _run_agentic_loop(
            messages=msgs,
            model=model_name,
            instructions=instructions,
            provider=provider,
            workdir=wd,
            auto=auto,
            on_text=stream_callback,
            on_tool_start=on_tool_start,
        )
        return AIMessage(content=text)

    @entrypoint()
    def agent(msgs: list[BaseMessage]) -> list[BaseMessage]:
        response = call_agent(msgs).result()
        return [*msgs, response]

    msgs: list[BaseMessage] = [HumanMessage(content=prompt)]
    result = agent.invoke(msgs)
    return result[-1].content
