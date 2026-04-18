"""DAG validation for multi-agent plans.

Uses graphlib.TopologicalSorter to detect cycles and validate
that all dependency references are valid task IDs.
"""

from graphlib import TopologicalSorter, CycleError

from .schemas import AgentPlan


def validate_dag(plan: AgentPlan) -> None:
    """Validate DAG has no cycles and all dep references are valid.

    Args:
        plan: AgentPlan to validate

    Raises:
        ValueError: If DAG contains a cycle or has invalid dep references

    Returns:
        None if DAG is valid
    """
    task_ids = {t.id for t in plan.tasks}
    graph = {}

    for task in plan.tasks:
        # Check for invalid dep references
        for dep in task.deps:
            if dep not in task_ids:
                raise ValueError(
                    f"Task '{task.id}' depends on unknown task '{dep}'. "
                    f"Valid task IDs: {sorted(task_ids)}"
                )
        graph[task.id] = task.deps

    # Check for cycles
    if graph:  # Only check if there are tasks with dependencies
        try:
            ts = TopologicalSorter(graph)
            ts.prepare()
        except CycleError as e:
            raise ValueError(f"DAG contains a cycle: {e}") from e
