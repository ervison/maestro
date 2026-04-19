"""Tests for multi-agent CLI integration."""

import pytest
import sys
from unittest.mock import patch, MagicMock


class TestMultiAgentCLI:
    """Tests for --multi flag in CLI."""

    def test_multi_flag_appears_in_help(self, capsys):
        """--multi flag is documented in help."""
        from maestro.cli import main

        with patch.object(sys, "argv", ["maestro", "run", "--help"]):
            with pytest.raises(SystemExit):
                main()

        captured = capsys.readouterr()
        assert "--multi" in captured.out

    def test_no_aggregate_flag_appears_in_help(self, capsys):
        """--no-aggregate flag is documented in help."""
        from maestro.cli import main

        with patch.object(sys, "argv", ["maestro", "run", "--help"]):
            with pytest.raises(SystemExit):
                main()

        captured = capsys.readouterr()
        assert "--no-aggregate" in captured.out

    def test_run_without_multi_uses_single_agent(self):
        """Running without --multi uses existing single-agent path."""
        from maestro.cli import main

        with (
            patch("maestro.cli.run") as mock_run,
            patch("maestro.models.resolve_model") as mock_resolve,
            patch("maestro.providers.registry.get_provider") as mock_get_provider,
        ):

            mock_provider = MagicMock()
            mock_provider.id = "chatgpt"
            mock_get_provider.return_value = mock_provider
            mock_resolve.return_value = (mock_provider, "gpt-4o")
            mock_run.return_value = "Single agent result"

            with patch.object(sys, "argv", ["maestro", "run", "test prompt"]):
                main()

            mock_run.assert_called_once()

    def test_run_with_multi_uses_multi_agent(self, tmp_path):
        """Running with --multi calls run_multi_agent."""
        from maestro.cli import main

        with (
            patch("maestro.cli.run_multi_agent") as mock_multi,
            patch("maestro.models.resolve_model") as mock_resolve,
            patch("maestro.providers.registry.get_provider") as mock_get_provider,
        ):

            mock_provider = MagicMock()
            mock_provider.id = "chatgpt"
            mock_get_provider.return_value = mock_provider
            mock_resolve.return_value = (mock_provider, "gpt-4o")
            mock_multi.return_value = {
                "outputs": {"t1": "Worker output"},
                "failed": [],
                "errors": [],
                "summary": "All done",
            }

            with patch.object(
                sys,
                "argv",
                [
                    "maestro",
                    "run",
                    "--multi",
                    "test prompt",
                    "--workdir",
                    str(tmp_path),
                ],
            ):
                main()

            mock_multi.assert_called_once()
            call_kwargs = mock_multi.call_args.kwargs
            assert call_kwargs["task"] == "test prompt"
            assert call_kwargs["depth"] == 0

    def test_multi_passes_auto_flag(self, tmp_path):
        """--auto is passed through to run_multi_agent."""
        from maestro.cli import main

        with (
            patch("maestro.cli.run_multi_agent") as mock_multi,
            patch("maestro.models.resolve_model") as mock_resolve,
            patch("maestro.providers.registry.get_provider") as mock_get_provider,
        ):

            mock_provider = MagicMock()
            mock_provider.id = "chatgpt"
            mock_get_provider.return_value = mock_provider
            mock_resolve.return_value = (mock_provider, "gpt-4o")
            mock_multi.return_value = {
                "outputs": {"t1": "Worker output"},
                "failed": [],
                "errors": [],
            }

            with patch.object(
                sys,
                "argv",
                [
                    "maestro",
                    "run",
                    "--multi",
                    "--auto",
                    "test",
                    "--workdir",
                    str(tmp_path),
                ],
            ):
                main()

            call_kwargs = mock_multi.call_args.kwargs
            assert call_kwargs["auto"] is True

    def test_multi_passes_workdir(self, tmp_path):
        """--workdir is passed through to run_multi_agent."""
        from maestro.cli import main

        with (
            patch("maestro.cli.run_multi_agent") as mock_multi,
            patch("maestro.models.resolve_model") as mock_resolve,
            patch("maestro.providers.registry.get_provider") as mock_get_provider,
        ):

            mock_provider = MagicMock()
            mock_provider.id = "chatgpt"
            mock_get_provider.return_value = mock_provider
            mock_resolve.return_value = (mock_provider, "gpt-4o")
            mock_multi.return_value = {
                "outputs": {"t1": "Worker output"},
                "failed": [],
                "errors": [],
            }

            with patch.object(
                sys,
                "argv",
                ["maestro", "run", "--multi", "test", "--workdir", str(tmp_path)],
            ):
                main()

            call_kwargs = mock_multi.call_args.kwargs
            assert call_kwargs["workdir"] == tmp_path

    def test_no_aggregate_flag_disables_aggregator(self, tmp_path):
        """--no-aggregate passes aggregate=False."""
        from maestro.cli import main

        with (
            patch("maestro.cli.run_multi_agent") as mock_multi,
            patch("maestro.models.resolve_model") as mock_resolve,
            patch("maestro.providers.registry.get_provider") as mock_get_provider,
        ):

            mock_provider = MagicMock()
            mock_provider.id = "chatgpt"
            mock_get_provider.return_value = mock_provider
            mock_resolve.return_value = (mock_provider, "gpt-4o")
            mock_multi.return_value = {
                "outputs": {"t1": "Worker output"},
                "failed": [],
                "errors": [],
            }

            with patch.object(
                sys,
                "argv",
                [
                    "maestro",
                    "run",
                    "--multi",
                    "--no-aggregate",
                    "test",
                    "--workdir",
                    str(tmp_path),
                ],
            ):
                main()

            call_kwargs = mock_multi.call_args.kwargs
            assert call_kwargs["aggregate"] is False

    def test_lifecycle_events_printed(self, tmp_path, capsys):
        """Lifecycle events are printed to stdout."""
        from maestro.cli import main

        with (
            patch("maestro.cli.run_multi_agent") as mock_multi,
            patch("maestro.models.resolve_model") as mock_resolve,
            patch("maestro.providers.registry.get_provider") as mock_get_provider,
        ):

            mock_provider = MagicMock()
            mock_provider.id = "chatgpt"
            mock_get_provider.return_value = mock_provider
            mock_resolve.return_value = (mock_provider, "gpt-4o")

            # Simulate lifecycle prints by having run_multi_agent print them
            def side_effect(**kwargs):
                print("[planner] done")
                print("[worker:t1] started")
                print("[worker:t1] done")
                print("[aggregator] done")
                return {
                    "outputs": {"t1": "Worker output"},
                    "failed": [],
                    "errors": [],
                    "summary": "Done",
                }

            mock_multi.side_effect = side_effect

            with patch.object(
                sys,
                "argv",
                ["maestro", "run", "--multi", "test", "--workdir", str(tmp_path)],
            ):
                main()

            captured = capsys.readouterr()
            assert "[planner] done" in captured.out
            assert "[worker:t1]" in captured.out
            assert "[aggregator] done" in captured.out

    def test_zero_regressions_single_agent_path(self):
        """Single-agent path is unchanged from Phase 5."""
        from maestro.cli import main

        # This test verifies the single-agent path still works identically
        with (
            patch("maestro.cli.run") as mock_run,
            patch("maestro.models.resolve_model") as mock_resolve,
            patch("maestro.providers.registry.get_provider") as mock_get_provider,
            patch("maestro.config.load") as mock_config,
        ):

            mock_provider = MagicMock()
            mock_provider.id = "chatgpt"
            mock_get_provider.return_value = mock_provider
            mock_resolve.return_value = (mock_provider, "gpt-4o")
            mock_config.return_value = MagicMock(model=None)
            mock_run.return_value = "Test result"

            with patch.object(sys, "argv", ["maestro", "run", "test prompt"]):
                main()

            # Verify run() was called with correct signature
            mock_run.assert_called_once()
            args, kwargs = mock_run.call_args
            assert args[0] == "gpt-4o"  # model
            assert args[1] == "test prompt"  # prompt

    def test_multi_exits_with_error_if_no_workers_complete(self, tmp_path, capsys):
        """Multi-agent mode exits with error if no workers complete, and prints worker errors."""
        from maestro.cli import main

        with (
            patch("maestro.cli.run_multi_agent") as mock_multi,
            patch("maestro.models.resolve_model") as mock_resolve,
            patch("maestro.providers.registry.get_provider") as mock_get_provider,
        ):

            mock_provider = MagicMock()
            mock_provider.id = "chatgpt"
            mock_get_provider.return_value = mock_provider
            mock_resolve.return_value = (mock_provider, "gpt-4o")
            # Return empty outputs (no workers completed) with errors
            mock_multi.return_value = {
                "outputs": {},
                "failed": ["t1", "t2"],
                "errors": ["t1: failed", "t2: failed"],
            }

            with patch.object(
                sys,
                "argv",
                ["maestro", "run", "--multi", "test", "--workdir", str(tmp_path)],
            ):
                with pytest.raises(SystemExit) as exc_info:
                    main()

                assert exc_info.value.code == 1

            captured = capsys.readouterr()
            # Verify worker errors are printed to stderr even when all fail
            assert "Worker Errors" in captured.err
            assert "t1: failed" in captured.err
            assert "t2: failed" in captured.err
            assert "No workers completed successfully" in captured.err

    def test_multi_shows_worker_outputs(self, tmp_path, capsys):
        """Multi-agent mode prints worker outputs when aggregation skipped."""
        from maestro.cli import main

        with (
            patch("maestro.cli.run_multi_agent") as mock_multi,
            patch("maestro.models.resolve_model") as mock_resolve,
            patch("maestro.providers.registry.get_provider") as mock_get_provider,
        ):

            mock_provider = MagicMock()
            mock_provider.id = "chatgpt"
            mock_get_provider.return_value = mock_provider
            mock_resolve.return_value = (mock_provider, "gpt-4o")
            # Return outputs without summary (aggregation skipped)
            mock_multi.return_value = {
                "outputs": {"t1": "Worker output"},
                "failed": [],
                "errors": [],
            }

            with patch.object(
                sys,
                "argv",
                [
                    "maestro",
                    "run",
                    "--multi",
                    "--no-aggregate",
                    "test",
                    "--workdir",
                    str(tmp_path),
                ],
            ):
                main()

            captured = capsys.readouterr()
            assert "Worker Outputs" in captured.out
            assert "Worker output" in captured.out

    def test_no_aggregate_shows_partial_failures(self, tmp_path, capsys):
        """Partial worker failures are surfaced even when aggregation is skipped."""
        from maestro.cli import main

        with (
            patch("maestro.cli.run_multi_agent") as mock_multi,
            patch("maestro.models.resolve_model") as mock_resolve,
            patch("maestro.providers.registry.get_provider") as mock_get_provider,
        ):

            mock_provider = MagicMock()
            mock_provider.id = "chatgpt"
            mock_get_provider.return_value = mock_provider
            mock_resolve.return_value = (mock_provider, "gpt-4o")
            # Return partial success with failures (structure from run_multi_agent)
            mock_multi.return_value = {
                "outputs": {"t1": "Worker output"},
                "failed": ["t2"],
                "errors": ["t2: Runtime error occurred"],
            }

            with patch.object(
                sys,
                "argv",
                [
                    "maestro",
                    "run",
                    "--multi",
                    "--no-aggregate",
                    "test",
                    "--workdir",
                    str(tmp_path),
                ],
            ):
                with pytest.raises(SystemExit) as exc_info:
                    main()

                assert exc_info.value.code == 1

            captured = capsys.readouterr()
            assert "Worker Outputs" in captured.out
            assert "Worker output" in captured.out
            # Errors go to stderr
            assert "Worker Errors" in captured.err
            assert "t2: Runtime error occurred" in captured.err

    def test_aggregated_mode_shows_partial_failures(self, tmp_path, capsys):
        """Partial worker failures are surfaced in aggregated mode too."""
        from maestro.cli import main

        with (
            patch("maestro.cli.run_multi_agent") as mock_multi,
            patch("maestro.models.resolve_model") as mock_resolve,
            patch("maestro.providers.registry.get_provider") as mock_get_provider,
        ):

            mock_provider = MagicMock()
            mock_provider.id = "chatgpt"
            mock_get_provider.return_value = mock_provider
            mock_resolve.return_value = (mock_provider, "gpt-4o")
            # Return partial success with summary and failures
            mock_multi.return_value = {
                "outputs": {"t1": "Worker output"},
                "failed": ["t2"],
                "errors": ["t2: Runtime error occurred"],
                "summary": "Completed with some issues",
            }

            with patch.object(
                sys,
                "argv",
                [
                    "maestro",
                    "run",
                    "--multi",
                    "test",
                    "--workdir",
                    str(tmp_path),
                ],
            ):
                with pytest.raises(SystemExit) as exc_info:
                    main()

                assert exc_info.value.code == 1

            captured = capsys.readouterr()
            assert "Final Summary" in captured.out
            # Errors go to stderr
            assert "Worker Errors" in captured.err
            assert "t2: Runtime error occurred" in captured.err
