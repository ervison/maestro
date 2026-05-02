"""CLI tests for gate failure exit code behavior."""
from __future__ import annotations

import io
import runpy
import sys
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from maestro.sdlc.schemas import (
    ArtifactType,
    ARTIFACT_FILENAMES,
    DiscoveryResult,
    GateResult,
    SDLCArtifact,
    SDLCRequest,
)


def _make_result_with_gate_failures(tmp_path) -> DiscoveryResult:
    """Build a DiscoveryResult that has gate failures."""
    arts = [
        SDLCArtifact(t, ARTIFACT_FILENAMES[t], "# content")
        for t in ArtifactType
    ]
    gate_fail = GateResult(sprint_id=1, passed=False, notes="stub fail", issues=["issue"])
    return DiscoveryResult(
        request=SDLCRequest(prompt="x"),
        artifacts=arts,
        spec_dir=str(tmp_path / "spec"),
        gate_failures=[gate_fail],
    )


def test_cli_exits_2_when_gate_failures_present(tmp_path, capsys) -> None:
    """When DiscoveryResult.gate_failures is non-empty, CLI must sys.exit(2)."""
    from maestro.sdlc.harness import DiscoveryHarness

    failing_result = _make_result_with_gate_failures(tmp_path)

    with patch.object(DiscoveryHarness, "run", return_value=failing_result):
        with pytest.raises(SystemExit) as exc_info:
            import maestro.cli as cli_module
            with patch.object(sys, "argv", ["maestro", "discover", "--sprints", "--no-reflect", "--no-browser", str(tmp_path), "test prompt"]):
                cli_module.main()

    assert exc_info.value.code == 2, f"expected exit 2, got {exc_info.value.code}"


def test_auth_login_chatgpt_uses_positional_method_argument(capsys) -> None:
    import maestro.cli as cli_module

    args = SimpleNamespace(provider="chatgpt", device=True)
    provider = MagicMock()

    with (
        patch.object(cli_module, "get_provider", return_value=provider),
        patch.object(cli_module.auth, "login") as mock_login,
        patch.object(
            cli_module.auth,
            "get",
            return_value={"email": "user@example.com", "account_id": ""},
        ),
    ):
        cli_module._auth_login(args)

    assert mock_login.call_args == (("device",), {})
    provider.login.assert_not_called()


def test_legacy_login_uses_positional_method_argument(capsys) -> None:
    import maestro.cli as cli_module

    args = SimpleNamespace(device=True)
    token_set = SimpleNamespace(email="user@example.com", account_id="")

    with (
        patch.object(cli_module.auth, "login", return_value=token_set) as mock_login,
        patch.object(cli_module.warnings, "warn"),
    ):
        cli_module._handle_legacy_login(args)

    assert mock_login.call_args == (("device",), {})


def test_main_prints_help_when_no_command_is_given() -> None:
    import maestro.cli as cli_module

    with (
        patch.object(sys, "argv", ["maestro"]),
        patch("sys.stdout", new_callable=io.StringIO) as stdout,
    ):
        cli_module.main()

    assert "LangGraph agent" in stdout.getvalue()


def test_main_parses_auth_login_arguments_and_routes_to_handler() -> None:
    import maestro.cli as cli_module

    with (
        patch.object(sys, "argv", ["maestro", "auth", "login", "github-copilot", "--device"]),
        patch.object(cli_module, "_handle_auth") as mock_handle_auth,
    ):
        cli_module.main()

    args, _ = mock_handle_auth.call_args.args
    assert args.command == "auth"
    assert args.auth_command == "login"
    assert args.provider == "github-copilot"
    assert args.device is True


def test_main_parses_run_arguments_and_routes_to_handler() -> None:
    import maestro.cli as cli_module

    with (
        patch.object(
            sys,
            "argv",
            [
                "maestro",
                "run",
                "fix tests",
                "--multi",
                "--no-aggregate",
                "--auto",
                "--workdir",
                ".",
                "--model",
                "chatgpt/gpt-5",
            ],
        ),
        patch.object(cli_module, "_handle_run") as mock_handle_run,
    ):
        cli_module.main()

    args = mock_handle_run.call_args.args[0]
    assert args.prompt == "fix tests"
    assert args.multi is True
    assert args.no_aggregate is True
    assert args.auto is True
    assert args.model == "chatgpt/gpt-5"


def test_handle_auth_prints_help_for_missing_subcommand() -> None:
    import maestro.cli as cli_module

    auth_parser = MagicMock()

    cli_module._handle_auth(SimpleNamespace(auth_command=None), auth_parser)

    auth_parser.print_help.assert_called_once()


def test_auth_login_exits_for_unknown_provider(capsys) -> None:
    import maestro.cli as cli_module

    args = SimpleNamespace(provider="missing", device=False)

    with patch.object(cli_module, "get_provider", side_effect=ValueError("Unknown provider")):
        with pytest.raises(SystemExit) as exc_info:
            cli_module._auth_login(args)

    assert exc_info.value.code == 1
    assert "Unknown provider" in capsys.readouterr().out


def test_auth_login_uses_provider_login_for_non_chatgpt() -> None:
    import maestro.cli as cli_module

    provider = MagicMock()
    args = SimpleNamespace(provider="github-copilot", device=False)

    with (
        patch.object(cli_module, "get_provider", return_value=provider),
        patch.object(cli_module.auth, "login") as mock_login,
    ):
        cli_module._auth_login(args)

    provider.login.assert_called_once_with()
    mock_login.assert_not_called()


def test_auth_logout_exits_for_unknown_provider(capsys) -> None:
    import maestro.cli as cli_module

    args = SimpleNamespace(provider="missing")

    with (
        patch("maestro.providers.registry.list_providers", return_value=["chatgpt"]),
        patch.object(cli_module.auth, "all_providers", return_value=[]),
    ):
        with pytest.raises(SystemExit) as exc_info:
            cli_module._auth_logout(args)

    assert exc_info.value.code == 1
    assert "Unknown provider: 'missing'" in capsys.readouterr().out


def test_auth_logout_prints_logged_out_when_credentials_exist(capsys) -> None:
    import maestro.cli as cli_module

    args = SimpleNamespace(provider="chatgpt")

    with (
        patch("maestro.providers.registry.list_providers", return_value=["chatgpt"]),
        patch.object(cli_module.auth, "all_providers", return_value=["chatgpt"]),
        patch.object(cli_module.auth, "remove", return_value=True),
    ):
        cli_module._auth_logout(args)

    assert "Logged out of chatgpt." in capsys.readouterr().out


def test_auth_logout_exits_when_provider_is_not_logged_in(capsys) -> None:
    import maestro.cli as cli_module

    args = SimpleNamespace(provider="chatgpt")

    with (
        patch("maestro.providers.registry.list_providers", return_value=["chatgpt"]),
        patch.object(cli_module.auth, "all_providers", return_value=[]),
        patch.object(cli_module.auth, "remove", return_value=False),
    ):
        with pytest.raises(SystemExit) as exc_info:
            cli_module._auth_logout(args)

    assert exc_info.value.code == 1
    assert "Not logged in to chatgpt." in capsys.readouterr().out


def test_auth_status_exits_zero_when_no_providers_are_installed(capsys) -> None:
    import maestro.cli as cli_module

    with (
        patch("maestro.providers.registry.list_providers", return_value=[]),
        patch.object(cli_module.auth, "all_providers", return_value=[]),
    ):
        with pytest.raises(SystemExit) as exc_info:
            cli_module._auth_status()

    assert exc_info.value.code == 0
    assert "No providers installed." in capsys.readouterr().out


def test_auth_status_reports_authenticated_and_stored_provider_states(capsys) -> None:
    import maestro.cli as cli_module

    provider = MagicMock()
    provider.is_authenticated.return_value = True

    with (
        patch("maestro.providers.registry.list_providers", return_value=["chatgpt"]),
        patch.object(cli_module.auth, "all_providers", return_value=["orphaned-provider"]),
        patch.object(cli_module, "get_provider", return_value=provider),
    ):
        cli_module._auth_status()

    output = capsys.readouterr().out
    assert "chatgpt: authenticated" in output
    assert "orphaned-provider: credentials stored" in output


def test_handle_models_exits_when_check_and_provider_are_combined(capsys) -> None:
    import maestro.cli as cli_module

    args = SimpleNamespace(refresh=False, provider="chatgpt", check=True)

    with pytest.raises(SystemExit) as exc_info:
        cli_module._handle_models(args)

    assert exc_info.value.code == 1
    assert "cannot be combined" in capsys.readouterr().out


def test_models_filter_provider_returns_selected_provider_models() -> None:
    import maestro.cli as cli_module

    args = SimpleNamespace(provider="chatgpt")

    filtered = cli_module._models_filter_provider(
        args, {"chatgpt": ["gpt-5"], "github-copilot": ["gpt-4o"]}
    )

    assert filtered == {"chatgpt": ["gpt-5"]}


def test_models_filter_provider_exits_for_unknown_provider(capsys) -> None:
    import maestro.cli as cli_module

    args = SimpleNamespace(provider="missing")

    with patch("maestro.providers.registry.list_providers", return_value=["chatgpt"]):
        with pytest.raises(SystemExit) as exc_info:
            cli_module._models_filter_provider(args, {"chatgpt": ["gpt-5"]})

    assert exc_info.value.code == 1
    assert "Unknown provider: 'missing'" in capsys.readouterr().out


def test_handle_status_exits_when_not_logged_in(capsys) -> None:
    import maestro.cli as cli_module

    with patch.object(cli_module.auth, "load", return_value=None):
        with pytest.raises(SystemExit) as exc_info:
            cli_module._handle_status()

    assert exc_info.value.code == 1
    assert "Not logged in." in capsys.readouterr().out


def test_handle_status_prints_remaining_token_time(capsys) -> None:
    import maestro.cli as cli_module

    token_set = SimpleNamespace(email="user@example.com", account_id="acct-1", expires=150.0)

    with (
        patch.object(cli_module.auth, "load", return_value=token_set),
        patch.object(cli_module.time, "time", return_value=100.0),
    ):
        cli_module._handle_status()

    output = capsys.readouterr().out
    assert "Email:      user@example.com" in output
    assert "Token:      valid (50s remaining)" in output


def test_handle_run_falls_back_to_default_chatgpt_provider_when_model_not_explicit(tmp_path: Path) -> None:
    import maestro.cli as cli_module

    resolved_provider = SimpleNamespace(id="github-copilot")
    default_provider = SimpleNamespace(id="chatgpt")
    args = SimpleNamespace(
        prompt="fix bug",
        model=None,
        system=None,
        auto=False,
        workdir=str(tmp_path),
        multi=False,
        no_aggregate=False,
    )

    with (
        patch("maestro.models.resolve_model", return_value=(resolved_provider, "copilot-model")),
        patch("maestro.config.load", return_value=SimpleNamespace(model=None)),
        patch.object(cli_module, "get_provider", return_value=default_provider),
        patch.object(cli_module, "_handle_run_single") as mock_run_single,
    ):
        cli_module._handle_run(args)

    assert mock_run_single.call_args.args[2] is default_provider
    assert mock_run_single.call_args.args[3] == cli_module.DEFAULT_MODEL


def test_handle_run_exits_with_supported_model_hint_when_model_is_unavailable(capsys) -> None:
    import maestro.cli as cli_module

    provider = SimpleNamespace(id="chatgpt")
    args = SimpleNamespace(
        prompt="fix bug",
        model="chatgpt/gpt-5",
        system=None,
        auto=False,
        workdir=None,
        multi=False,
        no_aggregate=False,
    )

    with (
        patch("maestro.models.resolve_model", return_value=(provider, "gpt-5")),
        patch.object(
            cli_module,
            "_handle_run_single",
            side_effect=RuntimeError("model 'gpt-5' not supported"),
        ),
    ):
        with pytest.raises(SystemExit) as exc_info:
            cli_module._handle_run(args)

    assert exc_info.value.code == 1
    output = capsys.readouterr().out
    assert "model 'gpt-5' is not available" in output
    assert "maestro models --check" in output


def test_handle_run_exits_with_generic_error_message(capsys) -> None:
    import maestro.cli as cli_module

    args = SimpleNamespace(
        prompt="fix bug",
        model=None,
        system=None,
        auto=False,
        workdir=None,
        multi=False,
        no_aggregate=False,
    )

    with patch("maestro.models.resolve_model", side_effect=ValueError("bad config")):
        with pytest.raises(SystemExit) as exc_info:
            cli_module._handle_run(args)

    assert exc_info.value.code == 1
    assert "Error: bad config" in capsys.readouterr().out


def test_legacy_logout_prints_not_logged_in_message(capsys) -> None:
    import maestro.cli as cli_module

    with (
        patch.object(cli_module.auth, "remove", return_value=False),
        patch.object(cli_module.warnings, "warn"),
    ):
        cli_module._handle_legacy_logout()

    assert "Not logged in to chatgpt." in capsys.readouterr().out


def test_spinner_start_stop_and_spin_paths(monkeypatch: pytest.MonkeyPatch, capsys) -> None:
    import maestro.cli as cli_module

    spinner = cli_module._Spinner("Working")
    monkeypatch.setattr(cli_module.sys.stdout, "isatty", lambda: False)
    spinner.start()
    spinner.stop()

    class FakeThread:
        def __init__(self, target=None, daemon=None):
            self.target = target
            self.join_called = False

        def start(self):
            self.target()

        def join(self, timeout=None):
            self.join_called = True

    class FakeEvent:
        def __init__(self):
            self.calls = 0

        def clear(self):
            return None

        def set(self):
            self.calls = 99

        def is_set(self):
            self.calls += 1
            return self.calls > 1

        def wait(self, interval):
            return interval

    monkeypatch.setattr(cli_module.sys.stdout, "isatty", lambda: True)
    monkeypatch.setattr(cli_module.threading, "Thread", FakeThread)
    spinner = cli_module._Spinner("Working")
    spinner._stop_event = FakeEvent()
    spinner.start()
    spinner.stop()

    assert "Working" in capsys.readouterr().out


def test_main_routes_remaining_commands_and_module_main_guard(tmp_path) -> None:
    import maestro.cli as cli_module

    with (
        patch.object(sys, "argv", ["maestro", "models", "--refresh", "--provider", "chatgpt"]),
        patch.object(cli_module, "_handle_models") as mock_models,
    ):
        cli_module.main()
    assert mock_models.call_args.args[0].provider == "chatgpt"

    with (
        patch.object(sys, "argv", ["maestro", "status"]),
        patch.object(cli_module, "_handle_status") as mock_status,
    ):
        cli_module.main()
    mock_status.assert_called_once()

    with (
        patch.object(sys, "argv", ["maestro", "logout"]),
        patch.object(cli_module, "_handle_legacy_logout") as mock_logout,
    ):
        cli_module.main()
    mock_logout.assert_called_once()

    with (
        patch.object(sys, "argv", ["maestro", "planning", "check", "--root", str(tmp_path)]),
        patch.object(cli_module, "_handle_planning") as mock_planning,
    ):
        cli_module.main()
    assert mock_planning.call_args.args[0].planning_command == "check"

    with (
        patch.object(sys, "argv", ["maestro", "discover", "ship it", "--no-browser"]),
        patch.object(cli_module, "_handle_discover") as mock_discover,
    ):
        cli_module.main()
    assert mock_discover.call_args.args[0].prompt == "ship it"

    with patch.object(sys, "argv", ["maestro"]):
        runpy.run_module("maestro.cli", run_name="__main__")


def test_handle_auth_dispatches_all_supported_subcommands() -> None:
    import maestro.cli as cli_module

    auth_parser = MagicMock()
    login_mock = MagicMock()
    logout_mock = MagicMock()
    status_mock = MagicMock()
    with patch.multiple(
        cli_module,
        _auth_login=login_mock,
        _auth_logout=logout_mock,
        _auth_status=status_mock,
    ):
        cli_module._handle_auth(SimpleNamespace(auth_command="login"), auth_parser)
        cli_module._handle_auth(SimpleNamespace(auth_command="logout"), auth_parser)
        cli_module._handle_auth(SimpleNamespace(auth_command="status"), auth_parser)

    login_mock.assert_called_once()
    logout_mock.assert_called_once()
    status_mock.assert_called_once()


def test_auth_login_chatgpt_prints_generic_message_when_login_returns_none(capsys) -> None:
    import maestro.cli as cli_module

    args = SimpleNamespace(provider="chatgpt", device=False)
    with (
        patch.object(cli_module, "get_provider", return_value=MagicMock()),
        patch.object(cli_module.auth, "login", return_value=None),
    ):
        cli_module._auth_login(args)

    assert "Logged in to chatgpt." in capsys.readouterr().out


def test_auth_status_reports_not_authenticated_and_provider_load_errors(capsys) -> None:
    import maestro.cli as cli_module

    provider = MagicMock()
    provider.is_authenticated.return_value = False

    def fake_get_provider(pid):
        if pid == "chatgpt":
            return provider
        raise RuntimeError("boom")

    with (
        patch("maestro.providers.registry.list_providers", return_value=["chatgpt", "broken"]),
        patch.object(cli_module.auth, "all_providers", return_value=[]),
        patch.object(cli_module, "get_provider", side_effect=fake_get_provider),
    ):
        cli_module._auth_status()

    output = capsys.readouterr().out
    assert "chatgpt: not authenticated" in output
    assert "broken: error loading provider" in output


def test_legacy_logout_prints_logged_out_message(capsys) -> None:
    import maestro.cli as cli_module

    with (
        patch.object(cli_module.auth, "remove", return_value=True),
        patch.object(cli_module.warnings, "warn"),
    ):
        cli_module._handle_legacy_logout()

    assert "Logged out of chatgpt." in capsys.readouterr().out


def test_models_probe_mode_lists_availability_and_requires_login(capsys) -> None:
    import maestro.cli as cli_module

    args = SimpleNamespace(provider=None)
    token_set = SimpleNamespace(token="x")

    with (
        patch.object(cli_module.auth, "load", return_value=token_set),
        patch.object(cli_module.auth, "ensure_valid", return_value=token_set),
        patch("maestro.providers.chatgpt.probe_available_models", return_value=["gpt-5"]),
        patch("maestro.providers.chatgpt.fetch_models", return_value=["gpt-5", "gpt-4o"]),
    ):
        cli_module._models_probe_mode(args)

    output = capsys.readouterr().out
    assert "chatgpt/gpt-5  [available]" in output
    assert "chatgpt/gpt-4o  [not available]" in output

    with patch.object(cli_module.auth, "load", return_value=None):
        with pytest.raises(SystemExit) as exc_info:
            cli_module._models_probe_mode(args)
    assert exc_info.value.code == 1


def test_models_filter_provider_exits_for_provider_without_models(capsys) -> None:
    import maestro.cli as cli_module

    args = SimpleNamespace(provider="chatgpt")
    with patch("maestro.providers.registry.list_providers", return_value=["chatgpt"]):
        with pytest.raises(SystemExit) as exc_info:
            cli_module._models_filter_provider(args, {"chatgpt": []})

    assert exc_info.value.code == 1
    assert "has no available models" in capsys.readouterr().out


def test_handle_models_refresh_probe_empty_and_formatted_paths(capsys) -> None:
    import maestro.cli as cli_module

    with (
        patch("maestro.providers.chatgpt.fetch_models") as mock_fetch,
        patch.object(cli_module, "_models_probe_mode") as mock_probe,
    ):
        cli_module._handle_models(SimpleNamespace(refresh=True, provider=None, check=True))
    mock_fetch.assert_called_once_with(force=True)
    mock_probe.assert_called_once()

    with (
        patch("maestro.models.get_available_models", return_value={"chatgpt": []}),
        patch("maestro.models.format_model_list", return_value="unused"),
    ):
        with pytest.raises(SystemExit) as exc_info:
            cli_module._handle_models(SimpleNamespace(refresh=False, provider=None, check=False))
    assert exc_info.value.code == 0

    with (
        patch("maestro.models.get_available_models", return_value={"chatgpt": ["gpt-5"]}),
        patch("maestro.models.format_model_list", return_value="formatted-models"),
    ):
        cli_module._handle_models(SimpleNamespace(refresh=False, provider=None, check=False))
    assert "formatted-models" in capsys.readouterr().out

    with (
        patch("maestro.models.get_available_models", return_value={"chatgpt": ["gpt-5"]}),
        patch.object(cli_module, "_models_filter_provider", return_value={"chatgpt": ["gpt-5"]}) as mock_filter,
        patch("maestro.models.format_model_list", return_value="provider-formatted"),
    ):
        cli_module._handle_models(SimpleNamespace(refresh=False, provider="chatgpt", check=False))
    mock_filter.assert_called_once()


def test_handle_status_prints_expired_token_message(capsys) -> None:
    import maestro.cli as cli_module

    token_set = SimpleNamespace(email="", account_id="acct-1", expires=50.0)
    with (
        patch.object(cli_module.auth, "load", return_value=token_set),
        patch.object(cli_module.time, "time", return_value=100.0),
    ):
        cli_module._handle_status()

    output = capsys.readouterr().out
    assert "Email:      (unknown)" in output
    assert "expired" in output


def test_handle_run_routes_explicit_and_environment_model_selection(tmp_path, monkeypatch) -> None:
    import maestro.cli as cli_module

    provider = SimpleNamespace(id="github-copilot")
    args = SimpleNamespace(
        prompt="fix bug",
        model="github-copilot/model",
        system="sys",
        auto=True,
        workdir=str(tmp_path),
        multi=False,
        no_aggregate=False,
    )
    with (
        patch("maestro.models.resolve_model", return_value=(provider, "model")),
        patch.object(cli_module, "_handle_run_single") as mock_single,
    ):
        cli_module._handle_run(args)
    assert mock_single.call_args.args[2] is provider
    assert mock_single.call_args.args[3] == "model"

    monkeypatch.setenv("MAESTRO_MODEL", "github-copilot/model")
    args = SimpleNamespace(
        prompt="fix bug",
        model=None,
        system=None,
        auto=False,
        workdir=None,
        multi=True,
        no_aggregate=True,
    )
    with (
        patch("maestro.models.resolve_model", return_value=(provider, "model")),
        patch.object(cli_module, "_handle_run_multi") as mock_multi,
    ):
        cli_module._handle_run(args)
    assert mock_multi.call_args.args[2] is provider


def test_handle_run_multi_covers_summary_output_worker_output_and_failures(capsys) -> None:
    import maestro.cli as cli_module

    args = SimpleNamespace(prompt="task", auto=False, no_aggregate=False)
    provider = SimpleNamespace(id="chatgpt")
    fake_server = MagicMock()

    with (
        patch("maestro.dashboard.server.start_dashboard_server", return_value=fake_server),
        patch("maestro.dashboard.emitter.DashboardEmitter", return_value=MagicMock()),
        patch.object(cli_module, "run_multi_agent", return_value={"outputs": {"a": "done"}, "summary": "summary text", "failed": [], "errors": ["boom"]}),
        patch("time.sleep"),
    ):
        cli_module._handle_run_multi(args, ".", provider, "gpt-5")
    output = capsys.readouterr()
    assert "Final Summary" in output.out
    assert "boom" in output.err
    fake_server.shutdown.assert_called()
    fake_server.server_close.assert_called()

    with (
        patch("maestro.dashboard.server.start_dashboard_server", return_value=None),
        patch("maestro.dashboard.emitter.DashboardEmitter", return_value=MagicMock()),
        patch.object(cli_module, "run_multi_agent", return_value={"outputs": {"a": "done"}, "failed": ["a"], "errors": []}),
        patch("time.sleep"),
    ):
        with pytest.raises(SystemExit) as exc_info:
            cli_module._handle_run_multi(args, ".", provider, "gpt-5")
    assert exc_info.value.code == 1

    with (
        patch("maestro.dashboard.server.start_dashboard_server", return_value=None),
        patch("maestro.dashboard.emitter.DashboardEmitter", return_value=MagicMock()),
        patch.object(cli_module, "run_multi_agent", return_value={"outputs": {}, "failed": [], "errors": []}),
        patch("time.sleep"),
    ):
        with pytest.raises(SystemExit) as exc_info:
            cli_module._handle_run_multi(args, ".", provider, "gpt-5")
    assert exc_info.value.code == 1

    with (
        patch("maestro.dashboard.server.start_dashboard_server", return_value=None),
        patch("maestro.dashboard.emitter.DashboardEmitter", return_value=MagicMock()),
        patch.object(cli_module, "run_multi_agent", return_value={"outputs": {"worker-1": "done"}, "failed": [], "errors": []}),
        patch("time.sleep"),
    ):
        cli_module._handle_run_multi(args, ".", provider, "gpt-5")
    assert "Worker Outputs" in capsys.readouterr().out


def test_handle_run_single_covers_streaming_and_non_streaming_paths(capsys) -> None:
    import maestro.cli as cli_module

    provider = SimpleNamespace(id="chatgpt")
    args = SimpleNamespace(prompt="task", system="sys", auto=False)

    spinner = MagicMock()
    with (
        patch.object(cli_module, "_Spinner", return_value=spinner),
        patch.object(cli_module, "run", return_value="final result"),
    ):
        cli_module._handle_run_single(args, ".", provider, "gpt-5")
    assert "final result" in capsys.readouterr().out
    assert spinner.start.called and spinner.stop.called

    def fake_run(*_args, **kwargs):
        kwargs["on_tool_start"]()
        kwargs["stream_callback"]("chunk")
        return "ignored"

    with (
        patch.object(cli_module, "_Spinner", return_value=MagicMock()),
        patch.object(cli_module, "run", side_effect=fake_run),
    ):
        cli_module._handle_run_single(args, ".", provider, "gpt-5")
    assert "chunk" in capsys.readouterr().out


def test_handle_discover_covers_request_and_model_errors_and_success(tmp_path, capsys) -> None:
    import maestro.cli as cli_module

    args = SimpleNamespace(
        prompt="prompt",
        brownfield=False,
        workdir=str(tmp_path),
        model=None,
        gaps_port=4041,
        no_browser=True,
        no_reflect=False,
        reflect_max_cycles=5,
        sprints=False,
    )

    with patch("maestro.sdlc.SDLCRequest", side_effect=ValueError("bad request")):
        with pytest.raises(SystemExit) as exc_info:
            cli_module._handle_discover(args)
    assert exc_info.value.code == 1

    with (
        patch("maestro.sdlc.SDLCRequest", return_value=SimpleNamespace(workdir=str(tmp_path))),
        patch("maestro.models.resolve_model", side_effect=ValueError("bad model")),
    ):
        with pytest.raises(SystemExit) as exc_info:
            cli_module._handle_discover(args)
    assert exc_info.value.code == 1

    harness = MagicMock()
    harness.run.return_value = SimpleNamespace(artifact_count=2, spec_dir=tmp_path, gate_failures=[])
    with (
        patch("maestro.sdlc.SDLCRequest", return_value=SimpleNamespace(workdir=str(tmp_path))),
        patch("maestro.models.resolve_model", return_value=(SimpleNamespace(id="chatgpt"), "gpt-5")),
        patch("maestro.sdlc.DiscoveryHarness", return_value=harness),
    ):
        cli_module._handle_discover(args)
    assert "artifacts written" in capsys.readouterr().out

    harness.run.return_value = SimpleNamespace(artifact_count=2, spec_dir=tmp_path, gate_failures=["failed"])
    with (
        patch("maestro.sdlc.SDLCRequest", return_value=SimpleNamespace(workdir=str(tmp_path))),
        patch("maestro.models.resolve_model", return_value=(SimpleNamespace(id="chatgpt"), "gpt-5")),
        patch("maestro.sdlc.DiscoveryHarness", return_value=harness),
    ):
        with pytest.raises(SystemExit) as exc_info:
            cli_module._handle_discover(args)
    assert exc_info.value.code == 2


def test_handle_planning_check_and_dispatch_paths(tmp_path, capsys) -> None:
    import maestro.cli as cli_module

    with patch("maestro.planning.check_planning_consistency", return_value=SimpleNamespace(errors=["oops"])):
        with pytest.raises(SystemExit) as exc_info:
            cli_module._handle_planning_check(SimpleNamespace(root=str(tmp_path)))
    assert exc_info.value.code == 1

    with patch("maestro.planning.check_planning_consistency", return_value=SimpleNamespace(errors=[])):
        with pytest.raises(SystemExit) as exc_info:
            cli_module._handle_planning_check(SimpleNamespace(root=str(tmp_path)))
    assert exc_info.value.code == 0
    assert str(tmp_path.resolve()) in capsys.readouterr().out

    planning_parser = MagicMock()
    with patch.object(cli_module, "_handle_planning_check") as mock_check:
        cli_module._handle_planning(SimpleNamespace(planning_command="check"), planning_parser)
    mock_check.assert_called_once()

    with pytest.raises(SystemExit) as exc_info:
        cli_module._handle_planning(SimpleNamespace(planning_command=None), planning_parser)
    assert exc_info.value.code == 1
    planning_parser.print_help.assert_called()
