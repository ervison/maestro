"""Multi-agent scheduler and worker execution module.

Provides LangGraph StateGraph for parallel DAG execution:
- scheduler_node: computes ready tasks from DAG dependencies
- dispatch_route: fans out ready tasks via LangGraph Send
- worker_node: executes tasks using domain prompts and _run_agentic_loop
- Compiled graph with scheduler -> dispatch -> worker -> scheduler loop
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, cast

from langgraph.graph import StateGraph, START, END
from langgraph.types import Send

from maestro.planner.schemas import AgentState, AgentPlan
from maestro.planner.validator import validate_dag
from maestro.domains import get_domain_prompt
from maestro.agent import _run_agentic_loop
from maestro.providers.registry import get_default_provider
from langchain_core.messages import BaseMessage, HumanMessage

logger = logging.getLogger(__name__)


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
            ready_tasks.append({
                "id": task.id,
                "domain": task.domain,
                "prompt": task.prompt,
            })

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
            error_msg = f"Scheduler ending: {len(blocked_tasks)} task(s) blocked by failed dependencies: {blocked_tasks}"
            logger.warning(error_msg)
            errors.append(error_msg)
        # If there are unfinished tasks that aren't blocked, that's an unexpected state
        # but we'll let the graph continue and eventually time out or be handled elsewhere

    result: dict[str, Any] = {"ready_tasks": list(ready_tasks)}
    if errors:
        result["errors"] = errors

    logger.debug("Scheduler: %d ready, %d completed, %d failed, %d unfinished",
                 len(ready_tasks), len(completed), len(failed), len(unfinished))

    return result


def scheduler_route(state: AgentState) -> str:
    """Route from scheduler to dispatch or END.

    Returns string destinations only (not Send objects).

    Args:
        state: AgentState with ready_tasks and execution status

    Returns:
        "dispatch" if there are ready tasks, END otherwise
    """
    ready_tasks = state.get("ready_tasks", [])

    if ready_tasks:
        return "dispatch"

    # Check if graph should end
    plan = _materialize_plan(state["dag"])
    completed = set(state.get("completed", []))
    failed = set(state.get("failed", []))
    terminal = completed | failed
    all_task_ids = {t.id for t in plan.tasks}
    unfinished = all_task_ids - terminal

    # End if all tasks are terminal
    if not unfinished:
        return END

    # Safety: if we're here with no ready tasks but unfinished work,
    # there may be a problem - but scheduler_node would have added errors
    return END


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

    sends = []
    for task in ready_tasks:
        payload: dict[str, Any] = {
            "current_task_id": task["id"],
            "current_task_domain": task["domain"],
            "current_task_prompt": task["prompt"],
            "depth": depth,
            "max_depth": max_depth,
            "workdir": workdir,
            "auto": auto,
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

    # Validate required fields
    if not task_id or not domain or not prompt:
        error_msg = "Worker missing required task fields (id, domain, prompt)"
        logger.error(error_msg)
        return {
            "failed": [task_id or "unknown"],
            "errors": [f"{task_id or 'unknown'}: {error_msg}"]
        }

    # Depth guard
    if depth > max_depth:
        error_msg = f"Depth {depth} exceeds max_depth {max_depth}"
        logger.warning("Task %s: %s", task_id, error_msg)
        return {
            "failed": [task_id],
            "errors": [f"{task_id}: {error_msg}"]
        }

    # Resolve workdir
    try:
        workdir = Path(workdir_str).resolve()
        # Ensure workdir exists
        workdir.mkdir(parents=True, exist_ok=True)
    except (OSError, ValueError) as e:
        error_msg = f"Invalid workdir '{workdir_str}': {e}"
        logger.error("Task %s: %s", task_id, error_msg)
        return {
            "failed": [task_id],
            "errors": [f"{task_id}: {error_msg}"]
        }

    # Compose system prompt
    domain_prompt = get_domain_prompt(domain)
    system_prompt = f"{domain_prompt}\n\n## Your Task\n\n{prompt}"

    try:
        # Resolve provider if not provided through state
        if provider is None:
            provider = get_default_provider()

        # Execute using _run_agentic_loop with task as HumanMessage
        messages: list[BaseMessage] = [HumanMessage(content=prompt)]
        result = _run_agentic_loop(
            messages=messages,
            model=model,
            instructions=system_prompt,
            provider=provider,
            workdir=workdir,
            auto=auto,
        )

        logger.debug("Task %s completed successfully", task_id)
        return {
            "completed": [task_id],
            "outputs": {task_id: result}
        }

    except Exception as e:
        error_msg = str(e)
        logger.exception("Task %s failed: %s", task_id, error_msg)
        return {
            "failed": [task_id],
            "errors": [f"{task_id}: {error_msg}"]
        }


# Build and compile the StateGraph
_builder = StateGraph(AgentState)
_builder.add_node("scheduler", scheduler_node)
_builder.add_node("dispatch", dispatch_node)
_builder.add_node("worker", worker_node)

_builder.add_edge(START, "scheduler")
_builder.add_conditional_edges("scheduler", scheduler_route, ["dispatch", END])
_builder.add_conditional_edges("dispatch", dispatch_route, ["worker"])
_builder.add_edge("worker", "scheduler")

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
) -> dict[str, str]:
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

    Returns:
        Dict mapping task_id -> output_text for completed tasks

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

    # Resolve model
    model = model or "gpt-4o"

    # Call planner to generate the DAG
    from maestro.planner.node import planner_node

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
        # Pass caller's provider/model override so planner uses same settings as workers
        "provider": provider,
        "model": model,
    }

    planner_result = planner_node(planner_state)
    dag = planner_result.get("dag")

    if dag is None:
        raise RuntimeError("Planner failed to produce a DAG")

    # Build initial state for graph execution
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
        "model": model,
    }

    # Run the graph
    final_state = cast(dict[str, Any], graph.invoke(cast(Any, initial_state)))

    # Return outputs dict
    return final_state.get("outputs", {})
