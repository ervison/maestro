"""Tests for planner schemas and DAG validation."""

import operator
from typing import get_type_hints

import pytest
from pydantic import ValidationError

from maestro.planner import AgentState, PlanTask, AgentPlan, validate_dag


# --- PlanTask validation tests ---


def test_plantask_valid():
    """Valid PlanTask can be created with all required fields."""
    task = PlanTask(id="t1", domain="backend", prompt="Build API", deps=["t0"])
    assert task.id == "t1"
    assert task.deps == ["t0"]


def test_plantask_rejects_unknown_fields():
    """PlanTask rejects unknown fields due to extra='forbid'."""
    with pytest.raises(ValidationError) as exc_info:
        PlanTask(id="t1", domain="backend", prompt="x", deps=[], unknown="bad")
    assert "extra_forbidden" in str(exc_info.value).lower() or "extra" in str(
        exc_info.value
    )


def test_plantask_deps_must_be_list():
    """PlanTask requires deps to be a list, not None."""
    with pytest.raises(ValidationError):
        PlanTask(id="t1", domain="backend", prompt="x", deps=None)  # type: ignore


def test_plantask_deps_items_must_be_str():
    """PlanTask requires deps items to be strings."""
    with pytest.raises(ValidationError):
        PlanTask(id="t1", domain="backend", prompt="x", deps=[123])  # type: ignore


def test_plantask_deps_empty_list():
    """PlanTask accepts empty list for deps (no dependencies)."""
    task = PlanTask(id="t1", domain="backend", prompt="x", deps=[])
    assert task.deps == []


def test_plantask_requires_deps_field():
    """PlanTask requires deps field to be explicitly provided."""
    with pytest.raises(ValidationError):
        PlanTask(id="t1", domain="backend", prompt="x")  # missing deps


def test_plantask_rejects_invalid_domain():
    """PlanTask rejects domain values not in the allowed set."""
    with pytest.raises(ValidationError):
        PlanTask(id="t1", domain="invalid_domain", prompt="x", deps=[])


def test_plantask_rejects_typo_domain():
    """PlanTask rejects common typo domain names like 'tests' or 'secuirty'."""
    with pytest.raises(ValidationError):
        PlanTask(id="t1", domain="tests", prompt="x", deps=[])  # should be "testing"
    with pytest.raises(ValidationError):
        PlanTask(id="t1", domain="secuirty", prompt="x", deps=[])  # typo for "security"


# --- AgentPlan validation tests ---


def test_agentplan_valid():
    """Valid AgentPlan can be created with tasks list."""
    plan = AgentPlan(
        tasks=[
            PlanTask(id="t1", domain="backend", prompt="Build API", deps=[]),
            PlanTask(id="t2", domain="testing", prompt="Write tests", deps=["t1"]),
        ]
    )
    assert len(plan.tasks) == 2


def test_agentplan_empty_tasks():
    """AgentPlan accepts empty tasks list."""
    plan = AgentPlan(tasks=[])
    assert plan.tasks == []


def test_agentplan_rejects_unknown_fields():
    """AgentPlan rejects unknown fields due to extra='forbid'."""
    with pytest.raises(ValidationError):
        AgentPlan(tasks=[], extra_field="bad")  # type: ignore


def test_agentplan_validates_task_types():
    """AgentPlan validates that tasks are PlanTask instances."""
    with pytest.raises(ValidationError):
        AgentPlan(tasks=[{"id": "t1", "domain": "backend"}])  # type: ignore


def test_agentplan_model_validate_json_accepts_valid_planner_payload():
    """Planner-facing JSON payloads validate into an AgentPlan."""
    payload = (
        '{"tasks":[{"id":"t1","domain":"backend","prompt":"Build API","deps":[]}]}'
    )

    plan = AgentPlan.model_validate_json(payload)

    assert len(plan.tasks) == 1
    assert plan.tasks[0].id == "t1"
    assert plan.tasks[0].domain == "backend"


# --- DAG validator tests for malformed inputs ---


def test_validate_dag_rejects_duplicate_task_ids():
    """validate_dag raises ValueError when duplicate task IDs exist."""
    plan = AgentPlan(
        tasks=[
            PlanTask(id="t1", domain="backend", prompt="x", deps=[]),
            PlanTask(id="t1", domain="testing", prompt="y", deps=[]),  # duplicate ID
        ]
    )
    with pytest.raises(ValueError, match="Duplicate task IDs"):
        validate_dag(plan)


def test_validate_dag_rejects_multiple_duplicate_ids():
    """validate_dag raises ValueError listing all duplicate IDs."""
    plan = AgentPlan(
        tasks=[
            PlanTask(id="a", domain="backend", prompt="x", deps=[]),
            PlanTask(id="b", domain="testing", prompt="y", deps=[]),
            PlanTask(id="a", domain="docs", prompt="z", deps=[]),  # duplicate
            PlanTask(id="b", domain="devops", prompt="w", deps=[]),  # duplicate
        ]
    )
    with pytest.raises(ValueError) as exc_info:
        validate_dag(plan)
    assert "a" in str(exc_info.value)
    assert "b" in str(exc_info.value)


# --- DAG validator tests ---


def test_validate_dag_passes_valid_dag():
    """validate_dag passes for valid acyclic DAG."""
    plan = AgentPlan(
        tasks=[
            PlanTask(id="t1", domain="backend", prompt="x", deps=[]),
            PlanTask(id="t2", domain="testing", prompt="y", deps=["t1"]),
            PlanTask(id="t3", domain="docs", prompt="z", deps=["t1", "t2"]),
        ]
    )
    validate_dag(plan)  # should not raise


def test_validate_dag_passes_empty_plan():
    """validate_dag passes for empty plan (no tasks)."""
    plan = AgentPlan(tasks=[])
    validate_dag(plan)  # should not raise


def test_validate_dag_passes_isolated_tasks():
    """validate_dag passes for isolated tasks (no deps)."""
    plan = AgentPlan(
        tasks=[
            PlanTask(id="t1", domain="backend", prompt="x", deps=[]),
            PlanTask(id="t2", domain="testing", prompt="y", deps=[]),
        ]
    )
    validate_dag(plan)  # should not raise


def test_validate_dag_rejects_cycle_two_nodes():
    """validate_dag raises ValueError for A→B→A cycle."""
    plan = AgentPlan(
        tasks=[
            PlanTask(id="a", domain="backend", prompt="x", deps=["b"]),
            PlanTask(id="b", domain="testing", prompt="y", deps=["a"]),
        ]
    )
    with pytest.raises(ValueError, match="cycle"):
        validate_dag(plan)


def test_validate_dag_rejects_cycle_three_nodes():
    """validate_dag raises ValueError for A→B→C→A cycle."""
    plan = AgentPlan(
        tasks=[
            PlanTask(id="a", domain="backend", prompt="x", deps=["c"]),
            PlanTask(id="b", domain="testing", prompt="y", deps=["a"]),
            PlanTask(id="c", domain="docs", prompt="z", deps=["b"]),
        ]
    )
    with pytest.raises(ValueError, match="cycle"):
        validate_dag(plan)


def test_validate_dag_rejects_self_cycle():
    """validate_dag raises ValueError for self-referencing task."""
    plan = AgentPlan(
        tasks=[
            PlanTask(id="a", domain="backend", prompt="x", deps=["a"]),
        ]
    )
    with pytest.raises(ValueError, match="cycle"):
        validate_dag(plan)


def test_validate_dag_rejects_invalid_dep_reference():
    """validate_dag raises ValueError for non-existent dependency."""
    plan = AgentPlan(
        tasks=[
            PlanTask(id="t1", domain="backend", prompt="x", deps=["nonexistent"]),
        ]
    )
    with pytest.raises(ValueError, match="unknown task 'nonexistent'"):
        validate_dag(plan)


def test_validate_dag_rejects_multiple_invalid_deps():
    """validate_dag raises ValueError on first invalid dependency encountered."""
    plan = AgentPlan(
        tasks=[
            PlanTask(id="t1", domain="backend", prompt="x", deps=["missing1"]),
            PlanTask(id="t2", domain="testing", prompt="y", deps=["missing2"]),
        ]
    )
    with pytest.raises(ValueError, match="unknown task"):
        validate_dag(plan)


def test_validate_dag_error_includes_valid_ids():
    """validate_dag error message includes list of valid task IDs."""
    plan = AgentPlan(
        tasks=[
            PlanTask(id="t1", domain="backend", prompt="x", deps=[]),
            PlanTask(
                id="t2", domain="testing", prompt="y", deps=["t3"]
            ),  # t3 doesn't exist
        ]
    )
    with pytest.raises(ValueError) as exc_info:
        validate_dag(plan)
    assert "t1" in str(exc_info.value) or "t2" in str(exc_info.value)


# --- AgentState reducer verification ---


def test_agentstate_completed_uses_add_reducer():
    """AgentState.completed uses operator.add as reducer."""
    hints = get_type_hints(AgentState, include_extras=True)
    completed_hint = hints.get("completed")
    # Check it's Annotated with operator.add
    assert hasattr(completed_hint, "__metadata__")
    assert operator.add in completed_hint.__metadata__


def test_agentstate_errors_uses_add_reducer():
    """AgentState.errors uses operator.add as reducer."""
    hints = get_type_hints(AgentState, include_extras=True)
    errors_hint = hints.get("errors")
    assert hasattr(errors_hint, "__metadata__")
    assert operator.add in errors_hint.__metadata__


def test_agentstate_failed_uses_add_reducer():
    """AgentState.failed uses operator.add as reducer."""
    hints = get_type_hints(AgentState, include_extras=True)
    failed_hint = hints.get("failed")
    assert hasattr(failed_hint, "__metadata__")
    assert operator.add in failed_hint.__metadata__


def test_agentstate_outputs_uses_merge_reducer():
    """AgentState.outputs uses _merge_dicts as reducer."""
    from maestro.planner.schemas import _merge_dicts

    hints = get_type_hints(AgentState, include_extras=True)
    outputs_hint = hints.get("outputs")
    assert hasattr(outputs_hint, "__metadata__")
    assert _merge_dicts in outputs_hint.__metadata__


def test_agentstate_reducers_preserve_parallel_worker_contributions():
    """Reducer functions combine list and dict updates without dropping data."""
    from maestro.planner.schemas import _merge_dicts

    completed = operator.add(["t1"], ["t2"])
    failed = operator.add(["t3"], ["t4"])
    errors = operator.add(["worker-a failed"], ["worker-b failed"])
    outputs = _merge_dicts({"t1": "api.py"}, {"t2": "test_api.py"})

    assert completed == ["t1", "t2"]
    assert failed == ["t3", "t4"]
    assert errors == ["worker-a failed", "worker-b failed"]
    assert outputs == {"t1": "api.py", "t2": "test_api.py"}


def test_agentstate_has_required_fields():
    """AgentState has all required TypedDict fields."""
    hints = get_type_hints(AgentState, include_extras=True)
    required_fields = {
        "task",
        "dag",
        "completed",
        "failed",
        "outputs",
        "errors",
        "depth",
        "max_depth",
        "workdir",
        "auto",
        "ready_tasks",
        # NotRequired fields are also in type hints but not required at runtime
        "current_task_id",
        "current_task_domain",
        "current_task_prompt",
    }
    assert set(hints.keys()) == required_fields
