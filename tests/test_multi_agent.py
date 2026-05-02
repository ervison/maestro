import asyncio
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest

from maestro import multi_agent
from maestro.planner.schemas import AgentPlan, AggregatorGuardrail
from maestro.providers.base import Message


class FakeEmitter:
    def __init__(self) -> None:
        self.events: list[dict] = []

    def emit(self, event: dict) -> None:
        self.events.append(event)


def make_plan(*tasks: dict) -> AgentPlan:
    return AgentPlan.model_validate({"tasks": list(tasks)})


def test_check_aggregator_guardrail_variants() -> None:
    assert multi_agent.check_aggregator_guardrail(AggregatorGuardrail(max_calls=0), 0, {}) == (
        False,
        "aggregation disabled (max_calls=0)",
    )
    assert multi_agent.check_aggregator_guardrail(AggregatorGuardrail(max_calls=1), 1, {}) == (
        False,
        "call limit reached (1/1)",
    )
    assert multi_agent.check_aggregator_guardrail(
        AggregatorGuardrail(max_tokens_per_run=1), 0, {"t1": "12345678"}
    ) == (False, "token budget exceeded (estimated 2 > max 1)")
    assert multi_agent.check_aggregator_guardrail(AggregatorGuardrail(), 0, {"t1": "ok"}) == (
        True,
        None,
    )


def test_plan_materialization_validation_and_task_collection() -> None:
    plan = make_plan(
        {"id": "t1", "domain": "backend", "prompt": "first", "deps": []},
        {"id": "t2", "domain": "testing", "prompt": "second", "deps": ["t1"]},
        {"id": "t3", "domain": "docs", "prompt": "third", "deps": ["t2"]},
    )

    assert multi_agent._materialize_plan(plan.model_dump()) == plan

    with patch("maestro.multi_agent.validate_dag", side_effect=ValueError("cycle")):
        assert multi_agent._validate_plan(plan) == "DAG validation failed: cycle"

    ready = multi_agent._collect_ready_tasks(plan, completed={"t1"}, in_progress=set(), terminal={"t1"})
    blocked = multi_agent._collect_blocked_tasks(plan, ready_ids={"t2"}, terminal={"t1", "t2"}, failed={"t2"})

    assert ready == [{"id": "t2", "domain": "testing", "prompt": "second"}]
    assert blocked == ["t3"]


def test_scheduler_node_reports_validation_and_blocked_tasks() -> None:
    emitter = FakeEmitter()
    state = {
        "dag": {"tasks": []},
        "completed": [],
        "failed": [],
        "dispatched": [],
        "emitter": emitter,
    }

    with patch("maestro.multi_agent._materialize_plan", return_value=Mock()), patch(
        "maestro.multi_agent._validate_plan", return_value="bad dag"
    ):
        assert multi_agent.scheduler_node(state) == {"ready_tasks": [], "errors": ["bad dag"]}

    plan = make_plan(
        {"id": "t1", "domain": "backend", "prompt": "first", "deps": []},
        {"id": "t2", "domain": "testing", "prompt": "second", "deps": ["t1"]},
    )
    state = {
        "dag": plan.model_dump(),
        "completed": [],
        "failed": ["t1"],
        "dispatched": [],
        "emitter": emitter,
    }
    result = multi_agent.scheduler_node(state)

    assert result["ready_tasks"] == []
    assert result["dispatched"] == []
    assert "blocked by failed dependencies" in result["errors"][0]
    assert emitter.events[-1] == {"type": "node_update", "id": "scheduler", "status": "done"}


def test_scheduler_route_dispatch_aggregator_wait_and_end() -> None:
    plan = make_plan(
        {"id": "t1", "domain": "backend", "prompt": "first", "deps": []}
    ).model_dump()

    assert multi_agent.scheduler_route({"ready_tasks": [{"id": "t1"}], "dag": plan}) == "dispatch"
    assert multi_agent.scheduler_route(
        {
            "ready_tasks": [],
            "dag": plan,
            "completed": ["t1"],
            "failed": [],
            "aggregate": False,
        }
    ) == multi_agent.END

    with patch(
        "maestro.multi_agent.check_aggregator_guardrail", return_value=(False, "nope")
    ) as guardrail:
        assert multi_agent.scheduler_route(
            {
                "ready_tasks": [],
                "dag": plan,
                "completed": ["t1"],
                "failed": [],
                "aggregate": True,
                "outputs": {},
                "agg_guardrail": AggregatorGuardrail(),
                "agg_calls_done": 0,
            }
        ) == multi_agent.END
        guardrail.assert_called_once()

    with patch(
        "maestro.multi_agent.check_aggregator_guardrail", return_value=(True, None)
    ):
        assert multi_agent.scheduler_route(
            {
                "ready_tasks": [],
                "dag": plan,
                "completed": ["t1"],
                "failed": [],
                "aggregate": True,
                "outputs": {},
                "agg_guardrail": AggregatorGuardrail(),
                "agg_calls_done": 0,
            }
        ) == "aggregator"

    assert multi_agent.scheduler_route(
        {
            "ready_tasks": [],
            "dag": make_plan(
                {"id": "t1", "domain": "backend", "prompt": "first", "deps": []},
                {"id": "t2", "domain": "testing", "prompt": "second", "deps": ["t1"]},
            ).model_dump(),
            "completed": [],
            "failed": [],
            "dispatched": ["t1"],
        }
    ) == "scheduler"

    assert multi_agent.scheduler_route(
        {
            "ready_tasks": [],
            "dag": make_plan(
                {"id": "t1", "domain": "backend", "prompt": "first", "deps": ["missing"]}
            ).model_dump(),
            "completed": [],
            "failed": [],
            "dispatched": [],
        }
    ) == multi_agent.END


def test_dispatch_node_and_route_emit_worker_sends() -> None:
    emitter = FakeEmitter()
    provider = SimpleNamespace(id="provider-1")
    state = {
        "ready_tasks": [{"id": "t1", "domain": "backend", "prompt": "build it"}],
        "depth": 1,
        "max_depth": 2,
        "workdir": "/tmp/work",
        "auto": True,
        "provider": provider,
        "model": "gpt-5",
        "emitter": emitter,
    }

    assert multi_agent.dispatch_node(state) == {}
    sends = multi_agent.dispatch_route(state)

    assert len(sends) == 1
    assert sends[0].node == "worker"
    assert sends[0].arg["current_task_id"] == "t1"
    assert sends[0].arg["provider"] is provider
    assert sends[0].arg["model"] == "gpt-5"
    assert emitter.events[0]["status"] == "active"


def test_worker_node_validation_and_invalid_workdir(tmp_path) -> None:
    assert multi_agent.worker_node({"current_task_id": "t1"}) == {
        "failed": ["t1"],
        "errors": ["t1: Worker missing required task fields (id, domain, prompt)"],
    }

    assert multi_agent.worker_node(
        {
            "current_task_id": "t1",
            "current_task_domain": "backend",
            "current_task_prompt": "do work",
            "depth": 3,
            "max_depth": 2,
        }
    ) == {"failed": ["t1"], "errors": ["t1: Depth 3 exceeds max_depth 2"]}

    bad_parent = tmp_path / "file-parent"
    bad_parent.write_text("x")
    result = multi_agent.worker_node(
        {
            "current_task_id": "t1",
            "current_task_domain": "backend",
            "current_task_prompt": "do work",
            "depth": 0,
            "max_depth": 2,
            "workdir": str(bad_parent / "child"),
        }
    )
    assert result["failed"] == ["t1"]
    assert "Invalid workdir" in result["errors"][0]


def test_worker_node_success_and_failure_emit_events(tmp_path) -> None:
    emitter = FakeEmitter()
    provider = SimpleNamespace(id="provider-1")
    state = {
        "current_task_id": "t1",
        "current_task_domain": "backend",
        "current_task_prompt": "do work",
        "depth": 0,
        "max_depth": 2,
        "workdir": str(tmp_path / "work"),
        "auto": False,
        "provider": provider,
        "model": "gpt-5",
        "emitter": emitter,
    }

    def fake_run_agentic_loop(**kwargs):
        kwargs["on_text"]("chunk")
        kwargs["on_tool_start"]()
        return "done"

    with patch("maestro.multi_agent.get_domain_prompt", return_value="domain prompt"), patch(
        "maestro.multi_agent.agent_module._run_agentic_loop", side_effect=fake_run_agentic_loop
    ):
        result = multi_agent.worker_node(state)

    assert result == {"completed": ["t1"], "outputs": {"t1": "done"}}
    assert any(event.get("kind") == "text" for event in emitter.events)
    assert any(event.get("kind") == "tool" for event in emitter.events)
    assert emitter.events[-1]["status"] == "done"

    with patch("maestro.multi_agent.get_domain_prompt", return_value="domain prompt"), patch(
        "maestro.multi_agent.agent_module._run_agentic_loop", side_effect=RuntimeError("boom")
    ):
        failure = multi_agent.worker_node(state)

    assert failure == {"failed": ["t1"], "errors": ["t1: boom"]}
    assert emitter.events[-1]["status"] == "failed"


def test_worker_node_resolves_default_provider_when_missing(tmp_path) -> None:
    provider = SimpleNamespace(id="provider-1")

    with patch("maestro.multi_agent.get_domain_prompt", return_value="domain prompt"), patch(
        "maestro.multi_agent.get_default_provider", return_value=provider
    ) as get_provider, patch(
        "maestro.multi_agent.agent_module._run_agentic_loop", return_value="done"
    ) as run_loop:
        result = multi_agent.worker_node(
            {
                "current_task_id": "t1",
                "current_task_domain": "backend",
                "current_task_prompt": "do work",
                "depth": 0,
                "max_depth": 2,
                "workdir": str(tmp_path / "work"),
                "auto": False,
                "model": "gpt-5",
            }
        )

    assert result == {"completed": ["t1"], "outputs": {"t1": "done"}}
    get_provider.assert_called_once()
    assert run_loop.call_args.kwargs["provider"] is provider


def test_aggregator_helpers_and_stream_behaviors() -> None:
    prompt = multi_agent._build_aggregator_prompt(
        "ship it", {"t1": "done"}, ["t2"], ["t2: boom"]
    )
    assert "=== t1 ===\ndone" in prompt
    assert "=== Failed Tasks ===" in prompt
    assert "=== Errors ===" in prompt

    runtime_provider = SimpleNamespace(id="provider-1")
    resolved_provider = SimpleNamespace(id="provider-1")
    with patch("maestro.multi_agent.resolve_model", return_value=(resolved_provider, "agg-model")):
        provider, model = multi_agent._resolve_aggregator_provider({"provider": runtime_provider})
        assert provider is runtime_provider
        assert model == "agg-model"

    other_provider = SimpleNamespace(id="provider-2")
    with patch("maestro.multi_agent.resolve_model", return_value=(resolved_provider, "agg-model")):
        provider, _ = multi_agent._resolve_aggregator_provider({"provider": other_provider})
        assert provider is resolved_provider

    class FakeProvider:
        async def stream(self, messages, model):
            assert messages[0].role == "system"
            assert model == "agg-model"
            yield "part1"
            yield Message(role="assistant", content="final")

    assert multi_agent._run_aggregator_sync(FakeProvider(), "agg-model", "user", "task") == "final"


def test_run_aggregator_sync_uses_existing_event_loop_branch() -> None:
    loop = Mock()
    loop.is_running.return_value = False
    loop.run_until_complete.side_effect = lambda coro: asyncio.run(coro)

    with patch("maestro.multi_agent.asyncio.get_running_loop", return_value=loop):
        with patch("maestro.multi_agent._run_aggregator_stream", return_value="done"):
            assert multi_agent._run_aggregator_sync(Mock(), "model", "user", "task") == "done"


def test_run_aggregator_sync_uses_threadpool_for_running_loop() -> None:
    loop = Mock()
    loop.is_running.return_value = True

    class FakeFuture:
        def __init__(self, fn):
            self._fn = fn

        def result(self):
            return self._fn()

    class FakeExecutor:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return None

        def submit(self, fn):
            return FakeFuture(fn)

    with patch("maestro.multi_agent.asyncio.get_running_loop", return_value=loop), patch(
        "maestro.multi_agent.concurrent.futures.ThreadPoolExecutor", return_value=FakeExecutor()
    ), patch("maestro.multi_agent._run_aggregator_stream", return_value="threaded"):
        assert multi_agent._run_aggregator_sync(Mock(), "model", "user", "task") == "threaded"


def test_aggregator_node_empty_success_blank_and_failure() -> None:
    emitter = FakeEmitter()
    state = {"task": "ship it", "outputs": {}, "failed": [], "errors": [], "emitter": emitter}
    assert multi_agent.aggregator_node(state) == {"summary": "No worker outputs to summarize."}
    assert emitter.events[-1] == {"type": "node_update", "id": "aggregator", "status": "done"}

    state = {
        "task": "ship it",
        "outputs": {"t1": "done"},
        "failed": [],
        "errors": [],
        "emitter": emitter,
        "agg_calls_done": 2,
    }
    with patch("maestro.multi_agent._resolve_aggregator_provider", return_value=(Mock(), "agg-model")), patch(
        "maestro.multi_agent._run_aggregator_sync", return_value="   "
    ):
        result = multi_agent.aggregator_node(state)
    assert result == {
        "summary": "Aggregation completed but produced no output.",
        "agg_calls_done": 3,
    }

    with patch("maestro.multi_agent._resolve_aggregator_provider", return_value=(Mock(), "agg-model")), patch(
        "maestro.multi_agent._run_aggregator_sync", side_effect=RuntimeError("boom")
    ):
        failure = multi_agent.aggregator_node(state)
    assert failure["summary"] == "Failed to generate summary: boom"


def test_run_multi_agent_validates_workdir_and_orchestrates_graph(tmp_path) -> None:
    missing = tmp_path / "missing"
    with pytest.raises(ValueError, match="workdir does not exist"):
        multi_agent.run_multi_agent(task="do work", workdir=missing, auto=False, depth=0)

    file_path = tmp_path / "file.txt"
    file_path.write_text("x")
    with pytest.raises(ValueError, match="workdir is not a directory"):
        multi_agent.run_multi_agent(task="do work", workdir=file_path, auto=False, depth=0)

    workdir = tmp_path / "work"
    workdir.mkdir()
    emitter = FakeEmitter()
    provider = SimpleNamespace(id="provider-1")
    dag = {
        "tasks": [
            {"id": "t1", "domain": "backend", "prompt": "build feature", "deps": []}
        ]
    }

    with patch("maestro.multi_agent.load_config", return_value=SimpleNamespace(get=lambda key, default=None: {"aggregator.enabled": False}.get(key, default))), patch(
        "maestro.multi_agent.planner_node", return_value={"dag": dag}
    ) as planner, patch(
        "maestro.multi_agent.graph.invoke",
        return_value={"outputs": {"t1": "done"}, "failed": [], "errors": [], "summary": "summary"},
    ) as invoke:
        result = multi_agent.run_multi_agent(
            task="do work",
            workdir=workdir,
            auto=True,
            depth=1,
            provider=provider,
            model="gpt-5",
            emitter=emitter,
        )

    assert result == {"outputs": {"t1": "done"}, "failed": [], "errors": [], "summary": "summary"}
    planner.assert_called_once()
    initial_state = invoke.call_args.args[0]
    assert initial_state["aggregate"] is False
    assert initial_state["model"] == "gpt-5"
    assert any(event["type"] == "dag_ready" for event in emitter.events)


def test_run_multi_agent_raises_when_planner_produces_no_dag(tmp_path) -> None:
    workdir = tmp_path / "work"
    workdir.mkdir()

    with patch("maestro.multi_agent.load_config", return_value=SimpleNamespace(get=lambda key, default=None: default)), patch(
        "maestro.multi_agent.get_default_provider", return_value=SimpleNamespace(id="provider-1")
    ), patch("maestro.multi_agent.planner_node", return_value={}):
        with pytest.raises(RuntimeError, match="Planner failed to produce a DAG"):
            multi_agent.run_multi_agent(task="do work", workdir=workdir, auto=False, depth=0)
