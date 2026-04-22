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


def test_harness_writes_each_artifact_incrementally(tmp_path: Path) -> None:
    """Each artifact must be written to disk as soon as it is generated, not all at the end."""
    harness = DiscoveryHarness(workdir=str(tmp_path))
    spec_dir = tmp_path / "spec"
    written_counts: list[int] = []

    original_gen = harness._generate_artifact

    async def counting_gen(req, artifact_type):
        artifact = await original_gen(req, artifact_type)
        # Count how many files exist on disk right after this artifact is generated
        # (the write happens inside arun, right after _generate_artifact returns)
        return artifact

    harness._generate_artifact = counting_gen

    # Patch write_artifact to record counts per call
    from maestro.sdlc import writer as writer_mod
    original_write = writer_mod.write_artifact

    def recording_write(sd, artifact):
        original_write(sd, artifact)
        written_counts.append(len(list(spec_dir.glob("*.md"))))

    with patch.object(writer_mod, "write_artifact", side_effect=recording_write):
        harness.run(SDLCRequest("Build X", workdir=str(tmp_path)))

    # Should have 13 write calls, one per artifact
    assert len(written_counts) == 13
    # Each write call should have produced exactly one more file than the previous
    for i, count in enumerate(written_counts, start=1):
        assert count == i, f"Expected {i} files after artifact {i}, got {count}"
