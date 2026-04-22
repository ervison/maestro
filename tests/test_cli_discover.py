"""Tests for the `maestro discover` CLI subcommand."""
from __future__ import annotations

import argparse
import io
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from maestro.sdlc.schemas import (
    ARTIFACT_FILENAMES,
    ArtifactType,
    DiscoveryResult,
    SDLCArtifact,
    SDLCRequest,
)


def _make_fake_result(tmp_path: Path) -> DiscoveryResult:
    arts = [SDLCArtifact(t, ARTIFACT_FILENAMES[t], f"# {t.value}") for t in ArtifactType]
    return DiscoveryResult(
        request=SDLCRequest("Build X"),
        artifacts=arts,
        spec_dir=str(tmp_path / "spec"),
    )


def _make_args(
    prompt: str = "Build a CRM",
    brownfield: bool = False,
    workdir: str = ".",
    model=None,
    gaps_port: int = 4041,
    no_browser: bool = False,
) -> argparse.Namespace:
    return argparse.Namespace(
        prompt=prompt,
        brownfield=brownfield,
        workdir=workdir,
        model=model,
        gaps_port=gaps_port,
        no_browser=no_browser,
    )


def test_discover_subcommand_exists() -> None:
    """The discover subcommand must be registered (--help exits 0)."""
    with patch("sys.argv", ["maestro", "discover", "--help"]):
        with pytest.raises(SystemExit) as exc_info:
            from maestro.cli import main
            main()
    assert exc_info.value.code == 0


def test_discover_help_includes_gap_flags() -> None:
    """The discover help output must expose gap questionnaire flags."""
    stdout_buf = io.StringIO()
    stderr_buf = io.StringIO()

    with patch("sys.argv", ["maestro", "discover", "--help"]):
        with patch("sys.stdout", stdout_buf), patch("sys.stderr", stderr_buf):
            with pytest.raises(SystemExit) as exc_info:
                from maestro.cli import main

                main()

    output = stdout_buf.getvalue() + stderr_buf.getvalue()
    assert exc_info.value.code == 0
    assert "--gaps-port" in output
    assert "--no-browser" in output


def test_discover_requires_prompt() -> None:
    """Running discover without a prompt must exit with a non-zero code."""
    stdout_buf = io.StringIO()
    stderr_buf = io.StringIO()
    with patch("sys.argv", ["maestro", "discover"]):
        with patch("sys.stdout", stdout_buf), patch("sys.stderr", stderr_buf):
            with pytest.raises(SystemExit) as exc_info:
                from maestro.cli import main
                main()
    assert exc_info.value.code != 0


def test_discover_empty_prompt_raises_value_error() -> None:
    """SDLCRequest with empty prompt must raise ValueError (tested at schema level)."""
    with pytest.raises(ValueError, match="prompt cannot be empty"):
        SDLCRequest("")


def test_discover_runs_harness(tmp_path: Path) -> None:
    """The discover handler must call DiscoveryHarness.run()."""
    fake_result = _make_fake_result(tmp_path)
    mock_harness = MagicMock()
    mock_harness.run.return_value = fake_result

    async def fake_gen(req, at):
        return SDLCArtifact(at, ARTIFACT_FILENAMES[at], "content")

    mock_harness._generate_artifact = fake_gen

    with patch("maestro.sdlc.DiscoveryHarness", return_value=mock_harness):
        with patch("maestro.models.resolve_model", return_value=(MagicMock(), "gpt-4o")):
                from maestro.cli import _handle_discover
                _handle_discover(_make_args(workdir=str(tmp_path)))

    mock_harness.run.assert_called_once()


def test_discover_prints_progress(tmp_path: Path) -> None:
    """The discover handler must print progress for each artifact."""
    fake_result = _make_fake_result(tmp_path)
    mock_harness = MagicMock()
    mock_harness.run.return_value = fake_result

    call_log: list[str] = []

    async def fake_gen(req, at):
        return SDLCArtifact(at, ARTIFACT_FILENAMES[at], "content")

    mock_harness._generate_artifact = fake_gen

    stdout_buf = io.StringIO()
    with patch("maestro.sdlc.DiscoveryHarness", return_value=mock_harness):
        with patch("maestro.models.resolve_model", return_value=(MagicMock(), "gpt-4o")):
                with patch("sys.stdout", stdout_buf):
                    from maestro.cli import _handle_discover
                    _handle_discover(_make_args(workdir=str(tmp_path)))

    output = stdout_buf.getvalue()
    assert "artifacts written to" in output


def test_discover_prints_completion(tmp_path: Path) -> None:
    """The discover handler must print a ✓ completion line."""
    fake_result = _make_fake_result(tmp_path)
    mock_harness = MagicMock()
    mock_harness.run.return_value = fake_result

    async def fake_gen(req, at):
        return SDLCArtifact(at, ARTIFACT_FILENAMES[at], "content")

    mock_harness._generate_artifact = fake_gen

    stdout_buf = io.StringIO()
    with patch("maestro.sdlc.DiscoveryHarness", return_value=mock_harness):
        with patch("maestro.models.resolve_model", return_value=(MagicMock(), "gpt-4o")):
                with patch("sys.stdout", stdout_buf):
                    from maestro.cli import _handle_discover
                    _handle_discover(_make_args(workdir=str(tmp_path)))

    output = stdout_buf.getvalue()
    assert "✓" in output
    assert "artifacts written to" in output


def test_discover_brownfield_flag(tmp_path: Path) -> None:
    """--brownfield=True must be forwarded to SDLCRequest."""
    captured: list[SDLCRequest] = []
    fake_result = _make_fake_result(tmp_path)
    mock_harness = MagicMock()

    async def fake_gen(req, at):
        return SDLCArtifact(at, ARTIFACT_FILENAMES[at], "content")

    mock_harness._generate_artifact = fake_gen

    def capturing_run(req):
        captured.append(req)
        return fake_result

    mock_harness.run.side_effect = capturing_run

    with patch("maestro.sdlc.DiscoveryHarness", return_value=mock_harness):
        with patch("maestro.models.resolve_model", return_value=(MagicMock(), "gpt-4o")):
                from maestro.cli import _handle_discover
                _handle_discover(_make_args(brownfield=True, workdir=str(tmp_path)))

    assert captured, "run() was not called"
    assert captured[0].brownfield is True


def test_discover_workdir_flag(tmp_path: Path) -> None:
    """--workdir must be forwarded to SDLCRequest and DiscoveryHarness."""
    fake_result = _make_fake_result(tmp_path)
    mock_harness = MagicMock()
    mock_harness.run.return_value = fake_result

    async def fake_gen(req, at):
        return SDLCArtifact(at, ARTIFACT_FILENAMES[at], "content")

    mock_harness._generate_artifact = fake_gen

    with patch("maestro.sdlc.DiscoveryHarness", return_value=mock_harness) as MockCls:
        with patch("maestro.models.resolve_model", return_value=(MagicMock(), "gpt-4o")):
                from maestro.cli import _handle_discover
                _handle_discover(_make_args(workdir=str(tmp_path)))

    assert MockCls.called, "DiscoveryHarness was not instantiated"
    _, kwargs = MockCls.call_args
    assert kwargs.get("workdir") == str(tmp_path)


def test_discover_forwards_gap_questionnaire_options(tmp_path: Path) -> None:
    """Gap questionnaire CLI options must be forwarded to DiscoveryHarness."""
    fake_result = _make_fake_result(tmp_path)
    mock_harness = MagicMock()
    mock_harness.run.return_value = fake_result

    async def fake_gen(req, at):
        return SDLCArtifact(at, ARTIFACT_FILENAMES[at], "content")

    mock_harness._generate_artifact = fake_gen

    stderr_buf = io.StringIO()
    with patch("maestro.sdlc.DiscoveryHarness", return_value=mock_harness) as MockCls:
        with patch("maestro.models.resolve_model", return_value=(MagicMock(), "gpt-4o")):
            with patch("sys.stderr", stderr_buf):
                from maestro.cli import _handle_discover

                _handle_discover(
                    _make_args(
                        workdir=str(tmp_path),
                        gaps_port=5050,
                        no_browser=True,
                    )
                )

    _, kwargs = MockCls.call_args
    assert kwargs.get("gaps_port") == 5050
    assert kwargs.get("open_browser") is False
    assert "http://localhost:5050" in stderr_buf.getvalue()


def test_discover_does_not_break_run() -> None:
    """`maestro run --help` must still work after discover is added."""
    with patch("sys.argv", ["maestro", "run", "--help"]):
        with pytest.raises(SystemExit) as exc_info:
            from maestro.cli import main
            main()
    assert exc_info.value.code == 0


def test_discover_does_not_break_run_multi() -> None:
    """`maestro run --multi --help` must still work."""
    with patch("sys.argv", ["maestro", "run", "--multi", "--help"]):
        with pytest.raises(SystemExit) as exc_info:
            from maestro.cli import main
            main()
    assert exc_info.value.code == 0
