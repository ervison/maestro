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
from maestro.providers.chatgpt import (
    RESPONSES_ENDPOINT,
    _reasoning_effort,
    _headers,
    resolve_model,
)


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


def _run_provider_stream_sync(provider, messages: list[Message], model: str, tools: list[Tool] | None = None):
    """Synchronous wrapper for async provider.stream().

    Since _run_agentic_loop is synchronous but provider.stream() is async,
    we use asyncio.run() to bridge the gap.
    """
    async def _inner():
        result = []
        async for chunk in provider.stream(messages, model, tools):
            result.append(chunk)
        return result

    return asyncio.run(_inner())


def _run_agentic_loop(
    messages: list[BaseMessage],
    model: str,
    instructions: str,
    provider,
    workdir: Path,
    auto: bool = False,
    max_iterations: int = 20,
) -> str:
    """Run the agentic loop using provider.stream() for HTTP delegation.

    Args:
        messages: LangChain messages (HumanMessage, AIMessage, etc.)
        model: Model identifier to use
        instructions: System prompt/instructions
        provider: ProviderPlugin instance for streaming
        workdir: Working directory for tool execution
        auto: Whether to auto-execute destructive tools without confirmation
        max_iterations: Maximum tool-call iterations before giving up

    Returns:
        Final text response from the model

    Raises:
        RuntimeError: If provider is unauthenticated or API returns error
    """
    # Convert messages to neutral types
    neutral_messages = _convert_messages_to_neutral(messages, instructions)

    # Convert tool schemas to neutral Tool types
    tools = _convert_tool_schemas(TOOL_SCHEMAS)

    for iteration in range(max_iterations):
        # Stream from provider (sync wrapper for async generator)
        stream_results = _run_provider_stream_sync(
            provider, neutral_messages, model, tools
        )

        text_parts: list[str] = []
        tool_calls: list[ToolCall] = []
        final_message: Message | None = None

        for chunk in stream_results:
            if isinstance(chunk, str):
                # Text chunk during streaming
                text_parts.append(chunk)
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
            result = execute_tool(tc.name, tc.arguments, workdir, auto=auto)
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
) -> str:
    """Run the agentic loop with the given model and prompt.

    Uses get_default_provider() to discover and use the first authenticated
    provider (or ChatGPT fallback). The provider raises RuntimeError with
    actionable guidance if not authenticated.
    """
    # Get default provider from registry - provider handles auth validation
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
        )
        return AIMessage(content=text)

    @entrypoint()
    def agent(msgs: list[BaseMessage]) -> list[BaseMessage]:
        response = call_agent(msgs).result()
        return [*msgs, response]

    msgs: list[BaseMessage] = [HumanMessage(content=prompt)]
    result = agent.invoke(msgs)
    return result[-1].content
