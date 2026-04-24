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


def _convert_messages_to_input(messages: list[Message]) -> tuple[list, str]:
    """Convert neutral Message objects to ChatGPT Responses API wire format.

    Args:
        messages: Neutral message list from the agentic loop.

    Returns:
        A tuple of ``(input_items, instructions)`` where *input_items* is the
        list of request items and *instructions* is the system-prompt string
        (empty string if none was found).
    """
    input_items: list = []
    instructions: str = ""
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
            if msg.tool_calls:
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
            input_items.append(
                {
                    "type": "function_call_output",
                    "call_id": msg.tool_call_id,
                    "output": msg.content,
                }
            )
    return input_items, instructions


def _convert_tools_to_chatgpt(tools: list[Tool]) -> list[dict]:
    """Convert neutral Tool objects to ChatGPT Responses API tool format.

    Args:
        tools: Neutral tool list.

    Returns:
        List of ChatGPT-formatted tool dicts.
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


def _parse_sse_events(response: httpx.Response) -> tuple[list[str], list[ToolCall]]:
    """Parse SSE lines from a streaming Responses API response.

    Accumulates text delta strings and fully-assembled ToolCall objects.

    Args:
        response: An open ``httpx.Response`` from a streaming request.

    Returns:
        A tuple of ``(text_parts, tool_calls)``.
    """
    text_parts: list[str] = []
    tool_calls: list[ToolCall] = []

    for line in response.iter_lines():
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
                # Responses API uses 'call_id' for function_call_output
                # references; 'id' is the output-item ID.
                tool_call_id = item.get("call_id") or item.get("id", "")
                tool_calls.append(
                    ToolCall(
                        id=tool_call_id,
                        name=item.get("name", ""),
                        arguments=json.loads(item.get("arguments", "{}")),
                    )
                )

    return text_parts, tool_calls


def _assemble_response(text_parts: list[str], tool_calls: list[ToolCall]) -> list:
    """Build the final result list from accumulated SSE data.

    Returns text-delta strings followed by the consolidated ``Message``.

    Args:
        text_parts: Individual text delta strings from the stream.
        tool_calls: Completed tool calls collected from the stream.

    Returns:
        List whose items are text-delta strings (for streaming display) plus a
        final ``Message`` with role ``"assistant"``.
    """
    result: list = []
    if text_parts:
        result.extend(text_parts)
    final_content = "".join(text_parts)
    result.append(
        Message(role="assistant", content=final_content, tool_calls=tool_calls)
    )
    return result


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

    input_items, instructions = _convert_messages_to_input(messages)
    chatgpt_tools = _convert_tools_to_chatgpt(tools)

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

        text_parts, tool_calls = _parse_sse_events(r)

    return _assemble_response(text_parts, tool_calls)


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


def _collect_stream_chunks(
    stream_results: list,
) -> tuple[str, list[ToolCall]]:
    """Extract final text and tool calls from a list of stream chunks.

    Args:
        stream_results: List of chunks returned by the streaming call; items are
            either ``str`` (text delta) or ``Message`` (final assembled response).

    Returns:
        A tuple of ``(final_text, tool_calls)``.

    Raises:
        RuntimeError: If no output was received at all.
    """
    text_parts: list[str] = []
    tool_calls: list[ToolCall] = []
    final_message: Message | None = None

    for chunk in stream_results:
        if isinstance(chunk, str):
            text_parts.append(chunk)
        elif isinstance(chunk, Message):
            final_message = chunk
            tool_calls = chunk.tool_calls

    if text_parts:
        return "".join(text_parts), tool_calls
    if final_message is not None:
        return final_message.content, tool_calls
    raise RuntimeError("No output received from agent loop")


def _check_tool_loop(
    recent_tool_signatures: list[str],
    tool_calls: list[ToolCall],
    max_repeated: int,
) -> None:
    """Detect an infinite tool-call loop and raise if one is found.

    Appends the current call signature to *recent_tool_signatures* (mutating it
    in place) and raises ``RuntimeError`` when the last *max_repeated* signatures
    are identical.

    Args:
        recent_tool_signatures: Rolling window of previous call signatures (mutated).
        tool_calls: Current iteration's tool calls.
        max_repeated: How many consecutive identical signatures trigger the guard.

    Raises:
        RuntimeError: If the same tool call pattern has repeated *max_repeated* times.
    """
    call_sig = json.dumps(
        [{"name": tc.name, "args": tc.arguments} for tc in tool_calls],
        sort_keys=True,
    )
    recent_tool_signatures.append(call_sig)
    if len(recent_tool_signatures) > max_repeated:
        recent_tool_signatures.pop(0)
    if (
        len(recent_tool_signatures) == max_repeated
        and len(set(recent_tool_signatures)) == 1
    ):
        raise RuntimeError(
            f"Agent loop detected: same tool call repeated {max_repeated} times"
            f" — {call_sig[:200]}"
        )


def _execute_tools_and_append(
    tool_calls: list[ToolCall],
    neutral_messages: list[Message],
    final_text: str,
    wd: Path,
    auto: bool,
    on_tool_start,
) -> tuple[bool, None]:
    """Append the assistant tool-call message and execute each tool.

    Mutates *neutral_messages* in place, adding the assistant request message
    followed by one tool-result message per call.

    Args:
        tool_calls: Tool calls to execute.
        neutral_messages: Conversation history to append to (mutated).
        final_text: The assistant text that accompanied the tool calls.
        wd: Working directory for tool execution.
        auto: Whether destructive tools are auto-approved.
        on_tool_start: Optional callable to invoke before first tool execution.

    Returns:
        ``(new_auto, None)`` where *new_auto* reflects any auto-escalation that
        occurred during execution.
    """
    neutral_messages.append(
        Message(
            role="assistant",
            content=final_text,
            tool_calls=tool_calls,
        )
    )

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

    return auto, None


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
    use_legacy_path = tokens is not None
    wd = workdir or Path.cwd()

    neutral_messages = _convert_messages_to_neutral(messages, instructions)
    tools = _convert_tool_schemas(TOOL_SCHEMAS)

    recent_tool_signatures: list[str] = []
    MAX_REPEATED_CALLS = 3

    for _iteration in range(max_iterations):
        # --- stream collection ---
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

        final_text, tool_calls = _collect_stream_chunks(stream_results)

        # No tool calls → final answer
        if not tool_calls:
            return final_text

        # --- loop detection ---
        _check_tool_loop(recent_tool_signatures, tool_calls, MAX_REPEATED_CALLS)

        # --- tool execution ---
        auto, _ = _execute_tools_and_append(
            tool_calls, neutral_messages, final_text, wd, auto, on_tool_start
        )
        on_tool_start = None  # already consumed (or not provided)

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
