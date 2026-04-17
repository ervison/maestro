"""
LangGraph agent that uses ChatGPT Plus/Pro subscription
via the Codex Responses API backend.

Payload structure follows oc-codex-multi-auth/lib/request/request-transformer.ts
"""

import json
import httpx
from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage, AIMessage
from langgraph.func import entrypoint, task

from maestro import auth

RESPONSES_ENDPOINT = f"{auth.CODEX_API_BASE}/codex/responses"

USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

# Reasoning effort defaults per model family (from request-transformer.ts)
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


def _call_responses_api(
    model: str,
    messages: list[BaseMessage],
    tokens: auth.TokenSet,
) -> str:
    """Call the ChatGPT Codex Responses API directly."""
    api_model = auth.resolve_model(model)

    # Convert LangChain messages to Responses API input format
    input_items = []
    for msg in messages:
        if isinstance(msg, SystemMessage):
            role = "developer"
        elif isinstance(msg, HumanMessage):
            role = "user"
        elif isinstance(msg, AIMessage):
            role = "assistant"
        else:
            continue
        input_items.append(
            {
                "type": "message",
                "role": role,
                "content": [{"type": "input_text", "text": msg.content}],
            }
        )

    # Extract system/developer message as top-level `instructions` field
    instructions = ""
    filtered_items = []
    for item in input_items:
        if item["role"] == "developer":
            instructions = item["content"][0]["text"]
        else:
            filtered_items.append(item)

    # Payload following Codex CLI / oc-codex-multi-auth conventions
    payload = {
        "model": api_model,
        "instructions": instructions or "You are a helpful assistant.",
        "input": filtered_items,
        "stream": True,
        "store": False,
        "reasoning": {
            "effort": _reasoning_effort(api_model),
            "summary": "auto",
        },
        "text": {"verbosity": "medium"},
        "include": ["reasoning.encrypted_content"],
    }

    headers = {
        "Authorization": f"Bearer {tokens.access}",
        "Content-Type": "application/json",
        "Accept": "text/event-stream",
        "User-Agent": USER_AGENT,
        "originator": "codex_cli_rs",
        "OpenAI-Beta": "responses=experimental",
    }
    if tokens.account_id:
        headers["chatgpt-account-id"] = tokens.account_id

    # Use streaming SSE and collect the final response.done event
    with httpx.stream(
        "POST",
        RESPONSES_ENDPOINT,
        json=payload,
        headers=headers,
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
            # Collect output_text delta chunks
            if etype == "response.output_text.delta":
                text_parts.append(event.get("delta", ""))
            # Full response in done event as fallback
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


def run(model_name: str, prompt: str, system: str | None = None) -> str:
    """Run a simple agent with the given model and prompt."""
    tokens = auth.load()
    if not tokens:
        raise RuntimeError("Not logged in. Run: maestro login")

    tokens = auth.ensure_valid(tokens)

    @task
    def call_llm(messages: list[BaseMessage]) -> AIMessage:
        text = _call_responses_api(model_name, messages, tokens)
        return AIMessage(content=text)

    @entrypoint()
    def agent(messages: list[BaseMessage]) -> list[BaseMessage]:
        response = call_llm(messages).result()
        return [*messages, response]

    messages: list[BaseMessage] = []
    if system:
        messages.append(SystemMessage(content=system))
    messages.append(HumanMessage(content=prompt))

    result = agent.invoke(messages)
    return result[-1].content
