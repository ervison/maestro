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

from maestro.providers.base import Message
from maestro.planner.schemas import AgentState, AgentPlan
from maestro.planner.validator import validate_dag
from maestro.domains import DOMAINS
from maestro.models import resolve_model

logger = logging.getLogger(__name__)

# JSON schema for structured output enforcement
_AGENT_PLAN_SCHEMA = AgentPlan.model_json_schema()

PLANNER_SYSTEM_PROMPT = """You are a task decomposition engine. The following rules are ABSOLUTE and MUST be followed without exception.

## ABSOLUTE LAWS

1. You MUST decompose the user task into the MINIMUM number of atomic subtasks. Fewer tasks is always correct. More tasks requires explicit justification.
2. You MUST assign each task to exactly ONE domain from: {domain_names}.
3. You MUST set `deps` to a list of task IDs that MUST complete before this task starts (can be empty list).
4. Task IDs MUST be short strings like "t1", "t2", etc.
5. You MUST NOT create cyclic dependencies.
6. The `prompt` field MUST be a complete, self-contained instruction for that domain agent.
7. You MUST NOT split a task merely because it involves multiple steps or touches multiple files — a single agent handles multi-step work within its domain.

## INDEPENDENCE TEST

A task is independent ONLY IF its result does not change based on another task's result.

If task B requires knowledge of what task A produced, task B MUST declare task A as a dependency. If task B's output would be the same regardless of task A's output, they MAY be split into independent tasks. When uncertain, MERGE.

## RATIONALIZATION TABLE

Before splitting tasks, check your reasoning against this table. If your reasoning matches a row, apply the verdict immediately.

| Rationalization | Why It Is Wrong | Verdict |
|---|---|---|
| "These tasks share context, so they must be separate" | Shared context means they are the SAME task. MUST merge. | MERGE |
| "These could run in parallel" | Parallel execution potential does NOT create independence. If sequencing is required, they are NOT independent. | MERGE or ADD DEP |
| "Separating them is cleaner" | Cleanliness is NOT a decomposition criterion. | MERGE |
| "They belong to different domains" | Domain boundaries do NOT equal task boundaries. | MERGE |
| "They might need separate handling" | Uncertainty is NOT a valid split reason. | MERGE |

These examples are not exhaustive. Any split justified by cleanliness, file boundaries,
domain boundaries, implementation steps, hypothetical parallelism, or vague future risk
is invalid unless the outputs are truly independent under the Independence Test above.

## COMMITMENT DEVICE

Before outputting JSON, you MUST output a reasoning block delimited by `<reasoning>` and `</reasoning>` tags. This block MUST contain:
(a) The final task count and why it is the minimum necessary.
(b) The domain assignment for each task and why that domain was chosen.
(c) For each split (where two tasks exist instead of one), the independence rationale: state explicitly that each task's result does NOT change based on the other's result.

After `</reasoning>`, output ONLY the JSON — no markdown fences, no commentary.

## Output Format (JSON only, no markdown)

{{schema}}

## Domains

{domain_list}
"""

# Build domain section from maestro/domains.py — single source of truth
_DOMAIN_NAMES = ", ".join(DOMAINS.keys())
_DOMAIN_LIST = "\n".join(
    f"- {name}: {prompt.split(chr(10))[1].strip()}"
    for name, prompt in DOMAINS.items()
)
PLANNER_SYSTEM_PROMPT = PLANNER_SYSTEM_PROMPT.format(
    domain_names=_DOMAIN_NAMES,
    domain_list=_DOMAIN_LIST,
)


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
    # Guard: bound task length to prevent excessive prompt injection surface
    if len(task) > 8000:
        raise ValueError(f"Task too long: {len(task)} chars (max 8000)")

    # Resolve provider and model via shared priority chain.
    # Always call resolve_model(agent_name="planner") so config.agent.planner.model
    # is honoured. If a provider was injected by the caller, use it for auth context
    # but keep the model from resolve_model.
    runtime_provider = state.get("provider")

    resolved_provider, model_id = resolve_model(agent_name="planner")
    # Prefer caller-supplied provider (has live auth credentials) over resolved one,
    # but always use the model from the resolution chain.
    provider = runtime_provider if runtime_provider is not None else resolved_provider

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

            # Strip a leading <reasoning>...</reasoning> block if present
            # (commitment device output). Only strip when the response starts
            # with the block — avoids removing content if <reasoning> appears
            # inside a JSON string value later in the response.
            raw = raw.strip()
            leading_raw = raw.lstrip()
            if leading_raw.startswith("<reasoning>"):
                end = leading_raw.find("</reasoning>")
                if end != -1:
                    raw = leading_raw[end + len("</reasoning>"):].strip()

            # Strip markdown code fences if present (after reasoning block removal)
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
                messages.append(Message(role="assistant", content=raw if 'raw' in locals() else ""))
                messages.append(Message(
                    role="user",
                    content=f"Your previous response was invalid: {str(exc)[:200]}\n\nOutput the <reasoning> block first, then ONLY the JSON matching the schema exactly."
                ))

    raise ValueError(
        f"Planner failed to produce a valid AgentPlan after {max_retries} attempts. "
        f"Last error: {last_error}"
    )
