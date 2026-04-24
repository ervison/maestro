"""Multi-agent scheduler and worker execution module.

Provides LangGraph StateGraph for parallel DAG execution:
- scheduler_node: computes ready tasks from DAG dependencies
- dispatch_route: fans out ready tasks via LangGraph Send
- worker_node: executes tasks using domain prompts and _run_agentic_loop
- aggregator_node: produces final summary from all worker outputs
- Compiled graph with scheduler -> dispatch -> worker -> scheduler loop -> aggregator
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import logging
import time as _time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

from langgraph.graph import StateGraph, START, END
from langgraph.types import Send

from maestro import agent as agent_module
from maestro.config import load as load_config
from maestro.domains import get_domain_prompt
from maestro.planner.node import planner_node
from maestro.planner.schemas import AgentState, AgentPlan, AggregatorGuardrail
from maestro.planner.validator import validate_dag
from maestro.models import resolve_model
from maestro.providers.registry import get_default_provider

try:
    from langchain_core.messages import BaseMessage, HumanMessage, AIMessage
except ImportError:  # pragma: no cover
    BaseMessage = Any  # type: ignore[assignment,misc]
    HumanMessage = None  # type: ignore[assignment]
    AIMessage = None  # type: ignore[assignment]

logger = logging.getLogger(__name__)


def check_aggregator_guardrail(
    guardrail: AggregatorGuardrail,
    calls_this_run: int,
    outputs: dict[str, str],
) -> tuple[bool, str | None]:
    """Check whether the aggregator is allowed to run under the given policy.

    Args:
        guardrail: Policy configuration.
        calls_this_run: How many times aggregator has already run this invocation.
        outputs: Worker outputs dict (used for token estimation).

    Returns:
        (allowed, reason) — reason is None when allowed is True.
    """
    # max_calls=0 means aggregation is explicitly disabled
    if guardrail.max_calls is not None and guardrail.max_calls == 0:
        return False, "aggregation disabled (max_calls=0)"

    # Call-count ceiling
    if guardrail.max_calls is not None and calls_this_run >= guardrail.max_calls:
        return False, f"call limit reached ({calls_this_run}/{guardrail.max_calls})"

    # Token budget: rough estimate (characters / 4 ≈ tokens)
    if guardrail.max_tokens_per_run is not None:
        estimated = sum(len(v) // 4 for v in outputs.values())
        if estimated > guardrail.max_tokens_per_run:
            return False, (
                f"token budget exceeded (estimated {estimated} > max {guardrail.max_tokens_per_run})"
            )

    return True, None


def _print_lifecycle(component: str, event: str) -> None:
    """Print lifecycle event to stdout.

    Format: [{component}] {event}
    """
    print(f"[{component}] {event}")


def _materialize_plan(dag_dict: dict) -> AgentPlan:
    """Materialize AgentPlan from serialized state['dag'].

    Args:
        dag_dict: Serialized AgentPlan dict (from AgentPlan.model_dump())

    Returns:
        Validated AgentPlan instance
    """
    return AgentPlan.model_validate(dag_dict)


def scheduler_node(state: AgentState) -> dict:
    """Compute ready tasks from DAG dependencies.

    Uses direct dependency checking to find tasks whose dependencies
    are all completed (subset of completed set) on every invocation.
    A task is blocked, not ready, if any dependency failed.
    Returns ready batch and termination metadata.

    Args:
        state: AgentState with dag, completed, failed populated

    Returns:
        Dict with ready_tasks and optional scheduler errors.
        Keys: ready_tasks (list[dict]), errors (list[str] - optional)
    """
    emitter = state.get("emitter")
    if emitter is not None:
        emitter.emit({"type": "node_update", "id": "scheduler", "status": "active"})

    plan = _materialize_plan(state["dag"])
    # Validate the DAG to catch duplicate IDs, invalid refs, etc.
    try:
        validate_dag(plan)
    except ValueError as e:
        error_msg = f"DAG validation failed: {e}"
        logger.error(error_msg)
        return {"ready_tasks": [], "errors": [error_msg]}
    completed = set(state.get("completed", []))
    failed = set(state.get("failed", []))
    terminal = completed | failed

    # Build dependency graph: task_id -> set of dependency task_ids
    deps_map = {t.id: set(t.deps) for t in plan.tasks}
    all_task_ids = set(deps_map.keys())

    # Find ready tasks: not terminal AND all deps are completed
    # A task is blocked (not ready) if any of its dependencies failed
    ready_ids = set()
    for tid, deps in deps_map.items():
        if tid not in terminal:
            # Check if all deps are completed (none failed)
            deps_all_completed = deps.issubset(completed)
            if deps_all_completed:
                ready_ids.add(tid)

    # Build ready task payloads
    task_map = {t.id: t for t in plan.tasks}
    ready_tasks = []
    for tid in ready_ids:
        task = task_map.get(tid)
        if task:
            ready_tasks.append(
                {
                    "id": task.id,
                    "domain": task.domain,
                    "prompt": task.prompt,
                }
            )

    # Detect end states
    unfinished = all_task_ids - terminal
    blocked_tasks = []

    # Check for tasks that are permanently blocked by failed dependencies
    for tid in unfinished:
        if tid not in ready_ids:
            # Task has unmet deps - check if any dep failed
            task = task_map.get(tid)
            if task:
                deps_failed = any(d in failed for d in task.deps)
                if deps_failed:
                    blocked_tasks.append(tid)

    # End state detection:
    # 1. All tasks terminal (completed + failed covers all tasks)
    # 2. No ready tasks and no unfinished tasks
    # 3. No ready tasks, unfinished tasks remain, but all are blocked by failures
    errors = []
    if not ready_tasks and unfinished:
        if blocked_tasks:
            # All remaining tasks are blocked by failures - report and end
            error_msg = (
                "Scheduler ending: "
                f"{len(blocked_tasks)} task(s) blocked by failed dependencies: "
                f"{blocked_tasks}"
            )
            logger.warning(error_msg)
            errors.append(error_msg)
        # If there are unfinished tasks that aren't blocked,
        # that's an unexpected state
        # but we'll let the graph continue and eventually time out,
        # or be handled elsewhere.

    result: dict[str, Any] = {"ready_tasks": list(ready_tasks)}
    if errors:
        result["errors"] = errors

    logger.debug(
        "Scheduler: %d ready, %d completed, %d failed, %d unfinished",
        len(ready_tasks),
        len(completed),
        len(failed),
        len(unfinished),
    )

    # Emit scheduler done when no more ready tasks (all workers dispatched or finished)
    if emitter is not None and not ready_tasks:
        emitter.emit({"type": "node_update", "id": "scheduler", "status": "done"})

    return result


def scheduler_route(state: AgentState) -> str:
    """Route from scheduler to dispatch or aggregator.

    Returns string destinations only (not Send objects).

    Args:
        state: AgentState with ready_tasks and execution status

    Returns:
        "dispatch" if there are ready tasks, "aggregator" when all tasks complete
        END if aggregation is disabled
    """
    ready_tasks = state.get("ready_tasks", [])

    if ready_tasks:
        return "dispatch"

    # Check if graph should proceed to aggregator
    plan = _materialize_plan(state["dag"])
    completed = set(state.get("completed", []))
    failed = set(state.get("failed", []))
    terminal = completed | failed
    all_task_ids = {t.id for t in plan.tasks}
    unfinished = all_task_ids - terminal

    # Route to aggregator if all tasks are terminal (completed or failed)
    if not unfinished:
        # Check if aggregation is disabled
        if not state.get("aggregate", True):
            return END
        # Guardrail check
        guardrail = state.get("agg_guardrail") or AggregatorGuardrail()
        calls_done = state.get("agg_calls_done", 0)
        allowed, reason = check_aggregator_guardrail(
            guardrail, calls_done, state.get("outputs", {})
        )
        if not allowed:
            _print_lifecycle("aggregator", f"skipped — {reason}")
            return END
        return "aggregator"

    # Safety: if we're here with no ready tasks but unfinished work,
    # there may be a problem - but scheduler_node would have added errors
    # Check if aggregation is disabled before routing to aggregator
    if not state.get("aggregate", True):
        return END
    return "aggregator"


def dispatch_node(state: AgentState) -> dict:
    """No-op dispatch node.

    Exists to isolate Send-returning router from termination router.
    The actual routing is done by dispatch_route.

    Args:
        state: AgentState

    Returns:
        Empty dict - state unchanged
    """
    return {}


def dispatch_route(state: AgentState) -> list[Send]:
    """Dispatch ready tasks to workers via LangGraph Send.

    Returns only list[Send] objects, never string destinations.

    Args:
        state: AgentState with ready_tasks populated

    Returns:
        List of Send objects targeting worker node with task payloads
    """
    ready_tasks = state.get("ready_tasks", [])
    depth = state["depth"]
    max_depth = state["max_depth"]
    workdir = state["workdir"]
    auto = state["auto"]
    provider = state.get("provider")
    model = state.get("model")
    emitter = state.get("emitter")

    sends = []
    for task in ready_tasks:
        _print_lifecycle(f"worker:{task['id']}", "started")
        if emitter is not None:
            emitter.emit(
                {
                    "type": "node_update",
                    "id": task["id"],
                    "domain": task.get("domain", ""),
                    "status": "active",
                    "model": model or "gpt-4o",
                }
            )
        payload: dict[str, Any] = {
            "current_task_id": task["id"],
            "current_task_domain": task["domain"],
            "current_task_prompt": task["prompt"],
            "depth": depth,
            "max_depth": max_depth,
            "workdir": workdir,
            "auto": auto,
            "emitter": emitter,
        }
        # Pass provider/model through to worker
        if provider is not None:
            payload["provider"] = provider
        if model is not None:
            payload["model"] = model
        sends.append(Send("worker", payload))
        logger.debug("Dispatching task %s (domain=%s)", task["id"], task["domain"])

    return sends


def worker_node(state: AgentState) -> dict:
    """Execute a single task using domain prompting and _run_agentic_loop.

    Worker receives task via Send payload with:
    - current_task_id, current_task_domain, current_task_prompt
    - depth, max_depth, workdir, auto
    - provider, model (optional, resolved in worker if not provided)

    Returns reducer-safe state updates:
    - On success: {"completed": [task_id], "outputs": {task_id: output}}
    - On failure: {"failed": [task_id], "errors": [f"{task_id}: {message}"]}

    Args:
        state: AgentState with worker-local task fields populated via Send

    Returns:
        Partial state update for reducer application
    """
    task_id = state.get("current_task_id")
    domain = state.get("current_task_domain")
    prompt = state.get("current_task_prompt")
    depth = state.get("depth", 0)
    max_depth = state.get("max_depth", 2)
    workdir_str = state.get("workdir", ".")
    auto = state.get("auto", False)
    # Provider/model may be passed through state or resolved here
    provider = state.get("provider")
    model = state.get("model", "gpt-4o")
    start_time = _time.monotonic()
    emitter = state.get("emitter")

    def _worker_emit(event: dict) -> None:
        if emitter is not None:
            emitter.emit(event)

    # Validate required fields
    if not task_id or not domain or not prompt:
        error_msg = "Worker missing required task fields (id, domain, prompt)"
        logger.error(error_msg)
        return {
            "failed": [task_id or "unknown"],
            "errors": [f"{task_id or 'unknown'}: {error_msg}"],
        }

    # Depth guard
    if depth > max_depth:
        error_msg = f"Depth {depth} exceeds max_depth {max_depth}"
        logger.warning("Task %s: %s", task_id, error_msg)
        return {"failed": [task_id], "errors": [f"{task_id}: {error_msg}"]}

    # Resolve workdir
    try:
        workdir = Path(workdir_str).resolve()
        # Ensure workdir exists
        workdir.mkdir(parents=True, exist_ok=True)
    except (OSError, ValueError) as e:
        error_msg = f"Invalid workdir '{workdir_str}': {e}"
        logger.error("Task %s: %s", task_id, error_msg)
        return {"failed": [task_id], "errors": [f"{task_id}: {error_msg}"]}

    # Compose system prompt
    domain_prompt = get_domain_prompt(domain)
    system_prompt = f"{domain_prompt}\n\n## Your Task\n\n{prompt}"

    try:
        # Resolve provider if not provided through state
        if provider is None:
            provider = get_default_provider()

        # Execute using _run_agentic_loop with task as HumanMessage
        messages: list[BaseMessage] = [HumanMessage(content=prompt)]
        tool_count = [0]

        def _on_tool_start() -> None:
            tool_count[0] += 1
            _worker_emit(
                {
                    "type": "node_log",
                    "id": task_id,
                    "kind": "tool",
                    "text": f"tool call #{tool_count[0]}",
                }
            )

        result = agent_module._run_agentic_loop(
            messages=messages,
            model=model,
            instructions=system_prompt,
            provider=provider,
            workdir=workdir,
            auto=auto,
            on_text=lambda chunk: _worker_emit(
                {"type": "node_log", "id": task_id, "kind": "text", "text": chunk}
            ),
            on_tool_start=_on_tool_start,
        )

        elapsed = _time.monotonic() - start_time
        logger.debug("Task %s completed successfully", task_id)
        _print_lifecycle(f"worker:{task_id}", "done")
        _worker_emit(
            {
                "type": "node_update",
                "id": task_id,
                "status": "done",
                "elapsed": round(elapsed, 1),
            }
        )
        return {"completed": [task_id], "outputs": {task_id: result}}

    except Exception as e:
        error_msg = str(e)
        elapsed = _time.monotonic() - start_time
        logger.exception("Task %s failed: %s", task_id, error_msg)
        _print_lifecycle(f"worker:{task_id}", "failed")
        _worker_emit(
            {
                "type": "node_update",
                "id": task_id,
                "status": "failed",
                "elapsed": round(elapsed, 1),
            }
        )
        return {"failed": [task_id], "errors": [f"{task_id}: {error_msg}"]}


# Aggregator system prompt
AGGREGATOR_SYSTEM_PROMPT = """
You are a synthesis specialist. Your task is to combine outputs from multiple
specialist agents into a coherent final report.

The user requested: {task}

You will receive outputs from various domain specialists (backend, testing,
docs, devops, etc.).
Your job is to:
1. Understand what each specialist accomplished
2. Identify how their work fits together
3. Present a clear, organized summary of the complete solution
4. Highlight any issues or gaps that need attention

If some tasks failed, acknowledge what succeeded and what needs to be
addressed.

Be concise but thorough.
"""


def aggregator_node(state: AgentState) -> dict:
    """Produce final summary from all worker outputs.

    Calls the LLM to generate a coherent summary of all worker outputs.
    Runs as the final node after all workers complete.

    Args:
        state: AgentState with outputs dict containing all worker results

    Returns:
        Dict with "summary" key containing the aggregated summary
    """
    task = state.get("task", "")
    outputs = state.get("outputs", {})
    failed = state.get("failed", [])
    errors = state.get("errors", [])
    emitter = state.get("emitter")

    def _agg_emit(event: dict) -> None:
        if emitter is not None:
            emitter.emit(event)

    _agg_emit({"type": "node_update", "id": "aggregator", "status": "active"})

    # Handle empty outputs gracefully
    if not outputs and not failed:
        _agg_emit({"type": "node_update", "id": "aggregator", "status": "done"})
        _print_lifecycle("aggregator", "done")
        return {"summary": "No worker outputs to summarize."}

    # Build the prompt for the aggregator
    outputs_text = "\n\n".join(
        f"=== {task_id} ===\n{output}" for task_id, output in outputs.items()
    )

    if failed:
        failed_text = "\n".join(f"- {tid}" for tid in failed)
        outputs_text += f"\n\n=== Failed Tasks ===\n{failed_text}"

    if errors:
        errors_text = "\n".join(f"- {err}" for err in errors)
        outputs_text += f"\n\n=== Errors ===\n{errors_text}"

    user_message = f"Original task: {task}\n\nWorker outputs:\n\n{outputs_text}"

    # Resolve provider and model via shared priority chain.
    # Always use resolve_model(agent_name="aggregator") so config.agent.aggregator.model
    # is honoured. If a provider was injected by the caller, use it for auth context
    # but still let resolve_model determine the model string.
    runtime_provider = state.get("provider")

    resolved_provider, aggregator_model = resolve_model(agent_name="aggregator")
    # Prefer the caller-supplied provider (has live auth credentials) over the
    # freshly-resolved one, but keep the model from resolve_model.
    provider = runtime_provider if runtime_provider is not None else resolved_provider

    # Use asyncio to run the async provider stream
    async def _aggregate():
        from maestro.providers.base import Message

        system_prompt = AGGREGATOR_SYSTEM_PROMPT.format(task=task)
        messages = [
            Message(role="system", content=system_prompt),
            Message(role="user", content=user_message),
        ]
        chunks: list[str] = []
        async for chunk in provider.stream(messages, model=aggregator_model):
            if isinstance(chunk, str):
                chunks.append(chunk)
            elif isinstance(chunk, Message) and chunk.content:
                chunks = [chunk.content]
        return "".join(chunks)

    # Separate loop detection from aggregation execution to properly handle
    # provider-side RuntimeError without confusing it with "no running loop" case
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    try:
        if loop and loop.is_running():
            # Called from an already running event loop (e.g., async test)
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                summary = pool.submit(lambda: asyncio.run(_aggregate())).result()
        elif loop is not None:
            # Loop exists but isn't running
            summary = loop.run_until_complete(_aggregate())
        else:
            # No running loop - safe to use asyncio.run()
            summary = asyncio.run(_aggregate())
    except Exception as e:
        logger.exception("Aggregator failed: %s", e)
        summary = f"Failed to generate summary: {e}"
    else:
        # No exception - check if summary is empty
        if not summary.strip():
            summary = "Aggregation completed but produced no output."

    _agg_emit({"type": "node_update", "id": "aggregator", "status": "done"})
    _agg_emit({"type": "node_log", "id": "aggregator", "kind": "text", "text": summary})
    _print_lifecycle("aggregator", "done")
    return {"summary": summary}


# Build and compile the StateGraph
_builder = StateGraph(AgentState)
_builder.add_node("scheduler", scheduler_node)
_builder.add_node("dispatch", dispatch_node)
_builder.add_node("worker", worker_node)
_builder.add_node("aggregator", aggregator_node)

_builder.add_edge(START, "scheduler")
_builder.add_conditional_edges("scheduler", scheduler_route, ["dispatch", "aggregator", END])
_builder.add_conditional_edges("dispatch", dispatch_route, ["worker"])
_builder.add_edge("worker", "scheduler")
_builder.add_edge("aggregator", END)

graph = _builder.compile()


def run_multi_agent(
    task: str,
    *,
    workdir: Path,
    auto: bool,
    depth: int,
    max_depth: int = 2,
    provider=None,
    model: str | None = None,
    aggregate: bool | None = None,
    emitter=None,
) -> dict[str, Any]:
    """Run multi-agent DAG execution on a task.

    This is a thin synchronous wrapper around the compiled LangGraph.
    It uses planner_node to generate the DAG, then executes it via the graph.

    Args:
        task: The user task to decompose and execute
        workdir: Working directory for tool execution (must exist)
        auto: Auto-approve destructive tools
        depth: Current recursion depth (required, no default)
        max_depth: Maximum recursion depth (default 2)
        provider: Optional provider instance (uses default if not provided)
        model: Optional model override
        aggregate: Whether to run aggregator (default: check config, fallback True)

    Returns:
        Dict with keys:
        - "outputs": dict mapping task_id -> output_text for completed tasks
        - "failed": list of task IDs that failed
        - "errors": list of error messages
        - "summary": optional aggregated summary (if aggregator ran)

    Raises:
        TypeError: If depth is not provided (it's required)
        ValueError: If workdir is invalid
    """
    # depth is required (no default) - Python signature enforces this
    # Workdir must exist and be a directory
    workdir = Path(workdir).resolve()
    if not workdir.exists():
        raise ValueError(f"workdir does not exist: {workdir}")
    if not workdir.is_dir():
        raise ValueError(f"workdir is not a directory: {workdir}")

    # Resolve provider if not provided
    if provider is None:
        provider = get_default_provider()

    def _emit(event: dict) -> None:
        if emitter is not None:
            emitter.emit(event)

    # Determine if we should aggregate
    cfg = load_config()
    if aggregate is None:
        aggregate = cfg.get("aggregator.enabled", True)

    agg_guardrail = AggregatorGuardrail(
        max_calls=cfg.get("aggregator.max_calls"),           # None if not set
        max_tokens_per_run=cfg.get("aggregator.max_tokens_per_run"),  # None if not set
    )

    # Call planner to generate the DAG
    # Only inject provider into planner state (for auth context).
    # Do NOT inject model — planner resolves its own via resolve_model(agent_name="planner"),
    # honouring config.agent.planner.model. The --model CLI flag only overrides workers.
    planner_state: AgentState = {
        "task": task,
        "dag": {"tasks": []},  # Will be populated by planner
        "completed": [],
        "failed": [],
        "outputs": {},
        "errors": [],
        "depth": depth,
        "max_depth": max_depth,
        "workdir": str(workdir),
        "auto": auto,
        "ready_tasks": [],
        "provider": provider,
        "emitter": emitter,
        # model intentionally omitted — planner uses resolve_model(agent_name="planner")
    }

    _emit({"type": "node_update", "id": "planner", "status": "active"})
    planner_result = planner_node(planner_state)
    _print_lifecycle("planner", "done")
    _emit({"type": "node_update", "id": "planner", "status": "done"})
    dag = planner_result.get("dag")

    if dag is None:
        raise RuntimeError("Planner failed to produce a DAG")

    dag_tasks_raw = dag.get("tasks", []) if isinstance(dag, dict) else []
    _emit(
        {
            "type": "dag_ready",
            "tasks": [
                {
                    "id": t.get("id", "") if isinstance(t, dict) else getattr(t, "id", ""),
                    "domain": (
                        t.get("domain", "")
                        if isinstance(t, dict)
                        else getattr(t, "domain", "")
                    ),
                    "description": (
                        t.get("prompt", "")[:100]
                        if isinstance(t, dict)
                        else getattr(t, "prompt", "")[:100]
                    ),
                    "deps": (
                        t.get("deps", [])
                        if isinstance(t, dict)
                        else getattr(t, "deps", [])
                    ),
                }
                for t in dag_tasks_raw
            ],
        }
    )

    # Build initial state for graph execution.
    # model is passed through so dispatch_route can give workers the --model override.
    # The aggregator node ignores state["model"] and uses resolve_model(agent_name="aggregator").
    initial_state: AgentState = {
        "task": task,
        "dag": dag,
        "completed": [],
        "failed": [],
        "outputs": {},
        "errors": [],
        "depth": depth,
        "max_depth": max_depth,
        "workdir": str(workdir),
        "auto": auto,
        "ready_tasks": [],
        "provider": provider,
        "model": model,  # workers only — aggregator resolves its own model
        "aggregate": aggregate,
        "emitter": emitter,
        "agg_guardrail": agg_guardrail,
        "agg_calls_done": 0,
    }

    # Run the graph
    final_state = cast(dict[str, Any], graph.invoke(cast(Any, initial_state)))

    # Return structured result with outputs, failures, errors, and optional summary
    result: dict[str, Any] = {
        "outputs": dict(final_state.get("outputs", {})),
        "failed": list(final_state.get("failed", [])),
        "errors": list(final_state.get("errors", [])),
    }
    if "summary" in final_state:
        result["summary"] = final_state["summary"]

    return result
