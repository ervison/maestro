"""CLI tests for gate failure exit code behavior."""
from __future__ import annotations

import sys
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
