"""Tests for scheduler, dispatch, worker, and graph execution."""

import pytest
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock
from langgraph.types import Send
from langgraph.graph import END

from maestro.multi_agent import (
    scheduler_node,
    scheduler_route,
    dispatch_node,
    dispatch_route,
    worker_node,
    run_multi_agent,
    graph,
    _materialize_plan,
)
from maestro.planner.schemas import AgentPlan, PlanTask


# --- Scheduler Node Tests ---


def test_scheduler_returns_initial_ready_batch():
    """Scheduler returns only tasks with no unmet dependencies."""
    plan = AgentPlan(tasks=[
        PlanTask(id="t1", domain="backend", prompt="Task 1", deps=[]),
        PlanTask(id="t2", domain="testing", prompt="Task 2", deps=["t1"]),
    ])
    state = {
        "task": "test",
        "dag": plan.model_dump(),
        "completed": [],
        "failed": [],
        "outputs": {},
        "errors": [],
        "depth": 0,
        "max_depth": 2,
        "workdir": ".",
        "auto": False,
        "ready_tasks": [],
    }

    result = scheduler_node(state)

    assert len(result["ready_tasks"]) == 1
    assert result["ready_tasks"][0]["id"] == "t1"
    assert result["ready_tasks"][0]["domain"] == "backend"


def test_scheduler_unblocks_next_batch_after_completion():
    """t2 and t3 are dispatched only after t1 is marked complete."""
    plan = AgentPlan(tasks=[
        PlanTask(id="t1", domain="backend", prompt="Task 1", deps=[]),
        PlanTask(id="t2", domain="testing", prompt="Task 2", deps=["t1"]),
        PlanTask(id="t3", domain="docs", prompt="Task 3", deps=["t1"]),
    ])

    # Initial: only t1 ready
    state1 = {
        "task": "test",
        "dag": plan.model_dump(),
        "completed": [],
        "failed": [],
        "outputs": {},
        "errors": [],
        "depth": 0,
        "max_depth": 2,
        "workdir": ".",
        "auto": False,
        "ready_tasks": [],
    }
    result1 = scheduler_node(state1)
    assert len(result1["ready_tasks"]) == 1
    assert result1["ready_tasks"][0]["id"] == "t1"

    # After t1 completes: t2 and t3 ready
    state2 = {
        "task": "test",
        "dag": plan.model_dump(),
        "completed": ["t1"],
        "failed": [],
        "outputs": {},
        "errors": [],
        "depth": 0,
        "max_depth": 2,
        "workdir": ".",
        "auto": False,
        "ready_tasks": [],
    }
    result2 = scheduler_node(state2)
    assert len(result2["ready_tasks"]) == 2
    ready_ids = {t["id"] for t in result2["ready_tasks"]}
    assert ready_ids == {"t2", "t3"}


def test_scheduler_ends_with_blocked_dependency_error_after_failure():
    """Scheduler terminates when remaining task depends on a failed task."""
    plan = AgentPlan(tasks=[
        PlanTask(id="t1", domain="backend", prompt="Task 1", deps=[]),
        PlanTask(id="t2", domain="testing", prompt="Task 2", deps=["t1"]),
    ])
    state = {
        "task": "test",
        "dag": plan.model_dump(),
        "completed": [],
        "failed": ["t1"],  # t1 failed
        "outputs": {},
        "errors": [],
        "depth": 0,
        "max_depth": 2,
        "workdir": ".",
        "auto": False,
        "ready_tasks": [],
    }

    result = scheduler_node(state)

    # No ready tasks and t2 is blocked
    assert len(result["ready_tasks"]) == 0
    assert "errors" in result
    assert "blocked" in result["errors"][0].lower()
    assert "t2" in result["errors"][0]


def test_scheduler_no_redispatch_of_terminal_tasks():
    """Scheduler does not return already completed or failed tasks as ready."""
    plan = AgentPlan(tasks=[
        PlanTask(id="t1", domain="backend", prompt="Task 1", deps=[]),
    ])
    state = {
        "task": "test",
        "dag": plan.model_dump(),
        "completed": ["t1"],  # Already done
        "failed": [],
        "outputs": {},
        "errors": [],
        "depth": 0,
        "max_depth": 2,
        "workdir": ".",
        "auto": False,
        "ready_tasks": [],
    }

    result = scheduler_node(state)

    assert len(result["ready_tasks"]) == 0


def test_scheduler_handles_empty_plan():
    """Scheduler handles empty task list gracefully."""
    plan = AgentPlan(tasks=[])
    state = {
        "task": "test",
        "dag": plan.model_dump(),
        "completed": [],
        "failed": [],
        "outputs": {},
        "errors": [],
        "depth": 0,
        "max_depth": 2,
        "workdir": ".",
        "auto": False,
        "ready_tasks": [],
    }

    result = scheduler_node(state)

    assert len(result["ready_tasks"]) == 0


def test_scheduler_detects_unknown_dependency():
    """Scheduler reports error for tasks with unknown dependencies."""
    # Create plan with invalid dependency via raw dict to bypass Pydantic validation
    dag_dict = {
        "tasks": [
            {"id": "t1", "domain": "backend", "prompt": "Task 1", "deps": ["nonexistent"]},
        ]
    }
    state = {
        "task": "test",
        "dag": dag_dict,
        "completed": [],
        "failed": [],
        "outputs": {},
        "errors": [],
        "depth": 0,
        "max_depth": 2,
        "workdir": ".",
        "auto": False,
        "ready_tasks": [],
    }

    result = scheduler_node(state)

    assert len(result["ready_tasks"]) == 0
    assert "errors" in result
    assert "unknown" in result["errors"][0].lower()


# --- Scheduler Route Tests ---


def test_scheduler_route_returns_dispatch_when_ready():
    """scheduler_route returns 'dispatch' when there are ready tasks."""
    plan = AgentPlan(tasks=[
        PlanTask(id="t1", domain="backend", prompt="Task 1", deps=[]),
    ])
    state = {
        "task": "test",
        "dag": plan.model_dump(),
        "completed": [],
        "failed": [],
        "outputs": {},
        "errors": [],
        "depth": 0,
        "max_depth": 2,
        "workdir": ".",
        "auto": False,
        "ready_tasks": [{"id": "t1", "domain": "backend", "prompt": "Task 1"}],
    }

    result = scheduler_route(state)

    assert result == "dispatch"


def test_scheduler_route_returns_end_when_all_done():
    """scheduler_route returns END when all tasks are terminal."""
    plan = AgentPlan(tasks=[
        PlanTask(id="t1", domain="backend", prompt="Task 1", deps=[]),
    ])
    state = {
        "task": "test",
        "dag": plan.model_dump(),
        "completed": ["t1"],
        "failed": [],
        "outputs": {},
        "errors": [],
        "depth": 0,
        "max_depth": 2,
        "workdir": ".",
        "auto": False,
        "ready_tasks": [],
    }

    result = scheduler_route(state)

    assert result == END


def test_scheduler_route_returns_end_when_no_ready_and_unfinished_blocked():
    """scheduler_route returns END when no ready tasks and unfinished are blocked."""
    plan = AgentPlan(tasks=[
        PlanTask(id="t1", domain="backend", prompt="Task 1", deps=[]),
        PlanTask(id="t2", domain="testing", prompt="Task 2", deps=["t1"]),
    ])
    state = {
        "task": "test",
        "dag": plan.model_dump(),
        "completed": [],
        "failed": ["t1"],  # t1 failed, t2 blocked
        "outputs": {},
        "errors": [],
        "depth": 0,
        "max_depth": 2,
        "workdir": ".",
        "auto": False,
        "ready_tasks": [],
    }

    result = scheduler_route(state)

    assert result == END


# --- Dispatch Node and Route Tests ---


def test_dispatch_node_returns_empty():
    """dispatch_node returns empty dict (no-op)."""
    state = {
        "task": "test",
        "dag": {"tasks": []},
        "completed": [],
        "failed": [],
        "outputs": {},
        "errors": [],
        "depth": 0,
        "max_depth": 2,
        "workdir": ".",
        "auto": False,
        "ready_tasks": [],
    }

    result = dispatch_node(state)

    assert result == {}


def test_dispatch_route_returns_one_send_per_ready_task():
    """dispatch_route produces parallel Send objects with correct payloads."""
    state = {
        "task": "test",
        "dag": {"tasks": []},
        "completed": [],
        "failed": [],
        "outputs": {},
        "errors": [],
        "depth": 1,
        "max_depth": 3,
        "workdir": "/tmp/test",
        "auto": True,
        "ready_tasks": [
            {"id": "t1", "domain": "backend", "prompt": "Build API"},
            {"id": "t2", "domain": "testing", "prompt": "Write tests"},
        ],
    }

    result = dispatch_route(state)

    assert len(result) == 2
    assert all(isinstance(s, Send) for s in result)
    assert all(s.node == "worker" for s in result)

    # Check first send
    send1 = result[0]
    assert send1.arg["current_task_id"] == "t1"
    assert send1.arg["current_task_domain"] == "backend"
    assert send1.arg["current_task_prompt"] == "Build API"
    assert send1.arg["depth"] == 1
    assert send1.arg["max_depth"] == 3
    assert send1.arg["workdir"] == "/tmp/test"
    assert send1.arg["auto"] == True

    # Check second send
    send2 = result[1]
    assert send2.arg["current_task_id"] == "t2"
    assert send2.arg["current_task_domain"] == "testing"


def test_dispatch_route_returns_empty_list_when_no_ready():
    """dispatch_route returns empty list when ready_tasks is empty."""
    state = {
        "task": "test",
        "dag": {"tasks": []},
        "completed": [],
        "failed": [],
        "outputs": {},
        "errors": [],
        "depth": 0,
        "max_depth": 2,
        "workdir": ".",
        "auto": False,
        "ready_tasks": [],
    }

    result = dispatch_route(state)

    assert result == []


# --- Worker Node Tests ---


def test_worker_uses_domain_prompt_and_task_prompt():
    """Worker composes system prompt from domain + task prompt."""
    # Patch at the usage site (where it's imported in multi_agent)
    with patch("maestro.multi_agent._run_agentic_loop") as mock_loop:
        mock_loop.return_value = "Task completed"

        state = {
            "task": "test",
            "dag": {"tasks": []},
            "completed": [],
            "failed": [],
            "outputs": {},
            "errors": [],
            "depth": 0,
            "max_depth": 2,
            "workdir": ".",
            "auto": False,
            "ready_tasks": [],
            "current_task_id": "t1",
            "current_task_domain": "backend",
            "current_task_prompt": "Build a REST API",
        }

        result = worker_node(state)

        mock_loop.assert_called_once()
        call_kwargs = mock_loop.call_args.kwargs

        # Check that instructions contain domain and task
        instructions = call_kwargs["instructions"]
        assert "backend" in instructions.lower() or "API design" in instructions
        assert "Build a REST API" in instructions

        # Check return shape
        assert result["completed"] == ["t1"]
        assert result["outputs"] == {"t1": "Task completed"}


def test_worker_records_error_and_failed_task_without_crashing_graph():
    """Worker exceptions are converted to failed + errors state."""
    with patch("maestro.multi_agent._run_agentic_loop") as mock_loop:
        mock_loop.side_effect = RuntimeError("Simulated failure")

        state = {
            "task": "test",
            "dag": {"tasks": []},
            "completed": [],
            "failed": [],
            "outputs": {},
            "errors": [],
            "depth": 0,
            "max_depth": 2,
            "workdir": ".",
            "auto": False,
            "ready_tasks": [],
            "current_task_id": "t1",
            "current_task_domain": "backend",
            "current_task_prompt": "Task that fails",
        }

        result = worker_node(state)

        # Should NOT raise - converts to state update
        assert result["failed"] == ["t1"]
        assert len(result["errors"]) == 1
        assert "t1:" in result["errors"][0]
        assert "Simulated failure" in result["errors"][0]
        assert "completed" not in result


def test_worker_rejects_depth_above_max_depth():
    """Worker does not execute when depth > max_depth."""
    with patch("maestro.multi_agent._run_agentic_loop") as mock_loop:
        state = {
            "task": "test",
            "dag": {"tasks": []},
            "completed": [],
            "failed": [],
            "outputs": {},
            "errors": [],
            "depth": 3,  # Exceeds max_depth of 2
            "max_depth": 2,
            "workdir": ".",
            "auto": False,
            "ready_tasks": [],
            "current_task_id": "t1",
            "current_task_domain": "backend",
            "current_task_prompt": "Some task",
        }

        result = worker_node(state)

        # Should not call agent loop
        mock_loop.assert_not_called()

        # Should record failure
        assert result["failed"] == ["t1"]
        assert "depth" in result["errors"][0].lower()
        assert "3" in result["errors"][0]


def test_worker_handles_missing_fields():
    """Worker handles missing task fields gracefully."""
    state = {
        "task": "test",
        "dag": {"tasks": []},
        "completed": [],
        "failed": [],
        "outputs": {},
        "errors": [],
        "depth": 0,
        "max_depth": 2,
        "workdir": ".",
        "auto": False,
        "ready_tasks": [],
        # Missing current_task_id, domain, prompt
    }

    result = worker_node(state)

    assert result["failed"] == ["unknown"]
    assert "missing" in result["errors"][0].lower() or "required" in result["errors"][0].lower()


def test_worker_blocks_write_outside_workdir():
    """Worker path guard prevents writes outside workdir during tool execution."""
    # Create a temp directory as workdir and a path outside it
    with tempfile.TemporaryDirectory() as workdir:
        # Path outside the workdir - simulating an escape attempt
        outside_path = Path(workdir).parent / "escape_attempt.txt"

        # Mock provider that returns a tool call to write outside workdir
        mock_provider = MagicMock()
        tool_call_chunk = {
            "choices": [{
                "delta": {
                    "tool_calls": [{
                        "index": 0,
                        "id": "call_123",
                        "function": {
                            "name": "write_file",
                            "arguments": '{"path": "../escape_attempt.txt", "content": "escaped"}'
                        }
                    }]
                },
                "finish_reason": None
            }]
        }
        finish_chunk = {
            "choices": [{
                "delta": {},
                "finish_reason": "tool_calls"
            }]
        }

        async def mock_stream(*args, **kwargs):
            """Simulate provider returning a write_file tool call for escaping path."""
            yield tool_call_chunk
            yield finish_chunk

        mock_provider.stream = mock_stream
        mock_provider.list_models.return_value = ["gpt-4o"]

        state = {
            "task": "test",
            "dag": {"tasks": []},
            "completed": [],
            "failed": [],
            "outputs": {},
            "errors": [],
            "depth": 0,
            "max_depth": 2,
            "workdir": workdir,
            "auto": True,  # Auto-approve to ensure tool runs
            "ready_tasks": [],
            "current_task_id": "t1",
            "current_task_domain": "backend",
            "current_task_prompt": "Write a file",
            "provider": mock_provider,
            "model": "gpt-4o",
        }

        result = worker_node(state)

        # The task should fail because the path guard blocked the write
        assert "failed" in result
        assert "t1" in result["failed"]
        assert "errors" in result
        assert len(result["errors"]) > 0

        # Verify the file was NOT created outside the workdir
        assert not outside_path.exists(), f"Security violation: file was created outside workdir at {outside_path}"


# --- Runner Tests ---


def test_depth_argument_is_required_on_runner():
    """Omitting depth when calling run_multi_agent() raises TypeError."""
    with tempfile.TemporaryDirectory() as tmpdir:
        with pytest.raises(TypeError, match="depth"):
            run_multi_agent(
                task="test",
                workdir=Path(tmpdir),
                auto=False,
                # depth is missing - should raise
            )


def test_run_multi_agent_rejects_invalid_workdir():
    """run_multi_agent raises ValueError for non-existent workdir."""
    with pytest.raises(ValueError, match="does not exist"):
        run_multi_agent(
            task="test",
            workdir=Path("/nonexistent/path"),
            auto=False,
            depth=0,
        )


def test_run_multi_agent_rejects_file_as_workdir():
    """run_multi_agent raises ValueError if workdir is a file."""
    import tempfile
    with tempfile.NamedTemporaryFile() as tmp:
        with pytest.raises(ValueError, match="not a directory"):
            run_multi_agent(
                task="test",
                workdir=Path(tmp.name),
                auto=False,
                depth=0,
            )


# --- Graph Integration Tests ---


def test_independent_branch_continues_after_other_worker_failure():
    """One branch fails, another independent branch succeeds; both outputs preserved."""
    plan = AgentPlan(tasks=[
        PlanTask(id="fail_task", domain="backend", prompt="Will fail", deps=[]),
        PlanTask(id="success_task", domain="testing", prompt="Will succeed", deps=[]),
    ])

    def mock_run_loop(messages, model, instructions, workdir, auto, **kwargs):
        """Mock that succeeds or fails based on task content."""
        # Instructions contain the task prompt (e.g., "Will fail")
        if "Will fail" in instructions:
            raise RuntimeError("Simulated failure")
        elif "Will succeed" in instructions:
            return "Output from success_task"
        return "default output"

    # Patch where the function is used (imported in multi_agent)
    with patch("maestro.multi_agent._run_agentic_loop", side_effect=mock_run_loop):
        state = {
            "task": "test",
            "dag": plan.model_dump(),
            "completed": [],
            "failed": [],
            "outputs": {},
            "errors": [],
            "depth": 0,
            "max_depth": 2,
            "workdir": ".",
            "auto": False,
            "ready_tasks": [],
        }

        final_state = graph.invoke(state)

        # Both tasks should be terminal
        assert "fail_task" in final_state.get("failed", [])
        assert "success_task" in final_state.get("completed", [])

        # Output from successful task should be preserved
        assert final_state["outputs"].get("success_task") == "Output from success_task"


def test_parallel_worker_writes_preserve_both_outputs():
    """Two ready workers complete; both outputs survive reducer fan-in."""
    plan = AgentPlan(tasks=[
        PlanTask(id="t1", domain="backend", prompt="Task 1", deps=[]),
        PlanTask(id="t2", domain="testing", prompt="Task 2", deps=[]),
    ])

    call_count = 0

    def mock_run_loop(messages, model, instructions, workdir, auto, **kwargs):
        """Mock that returns output based on task content."""
        nonlocal call_count
        call_count += 1
        if "Task 1" in instructions:
            return "Result from t1"
        elif "Task 2" in instructions:
            return "Result from t2"
        return "default"

    with patch("maestro.multi_agent._run_agentic_loop", side_effect=mock_run_loop):
        state = {
            "task": "test",
            "dag": plan.model_dump(),
            "completed": [],
            "failed": [],
            "outputs": {},
            "errors": [],
            "depth": 0,
            "max_depth": 2,
            "workdir": ".",
            "auto": False,
            "ready_tasks": [],
        }

        final_state = graph.invoke(state)

        # Both tasks completed
        assert set(final_state["completed"]) == {"t1", "t2"}

        # Both outputs preserved
        assert final_state["outputs"].get("t1") == "Result from t1"
        assert final_state["outputs"].get("t2") == "Result from t2"


def test_graph_executes_dependent_task_chain():
    """Graph runs t1 then t2 (depends on t1) in sequence."""
    plan = AgentPlan(tasks=[
        PlanTask(id="t1", domain="backend", prompt="Task 1", deps=[]),
        PlanTask(id="t2", domain="testing", prompt="Task 2", deps=["t1"]),
    ])

    execution_order = []

    def mock_run_loop(messages, model, instructions, workdir, auto, **kwargs):
        """Mock that tracks execution order and returns results."""
        nonlocal execution_order
        if "Task 1" in instructions:
            execution_order.append("t1")
            return "Result from t1"
        elif "Task 2" in instructions:
            execution_order.append("t2")
            return "Result from t2"
        return "default"

    with patch("maestro.multi_agent._run_agentic_loop", side_effect=mock_run_loop):
        state = {
            "task": "test",
            "dag": plan.model_dump(),
            "completed": [],
            "failed": [],
            "outputs": {},
            "errors": [],
            "depth": 0,
            "max_depth": 2,
            "workdir": ".",
            "auto": False,
            "ready_tasks": [],
        }

        final_state = graph.invoke(state)

        # Both tasks should complete
        assert set(final_state["completed"]) == {"t1", "t2"}

        # t1 should execute before t2
        assert execution_order.index("t1") < execution_order.index("t2")
