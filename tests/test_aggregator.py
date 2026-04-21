"""Tests for aggregator node."""

import asyncio
from pathlib import Path
from unittest.mock import MagicMock, patch

from maestro.multi_agent import aggregator_node, run_multi_agent
from maestro.planner.schemas import AgentPlan, PlanTask


class TestAggregatorNode:
    """Tests for aggregator_node function."""

    def test_aggregator_returns_summary_from_outputs(self):
        """Aggregator calls LLM and returns summary."""
        # Setup state with worker outputs
        plan = AgentPlan(
            tasks=[
                PlanTask(id="t1", domain="backend", prompt="Task 1", deps=[]),
            ]
        )
        state = {
            "task": "test",
            "dag": plan.model_dump(),
            "completed": ["t1"],
            "failed": [],
            "outputs": {"t1": "Created API endpoint"},
            "errors": [],
            "depth": 0,
            "max_depth": 2,
            "workdir": ".",
            "auto": False,
            "ready_tasks": [],
        }

        mock_provider = MagicMock()
        with patch("maestro.multi_agent.resolve_model", return_value=(mock_provider, "gpt-4o")):

            # Mock the async stream
            async def mock_stream(*args, **kwargs):
                from maestro.providers.base import Message

                yield Message(
                    role="assistant",
                    content="Summary: API endpoint created successfully.",
                )

            mock_provider.stream = mock_stream

            result = aggregator_node(state)

        assert "summary" in result
        assert isinstance(result["summary"], str)
        assert len(result["summary"]) > 0

    def test_aggregator_handles_empty_outputs(self):
        """Aggregator handles case with no worker outputs."""
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

        result = aggregator_node(state)

        assert "summary" in result
        # Should indicate no outputs
        assert "No worker outputs" in result["summary"] or result["summary"] != ""

    def test_aggregator_includes_all_worker_outputs_in_prompt(self):
        """Aggregator sends all worker outputs to LLM."""
        plan = AgentPlan(
            tasks=[
                PlanTask(id="t1", domain="backend", prompt="Task 1", deps=[]),
                PlanTask(id="t2", domain="testing", prompt="Task 2", deps=[]),
            ]
        )
        state = {
            "task": "Build feature",
            "dag": plan.model_dump(),
            "completed": ["t1", "t2"],
            "failed": [],
            "outputs": {
                "t1": "Backend code written",
                "t2": "Tests added and passing",
            },
            "errors": [],
            "depth": 0,
            "max_depth": 2,
            "workdir": ".",
            "auto": False,
            "ready_tasks": [],
        }

        captured_messages = []

        mock_provider = MagicMock()
        with patch("maestro.multi_agent.resolve_model", return_value=(mock_provider, "gpt-4o")):

            async def capture_stream(messages, **kwargs):
                captured_messages.extend(messages)
                from maestro.providers.base import Message

                yield Message(role="assistant", content="Summary")

            mock_provider.stream = capture_stream

            aggregator_node(state)

        # Check that both outputs are in the prompt
        prompt_content = str(captured_messages)
        assert "Backend code written" in prompt_content
        assert "Tests added and passing" in prompt_content

    def test_aggregator_handles_failed_tasks_gracefully(self):
        """Aggregator still runs even if some tasks failed."""
        plan = AgentPlan(
            tasks=[
                PlanTask(id="t1", domain="backend", prompt="Task 1", deps=[]),
                PlanTask(id="t2", domain="testing", prompt="Task 2", deps=[]),
            ]
        )
        state = {
            "task": "test",
            "dag": plan.model_dump(),
            "completed": ["t1"],
            "failed": ["t2"],
            "outputs": {"t1": "Backend done"},
            "errors": ["t2: Test failure"],
            "depth": 0,
            "max_depth": 2,
            "workdir": ".",
            "auto": False,
            "ready_tasks": [],
        }

        mock_provider = MagicMock()
        with patch("maestro.multi_agent.resolve_model", return_value=(mock_provider, "gpt-4o")):

            async def mock_stream(*args, **kwargs):
                from maestro.providers.base import Message

                yield Message(role="assistant", content="Partial summary")

            mock_provider.stream = mock_stream

            result = aggregator_node(state)

        assert "summary" in result

    def test_aggregator_handles_provider_runtimeerror_in_async_context(self):
        """Aggregator returns error summary when provider raises RuntimeError in async context."""
        plan = AgentPlan(
            tasks=[
                PlanTask(id="t1", domain="backend", prompt="Task 1", deps=[]),
            ]
        )
        state = {
            "task": "test",
            "dag": plan.model_dump(),
            "completed": ["t1"],
            "failed": [],
            "outputs": {"t1": "Created API endpoint"},
            "errors": [],
            "depth": 0,
            "max_depth": 2,
            "workdir": ".",
            "auto": False,
            "ready_tasks": [],
        }

        async def mock_stream_that_raises(*args, **kwargs):
            raise RuntimeError("provider boom")
            yield  # Make it a generator

        async def run_in_async_context():
            """Run aggregator_node from inside a running event loop."""
            mock_provider = MagicMock()
            mock_provider.stream = mock_stream_that_raises
            with patch("maestro.multi_agent.resolve_model", return_value=(mock_provider, "gpt-4o")):
                return aggregator_node(state)

        # Run from an already running event loop - this should not crash
        result = asyncio.run(run_in_async_context())

        # Should return error summary instead of crashing
        assert "summary" in result
        assert "Failed to generate summary" in result["summary"]
        assert "provider boom" in result["summary"]

    def test_run_multi_agent_executes_full_pipeline_and_emits_lifecycle_events(
        self, tmp_path, capsys
    ):
        """run_multi_agent executes planner, workers, and aggregator end-to-end."""

        planner_calls = []
        worker_calls = []
        aggregator_messages = []

        class StubProvider:
            id = "chatgpt"

            async def stream(self, messages, *, model):
                aggregator_messages.append({"messages": messages, "model": model})
                from maestro.providers.base import Message

                yield Message(role="assistant", content="Final integrated summary")

        def mock_planner_node(state):
            planner_calls.append(state)
            return {
                "dag": {
                    "tasks": [
                        {"id": "t1", "domain": "backend", "prompt": "Build API", "deps": []},
                        {
                            "id": "t2",
                            "domain": "testing",
                            "prompt": "Test API",
                            "deps": ["t1"],
                        },
                    ]
                }
            }

        def mock_run_loop(messages, model, instructions, provider, workdir, auto):
            worker_calls.append(
                {
                    "prompt": messages[0].content,
                    "model": model,
                    "provider": provider,
                    "workdir": workdir,
                    "auto": auto,
                }
            )
            return f"completed {messages[0].content}"

        provider = StubProvider()

        with (
            patch("maestro.planner.node.planner_node", side_effect=mock_planner_node),
            patch("maestro.multi_agent._run_agentic_loop", side_effect=mock_run_loop),
        ):
            result = run_multi_agent(
                task="Ship the feature",
                workdir=tmp_path,
                auto=True,
                depth=0,
                provider=provider,
                model="gpt-4o-mini",
            )

        assert len(planner_calls) == 1
        assert result["outputs"] == {
            "t1": "completed Build API",
            "t2": "completed Test API",
        }
        assert result["summary"] == "Final integrated summary"

        assert [call["prompt"] for call in worker_calls] == ["Build API", "Test API"]
        assert all(call["workdir"] == Path(tmp_path).resolve() for call in worker_calls)
        assert all(call["auto"] is True for call in worker_calls)
        assert all(call["provider"] is provider for call in worker_calls)

        assert len(aggregator_messages) == 1
        aggregator_prompt = aggregator_messages[0]["messages"][1].content
        assert "completed Build API" in aggregator_prompt
        assert "completed Test API" in aggregator_prompt

        captured = capsys.readouterr()
        lines = [line.strip() for line in captured.out.splitlines() if line.strip()]
        assert "[planner] done" in lines
        assert "[worker:t1] started" in lines
        assert "[worker:t1] done" in lines
        assert "[worker:t2] started" in lines
        assert "[worker:t2] done" in lines
        assert "[aggregator] done" in lines
        assert lines.index("[aggregator] done") > lines.index("[worker:t2] done")

    def test_run_multi_agent_can_disable_aggregation_via_config(self, tmp_path):
        """run_multi_agent skips aggregator when config disables it."""

        class ConfigStub:
            def get(self, key, default=None):
                if key == "aggregator.enabled":
                    return False
                return default

        class StubProvider:
            id = "chatgpt"

            def __init__(self):
                self.stream_called = False

            async def stream(self, messages, *, model):
                self.stream_called = True
                from maestro.providers.base import Message

                yield Message(role="assistant", content="unused")

        provider = StubProvider()

        with (
            patch(
                "maestro.planner.node.planner_node",
                return_value={
                    "dag": {
                        "tasks": [
                            {"id": "t1", "domain": "backend", "prompt": "Build API", "deps": []}
                        ]
                    }
                },
            ),
            patch("maestro.multi_agent._run_agentic_loop", return_value="completed Build API"),
            patch("maestro.multi_agent.load_config", return_value=ConfigStub()),
        ):
            result = run_multi_agent(
                task="Ship the feature",
                workdir=tmp_path,
                auto=False,
                depth=0,
                provider=provider,
                model="gpt-4o-mini",
                aggregate=None,
            )

        assert result["outputs"] == {"t1": "completed Build API"}
        assert "summary" not in result
        assert provider.stream_called is False
