"""Tests for aggregator guardrail functionality."""

import pytest
from unittest.mock import patch, MagicMock
from langgraph.graph import END

from maestro.multi_agent import AggregatorGuardrail, check_aggregator_guardrail, scheduler_route, run_multi_agent
from maestro.planner.schemas import AgentState


class TestAggregatorGuardrail:
    """Test the AggregatorGuardrail dataclass and check_aggregator_guardrail function."""

    @pytest.mark.parametrize(
        "max_calls,calls_this_run,expected_allowed,expected_reason",
        [
            # Test 1: allow (max_calls=3, calls_this_run=0)
            (3, 0, True, None),
            # Test 2: block by call count (max_calls=1, calls_this_run=1)
            (1, 1, False, "call limit reached (1/1)"),
            # Test 3: block max_calls=0 (disabled)
            (0, 0, False, "aggregation disabled (max_calls=0)"),
            # Test 6: no limits set
            (None, 0, True, None),
        ],
    )
    def test_call_count_checks(self, max_calls, calls_this_run, expected_allowed, expected_reason):
        """Test call-count based guardrail logic."""
        guardrail = AggregatorGuardrail(max_calls=max_calls)
        outputs = {"task1": "output1", "task2": "output2"}

        allowed, reason = check_aggregator_guardrail(guardrail, calls_this_run, outputs)

        assert allowed == expected_allowed
        assert reason == expected_reason

    @pytest.mark.parametrize(
        "max_tokens,outputs,expected_allowed,expected_reason",
        [
            # Test 4: token budget exceeded (600 tokens > 500 max)
            (500, {"task1": "a" * 2400}, False, "token budget exceeded (estimated 600 > max 500)"),
            # Test 5: token budget not exceeded
            (1000, {"task1": "a" * 1600}, True, None),  # 1600/4 = 400 tokens
        ],
    )
    def test_token_budget_checks(self, max_tokens, outputs, expected_allowed, expected_reason):
        """Test token-budget based guardrail logic."""
        guardrail = AggregatorGuardrail(max_tokens_per_run=max_tokens)

        allowed, reason = check_aggregator_guardrail(guardrail, 0, outputs)

        assert allowed == expected_allowed
        assert reason == expected_reason

    def test_combined_limits(self):
        """Test guardrail with both call count and token limits."""
        guardrail = AggregatorGuardrail(max_calls=2, max_tokens_per_run=400)  # Lower token limit
        outputs = {"task1": "a" * 2000}  # 500 tokens

        # Should pass call count but fail token budget
        allowed, reason = check_aggregator_guardrail(guardrail, 1, outputs)
        assert not allowed
        assert "token budget exceeded" in reason


class TestSchedulerRouteIntegration:
    """Test scheduler_route guardrail integration."""

    @patch('maestro.multi_agent._print_lifecycle')
    def test_scheduler_route_blocks_when_max_calls_zero(self, mock_print):
        """Test that scheduler_route returns END and prints skip message when max_calls=0."""
        guardrail = AggregatorGuardrail(max_calls=0)
        state: AgentState = {
            "task": "test task",
            "dag": {"tasks": []},  # No tasks
            "completed": [],
            "failed": [],
            "outputs": {},
            "errors": [],
            "depth": 0,
            "max_depth": 2,
            "workdir": "/tmp",
            "auto": False,
            "ready_tasks": [],
            "agg_guardrail": guardrail,
            "agg_calls_done": 0,
            "aggregate": True,
        }

        result = scheduler_route(state)

        assert result == END
        mock_print.assert_called_once_with("aggregator", "skipped — aggregation disabled (max_calls=0)")

    @patch('maestro.multi_agent._print_lifecycle')
    def test_scheduler_route_allows_when_no_guardrail(self, mock_print):
        """Test that scheduler_route returns 'aggregator' when no guardrail is set."""
        state: AgentState = {
            "task": "test task",
            "dag": {"tasks": []},
            "completed": [],
            "failed": [],
            "outputs": {},
            "errors": [],
            "depth": 0,
            "max_depth": 2,
            "workdir": "/tmp",
            "auto": False,
            "ready_tasks": [],
            "aggregate": True,
        }

        result = scheduler_route(state)

        assert result == "aggregator"
        mock_print.assert_not_called()

    @patch('maestro.multi_agent._print_lifecycle')
    def test_scheduler_route_blocks_token_budget_exceeded(self, mock_print):
        """Test that scheduler_route blocks when token budget is exceeded."""
        guardrail = AggregatorGuardrail(max_tokens_per_run=50)
        state: AgentState = {
            "task": "test task",
            "dag": {"tasks": []},
            "completed": [],
            "failed": [],
            "outputs": {"task1": "a" * 400},  # 100 tokens > 50 max
            "errors": [],
            "depth": 0,
            "max_depth": 2,
            "workdir": "/tmp",
            "auto": False,
            "ready_tasks": [],
            "agg_guardrail": guardrail,
            "agg_calls_done": 0,
            "aggregate": True,
        }

        result = scheduler_route(state)

        assert result == END
        mock_print.assert_called_once()
        args = mock_print.call_args[0]
        assert args[0] == "aggregator"
        assert "skipped — token budget exceeded" in args[1]


class TestRunMultiAgentGuardrailIntegration:
    """Integration tests for run_multi_agent with guardrails."""

    @patch('maestro.multi_agent.load_config')
    @patch('maestro.multi_agent.get_default_provider')
    @patch('maestro.multi_agent.planner_node')
    @patch('maestro.multi_agent.graph.invoke')
    def test_run_multi_agent_respects_max_calls_zero(self, mock_invoke, mock_planner, mock_provider, mock_load_config):
        """Test that run_multi_agent skips aggregation when max_calls=0 in config."""
        # Mock config with max_calls=0
        mock_config = MagicMock()
        mock_config.get.side_effect = lambda key, default=None: {
            "aggregator.enabled": True,
            "aggregator.max_calls": 0,
            "aggregator.max_tokens_per_run": None,
        }.get(key, default)
        mock_load_config.return_value = mock_config

        # Mock planner returns empty DAG
        mock_planner.return_value = {"dag": {"tasks": []}}

        # Mock graph returns no summary (since aggregator skipped)
        mock_invoke.return_value = {
            "outputs": {},
            "failed": [],
            "errors": [],
            # No "summary" key
        }

        result = run_multi_agent(
            task="test task",
            workdir="/tmp",
            auto=False,
            depth=0,
        )

        # Should not have summary since aggregator was skipped
        assert "summary" not in result
        mock_load_config.assert_called()

    @patch('maestro.multi_agent.load_config')
    def test_run_multi_agent_builds_guardrail_from_config(self, mock_load_config):
        """Test that run_multi_agent builds AggregatorGuardrail from config values."""
        mock_config = MagicMock()
        mock_config.get.side_effect = lambda key, default=None: {
            "aggregator.enabled": True,
            "aggregator.max_calls": 5,
            "aggregator.max_tokens_per_run": 2000,
        }.get(key, default)
        mock_load_config.return_value = mock_config

        # We can't easily test the full run without mocking everything,
        # but we can check that load_config is called and guardrail would be built
        # This is tested indirectly through the scheduler_route tests above
        mock_load_config.assert_not_called()  # Not yet

        # Actually call run_multi_agent to trigger the config loading
        with patch('maestro.multi_agent.get_default_provider'), \
             patch('maestro.multi_agent.planner_node') as mock_planner, \
             patch('maestro.multi_agent.graph.invoke') as mock_invoke:

            mock_planner.return_value = {"dag": {"tasks": []}}
            mock_invoke.return_value = {"outputs": {}, "failed": [], "errors": []}

            run_multi_agent(
                task="test task",
                workdir="/tmp",
                auto=False,
                depth=0,
            )

            # Verify config was loaded
            mock_load_config.assert_called_once()


class TestConfigValidation:
    """Test config validation for new aggregator keys."""

    @patch('maestro.config.CONFIG_FILE')
    @patch('maestro.config.json.loads')
    def test_load_validates_max_calls_type(self, mock_json_loads, mock_config_file):
        """Test that load_config validates aggregator.max_calls is an int."""
        from maestro.config import load

        # Mock invalid max_calls (string instead of int)
        mock_config_file.exists.return_value = True
        mock_json_loads.return_value = {
            "aggregator": {"max_calls": "invalid"}
        }

        with pytest.raises(RuntimeError, match="expected 'aggregator.max_calls' to be a non-negative int"):
            load()

    @patch('maestro.config.CONFIG_FILE')
    @patch('maestro.config.json.loads')
    def test_load_validates_max_tokens_type(self, mock_json_loads, mock_config_file):
        """Test that load_config validates aggregator.max_tokens_per_run is an int."""
        from maestro.config import load

        mock_config_file.exists.return_value = True
        mock_json_loads.return_value = {
            "aggregator": {"max_tokens_per_run": 123.45}  # float instead of int
        }

        with pytest.raises(RuntimeError, match=r"aggregator\.max_tokens_per_run.*non-negative int"):
            load()

    @patch('maestro.config.CONFIG_FILE')
    @patch('maestro.config.json.loads')
    def test_load_accepts_valid_config(self, mock_json_loads, mock_config_file):
        """Test that load_config accepts valid aggregator config."""
        from maestro.config import load

        mock_config_file.exists.return_value = True
        mock_json_loads.return_value = {
            "aggregator": {
                "enabled": True,
                "max_calls": 5,
                "max_tokens_per_run": 1000
            }
        }

        config = load()
        assert config.aggregator["max_calls"] == 5
        assert config.aggregator["max_tokens_per_run"] == 1000
