"""Tests for aggregator node."""

import asyncio
from unittest.mock import MagicMock, patch
from maestro.multi_agent import aggregator_node
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

        with patch("maestro.multi_agent.get_default_provider") as mock_get:
            mock_provider = MagicMock()
            mock_get.return_value = mock_provider
            mock_provider.list_models.return_value = ["gpt-4o"]

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

        with patch("maestro.multi_agent.get_default_provider") as mock_get:
            mock_provider = MagicMock()
            mock_get.return_value = mock_provider
            mock_provider.list_models.return_value = ["gpt-4o"]

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

        with patch("maestro.multi_agent.get_default_provider") as mock_get:
            mock_provider = MagicMock()
            mock_get.return_value = mock_provider
            mock_provider.list_models.return_value = ["gpt-4o"]

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
            with patch("maestro.multi_agent.get_default_provider") as mock_get:
                mock_provider = MagicMock()
                mock_get.return_value = mock_provider
                mock_provider.list_models.return_value = ["gpt-4o"]
                mock_provider.stream = mock_stream_that_raises

                return aggregator_node(state)

        # Run from an already running event loop - this should not crash
        result = asyncio.run(run_in_async_context())

        # Should return error summary instead of crashing
        assert "summary" in result
        assert "Failed to generate summary" in result["summary"]
        assert "provider boom" in result["summary"]
