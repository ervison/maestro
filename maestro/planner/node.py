"""Planner node for multi-agent DAG generation.

The planner node calls an LLM to decompose a user task into a
structured AgentPlan (list of PlanTask items). It uses:
1. API-level JSON schema enforcement (response_format) when supported
2. Falls back to prompt-only enforcement for other providers
3. Always validates with AgentPlan.model_validate_json()
4. Calls validate_dag() to detect cycles/invalid refs
5. Retries up to 3 times on validation failure
"""

from __future__ import annotations

import json
import logging
from typing import Any

from maestro.config import load as load_config
from maestro.providers.registry import get_default_provider, get_provider
from maestro.providers.base import Message
from maestro.planner.schemas import AgentState, AgentPlan
from maestro.planner.validator import validate_dag

logger = logging.getLogger(__name__)

# JSON schema for structured output enforcement
_AGENT_PLAN_SCHEMA = AgentPlan.model_json_schema()

PLANNER_SYSTEM_PROMPT = """You are a task decomposition specialist for a multi-agent system.

Your job: decompose a user task into a minimal list of atomic subtasks that can be executed by specialized agents.

## Rules

1. Each task must be atomic and independently executable by a domain specialist.
2. Assign each task to exactly ONE domain from: backend, testing, docs, devops, general, security, data.
3. Set `deps` to a list of task IDs that must complete before this task starts (can be empty).
4. Prefer FEWER larger tasks over many tiny ones — avoid over-decomposition.
5. Task IDs must be short strings like "t1", "t2", etc.
6. Never create cyclic dependencies.
7. The `prompt` field must be a complete, self-contained instruction for that domain agent.

## Output Format (JSON only, no markdown)

{schema}

## Domains

- backend: API design, database, business logic, server-side code
- testing: unit tests, integration tests, fixtures, mocking
- docs: README, API docs, user guides, code comments
- devops: CI/CD, Docker, deployment scripts, environment config
- security: authentication, authorization, input validation, encryption
- data: data pipelines, ETL, analytics, data models
- general: tasks that don't fit other domains
"""


def _build_system_prompt() -> str:
    """Build system prompt with embedded JSON schema."""
    schema_str = json.dumps(_AGENT_PLAN_SCHEMA, indent=2)
    return PLANNER_SYSTEM_PROMPT.format(schema=schema_str)


def _call_provider_with_schema(
    provider: Any,
    messages: list[Message],
    model: str,
) -> str:
    """Try api-level JSON schema enforcement, fall back to prompt-only.

    Returns the raw text response from the provider.
    """
    import asyncio

    # Collect streamed chunks into a full response string
    def _collect_stream(use_response_format: bool) -> str:
        """Run async stream collection synchronously."""
        async def _async_collect() -> str:
            chunks = []
            try:
                if use_response_format:
                    extra = {
                        "response_format": {
                            "type": "json_schema",
                            "json_schema": {
                                "name": "AgentPlan",
                                "schema": _AGENT_PLAN_SCHEMA,
                                "strict": True,
                            },
                        }
                    }
                    stream = provider.stream(messages=messages, model=model, tools=[], extra=extra)
                else:
                    stream = provider.stream(messages=messages, model=model, tools=[])

                async for chunk in stream:
                    if isinstance(chunk, str):
                        chunks.append(chunk)
                    elif isinstance(chunk, Message) and chunk.content:
                        # Final Message.content is canonical — it is the complete,
                        # assembled response. Replace any accumulated str deltas with it.
                        chunks = [chunk.content]
            except Exception:
                raise
            return "".join(chunks)

        try:
            # Try to get the running loop (Python 3.12+ preferred)
            loop = asyncio.get_running_loop()
            if loop.is_running():
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as pool:
                    future = pool.submit(asyncio.run, _async_collect())
                    return future.result()
            else:
                return loop.run_until_complete(_async_collect())
        except RuntimeError:
            # No running loop, use asyncio.run()
            return asyncio.run(_async_collect())

    # Try api-level enforcement first, only fall back on unsupported kwargs
    try:
        return _collect_stream(use_response_format=True)
    except TypeError as exc:
        # Provider doesn't support extra/response_format kwargs
        logger.debug("api-level response_format not supported (%s), falling back to prompt-only", exc)
        return _collect_stream(use_response_format=False)
    # Let auth/network/runtime errors propagate


def planner_node(state: AgentState) -> dict:
    """LangGraph planner node — generates validated DAG from user task.

    Args:
        state: Current AgentState with at minimum `task` populated.

    Returns:
        Dict with `dag` key containing the serialized AgentPlan.

    Raises:
        ValueError: If LLM output cannot be validated after max retries.
    """
    task = state["task"]
    config = load_config()

    # Resolve model: config.agent.planner.model -> default provider model
    planner_model_raw = config.get("agent.planner.model")

    if planner_model_raw:
        # Format: "provider_id/model_id" or just "model_id"
        if "/" in planner_model_raw:
            provider_id, model_id = planner_model_raw.split("/", 1)
            try:
                provider = get_provider(provider_id)
            except (ValueError, KeyError):
                logger.warning("Configured planner provider '%s' not found, using default", provider_id)
                provider = get_default_provider()
                model_id = None
        else:
            provider = get_default_provider()
            model_id = planner_model_raw
    else:
        provider = get_default_provider()
        model_id = None

    # Resolve model_id to first available if not set
    if model_id is None:
        models = provider.list_models()
        model_id = models[0] if models else "gpt-4o"

    system_prompt = _build_system_prompt()
    messages = [
        Message(role="system", content=system_prompt),
        Message(role="user", content=f"Decompose this task into a multi-agent plan:\n\n{task}"),
    ]

    max_retries = 3
    last_error: Exception | None = None

    for attempt in range(1, max_retries + 1):
        try:
            raw = _call_provider_with_schema(provider, messages, model_id)

            # Strip markdown code fences if present
            raw = raw.strip()
            if raw.startswith("```"):
                lines = raw.split("\n")
                raw = "\n".join(lines[1:-1]) if len(lines) > 2 else raw

            plan = AgentPlan.model_validate_json(raw)
            validate_dag(plan)
            logger.debug("Planner produced valid DAG with %d tasks on attempt %d", len(plan.tasks), attempt)
            return {"dag": plan.model_dump()}

        except (ValueError, json.JSONDecodeError) as exc:
            last_error = exc
            logger.warning("Planner attempt %d/%d failed: %s", attempt, max_retries, exc)
            if attempt < max_retries:
                # Add error feedback to messages for next retry
                messages.append(Message(role="assistant", content=raw if 'raw' in dir() else ""))
                messages.append(Message(
                    role="user",
                    content=f"Your previous response was invalid: {exc}\n\nPlease respond with valid JSON only, matching the schema exactly."
                ))

    raise ValueError(
        f"Planner failed to produce a valid AgentPlan after {max_retries} attempts. "
        f"Last error: {last_error}"
    )
