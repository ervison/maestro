"""Integration tests verifying run_multi_agent emits correct SSE events."""

import logging

from unittest.mock import MagicMock, patch

from maestro.dashboard.emitter import DashboardEmitter


def _make_planner_result(tasks):
    """Build a minimal planner DAG result."""
    from maestro.planner.schemas import AgentPlan, PlanTask

    plan = AgentPlan(
        tasks=[
            PlanTask(
                id=t["id"],
                domain=t["domain"],
                prompt=t["prompt"],
                deps=t.get("deps", []),
            )
            for t in tasks
        ]
    )
    return {"dag": plan.model_dump(), "ready_tasks": []}


def test_dag_ready_event_emitted():
    """dag_ready event is emitted after planner succeeds."""
    emitter = DashboardEmitter()
    received = []
    emitter.subscribe(lambda e: received.append(e))

    with (
        patch("maestro.multi_agent.planner_node") as mock_planner,
        patch("maestro.multi_agent.get_default_provider") as mock_provider,
        patch("maestro.agent._run_agentic_loop", return_value="result"),
    ):
        mock_planner.return_value = _make_planner_result(
            [{"id": "t1", "domain": "general", "prompt": "do something", "deps": []}]
        )
        mock_provider.return_value = MagicMock()

        from maestro.multi_agent import run_multi_agent

        run_multi_agent(
            task="test task",
            workdir=".",
            auto=True,
            depth=0,
            max_depth=2,
            aggregate=False,
            emitter=emitter,
        )

    dag_events = [e for e in received if e["type"] == "dag_ready"]
    assert len(dag_events) == 1
    assert len(dag_events[0]["tasks"]) == 1


def test_node_update_active_emitted_for_workers():
    """node_update with status=active is emitted when a worker starts."""
    emitter = DashboardEmitter()
    received = []
    emitter.subscribe(lambda e: received.append(e))

    with (
        patch("maestro.multi_agent.planner_node") as mock_planner,
        patch("maestro.multi_agent.get_default_provider") as mock_provider,
        patch("maestro.agent._run_agentic_loop", return_value="result"),
    ):
        mock_planner.return_value = _make_planner_result(
            [{"id": "t1", "domain": "general", "prompt": "do something", "deps": []}]
        )
        mock_provider.return_value = MagicMock()

        from maestro.multi_agent import run_multi_agent

        run_multi_agent(
            task="test task",
            workdir=".",
            auto=True,
            depth=0,
            max_depth=2,
            aggregate=False,
            emitter=emitter,
        )

    active_events = [
        e
        for e in received
        if e["type"] == "node_update"
        and e.get("status") == "active"
        and e.get("id") == "t1"
    ]
    assert len(active_events) >= 1


def test_node_update_done_emitted_for_workers():
    """node_update with status=done is emitted when a worker completes."""
    emitter = DashboardEmitter()
    received = []
    emitter.subscribe(lambda e: received.append(e))

    with (
        patch("maestro.multi_agent.planner_node") as mock_planner,
        patch("maestro.multi_agent.get_default_provider") as mock_provider,
        patch("maestro.agent._run_agentic_loop", return_value="result"),
    ):
        mock_planner.return_value = _make_planner_result(
            [{"id": "t1", "domain": "general", "prompt": "do something", "deps": []}]
        )
        mock_provider.return_value = MagicMock()

        from maestro.multi_agent import run_multi_agent

        run_multi_agent(
            task="test task",
            workdir=".",
            auto=True,
            depth=0,
            max_depth=2,
            aggregate=False,
            emitter=emitter,
        )

    done_events = [
        e
        for e in received
        if e["type"] == "node_update"
        and e.get("status") == "done"
        and e.get("id") == "t1"
    ]
    assert len(done_events) >= 1


def test_no_emitter_does_not_crash():
    """run_multi_agent with emitter=None runs without errors."""
    with (
        patch("maestro.multi_agent.planner_node") as mock_planner,
        patch("maestro.multi_agent.get_default_provider") as mock_provider,
        patch("maestro.agent._run_agentic_loop", return_value="result"),
    ):
        mock_planner.return_value = _make_planner_result(
            [{"id": "t1", "domain": "general", "prompt": "do something", "deps": []}]
        )
        mock_provider.return_value = MagicMock()

        from maestro.multi_agent import run_multi_agent

        result = run_multi_agent(
            task="test task",
            workdir=".",
            auto=True,
            depth=0,
            max_depth=2,
            aggregate=False,
            emitter=None,
        )

    assert "outputs" in result


def test_emitter_replays_history_to_new_subscriber_and_logs_replay_errors(caplog):
    emitter = DashboardEmitter()
    replayed = []
    emitter.emit({"type": "dag_ready", "tasks": []})

    caplog.set_level(logging.WARNING, logger="maestro.dashboard.emitter")

    def bad_handler(event):
        raise RuntimeError(f"replay failed for {event['type']}")

    emitter.subscribe(bad_handler)
    emitter.subscribe(lambda event: replayed.append(event))

    assert replayed == [{"type": "dag_ready", "tasks": []}]
    assert "DashboardEmitter: replay subscriber raised: replay failed for dag_ready" in caplog.text


def test_emitter_unsubscribe_missing_handler_is_ignored() -> None:
    emitter = DashboardEmitter()

    emitter.unsubscribe(lambda event: None)


def test_emitter_suppresses_subscriber_errors_during_emit(caplog) -> None:
    emitter = DashboardEmitter()
    received = []

    caplog.set_level(logging.WARNING, logger="maestro.dashboard.emitter")

    def bad_handler(event):
        raise RuntimeError(f"subscriber crashed for {event['type']}")

    emitter.subscribe(bad_handler)
    emitter.subscribe(lambda event: received.append(event))

    emitter.emit({"type": "node_update", "id": "t1", "status": "done"})

    assert received == [{"type": "node_update", "id": "t1", "status": "done"}]
    assert "DashboardEmitter: subscriber raised: subscriber crashed for node_update" in caplog.text
