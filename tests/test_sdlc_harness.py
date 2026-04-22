"""Tests for maestro/sdlc/harness.py — DiscoveryHarness orchestrator."""
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from maestro.sdlc.harness import DiscoveryHarness
from maestro.sdlc.schemas import (
    ARTIFACT_FILENAMES,
    ARTIFACT_ORDER,
    ArtifactType,
    DiscoveryResult,
    SDLCRequest,
)


def test_harness_instantiation() -> None:
    harness = DiscoveryHarness()
    assert harness is not None


def test_harness_run_returns_discovery_result(tmp_path: Path) -> None:
    harness = DiscoveryHarness(workdir=str(tmp_path))
    result = harness.run(SDLCRequest("Build X", workdir=str(tmp_path)))
    assert isinstance(result, DiscoveryResult)


def test_harness_run_produces_13_artifacts(tmp_path: Path) -> None:
    harness = DiscoveryHarness(workdir=str(tmp_path))
    result = harness.run(SDLCRequest("Build X", workdir=str(tmp_path)))
    assert result.artifact_count == 13


def test_harness_creates_spec_directory(tmp_path: Path) -> None:
    harness = DiscoveryHarness(workdir=str(tmp_path))
    harness.run(SDLCRequest("Build X", workdir=str(tmp_path)))
    assert (tmp_path / "spec").is_dir()


def test_harness_writes_13_files(tmp_path: Path) -> None:
    harness = DiscoveryHarness(workdir=str(tmp_path))
    harness.run(SDLCRequest("Build X", workdir=str(tmp_path)))
    written = list((tmp_path / "spec").glob("*.md"))
    assert len(written) == 13


def test_harness_artifact_filenames_match_schema(tmp_path: Path) -> None:
    harness = DiscoveryHarness(workdir=str(tmp_path))
    result = harness.run(SDLCRequest("Build X", workdir=str(tmp_path)))
    expected = set(ARTIFACT_FILENAMES.values())
    actual = {a.filename for a in result.artifacts}
    assert actual == expected


def test_harness_run_respects_workdir(tmp_path: Path) -> None:
    subdir = tmp_path / "project"
    subdir.mkdir()
    harness = DiscoveryHarness(workdir=str(subdir))
    result = harness.run(SDLCRequest("Build X", workdir=str(subdir)))
    assert result.spec_dir.startswith(str(subdir))
    assert (subdir / "spec").is_dir()


def test_harness_brownfield_false_does_not_scan(tmp_path: Path) -> None:
    harness = DiscoveryHarness(workdir=str(tmp_path))
    with patch.object(harness, "_scan_codebase") as mock_scan:
        harness.run(SDLCRequest("Build X", workdir=str(tmp_path), brownfield=False))
    mock_scan.assert_not_called()


def test_harness_brownfield_true_appends_codebase_context(tmp_path: Path) -> None:
    harness = DiscoveryHarness(workdir=str(tmp_path))
    captured_prompts: list[str] = []

    original_gen = harness._generate_artifact

    async def capturing_gen(req, artifact_type):
        captured_prompts.append(req.prompt)
        return await original_gen(req, artifact_type)

    harness._generate_artifact = capturing_gen
    harness.run(SDLCRequest("Build X", workdir=str(tmp_path), brownfield=True))

    assert captured_prompts, "No artifacts generated"
    assert "## Existing Codebase" in captured_prompts[0]
