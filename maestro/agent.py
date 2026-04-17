"""
LangGraph agent that uses ChatGPT Plus/Pro subscription
via the Codex Responses API backend — with agentic tool loop.
"""

import json
import httpx
from pathlib import Path
from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage, AIMessage
from langgraph.func import entrypoint, task

from maestro import auth
from maestro.tools import execute_tool, TOOL_SCHEMAS

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


def _reasoning_effort(model: str) -> str:
    return _REASONING_DEFAULTS.get(model, "medium")


def _headers(tokens: auth.TokenSet) -> dict:
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


def _run_agentic_loop(
    messages: list[BaseMessage],
    model: str,
    instructions: str,
    tokens: auth.TokenSet,
    workdir: Path,
    auto: bool = False,
    max_iterations: int = 20,
) -> str:
    api_model = auth.resolve_model(model)

    # Build initial input list (user/assistant messages only — no developer)
    input_items: list[dict] = []
    for msg in messages:
        if isinstance(msg, HumanMessage):
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

    for iteration in range(max_iterations):
        payload = {
            "model": api_model,
            "instructions": instructions or "You are a helpful assistant.",
            "input": input_items,
            "tools": TOOL_SCHEMAS,
            "stream": True,
            "store": False,
            "reasoning": {
                "effort": _reasoning_effort(api_model),
                "summary": "auto",
            },
            "text": {"verbosity": "medium"},
            "include": ["reasoning.encrypted_content"],
        }

        text_parts: list[str] = []
        tool_calls: list[dict] = []

        with httpx.stream(
            "POST",
            RESPONSES_ENDPOINT,
            json=payload,
            headers=_headers(tokens),
            timeout=120,
        ) as r:
            if not r.is_success:
                body = r.read().decode()
                raise RuntimeError(
                    f"API error {r.status_code} (iter {iteration}): {body[:800]}"
                )

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
                        tool_calls.append(item)
                elif etype == "response.done":
                    resp = event.get("response", {})
                    for out in resp.get("output", []):
                        if out.get("type") == "message" and not text_parts:
                            for part in out.get("content", []):
                                if part.get("type") == "output_text":
                                    text_parts.append(part["text"])

        # No tool calls → final answer
        if not tool_calls:
            if text_parts:
                return "".join(text_parts)
            raise RuntimeError("No output received from agent loop")

        # Append model's function_call items to input
        for tc in tool_calls:
            input_items.append(
                {
                    "type": "function_call",
                    "id": tc.get("id", ""),
                    "call_id": tc.get("id", ""),
                    "name": tc["name"],
                    "arguments": tc["arguments"],
                }
            )

        # Execute each tool and append results
        for tc in tool_calls:
            try:
                args = json.loads(tc["arguments"])
            except json.JSONDecodeError:
                args = {}
            result = execute_tool(tc["name"], args, workdir, auto=auto)
            input_items.append(
                {
                    "type": "function_call_output",
                    "call_id": tc.get("id", ""),
                    "output": json.dumps(result),
                }
            )

    raise RuntimeError(f"Agent loop exceeded max_iterations={max_iterations}")


def _call_responses_api(
    model: str,
    messages: list[BaseMessage],
    tokens: auth.TokenSet,
) -> str:
    """Single-shot call to the Responses API (no tool loop). Used by models --check."""
    api_model = auth.resolve_model(model)

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
    """Run the agentic loop with the given model and prompt."""
    tokens = auth.load()
    if not tokens:
        raise RuntimeError("Not logged in. Run: maestro login")
    tokens = auth.ensure_valid(tokens)

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
            tokens=tokens,
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
