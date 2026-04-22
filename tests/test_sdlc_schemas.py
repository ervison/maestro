"""Tests for maestro/sdlc/schemas.py — ArtifactType, SDLCRequest, SDLCArtifact, DiscoveryResult."""
import pytest

from maestro.sdlc.schemas import (
    ARTIFACT_FILENAMES,
    ARTIFACT_ORDER,
    ArtifactType,
    DiscoveryResult,
    SDLCArtifact,
    SDLCRequest,
)


def test_artifact_type_has_13_members() -> None:
    assert len(ArtifactType) == 13


def test_artifact_filenames_has_all_types() -> None:
    missing = set(ArtifactType) - set(ARTIFACT_FILENAMES)
    assert not missing, f"Missing filenames for: {missing}"


def test_artifact_order_has_all_types() -> None:
    assert set(ARTIFACT_ORDER) == set(ArtifactType)


def test_artifact_filenames_numbered_01_to_13() -> None:
    numbers = sorted(
        int(v.split("-")[0]) for v in ARTIFACT_FILENAMES.values()
    )
    assert numbers == list(range(1, 14))


def test_sdlc_request_valid() -> None:
    req = SDLCRequest("Build a CRM")
    assert req.prompt == "Build a CRM"
    assert req.brownfield is False
    assert req.language is None
    assert req.workdir == "."


def test_sdlc_request_empty_prompt_raises() -> None:
    with pytest.raises(ValueError, match="prompt cannot be empty"):
        SDLCRequest("")


def test_sdlc_request_whitespace_prompt_raises() -> None:
    with pytest.raises(ValueError, match="prompt cannot be empty"):
        SDLCRequest("   ")


def test_sdlc_artifact_creation() -> None:
    art = SDLCArtifact(ArtifactType.PRD, "04-prd.md", "# PRD")
    assert art.artifact_type == ArtifactType.PRD
    assert art.filename == "04-prd.md"
    assert art.content == "# PRD"


def test_discovery_result_artifact_count() -> None:
    req = SDLCRequest("Build X")
    arts = [
        SDLCArtifact(t, ARTIFACT_FILENAMES[t], "content")
        for t in ArtifactType
    ]
    result = DiscoveryResult(request=req, artifacts=arts, spec_dir="/tmp/spec")
    assert result.artifact_count == 13
