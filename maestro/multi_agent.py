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
from typing import Any
from graphlib import TopologicalSorter, CycleError

from langgraph.graph import StateGraph, START, END
from langgraph.types import Send

from maestro.planner.schemas import AgentState, AgentPlan
from maestro.planner.validator import validate_dag
from maestro.domains import get_domain_prompt
from maestro.agent import _run_agentic_loop
from langchain_core.messages import HumanMessage

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
    are all satisfied (completed or failed) on every invocation.
    Returns ready batch and termination metadata.

    Args:
        state: AgentState with dag, completed, failed populated

    Returns:
        Dict with ready_tasks and optional scheduler errors.
        Keys: ready_tasks (list[dict]), errors (list[str] - optional)
    """
    plan = _materialize_plan(state["dag"])
    completed = set(state.get("completed", []))
    failed = set(state.get("failed", []))
    terminal = completed | failed

    # Build dependency graph: task_id -> set of dependency task_ids
    deps_map = {t.id: set(t.deps) for t in plan.tasks}
    all_task_ids = set(deps_map.keys())

    # Validate: all deps must exist in the plan
    for task_id, deps in deps_map.items():
        for dep in deps:
            if dep not in all_task_ids:
                error_msg = f"Task '{task_id}' has unknown dependency '{dep}'. Valid tasks: {sorted(all_task_ids)}"
                logger.error(error_msg)
                return {"ready_tasks": [], "errors": [error_msg]}

    # Validate for cycles using TopologicalSorter
    try:
        ts = TopologicalSorter(deps_map)
        ts.prepare()
    except CycleError as e:
        error_msg = f"DAG contains cycle: {e.args[1]}"
        logger.error(error_msg)
        return {"ready_tasks": [], "errors": [error_msg]}

    # Find ready tasks: not terminal AND all deps are completed (not failed)
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

    result = {"ready_tasks": list(ready_tasks)}
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

    # End if all tasks are terminal or no unfinished tasks remain
    if not unfinished or unfinished.issubset(failed):
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

    sends = []
    for task in ready_tasks:
        payload = {
            "current_task_id": task["id"],
            "current_task_domain": task["domain"],
            "current_task_prompt": task["prompt"],
            "depth": depth,
            "max_depth": max_depth,
            "workdir": workdir,
            "auto": auto,
        }
        sends.append(Send("worker", payload))
        logger.debug("Dispatching task %s (domain=%s)", task["id"], task["domain"])

    return sends


def worker_node(state: AgentState) -> dict:
    """Execute a single task using domain prompting and _run_agentic_loop.

    Worker receives task via Send payload with:
    - current_task_id, current_task_domain, current_task_prompt
    - depth, max_depth, workdir, auto

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
        # Execute using _run_agentic_loop
        # Note: We pass an empty list for messages since the task prompt is in system
        # Actually, we should pass the task as a HumanMessage
        messages = [HumanMessage(content=prompt)]
        result = _run_agentic_loop(
            messages=messages,
            model="gpt-4o",  # TODO: Get from config or state
            instructions=system_prompt,
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

    # TODO: Integrate with planner_node to get initial DAG
    # For now, this is a placeholder - the graph needs a dag to run
    # This function will need to be called with a pre-populated state
    # or we'll need to add planner invocation here

    initial_state: AgentState = {
        "task": task,
        "dag": {"tasks": []},  # Placeholder - should come from planner
        "completed": [],
        "failed": [],
        "outputs": {},
        "errors": [],
        "depth": depth,
        "max_depth": max_depth,
        "workdir": str(workdir),
        "auto": auto,
        "ready_tasks": [],
    }

    # Run the graph
    final_state = graph.invoke(initial_state)

    # Return outputs dict
    return final_state.get("outputs", {})
